"""Failure-injection tests; no radio connection and no physical motor commands."""
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import pty
import struct
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from uuid import UUID

import pytest

from hardware.controller_protocol import PacketType
from navigation.demo import MISSING, PERSON, observation
from navigation.drive import PulseLink
from navigation.run_source import read_run_info
from navigation.step import StepSettings, StepSupervisor
from navigation.supervised import input_action


def ready(settings=StepSettings(pulse_ms=100)):
    supervisor = StepSupervisor(settings, started=0.)
    for seq, t in enumerate((0., .15, .3)):
        supervisor.update(*observation(seq, t))
    assert supervisor.resume()
    assert supervisor.phase() == ("READY", "forward")
    return supervisor


@pytest.mark.parametrize("field,value", [
    ("seconds", float("nan")), ("seconds", float("inf")), ("seconds", 121),
    ("seconds", True), ("max_steps", 0), ("max_steps", 31), ("max_steps", 1.5),
    ("pulse_ms", 99), ("pulse_ms", 501), ("pulse_ms", True),
    ("settle_s", .9), ("settle_s", float("nan")),
])
def test_limits_reject_unbounded_runs(field, value):
    with pytest.raises(ValueError):
        StepSettings(**{field: value})


def test_half_second_step_keeps_monitoring_after_dispatch_deadline():
    s = ready(StepSettings())
    req = s.request()
    assert req.pulse_ms == 500
    s.update(*observation(3, .7))
    assert not s.allowed(req, .7)  # Too late to dispatch a new packet.
    assert s.allowed(req, .7, continuing=True)
    s.update(*observation(4, .75, boxes=(PERSON,)))
    assert not s.allowed(req, .75, continuing=True)


def test_half_second_transport_sends_one_lease_and_stops():
    async def scenario():
        c = FakeClient()
        link = PulseLink(c, clock=lambda: .3)
        await link.stop()
        req = ready(StepSettings()).request()
        assert await link.pulse(req, lambda: True, asyncio.Event())
        motions = [p for p in c.writes if p[1] == PacketType.MOTION]
        assert len(motions) == 1
        assert struct.unpack("<BBIIHhh", motions[0])[4] == 500
        assert c.writes[-1][1] == PacketType.STOP
        assert not c.armed and not c.moving
    asyncio.run(scenario())


def test_no_automatic_movement_and_no_queued_permission():
    s = ready()
    assert s.active is None and s.attempts == 0
    request = s.request()
    assert request.direction == "forward" and request.pulse_ms == 100
    assert s.allowed(request, .3) and not s.allowed(request, 1.)
    assert s.request() is None  # Holding/repeating space cannot queue a burst.
    s.finished(observation(3, .4)[2], .4)
    for seq, t in enumerate((.6, .9, 1.1), 3):
        s.update(*observation(seq, t))
        assert s.request() is None
    # A detection completed after settling, but was received before settling.
    event, health, wall, _ = observation(6, 1.2)
    s.update(event, health, wall + 210_000_000, 1.41)
    assert s.phase() == ("WAITING", "waiting for a post-settle frame")
    assert s.request() is None
    s.update(*observation(7, 1.5))
    assert s.phase()[0] == "READY"
    assert s.active is None and s.attempts == 1  # Freshness alone cannot resume.
    assert s.request().seq_id == 7


@pytest.mark.parametrize("failure", ["stale", "tracking", "pose", "session", "missing", "clock"])
def test_data_failure_revokes_active_permission_and_latches_pause(failure):
    s = ready()
    request = s.request()
    e, h, wall, mono = observation(3, .35)
    if failure == "stale":
        wall += 1_000_000_000
    elif failure == "tracking":
        h = h.model_copy(update={"tracking_state": "limited"})
    elif failure == "pose":
        e = e.model_copy(update={"pose_valid": False})
    elif failure == "session":
        h = h.model_copy(update={"session_id": UUID(int=99)})
    elif failure == "missing":
        e = None
    else:
        mono = .1
    s.update(e, h, wall, mono)
    assert not s.allowed(request, .35)
    s.finished(wall, .4)
    for seq, t in enumerate((2., 2.2, 2.4), 4):
        s.update(*observation(seq, t))
    assert s.request() is None
    assert s.phase()[0] in {"PAUSED", "FAULT"}


