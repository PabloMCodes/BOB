"""Shared scene assessment and bounded JSONL publication for live/replay consumers."""
from __future__ import annotations

import hashlib
import json
import queue
import threading
import time
from pathlib import Path
from typing import TextIO
from uuid import uuid4

import yaml

from vision.server.detection import Detection
from vision.tape import TapeConfig, detect_tape
from vision.zones import ZoneAssessment, ZoneRegion, assess_zone


class SceneInspector:
    def __init__(self, profile: TapeConfig):
        self.profile = profile
        self.run_id = str(uuid4())
        self.profile_sha256 = hashlib.sha256(profile.model_dump_json().encode()).hexdigest()

    @classmethod
    def from_file(cls, path: Path) -> SceneInspector:
        return cls(TapeConfig.model_validate(yaml.safe_load(path.read_text())))

    def inspect(self, detection: Detection, source_mode: str) -> tuple[dict, ZoneAssessment]:
        if source_mode not in {"LIVE", "REPLAY", "SAMPLE"}:
            raise ValueError("scene source_mode must be LIVE, REPLAY or SAMPLE")
        start = time.perf_counter()
        event = detection.event
        region = detect_tape(detection.image, self.profile)
        if event.pose_invalid_reason == "session_mismatch":
            region = ZoneRegion(region.zone_id, "unverified", "retired_source_session", ())
        assessment = assess_zone(region, event.boxes, event.image_size)
        record = {
            "scene_version": 1, "run_id": self.run_id, "source_mode": source_mode,
            "source_event_id": str(event.event_id), "session_id": str(event.session_id),
            "seq_id": event.seq_id, "iphone_frame_ts_ns": event.iphone_frame_ts_ns,
            "model_id": event.model_id, "image_size": event.image_size.model_dump(),
            "image_pixels_sha256": hashlib.sha256(detection.image.tobytes()).hexdigest(),
            "profile_sha256": self.profile_sha256,
            "assessment": assessment.as_dict(),
            "location_meaning": "camera_observation_position" if event.pose_valid else "unlocalized",
            "observation_pose": event.pose.model_dump() if event.pose_valid else None,
            "pose_invalid_reason": event.pose_invalid_reason,
            "scene_processing_ms": (time.perf_counter() - start) * 1000,
        }
        return record, assessment


class SceneWriter:
    """Bounded observation writer: slow/full storage cannot hold up the frame consumer.

    Overflow drops new scene records and counts them. This is not durable incident storage.
    Shutdown waits at most two seconds; the summary explicitly reports unfinished work.
    """
    def __init__(self, stream: TextIO, capacity: int = 8):
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self.stream = stream
        self.queue: queue.Queue[str] = queue.Queue(maxsize=capacity)
        self.closed = threading.Event()
        self.lock = threading.Lock()
        self.written = self.dropped = self.errors = 0
        self.last_error = None
        self.thread = threading.Thread(target=self._run, daemon=True, name="scene-writer")
        self.thread.start()

    def submit(self, record: dict) -> None:
        with self.lock:
            if self.closed.is_set():
                raise RuntimeError("scene writer is closed")
            try:
                self.queue.put_nowait(json.dumps(record) + "\n")
            except queue.Full:
                self.dropped += 1

    def _run(self):
        try:
            while not self.closed.is_set() or not self.queue.empty():
                try:
                    line = self.queue.get(timeout=.05)
                except queue.Empty:
                    continue
                try:
                    self.stream.write(line)
                    self.stream.flush()
                    with self.lock:
                        self.written += 1
                except OSError as exc:
                    with self.lock:
                        self.errors += 1
                        self.last_error = str(exc)
                finally:
                    self.queue.task_done()
        finally:
            try:
                self.stream.close()
            except OSError as exc:
                with self.lock:
                    self.errors += 1
                    self.last_error = str(exc)

    def stats(self) -> dict:
        with self.lock:
            return {"written": self.written, "dropped": self.dropped, "write_errors": self.errors,
                    "pending": self.queue.unfinished_tasks, "last_error": self.last_error,
                    "worker_running": self.thread.is_alive()}

    def close(self, timeout: float = 2.) -> dict:
        with self.lock:
            self.closed.set()
        self.thread.join(timeout=timeout)
        return self.stats()
