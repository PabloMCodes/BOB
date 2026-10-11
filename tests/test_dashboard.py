"""Measured dashboard telemetry, latest history, and backward-paged operational logs."""
import time
from types import SimpleNamespace
from uuid import uuid4

from bobapp.contracts import Delivery, Lane, LivePose, LiveState, NoticeBody, SourceMode
from bobapp.edge.publish.live import LiveSnapshot
from bobapp.edge.publish.metrics import MetricsWindow
from tests.test_hub_api import AUTH, hub, replicate  # noqa: F401


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


def test_logs_are_authenticated_workspace_scoped_and_page_backwards(hub):
    client = hub['client']
    assert client.get('/v1/logs').status_code == 401
    first = client.get('/v1/logs?workspace=sample&limit=3', headers=AUTH).json()
    second = client.get(f"/v1/logs?workspace=sample&limit=3&before={first['items'][0]['cursor']}", headers=AUTH).json()
    assert len(first['items']) == len(second['items']) == 3
    assert max(i['cursor'] for i in second['items']) < min(i['cursor'] for i in first['items'])
    assert all(i['record']['source_mode'] == 'SAMPLE' for i in first['items'] + second['items'])
    assert client.get('/v1/logs?workspace=rover', headers=AUTH).json()['items'] == []
    assert client.get('/v1/logs?before=0', headers=AUTH).status_code == 422


def test_latest_observations_return_the_tail_without_changing_default_paging(hub):
    client = hub['client']
    beginning = client.get('/v1/observations?workspace=sample&limit=3', headers=AUTH).json()['items']
    tail = client.get('/v1/observations?workspace=sample&limit=3&latest=true', headers=AUTH).json()['items']
    assert beginning[-1]['cursor'] < tail[0]['cursor']
    assert [i['cursor'] for i in tail] == sorted(i['cursor'] for i in tail)
    assert len(tail) == 3


def test_metrics_never_become_current_after_a_link_cut_or_for_a_different_run(hub):
    store, replica, client = hub['rover_store'], hub['rover'], hub['client']
    session = uuid4()
    now = time.monotonic_ns()
    details = dict(session_id=str(session), measured_mono_ns=now, window_s=2,
                   frame_fps=30, pose_hz=60, processing_hz=10, inference_latency_ms=50, confidence_mean=0.85)
    store.append(NoticeBody(kind='notice', code='stream_metrics', message='Measured performance', details=details),
                 SourceMode.LIVE, 'metrics-run')
    ws = replicate(store, replica)
    text, _, _, _ = replica.get_live()
    live = LiveState.model_validate_json(text).model_copy(update={
        'run_id': 'metrics-run', 'source_mode': SourceMode.LIVE,
        'pose': LivePose(session_id=session, seq_id=1, iphone_ts_ns=1, pose_valid=False, pose_invalid_reason='no_pose')})
    replica.set_live(live.model_dump_json())
    status = client.get('/v1/status', headers=AUTH).json()
    assert status['telemetry']['frame_fps'] == 30 and status['telemetry']['current']
    later = live.model_copy(update={'rover': live.rover.model_copy(update={'mono_ns': now + 2_000_000_000})})
    replica.set_live(later.model_dump_json())
    replica.db.execute('UPDATE live SET hub_rx_wall_ns=?', (time.time_ns() - 1_100_000_000,))
    status = client.get('/v1/status', headers=AUTH).json()
    assert status['live_is_current'] and not status['telemetry']['current']
    assert status['telemetry']['age_ms'] >= 3100  # rover age + hub receive age, one domain at a time
    replica.set_live(live.model_dump_json())
    replica.set_link({'state': 'DISCONNECTED', 'lanes': {}})
    assert not client.get('/v1/status', headers=AUTH).json()['telemetry']['current']
    replica.set_live(live.model_copy(update={'run_id': 'another-run'}).model_dump_json())
    assert client.get('/v1/status', headers=AUTH).json()['telemetry'] is None
    replica.set_live(live.model_dump_json())
    replica.db.execute("UPDATE records SET delivery='backfilled' WHERE ws_id=? AND kind='notice'", (ws.ws_id,))
    replica.set_link({'state': 'CONNECTED', 'lanes': {}})
    assert not client.get('/v1/status', headers=AUTH).json()['telemetry']['current']


def test_malformed_optional_metrics_do_not_hide_link_or_capabilities(hub):
    store, replica, client = hub['rover_store'], hub['rover'], hub['client']
    session = uuid4()
    store.append(NoticeBody(kind='notice', code='stream_metrics', message='Bad producer metrics',
                            details={'session_id': str(session)}), SourceMode.LIVE, 'bad-run')
    replicate(store, replica)
    text, _, _, _ = replica.get_live()
    live = LiveState.model_validate_json(text).model_copy(update={
        'run_id': 'bad-run', 'pose': LivePose(session_id=session, seq_id=1, iphone_ts_ns=1,
                                           pose_valid=False, pose_invalid_reason='no_pose')})
    replica.set_live(live.model_dump_json())
    response = client.get('/v1/status', headers=AUTH)
    assert response.status_code == 200
    status = response.json()
    assert status['link']['state'] == 'CONNECTED' and status['telemetry'] is None
    assert 'invalid' in status['telemetry_reason']
