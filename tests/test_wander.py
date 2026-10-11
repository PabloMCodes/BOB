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
    assert w.update(clear(), 0, start=True) == 'F'
    assert w.update(clear(.81, '2'), .81) is None
    assert w.update(clear(1.02, '2'), 1.02) is None
    assert w.update(clear(1.03, '3'), 1.03) == 'F'


def person(now, key, missing=()):
    return replace(clear(now, key), person=True, subject=(100, 50, 300, 600),
                   missing=missing, photo_sha='a' * 64)


def test_person_inspection_is_bounded_then_turns_away_and_resumes():
    w = Wander()
    w.update(clear(), 0, start=True)
    assert w.update(person(.1, '2'), .1) is None
    for n, t in enumerate((.6, 1.1, 1.6, 2.1, 2.6, 3.1, 3.6), 3):
        assert w.update(person(t, str(n)), t) is None
    assert w.update(person(4.2, '10'), 4.2) == w.turn
    assert w.report['result'] == 'unverified'
    assert w.report['evidence_sha256'] == 'a' * 64
    assert not w.announce
    assert w.update(clear(4.8, '11'), 4.8) == w.turn
    assert w.update(clear(5.3, '12'), 5.3) is None
    assert w.phase == 'SEARCH'
    assert w.update(clear(5.6, '13'), 5.6) == 'F'


@pytest.mark.parametrize('cause', ['expired', 'missing', 'session', 'stop', 'frozen'])
def test_stop_conditions_latch(cause):
    w = Wander()
    w.update(clear(), 0, start=True)
    obs, now, stop = clear(.1, '2'), .1, False
    if cause == 'expired': obs = replace(obs, expires=0)
    if cause == 'missing': obs = None
    if cause == 'session': obs = replace(obs, identity=('edge', 'epoch', 'new', 'session'))
    if cause == 'stop': stop = True
    if cause == 'frozen': obs, now = replace(clear(), expires=5), 1.1
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


def test_scan_error_keeps_detail_and_does_not_start_window(monkeypatch):
    import asyncio
    import sys
    from types import SimpleNamespace
    from hardware.esp32.wander import run

    async def failed_scan(*args, **kwargs):
        raise RuntimeError('Bluetooth is turned off')
    calls = []
    monkeypatch.setitem(sys.modules, 'pygame', SimpleNamespace(
        init=lambda: calls.append('init'), quit=lambda: calls.append('quit')))
    monkeypatch.setitem(sys.modules, 'bleak', SimpleNamespace(
        BleakClient=object,
        BleakScanner=SimpleNamespace(find_device_by_filter=failed_scan)))
    with pytest.raises(RuntimeError, match='Bluetooth scan: RuntimeError: Bluetooth is turned off'):
        asyncio.run(run('http://127.0.0.1:8780'))
    assert calls == ['quit']


@pytest.mark.parametrize('case', ['weak', 'head_only', 'tiny'])
def test_weak_partial_or_tiny_person_does_not_interrupt_scan(feed, case):
    status, page = feed
    box = page['items'][0]['record']['body']['event']['boxes'][0]
    if case == 'weak': box['conf'] = .6
    if case == 'head_only': box['cls_name'] = 'head'
    if case == 'tiny': box['xyxy'] = [100, 50, 120, 70]
    obs = observation(status, page, 10, 10.05)
    assert not obs.person
    assert obs.missing == ()


def test_violation_is_from_subject_verdict_not_frame_summary(feed):
    status, page = feed
    obs = observation(status, page, 10, 10.05)
    assert obs.missing == ('glasses',)
    # Keep per-frame not_wearing summary but remove the subject verdict evidence.
    page['items'][0]['record']['body']['verdicts'] = []
    assert observation(status, page, 10, 10.05).missing == ()


def test_multiple_people_do_not_mix_ppe_evidence(feed):
    from copy import deepcopy
    status, page = feed
    boxes = page['items'][0]['record']['body']['event']['boxes']
    boxes.append(deepcopy(boxes[0]))
    obs = observation(status, page, 10, 10.05)
    assert obs.person and not obs.missing


def confirmed_inspection(w, start=0, prefix=''):
    w.update(person(start, prefix+'0', ('helmet',)), start, start=True)
    for n, dt in enumerate((.4, .7), 1):
        w.update(person(start+dt, prefix+str(n), ('helmet',)), start+dt)


def test_confirmed_missing_speaks_once_logs_exact_frame_then_turns():
    w = Wander()
    confirmed_inspection(w)
    assert w.announce and w.phase == 'SPEAK'
    assert w.report['confirmed_missing'] == ['helmet']
    assert w.report['event_id'] == '2' and w.report['evidence_sha256'] == 'a' * 64
    assert w.update(person(1, '4'), 1) is None
    assert not w.announce
    w.update(person(1.8, '5'), 1.8)
    assert w.update(person(2.4, '6'), 2.4) == w.turn
    assert w.phase == 'TURN_AWAY'


