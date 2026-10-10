"""EdgePublisher: the one hand-off from vision.server (and tools/replay_detect) to the edge store.

Called on CV threads, every method only stamps a time and enqueues (bounded, never blocking in live
runs); hashing, JPEG encoding, association of standalone poses and disk I/O happen on the writer thread.
A frame that triggers evidence travels with its observation in one control item, so an observation is
never stored before the evidence it references.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Optional

from bobapp.contracts import SourceMode
from bobapp.edge.store import EdgeStore
from bobapp.edge.writer import EdgeWriter
from vision.association import associate
from vision.schema import FramePacket, PosePacket, StreamHealth

from .evidence import EvidenceGate, encode_jpeg, evidence_body, evidence_triggers
from .live import LiveSnapshot, render_preview
from .observation import observation_body, rule_statuses
from .track import TrackSampler


class EdgePublisher:
    def __init__(self, store: EdgeStore, edge_config: dict[str, Any], *, source_mode: SourceMode, run_id: str,
                 pipeline: Any, render_config: dict[str, Any], stale_ms: float, zones_enabled: bool,
                 blocking: bool = False) -> None:
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
        # The store connection belongs to the writer thread alone; announce the run (source mode,
        # capabilities) through it before the first frame.
        self.writer.submit_control(lambda store: self._flush())

    # --- CV threads: stamp + enqueue only -------------------------------------------------------
    def on_admit(self, msg: FramePacket | PosePacket, gap_ns: Optional[int], rx_ns: int) -> None:
        """Receive thread (FrameServer.admit): every kept phone message."""
        now = time.monotonic_ns()
        self.live.mark("pose", now)
        if isinstance(msg, FramePacket):
            self.live.mark("video", now)
        self.writer.submit_data(lambda store: self._track(store, msg, gap_ns))
        self._maybe_flush(now)

    def on_detection(self, detection: Any, scene: Optional[dict] = None) -> None:
        """Frame consumer: one processed frame (C2) and its optional C7 record."""
        now = time.monotonic_ns()
        self.live.mark("results", now)
        event = detection.event
        reason, keys = evidence_triggers(detection, scene)
        due = self.gate.admit(event.session_id, keys, event.iphone_frame_ts_ns) if keys else []
        if due:
            self.writer.submit_control(lambda store: self._observe(store, detection, scene, (reason, due)))
        else:
            self.writer.submit_data(lambda store: self._observe(store, detection, scene, None))
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
                 evidence: Optional[tuple[Any, list[str]]]) -> None:
        pixels = hashlib.sha256(detection.image.tobytes()).hexdigest()
        evidence_sha = None
        if evidence is not None:
            data = encode_jpeg(detection.image, self.evidence_quality)
            evidence_sha = store.put_blob(data)
            store.append(evidence_body(detection, evidence_sha, len(data), pixels, *evidence),
                         self.source_mode, self.run_id)
            self.counts["evidence"] += 1
        store.append(observation_body(detection, self.rules, pixels, evidence_sha, scene),
                     self.source_mode, self.run_id)
        self.counts["observations"] += 1

    def _preview(self, detection: Any) -> None:
        data, ref = render_preview(detection, self.render, self.preview["width"], self.preview["jpeg_quality"])
        self.live.set("preview", ref)
        self._flush(data, ref["sha256"])
        self.counts["previews"] += 1

    def _flush(self, preview: Optional[bytes] = None, preview_sha256: Optional[str] = None) -> None:
        stats = self.writer.stats()
        self.live.set("edge", {
            "store_bytes": self.store.size_bytes(), "disk_free_bytes": self.store.disk_free_bytes(),
            "writer_queued": stats["queued"], "writer_dropped": sum(stats["dropped"].values()),
            "writer_errors": stats["write_errors"], "last_error": stats["last_error"]})
        self.store.put_live(self.live.copy(), preview, preview_sha256)

    # --- shutdown ---------------------------------------------------------------------------------
    def close(self, timeout: float = 2.) -> dict[str, Any]:
        """Finish queued work (bounded), mark the run stopped in the live row, report counts."""
        self.live.set("running", False)
        try:
            self.writer.submit_control(lambda store: self._flush())
        except RuntimeError:
            pass
        stats = self.writer.close(timeout)
        return {**stats, **self.counts, "store_epoch": str(self.store.store_epoch)}
