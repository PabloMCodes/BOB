"""Bounded, per-session rates on the rover clock; never inferred from phone sequence numbers."""
from __future__ import annotations

from collections import deque
from typing import Optional


class MetricsWindow:
    WINDOW_NS = 2_000_000_000

    def __init__(self) -> None:
        self.session_id: Optional[str] = None
        self.started_ns = 0
        self.times = {name: deque(maxlen=4096) for name in ("video", "pose", "results")}
        self.inference_ms: Optional[float] = None
        self.confidence: Optional[float] = None

    def session(self, session_id: str, now: int) -> None:
        if session_id == self.session_id:
            return
        self.session_id, self.started_ns = session_id, now
        for times in self.times.values():
            times.clear()
        self.inference_ms = self.confidence = None

    def mark(self, feed: str, now: int) -> None:
        if feed in self.times:
            self.times[feed].append(now)

    def snapshot(self, now: int) -> Optional[dict]:
        if self.session_id is None:
            return None
        rates = {}
        for name, times in self.times.items():
            while times and times[0] <= now - self.WINDOW_NS:
                times.popleft()
            rates[name] = len(times) / 2 if now - self.started_ns >= self.WINDOW_NS else None
        return {"session_id": self.session_id, "measured_mono_ns": now, "window_s": 2.0,
                "frame_fps": rates["video"], "pose_hz": rates["pose"], "processing_hz": rates["results"],
                "inference_latency_ms": self.inference_ms, "confidence_mean": self.confidence}