def test_frozen_frame_never_satisfies_startup_confirmation():
    s = StepSupervisor(started=0.)
    e, h, wall, _ = observation(0, 0.)
    for tick in range(5):
        s.update(e, h, wall + tick * 100_000_000, tick * .1)
        s.resume()
        assert s.request() is None
    assert s.clear_count == 1


def test_person_stops_active_step_then_holds_for_ppe_and_requires_new_space():
    s = ready()
    request = s.request()
    for seq, t in enumerate((.35, .6, .85), 3):
        d = s.update(*observation(seq, t, boxes=(PERSON, MISSING)))
        assert not s.allowed(request, t)
    assert d.announcement == "Missing PPE"
    s.finished(observation(6, .9)[2], .9)
    for seq in range(6, 56):
        t = .9 + (seq - 6) * .2
        s.update(*observation(seq, t))
        assert s.request() is None
    s.update(*observation(56, 11.1))
    s.update(*observation(57, 11.3))
    s.update(*observation(58, 11.5))
    assert s.phase()[0] == "READY"
    assert s.active is None


def test_operator_stop_requires_resume_and_never_resumes_motion_itself():
    s = ready()
    request = s.request()
    s.pause()
    assert not s.allowed(request, .3)
    assert not s.resume()  # Cannot resume while a pulse is ending.
    s.finished(observation(3, .4)[2], .4)
    for seq, t in enumerate((1.5, 1.7, 1.9), 3):
        s.update(*observation(seq, t))
    assert s.request() is None and s.resume()
    assert s.active is None and s.attempts == 1


def test_hard_limits_finish_even_with_fresh_camera():
    s = ready(StepSettings(max_steps=1))
    s.request()
    s.finished(observation(3, .4)[2], .4)
    assert s.phase()[0] == "COMPLETE" and s.request() is None
    s = ready(StepSettings(seconds=1))
    s.update(*observation(4, 1.1))
    assert s.phase()[0] == "COMPLETE" and s.request() is None


def test_empty_timeout_message_still_latches_fault():
    s = ready()
    request = s.request()
    s.fail(str(asyncio.TimeoutError()))
    assert s.phase()[0] == "FAULT" and not s.allowed(request, .3)
    s.finished(observation(3, .4)[2], .4)
    s.update(*observation(4, 1.5))
    assert not s.resume() and s.request() is None


@pytest.mark.parametrize("keys,action", [(" r ", "resume"), ("   s", "stop"),
    ("r q ", "quit"), ("\x1b[A ", "stop"), ("    ", "step"), ("F", None)])
def test_keyboard_prioritizes_stop_and_discards_typeahead(keys, action):
    assert input_action(keys) == action


class FakeClient:
    def __init__(self):
        self.is_connected = True
        self.writes = []
        self.armed = False
        self.seq = None
        self.session = 17
        self.read_count = 0
        self.before_read = lambda: None
        self.after_write = lambda p: None
        self.moving = False

    async def write_gatt_char(self, uuid, packet, response):
        self.writes.append(packet)
        kind = packet[1]
        if kind == PacketType.STOP:
            self.armed = self.moving = False
        elif kind == PacketType.ARM:
            self.armed = True
        elif kind == PacketType.MOTION:
            assert self.armed
            _, _, session, seq, lease, linear, angular = struct.unpack("<BBIIHhh", packet)
            assert session == self.session
            self.seq = seq
            self.moving = True
        self.after_write(packet)

    async def read_gatt_char(self, uuid):
        self.read_count += 1
        self.before_read()
        return struct.pack("<BBBBIIhh", 1, 2 if self.moving else int(self.armed), 0,
                           1 | (2 if self.armed else 0) | (4 if self.seq is not None else 0),
                           self.session, self.seq or 0, 85 if self.moving else 0,
                           85 if self.moving else 0)

    async def disconnect(self):
        self.is_connected = False


