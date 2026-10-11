"""EdgePublisher: the one hand-off from vision.server (and tools/replay_detect) to the edge store.

Called on CV threads, every method only stamps a time and enqueues (bounded, never blocking in live
runs); hashing, JPEG encoding, association of standalone poses and disk I/O happen on the writer thread.
Observations go through one queue in frame order (the incident policy needs that order); a frame
that triggers evidence carries it in the same item, so an observation is never stored before the
evidence it references. Incidents (plan §8) are decided on the writer thread from each stored
observation (incidents.py).

Inspection binding (plan §4): the writer thread re-reads the rover's active inspection with every live
flush (≤ `sync.live_interval_s`) and the frame consumer stamps each frame with the inspection known at
that moment, so a frame is assessed under exactly one revision, and only one that was explicitly
started. A run whose declared source mode differs from the inspection's is never assessed under it.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Optional

from bobapp.contracts import IncidentEndReason, NoticeBody, SourceMode
from bobapp.edge.store import ActiveInspection, EdgeStore
from bobapp.edge.writer import EdgeWriter
from bobapp.incidents import PolicyParams
from vision.association import associate
from vision.schema import FramePacket, PosePacket, StreamHealth

from .assessment import assess, unavailable_requirements
from .evidence import EvidenceGate, encode_jpeg, evidence_body, evidence_triggers
from .incidents import IncidentRecorder
from .live import LiveSnapshot, render_preview
from .observation import observation_body, rule_statuses
from .track import TrackSampler


class EdgePublisher:
    def __init__(self, store: EdgeStore, edge_config: dict[str, Any], *, source_mode: SourceMode, run_id: str,
                 pipeline: Any, render_config: dict[str, Any], stale_ms: float, zones_enabled: bool,
                 blocking: bool = False, incident_params: Optional[PolicyParams] = None) -> None:
        self.store, self.source_mode, self.run_id = store, SourceMode(source_mode), run_id
        writer = edge_config["writer"]
        self.writer = EdgeWriter(store, self.source_mode, run_id, writer["control_capacity"],
                                 writer["data_capacity"], retention=edge_config["retention"], blocking=blocking)
        self.rules = rule_statuses(pipeline)
        self.live = LiveSnapshot(run_id, self.source_mode, pipeline.model_id, self.rules, zones_enabled)
        self.gate = EvidenceGate(edge_config["evidence"]["min_interval_s"])
        self.evidence_quality = edge_config["evidence"]["jpeg_quality"]
        self.preview = edge_config["preview"]
        self.render = render_config
        self.preview_interval_ns = int(1e9 / self.preview["max_hz"])
        self.flush_interval_ns = int(edge_config["sync"]["live_interval_s"] * 1e9)
        self.stale_ns = int(stale_ms * 1e6)
        self.sampler = TrackSampler(**edge_config["track"])           # writer thread only
        self.counts = {"observations": 0, "track_points": 0, "evidence": 0, "previews": 0}  # writer thread
        self._last_preview_ns = self._last_flush_ns = 0
        self._last_metrics_ns = 0
        self.incidents = IncidentRecorder(store, incident_params or PolicyParams.load(), self.source_mode, run_id,
                                          self.evidence_quality)              # writer thread only
        self.inspection: Optional[ActiveInspection] = None  # written by the writer thread only
        self._noticed: set = set()
        # The store connection belongs to the writer thread alone; announce the run (source mode,
        # capabilities) and pick up an inspection that was already active through it.
        self.writer.submit_control(lambda store: self._flush(run_start=True))

    # --- CV threads: stamp + enqueue only -------------------------------------------------------
    def on_admit(self, msg: FramePacket | PosePacket, gap_ns: Optional[int], rx_ns: int) -> None:
        """Receive thread (FrameServer.admit): every kept phone message."""
        now = time.monotonic_ns()
        self.live.start_session(str(msg.session_id), now)
        self.live.mark("pose", now)
        if isinstance(msg, FramePacket):
            self.live.mark("video", now)
        self.writer.submit_data(lambda store: self._track(store, msg, gap_ns))
        self._maybe_flush(now)

    def on_detection(self, detection: Any, scene: Optional[dict] = None) -> None:
        """Frame consumer: one processed frame (C2) and its optional C7 record."""
        now = time.monotonic_ns()
        event, inspection = detection.event, self.inspection  # the inspection known at processing time
        self.live.result_metrics(event)
        reason, keys = evidence_triggers(detection, scene)
        due = self.gate.admit(event.session_id, keys, event.iphone_frame_ts_ns) if keys else []
        evidence = (reason, due) if due else None
        self.writer.submit_data(lambda store: self._observe(store, detection, scene, evidence, inspection))
        if now - self._last_preview_ns >= self.preview_interval_ns:
            self._last_preview_ns = self._last_flush_ns = now
            self.writer.submit_data(lambda store: self._preview(detection))

    def on_health(self, health: StreamHealth) -> None:
        now = time.monotonic_ns()
        self.live.set("health", health.model_dump(mode="json"))
        self.live.mark("health", now)
        self._maybe_flush(now)

    def _maybe_flush(self, now: int) -> None:
        if now - self._last_flush_ns >= self.flush_interval_ns:
            self._last_flush_ns = now
            self.writer.submit_data(lambda store: self._flush())

    # --- writer thread ----------------------------------------------------------------------------
    def _track(self, store: EdgeStore, msg: FramePacket | PosePacket, gap_ns: Optional[int]) -> None:
        # Admitted messages are of the newest session (the stream monitor drops older ones).
        association = associate(msg, gap_ns, msg.session_id, self.stale_ns)
        self.live.set("pose", {
            "session_id": str(msg.session_id), "seq_id": msg.seq_id, "iphone_ts_ns": msg.iphone_frame_ts_ns,
            "pose": association.pose.model_dump() if association.pose_valid else None,
            "pose_valid": association.pose_valid,
            "pose_invalid_reason": association.reason.value if association.reason else None})
        point = self.sampler.offer(msg, association)
        if point is not None:
            store.append(point, self.source_mode, self.run_id)
            self.counts["track_points"] += 1

    def _observe(self, store: EdgeStore, detection: Any, scene: Optional[dict],
                 evidence: Optional[tuple[Any, list[str]]], inspection: Optional[ActiveInspection] = None) -> None:
        pixels = hashlib.sha256(detection.image.tobytes()).hexdigest()
        evidence_sha = None
        if evidence is not None:
            data = encode_jpeg(detection.image, self.evidence_quality)
            evidence_sha = store.put_blob(data)
            store.append(evidence_body(detection, evidence_sha, len(data), pixels, *evidence),
                         self.source_mode, self.run_id)
            self.counts["evidence"] += 1
        assessment = None
        if inspection is not None and inspection.source_mode == self.source_mode:
            assessment = assess(detection.verdicts, self.rules, inspection)
        store.append(observation_body(detection, self.rules, pixels, evidence_sha, scene, assessment),
                     self.source_mode, self.run_id)
        self.counts["observations"] += 1
        self.incidents.observe(detection, assessment, scene, pixels)

    def _preview(self, detection: Any) -> None:
        data, ref = render_preview(detection, self.render, self.preview["width"], self.preview["jpeg_quality"])
        self.live.set("preview", ref)
        self._flush(data, ref["sha256"])
        self.counts["previews"] += 1

    def _notice(self, code: str, message: str, **details: Any) -> None:
        self.store.append(NoticeBody(kind="notice", code=code, message=message, details=details),
                          self.source_mode, self.run_id)

    def _refresh_inspection(self, run_start: bool) -> None:
        if run_start:
            self.incidents.close_stale()
        active = self.store.active_inspection()
        if self.inspection is not None and (active is None or active.inspection_id != self.inspection.inspection_id):
            self.incidents.end(IncidentEndReason.INSPECTION_ENDED)
        if active is not None and active.inspection_id not in self._noticed:
            self._noticed.add(active.inspection_id)
            iid = str(active.inspection_id)
            if run_start:
                self._notice("source_restarted_during_inspection", "vision.server (re)started while this inspection "
                             "was active; frames before this run's first observation were not assessed",
                             inspection_id=iid, run_id=self.run_id)
            if active.source_mode != self.source_mode:
                self._notice("source_mode_mismatch", f"inspection is {active.source_mode.value} but this run is "
                             f"{self.source_mode.value}: its frames are not assessed under the inspection",
                             inspection_id=iid, run_id=self.run_id)
            else:
                for requirement, reason in unavailable_requirements(active.profile, self.rules).items():
                    self._notice("assessment_unavailable", f"Required — assessment unavailable: {requirement} ({reason})",
                                 inspection_id=iid, requirement=requirement, reason=reason)
        self.inspection = active

    def _flush(self, preview: Optional[bytes] = None, preview_sha256: Optional[str] = None,
               run_start: bool = False) -> None:
        self._refresh_inspection(run_start)
        stats = self.writer.stats()
        self.live.set("edge", {
            "store_bytes": self.store.size_bytes(), "disk_free_bytes": self.store.disk_free_bytes(),
            "writer_queued": stats["queued"], "writer_dropped": sum(stats["dropped"].values()),
            "writer_errors": stats["write_errors"], "last_error": stats["last_error"]})
        self.store.put_live(self.live.copy(), preview, preview_sha256)
        now = time.monotonic_ns()
        if now - self._last_metrics_ns >= 1_000_000_000:
            metrics = self.live.stream_metrics(now)
            if metrics is not None:
                # Existing v1 notice envelope: C2/C3 and sync message shapes remain frozen.
                self._notice("stream_metrics", "Measured stream performance", **metrics)
                self._last_metrics_ns = now

    # --- shutdown ---------------------------------------------------------------------------------
    def close(self, timeout: float = 2.) -> dict[str, Any]:
        """Finish queued work (bounded), mark the run stopped in the live row, report counts."""
        self.live.set("running", False)

        def stop(store: EdgeStore) -> None:  # after every queued frame: open incidents end source_stopped
            self.incidents.end(IncidentEndReason.SOURCE_STOPPED)
            self._flush()
        try:
            if not self.writer.submit_data(stop):
                self.writer.submit_control(stop)  # queue full: still close them (startup would otherwise)
        except RuntimeError:
            pass
        stats = self.writer.close(timeout)
        return {**stats, **self.counts, **self.incidents.counts, "store_epoch": str(self.store.store_epoch)}
