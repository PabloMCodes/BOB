"""In-memory live snapshot of one vision.server run, flushed to the store's single live row.

Feed times are rover-monotonic (`time.monotonic_ns`, shared by processes on one machine), so the edge
API can report ages. Nothing here is a lane record or is ever backfilled.
"""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Any, Optional

import cv2

from bobapp.contracts import Producer, ProducerStatus, RuleStatus, SourceMode

from .evidence import encode_jpeg
from .metrics import MetricsWindow

FEEDS = ("video", "results", "pose", "health")


def producers(zones_enabled: bool) -> list[Producer]:
    """Hazard producers as they actually are — not as planned."""
    return [
        Producer(name="ppe", status=ProducerStatus.PROTOTYPE, note="per-frame rules; live on/off acceptance pending"),
        Producer(name="restricted_zone", status=ProducerStatus.PROTOTYPE,
                 note="physical tape acceptance pending" + ("" if zones_enabled else "; not enabled in this run")),
        Producer(name="person_in_path", status=ProducerStatus.NOT_INTEGRATED, note="no producer"),
        Producer(name="walkway", status=ProducerStatus.NOT_INTEGRATED, note="C8 library only"),
        Producer(name="controller_telemetry", status=ProducerStatus.NOT_INTEGRATED, note=None),
        Producer(name="supervisor", status=ProducerStatus.NOT_INTEGRATED, note=None),
    ]


class LiveSnapshot:
    def __init__(self, run_id: str, source_mode: SourceMode, model_id: str, rules: list[RuleStatus],
                 zones_enabled: bool) -> None:
        self.lock = threading.Lock()
        self.metrics = MetricsWindow()
        self.state: dict[str, Any] = {
            "running": True, "run_id": run_id, "source_mode": SourceMode(source_mode).value,
            "feeds_mono_ns": dict.fromkeys(FEEDS), "pose": None, "health": None, "preview": None,
            "capabilities": {"model_id": model_id, "rules": [r.model_dump(mode="json") for r in rules],
                             "producers": [p.model_dump(mode="json") for p in producers(zones_enabled)]},
            "edge": None,
        }

    def mark(self, feed: str, mono_ns: Optional[int] = None) -> None:
        with self.lock:
            now = time.monotonic_ns() if mono_ns is None else mono_ns
            self.state["feeds_mono_ns"][feed] = now
            self.metrics.mark(feed, now)

    def start_session(self, session_id: str, now: int) -> None:
        with self.lock:
            self.metrics.session(session_id, now)

    def result_metrics(self, event: Any) -> None:
        with self.lock:
            if str(event.session_id) != self.metrics.session_id:
                return  # an in-flight result from the previous world origin
            now = time.monotonic_ns()
            self.state["feeds_mono_ns"]["results"] = now
            self.metrics.mark("results", now)
            self.metrics.inference_ms = event.inference_latency_ms
            confidences = [box.conf for box in event.boxes if box.source == "model"]
            self.metrics.confidence = sum(confidences) / len(confidences) if confidences else None

    def stream_metrics(self, now: int) -> Optional[dict]:
        with self.lock:
            return self.metrics.snapshot(now) if self.state["running"] else None

    def set(self, key: str, value: Any) -> None:
        with self.lock:
            self.state[key] = value

    def copy(self) -> dict[str, Any]:
        with self.lock:
            return {**self.state, "feeds_mono_ns": dict(self.state["feeds_mono_ns"])}


def render_preview(detection: Any, render: dict[str, Any], width: int, quality: int) -> tuple[bytes, dict[str, Any]]:
    """Annotated, downscaled preview (D5). Boxes stay in source pixels: `source_image_size` lets a
    frontend scale its own overlay exactly."""
    from vision.render import draw
    image = draw(detection.image, detection.result.boxes, render["categories"], hide=render["hide"])
    h, w = image.shape[:2]
    if w > width:
        image = cv2.resize(image, (width, round(h * width / w)), interpolation=cv2.INTER_AREA)
    data = encode_jpeg(image, quality)
    event = detection.event
    ref = {"event_id": str(event.event_id), "session_id": str(event.session_id), "seq_id": event.seq_id,
           "image_size": {"width": image.shape[1], "height": image.shape[0]},
           "source_image_size": event.image_size.model_dump(), "sha256": hashlib.sha256(data).hexdigest()}
    return data, ref
