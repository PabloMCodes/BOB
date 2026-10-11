"""Mac demo tests: recorded contracts and fake motors, never a live phone/robot."""
from dataclasses import replace
import json
from pathlib import Path
import random

import pytest

from hardware.esp32.wander import Observation, Wander, observation

FIXTURES = Path(__file__).parent / 'fixtures' / 'app' / 'valid'


@pytest.fixture
def feed():
    live = json.loads((FIXTURES / 'live_state.json').read_text())
    live['health']['stale'] = False
    record = json.loads((FIXTURES / 'record_observation_live.json').read_text())
    live['rover']['wall_ns'] += 100_000_000
    live['rover']['mono_ns'] += 100_000_000
    status = dict(workspace='rover', link={'state': 'CONNECTED'}, live_is_current=True,
                  live=live, live_received_age_ms=50, lanes={}, gaps=[], evidence={}, workspaces=[])
    page = dict(workspace='rover', items=[dict(cursor=1, delivery='realtime',
                hub_rx_wall_ns=1, record=record)], next_after=1)
    return status, page


def test_existing_hub_contracts_and_clock_domains(feed):
    status, page = feed
    obs = observation(status, page, 10, 10.05)
    assert obs.person
    assert 10.05 < obs.expires < 11.05
    # Mac absolute wall clock / hub receipt epoch is deliberately unrelated.
    page['items'][0]['hub_rx_wall_ns'] = 999999999999999999
    assert observation(status, page, 10, 10.05) == obs


@pytest.mark.parametrize('case', ['sample', 'backfill', 'stale', 'run', 'session',
                                  'missing_age', 'old_frame', 'slow_request', 'old_record'])
def test_rejects_unusable_inputs(feed, case):
    status, page = feed
    record = page['items'][0]['record']
    now = 10.05
    if case == 'sample': record['source_mode'] = 'SAMPLE'
    if case == 'backfill': page['items'][0]['delivery'] = 'backfilled'
    if case == 'stale': status['live_is_current'] = False
    if case == 'run': record['run_id'] = 'previous'
    if case == 'session': status['live']['health']['session_id'] = '00000000-0000-0000-0000-000000000001'
    if case == 'missing_age': status['live_received_age_ms'] = None
    if case == 'old_frame': record['body']['event']['jetson_receive_ts_ns'] -= 2_000_000_000
    if case == 'old_record': record['rover']['mono_ns'] -= 2_000_000_000
    if case == 'slow_request': now = 12
    with pytest.raises(ValueError): observation(status, page, 10, now)


def clear(now=0, key='1'):
    return Observation(('edge', 'epoch', 'run', 'session'), key, False, now + 1, 'unverified')


def test_bursts_rest_and_new_frame_required():
    w = Wander(random.Random(3))
    assert w.update(clear(), 0) is None
    assert w.update(clear(), 0, start=True) in 'FLR'
    assert w.update(clear(), .26) is None
    assert w.update(replace(clear(), expires=2), .9) is None  # repeated frame
    assert w.update(clear(.91, '2'), .91) in 'FLR'


def test_person_stops_and_stays_stopped_until_explicit_restart():
    w = Wander()
    w.update(clear(), 0, start=True)
    assert w.update(replace(clear(.1, '2'), person=True), .1) is None
    assert 'PERSON FOUND' in w.reason
    assert w.update(clear(.2, '3'), .2) is None
    assert w.update(clear(.3, '4'), .3, start=True) in 'FLR'


@pytest.mark.parametrize('cause', ['expired', 'missing', 'session', 'stop', 'frozen', 'timeout'])
def test_stop_conditions_latch(cause):
    w = Wander()
    w.update(clear(), 0, start=True)
    obs, now, stop = clear(.1, '2'), .1, False
    if cause == 'expired': obs = replace(obs, expires=0)
    if cause == 'missing': obs = None
    if cause == 'session': obs = replace(obs, identity=('edge', 'epoch', 'new', 'session'))
    if cause == 'stop': stop = True
    if cause == 'frozen': obs, now = replace(clear(), expires=5), 1.1
    if cause == 'timeout': obs, now = clear(31, '2'), 31
    assert w.update(obs, now, stop=stop) is None
    assert not w.active
    assert w.update(clear(now + .1, '3'), now + .1) is None


def test_stop_wins_over_start_and_person_wins_over_start():
    w = Wander()
    assert w.update(clear(), 0, start=True, stop=True) is None
    assert w.update(replace(clear(), person=True), 0, start=True) is None


def test_spawned_feed_worker_reads_http_and_shuts_down(feed):
    import asyncio
    from contextlib import suppress
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    from hardware.esp32.wander import HubFeed

    status, page = feed
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            data = status if self.path.startswith('/v1/status') else page
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args): pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    async def check():
        source = HubFeed(f'http://127.0.0.1:{server.server_port}')
        task = asyncio.create_task(source.poll())
        try:
            for _ in range(150):
                if source.current is not None:
                    break
                await asyncio.sleep(.02)
            assert source.current is not None, source.error
            assert source.current.person
            status['live_is_current'] = False
            for _ in range(100):
                if source.current is None:
                    break
                await asyncio.sleep(.02)
            assert source.current is None
            assert source.error
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError): await task
    try:
        asyncio.run(check())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