def test_startup_accepts_slow_stop_without_relaxing_runtime_timeout(monkeypatch):
    class SlowClient(FakeClient):
        async def connect(self):
            pass

        async def write_gatt_char(self, *args, **kwargs):
            await asyncio.sleep(.4)
            await super().write_gatt_char(*args, **kwargs)

    client = SlowClient()

    async def find(*args, **kwargs):
        return object()

    monkeypatch.setitem(sys.modules, "bleak", SimpleNamespace(
        BleakClient=lambda device: client,
        BleakScanner=SimpleNamespace(find_device_by_name=find)))

    async def scenario():
        link = await PulseLink.connect()
        assert [p[1] for p in client.writes] == [PacketType.STOP]
        assert not client.armed and link.last_status.left_pwm == 0
        with pytest.raises(asyncio.TimeoutError):
            await link.stop()
        await client.disconnect()

    asyncio.run(scenario())


def test_transport_sends_one_short_lease_and_verifies_stop_and_sequence():
    async def scenario():
        s, c = ready(), FakeClient()
        link = PulseLink(c, clock=lambda: .3)
        await link.stop()
        for seq in range(2):
            request = replace(s.request() if seq == 0 else previous, deadline=1.)
            assert await link.pulse(request, lambda: True, asyncio.Event())
            previous = request
        motions = [p for p in c.writes if p[1] == PacketType.MOTION]
        assert len(motions) == 2
        for seq, p in enumerate(motions):
            assert struct.unpack("<BBIIHhh", p)[3:] == (seq, 100, 200, 0)
        assert c.writes[-1][1] == PacketType.STOP
        assert not link.last_status.armed and link.last_status.left_pwm == 0
        await link.close()
        assert not c.is_connected
    asyncio.run(scenario())


@pytest.mark.parametrize("block", ["expires_before_arm", "expires_after_arm", "abort", "person"])
def test_permission_rechecked_after_ble_awaits(block):
    async def scenario():
        s, c, now, abort = ready(), FakeClient(), [.3], asyncio.Event()
        link = PulseLink(c, clock=lambda: now[0])
        await link.stop()
        req = s.request()

        def hook():
            if block == "expires_before_arm" and c.read_count == 2:
                now[0] = 1.
            if c.read_count == 3:
                if block == "expires_after_arm":
                    now[0] = 1.
                elif block == "abort":
                    abort.set()
                elif block == "person":
                    s.update(*observation(3, .35, boxes=(PERSON,)))
        c.before_read = hook
        assert not await link.pulse(req, lambda: s.allowed(req, now[0]), abort)
        assert not any(p[1] == PacketType.MOTION for p in c.writes)
        assert c.writes[-1][1] == PacketType.STOP
    asyncio.run(scenario())


def test_stop_during_pulse_and_motion_write_failure_do_not_refresh_lease():
    async def scenario():
        for fail in (False, True):
            s, c, abort = ready(), FakeClient(), asyncio.Event()
            link = PulseLink(c, clock=lambda: .3)
            await link.stop()
            def hook(packet):
                if packet[1] == PacketType.MOTION:
                    abort.set()
                    if fail:
                        raise OSError("BLE lost after delivery")
            c.after_write = hook
            if fail:
                with pytest.raises(OSError):
                    await link.pulse(s.request(), lambda: True, abort)
            else:
                assert await link.pulse(s.request(), lambda: True, abort)
            assert sum(p[1] == PacketType.MOTION for p in c.writes) == 1
            assert c.writes[-1][1] == PacketType.STOP and not c.armed
    asyncio.run(scenario())


def test_changed_controller_session_cannot_move():
    async def scenario():
        c, s = FakeClient(), ready()
        link = PulseLink(c, clock=lambda: .3)
        await link.stop()
        c.session = 18
        with pytest.raises(RuntimeError, match="session changed"):
            await link.pulse(s.request(), lambda: True, asyncio.Event())
        assert not any(p[1] in {PacketType.ARM, PacketType.MOTION} for p in c.writes)
    asyncio.run(scenario())


def test_speech_cannot_arm_and_rechecks_permission():
    async def scenario():
        c = FakeClient()
        link = PulseLink(c, clock=lambda: 1.)
        await link.stop()
        assert not await link.announce(.9, lambda: True)
        assert not await link.announce(2., lambda: False)
        assert await link.announce(2., lambda: True)
        assert [p[1] for p in c.writes] == [PacketType.STOP, PacketType.TONE]
    asyncio.run(scenario())