def test_single_frame_or_changed_subject_never_triggers_speech():
    w = Wander()
    w.update(person(0, '1', ('helmet',)), 0, start=True)
    for t in (.4, .65, .85):
        # Repeated same frame cannot confirm a violation.
        w.update(person(t, '2', ('helmet',)), t)
    assert not w.announce
    w.update(replace(person(.9, '3', ('helmet',)), subject=(500, 50, 700, 600)), .9)
    assert not w.announce
    w.update(person(1.2, '4'), 1.2)
    assert not w.evidence


def test_speech_cooldown_survives_manual_restart():
    w = Wander()
    confirmed_inspection(w)
    assert w.announce
    w.update(clear(1, '4'), 1, stop=True)
    confirmed_inspection(w, 2, 'again')
    assert not w.announce and w.phase == 'TURN_AWAY'
    assert w.report['confirmed_missing'] == ['helmet']


def test_turn_away_has_a_limit_when_person_never_leaves_view():
    w = Wander()
    confirmed_inspection(w)
    for n in range(1, 14):
        t = .85 + n * .5
        w.update(person(t, str(10+n)), t)
    assert w.active and w.phase == 'RECHECK'
    assert w.command is None
    assert w.update(person(11, 'new'), 11) is None
    assert w.phase == 'INSPECT'


@pytest.mark.parametrize('legacy', [False, True])
def test_speech_uses_existing_packet_while_stopped(legacy):
    import asyncio
    from hardware.esp32.wander import say_missing
    from hardware.esp32.remote import Remote
    from hardware.controller_protocol import encode_stop, encode_tone
    from tests.test_keyboard_remote import Client
    async def check():
        client = Client()
        remote = Remote(client, legacy=legacy)
        result = await say_missing(remote)
        assert not remote.moving
        assert client.packets == ([b'S'] if legacy else [encode_stop(), encode_tone(123)])
        assert result == ('unsupported_on_MotorTest' if legacy else 'write_acknowledged')
    asyncio.run(check())


def test_single_start_runs_beyond_thirty_seconds_with_forward_and_turns():
    w = Wander(random.Random(2))
    commands = []
    for n in range(201):
        command = w.update(clear(n*.2, str(n)), n*.2, start=n == 0)
        if command: commands.append(command)
    assert w.active and w.enabled
    assert 'F' in commands and any(c in 'LR' for c in commands)
    assert w.turn_count < 3


def test_feed_failure_stops_then_healthy_feed_resumes_without_r():
    w = Wander()
    assert w.update(clear(), 0, start=True) == 'F'
    assert w.update(None, .1) is None
    assert not w.active and w.enabled
    for n, t in enumerate((.2, .7, 1.2, 1.7)):
        assert w.update(clear(t, str(n+10)), t) is None
    assert w.update(clear(2.3, '20'), 2.3) == 'F'
    assert w.active


def test_space_remains_paused_through_feed_loss_and_recovery():
    w = Wander()
    w.update(clear(), 0, start=True)
    w.update(clear(.1, '2'), .1, stop=True)
    w.update(None, .2)
    for n in range(30):
        assert w.update(clear(n*.2+.3, str(n+10)), n*.2+.3) is None
    assert not w.enabled
    assert w.update(clear(7, '50'), 7, start=True) == 'F'


def test_frozen_frame_cannot_rearm_even_with_refreshed_expiry():
    w = Wander()
    w.update(clear(), 0, start=True)
    w.update(None, .1)
    for n in range(30):
        assert w.update(clear(n*.2+.2, 'same'), n*.2+.2) is None
    assert not w.active


def test_two_real_violations_allow_brief_unverified_gap_not_announcement_on_gap():
    w = Wander()
    w.update(person(0, '0'), 0, start=True)
    w.update(person(.4, '1', ('helmet',)), .4)
    assert not w.announce
    w.update(person(.55, '2'), .55)
    assert not w.announce
    w.update(person(.75, '3', ('helmet',)), .75)
    assert w.announce


def test_old_positive_cannot_accumulate_into_later_warning():
    w = Wander()
    w.update(person(0, '0'), 0, start=True)
    w.update(person(.4, '1', ('helmet',)), .4)
    w.update(person(.8, '2'), .8)
    w.update(person(1.2, '3'), 1.2)
    w.update(person(1.4, '4', ('helmet',)), 1.4)
    assert not w.announce
    assert w.evidence['helmet'][0] == 1


def test_speech_can_repeat_after_ten_seconds_with_new_confirmation():
    w = Wander()
    confirmed_inspection(w)
    assert w.announce
    w.update(clear(1, '4'), 1, stop=True)
    confirmed_inspection(w, 11, 'later')
    assert w.announce
