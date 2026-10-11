"""Measured dashboard telemetry, latest history, and backward-paged operational logs."""
import time
from types import SimpleNamespace
from uuid import uuid4

from bobapp.contracts import SourceMode
from bobapp.edge.publish.live import LiveSnapshot
from bobapp.edge.publish.metrics import MetricsWindow


def test_rates_are_measured_on_one_clock_and_expire_when_idle():
    metrics = MetricsWindow()
    assert metrics.snapshot(0) is None
    metrics.session('one', 0)
    for n in range(1, 61):
        metrics.mark('video', int(n * 1e9 / 30))
    for n in range(1, 21):
        metrics.mark('results', n * 100_000_000)
    assert metrics.snapshot(1_000_000_000)['frame_fps'] is None
    measured = metrics.snapshot(2_000_000_000)
    assert measured['frame_fps'] == 30 and measured['processing_hz'] == 10
    assert metrics.snapshot(4_000_000_000)['frame_fps'] == 0
    metrics.session('two', 4_000_000_000)
    assert metrics.snapshot(4_500_000_000)['processing_hz'] is None


def test_confidence_excludes_derived_boxes_and_previous_session_results():
    live = LiveSnapshot('run', SourceMode.LIVE, 'model', [], False)
    live.start_session('new', 0)
    def event(session):
        return SimpleNamespace(session_id=session, inference_latency_ms=42, boxes=[
            SimpleNamespace(source='model', conf=0.8), SimpleNamespace(source='model', conf=0.6),
            SimpleNamespace(source='derived', conf=1.0)])
    live.result_metrics(event('old'))
    assert live.stream_metrics(2_000_000_000)['confidence_mean'] is None
    live.result_metrics(event('new'))
    assert live.stream_metrics(time.monotonic_ns())['confidence_mean'] == 0.7
    live.set('running', False)
    assert live.stream_metrics(time.monotonic_ns()) is None