def test_missing_controller_sequence_ack_and_stalled_write_fail_closed():
    async def scenario():
        c, s = FakeClient(), ready()
        link = PulseLink(c, clock=lambda: .3)
        await link.stop()
        def lose_ack(packet):
            if packet[1] == PacketType.STOP:
                c.seq = None
        c.after_write = lose_ack
        with pytest.raises(RuntimeError, match="acknowledge"):
            await link.pulse(s.request(), lambda: True, asyncio.Event())
        assert not c.armed

        c, s = FakeClient(), ready()
        link = PulseLink(c, clock=lambda: .3)
        await link.stop()
        original = c.write_gatt_char
        async def stalled(uuid, packet, response):
            await original(uuid, packet, response)
            if packet[1] == PacketType.MOTION:
                await asyncio.sleep(10)
        c.write_gatt_char = stalled
        with pytest.raises(asyncio.TimeoutError):
            await link.pulse(s.request(), lambda: True, asyncio.Event())
        assert c.writes[-1][1] == PacketType.STOP
        assert sum(p[1] == PacketType.MOTION for p in c.writes) == 1
    asyncio.run(scenario())


def run_info(path, source="LIVE"):
    info = dict(run_info_version=1, producer="vision.server", run_id=str(UUID(int=10)),
                started_ts_ns=1_800_000_000_000_000_000, source_mode=source)
    (path / "run_info.json").write_text(json.dumps(info))
    return info


@pytest.mark.parametrize("source", ["REPLAY", "SAMPLE"])
def test_cli_refuses_simulated_hardware_use_before_opening_ble(tmp_path, source):
    run_info(tmp_path, source)
    result = subprocess.run([sys.executable, "-m", "navigation.supervised", "--run-dir",
                             str(tmp_path), "--execute"], capture_output=True, timeout=5)
    assert result.returncode == 2 and b"refuses REPLAY/SAMPLE" in result.stderr


def test_source_metadata_is_bounded_and_missing_source_never_assumed_live(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_run_info(tmp_path)
    assert read_run_info_after_write(tmp_path)["source_mode"] == "LIVE"
    (tmp_path / "run_info.json").write_text('{"source_mode":"LIVE"}')
    with pytest.raises(ValueError):
        read_run_info(tmp_path)
    (tmp_path / "run_info.json").write_text(" " * 4097)
    with pytest.raises(ValueError, match="size limit"):
        read_run_info(tmp_path)


def read_run_info_after_write(path):
    run_info(path)
    return read_run_info(path)


def test_execute_runner_with_fake_radio_stops_on_person_and_closes(tmp_path, monkeypatch):
    """Exercise orchestration + real packet encoder with an injected radio only."""
    from navigation import supervised
    run_info(tmp_path)
    client = FakeClient()
    link = PulseLink(client)
    start = time.monotonic()

    async def connect(name):
        await link.stop()
        return link

    def feed(path, model):
        t = time.monotonic() - start
        seq = int(t * 40)
        e, h, _, _ = observation(seq, t, boxes=(PERSON, MISSING) if t > .6 else ())
        wall = time.time_ns()
        if path.name == "detections.jsonl":
            return e.model_copy(update={"jetson_receive_ts_ns": wall})
        return h.model_copy(update={"emitted_ts_ns": wall, "last_rx_ts_ns": wall})

    class ScriptedKeyboard:
        def __init__(self, callback):
            self.callback = callback
        def __enter__(self):
            loop = asyncio.get_running_loop()
            for delay, keys in ((.35, "r"), (.5, " "), (.8, " "), (1.25, "q")):
                loop.call_later(delay, self.callback, keys)
        def __exit__(self, *_):
            pass

    monkeypatch.setattr(PulseLink, "connect", connect)
    monkeypatch.setattr(supervised, "Keyboard", ScriptedKeyboard)
    monkeypatch.setattr(supervised, "latest", feed)
    # Actual clock for the synthetic run identity; the fixture's fixed timestamp
    # must not make current test frames look like old records from a previous run.
    info = read_run_info(tmp_path)
    info["started_ts_ns"] = time.time_ns()
    (tmp_path / "run_info.json").write_text(json.dumps(info))
    args = SimpleNamespace(run_dir=tmp_path, output_dir=tmp_path / "output", execute=True,
                           speech=True, seconds=5., steps=5, pulse_ms=100, ble_name="fake")
    asyncio.run(supervised.run(args))
    packets = [p[1] for p in client.writes]
    assert packets.count(PacketType.MOTION) == 1
    assert packets.count(PacketType.TONE) == 1
    assert packets[-1] == PacketType.STOP and not client.is_connected
    records = [json.loads(line) for line in (args.output_dir / "steps.jsonl").read_text().splitlines()]
    assert any(r["kind"] == "step_finished" and r["motion_write_acknowledged"] for r in records)
    assert any(r["kind"] == "step_refused" for r in records)


def test_interactive_dry_run_consumes_live_files_and_discards_blocked_spaces(tmp_path):
    """Real CLI + pseudo terminal, fresh SAMPLE C2/C3 files; no BLE imports."""
    info = run_info(tmp_path, "SAMPLE")
    info["started_ts_ns"] = time.time_ns()
    (tmp_path / "run_info.json").write_text(json.dumps(info))
    output = tmp_path / "output"
    halt = threading.Event()
    person = threading.Event()
    streaming = threading.Event()
    streaming.set()

    def writer():
        with (tmp_path / "detections.jsonl").open("w", buffering=1) as events, (
                tmp_path / "stream_health.jsonl").open("w", buffering=1) as health:
            seq = 0
            while not halt.wait(.05):
                if not streaming.is_set():
                    continue
                wall = time.time_ns()
                e, h, _, _ = observation(seq, seq * .05, boxes=(PERSON,) if person.is_set() else ())
                events.write(e.model_copy(update={"jetson_receive_ts_ns": wall}).model_dump_json() + "\n")
                health.write(h.model_copy(update={"emitted_ts_ns": wall,
                                                   "last_rx_ts_ns": wall}).model_dump_json() + "\n")
                seq += 1

    def rows():
        path = output / "steps.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().split("\n")[:-1]]

    def wait_until(predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            assert proc.poll() is None, proc.communicate()[0]
            time.sleep(.025)
        pytest.fail(f"terminal did not reach expected state: {rows()[-3:]}")

    worker = threading.Thread(target=writer)
    worker.start()
    master, slave = pty.openpty()
    proc = subprocess.Popen([sys.executable, "-m", "navigation.supervised", "--run-dir",
                             str(tmp_path), "--output-dir", str(output), "--seconds", "15"],
                            stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    os.close(slave)
    try:
        wait_until(lambda: any(r["kind"] == "observation" for r in rows()))
        os.write(master, b"r")
        wait_until(lambda: rows()[-1].get("phase", [None])[0] == "READY")
        os.write(master, b" ")
        wait_until(lambda: any(r["kind"] == "step_finished" for r in rows()))
        person.set()
        wait_until(lambda: rows()[-1].get("phase", [None])[0] == "OBSERVE")
        os.write(master, b"     ")
        wait_until(lambda: any(r["kind"] == "step_refused" for r in rows()))
        streaming.clear()
        wait_until(lambda: rows()[-1].get("phase", [None])[0] == "PAUSED")
        os.write(master, b"q")
        stdout = proc.communicate(timeout=5)[0]
        assert proc.returncode == 0, stdout
        assert b"no BLE connection was opened" in stdout
        assert sum(r["kind"] == "step_requested" for r in rows()) == 1
        assert all(r["mode"] == "DRY_RUN" and r["source_mode"] == "SAMPLE" for r in rows())
        assert all(not r["motion_write_acknowledged"] for r in rows() if r["kind"] == "step_finished")
        assert "ADVISORY camera trail" in (output / "map.svg").read_text()
    finally:
        halt.set()
        worker.join(timeout=3)
        if proc.poll() is None:
            proc.terminate()
            proc.communicate(timeout=5)
        os.close(master)
