"""No phone, model inference or physical BLE access in navigation tests."""
import asyncio
import json
from pathlib import Path
import struct
import subprocess
import sys
from uuid import UUID

import pytest

from hardware.controller_protocol import PacketType
from navigation.demo import MISSING, PERSON, observation, steps
from navigation.feed import latest, map_svg
from navigation.preview import Preview, Settings
from navigation.speech import Speaker
from vision.schema import DetectionEvent, StreamHealth


def update(preview, seq, seconds, **kwargs):
    return preview.update(*observation(seq, seconds, **kwargs))


def confirm(preview, start=0., seq=0):
    for i in range(3):
        result = update(preview, seq + i, start + i * .25, boxes=(PERSON, MISSING))
    return result


@pytest.mark.parametrize("setting,value", [
    ("stale_s", 0), ("mission_s", float("nan")), ("hold_s", -1),
    ("radius_cells", 2.5), ("radius_cells", 21), ("confirm_frames", 1),
    ("confirm_frames", True), ("confirm_s", 3.),
])
def test_invalid_settings(setting, value):
    with pytest.raises(ValueError):
        Settings(**{setting: value})


def test_exploration_tracks_camera_cells_and_prefers_unvisited():
    p = Preview()
    d = update(p, 0, 0.)
    assert d.goal_cell == (0, -1) and d.suggested_direction == "forward"
    assert d.visited_cells == 1 and not d.motor_output_enabled
    assert update(p, 1, .1).visited_cells == 1
    assert update(p, 2, .2, z=-.5).visited_cells == 2
    d = update(p, 3, .3)
    assert d.goal_cell != (0, -1) and d.visited_cells == 2
    assert p.visits[(0, 0)] == 2
    assert "obstacle clearance unknown" in map_svg(p, d)


def test_yaw_positive_left_and_bounded_map():
    p = Preview()
    assert update(p, 0, 0., yaw=1.57079632679).goal_cell == (-1, 0)
    assert update(p, 1, .1, x=2.1).reason == "outside_preview_bounds"
    assert len(p.visits) == 1


def test_person_stops_suggestions_immediately_without_claiming_violation():
    p = Preview()
    d = update(p, 0, 0., boxes=(PERSON,))
    assert d.state == "OBSERVE" and d.suggested_direction == "stop"
    assert not d.confirmed_ppe and d.announcement is None
    for seq in range(1, 12):
        d = update(p, seq, seq * .2, boxes=(PERSON,))
    assert d.state == "HOLD" and not d.confirmed_ppe


def test_single_flash_clears_without_ten_second_hold():
    p = Preview()
    assert update(p, 0, 0., boxes=(PERSON,)).state == "OBSERVE"
    for seq in range(1, 7):
        d = update(p, seq, seq * .2)
        assert d.state != "HOLD"
    assert d.state == "EXPLORE"


def test_intermittent_flashes_do_not_accumulate_confirmation():
    p = Preview()
    for seq in range(20):
        d = update(p, seq, seq * .2, boxes=(PERSON,) if seq % 2 == 0 else ())
        assert d.state == "OBSERVE"
    for seq in range(20, 27):
        d = update(p, seq, seq * .2)
    assert d.state == "EXPLORE"


def test_only_repeated_same_person_derived_ppe_announces_once():
    p = Preview()
    d = confirm(p)
    assert d.state == "ANNOUNCE" and d.announcement == "Missing PPE"
    assert d.confirmed_ppe == ("no-helmet",)
    for seq in range(3, 54):
        d = update(p, seq, seq * .2, boxes=(PERSON, MISSING))
        assert d.state == "HOLD" and d.announcement is None
    # Ten seconds elapsed, but person still present keeps suggestions stopped.
    assert d.reason == "person_present_or_clear_interval_pending"
    assert update(p, 54, 10.8).state == "HOLD"
    for seq in range(55, 60):
        d = update(p, seq, seq * .2)
    assert d.state == "EXPLORE"


def test_duplicates_do_not_confirm():
    p = Preview()
    event, health, wall, _ = observation(0, 0., boxes=(PERSON, MISSING))
    for i in range(7):
        d = p.update(event, health, wall + i * 100_000_000, i * .1)
        assert d.announcement is None
    assert p.evidence["no-helmet"][0] == 1


@pytest.mark.parametrize("replacement", [
    (), (PERSON,), (PERSON, dict(MISSING, source="model", cls_id=1)),
    (PERSON, dict(MISSING, cls_name="shoes")),
    (PERSON, dict(MISSING, xyxy=(400., 10., 450., 30.))),
    (PERSON, dict(PERSON, xyxy=(400., 50., 500., 450.)), MISSING),
    (dict(PERSON, xyxy=(400., 50., 500., 450.)), MISSING),
])
def test_interrupted_or_ambiguous_evidence_cannot_confirm(replacement):
    p = Preview()
    update(p, 0, 0., boxes=(PERSON, MISSING))
    update(p, 1, .25, boxes=replacement)
    assert update(p, 2, .5, boxes=(PERSON, MISSING)).announcement is None


def test_gap_between_fresh_events_restarts_confirmation():
    p = Preview()
    update(p, 0, 0., boxes=(PERSON, MISSING))
    update(p, 1, .25, boxes=(PERSON, MISSING))
    assert update(p, 2, 1.5, boxes=(PERSON, MISSING)).announcement is None
    assert p.evidence["no-helmet"][0] == 1


def test_global_announcement_cooldown_survives_session_change():
    p = Preview()
    assert confirm(p).announcement
    event, health, wall, mono = observation(0, 1., session=UUID(int=2))
    assert p.update(event, health, wall, mono).state == "STOPPED"
    for i in range(3):
        d = update(p, i, 1.1 + i * .25, session=UUID(int=2), boxes=(PERSON, MISSING))
    assert d.state == "HOLD" and d.announcement is None


@pytest.mark.parametrize("bad", ["missing", "stale_c2", "stale_c3", "future", "health", "pose", "tracking"])
def test_invalid_observations_stop_and_clear_confirmation(bad):
    p = Preview()
    update(p, 0, 0., boxes=(PERSON, MISSING))
    e, h, wall, mono = observation(1, .25, boxes=(PERSON, MISSING))
    if bad == "missing":
        e = None
    elif bad == "stale_c2":
        e = e.model_copy(update={"jetson_receive_ts_ns": wall - 1_000_000_000})
    elif bad == "stale_c3":
        h = h.model_copy(update={"emitted_ts_ns": wall - 1_000_000_000})
    elif bad == "future":
        wall -= 1
    elif bad == "health":
        h = h.model_copy(update={"stale": True})
    elif bad == "pose":
        e = e.model_copy(update={"pose_valid": False})
    elif bad == "tracking":
        h = h.model_copy(update={"tracking_state": "limited"})
    d = p.update(e, h, wall, mono)
    assert d.state == "STOPPED" and not p.evidence
    assert d.suggested_direction == "stop" and not d.motor_output_enabled


def test_session_change_clears_map_before_old_detection_can_be_used():
    p = Preview()
    update(p, 0, 0.)
    update(p, 1, .1, x=.5)
    e, _, wall, mono = observation(2, .2)
    _, h, _, _ = observation(0, .2, session=UUID(int=2))
    assert p.update(e, h, wall, mono).reason == "session_changed_map_cleared"
    assert p.visits == {} and p.origin is None
    assert p.update(e, h, wall, mono).reason == "session_mismatch"
    assert update(p, 0, .3, session=UUID(int=2), x=99.).camera_cell == (0, 0)
    assert update(p, 3, .4).state == "STOPPED"  # Retired session.
    assert update(p, 1, .5, session=UUID(int=2)).state == "FAULT"


def test_reordering_and_clock_regression():
    p = Preview()
    update(p, 3, 1.)
    assert update(p, 2, 1.1).reason == "reordered_observation"
    assert update(p, 4, .9).state == "FAULT"
    assert update(p, 5, 2.).state == "FAULT"


def test_mission_limit_does_not_enable_motors():
    p = Preview(Settings(mission_s=1.))
    update(p, 0, 0.)
    d = update(p, 1, 1.)
    assert d.state == "COMPLETE" and not d.motor_output_enabled


def test_latest_complete_record_only_and_invalid_latest_fails(tmp_path):
    path = tmp_path / "events.jsonl"
    assert latest(path, DetectionEvent) is None
    events = [observation(i, i * .1)[0] for i in range(5)]
    text = "".join(e.model_dump_json() + "\n" for e in events)
    path.write_text(text + '{"unfinished":')
    assert latest(path, DetectionEvent).seq_id == 4
    assert latest(path, DetectionEvent, limit=2048).seq_id == 4
    path.write_text(text + "{bad}\n")
    with pytest.raises(ValueError):
        latest(path, DetectionEvent)
    path.write_text("")
    assert latest(path, DetectionEvent) is None
    replacement = tmp_path / "new"
    replacement.write_text(events[0].model_dump_json() + "\n")
    replacement.replace(path)
    assert latest(path, DetectionEvent).seq_id == 0
    path.write_text("x" * 300)
    with pytest.raises(ValueError, match="read limit"):
        latest(path, DetectionEvent, limit=100)


class FakeClient:
    def __init__(self):
        self.writes = []
        self.session = 12
        self.state = 0
        self.is_connected = True
        self.on_read = lambda: None

    async def read_gatt_char(self, uuid):
        self.on_read()
        return struct.pack("<BBBBIIhh", 1, self.state, 0, 1, self.session, 0, 0, 0)

    async def write_gatt_char(self, uuid, packet, response):
        self.writes.append(packet)

    async def disconnect(self):
        self.is_connected = False


def test_speaker_can_only_stop_and_speak_and_rejects_new_session():
    async def scenario():
        client = FakeClient()
        speaker = Speaker(client, clock=lambda: 0.)
        await speaker.initialize()
        assert await speaker.announce(1.)
        client.session = 13
        with pytest.raises(RuntimeError, match="session changed"):
            await speaker.announce(1.)
        await speaker.close()
        assert [p[1] for p in client.writes] == [PacketType.STOP, PacketType.TONE, PacketType.STOP]
        assert not client.is_connected
    asyncio.run(scenario())


def test_speaker_drops_expired_evidence_after_status_read_and_rejects_armed():
    async def scenario():
        now = [0.]
        client = FakeClient()
        speaker = Speaker(client, clock=lambda: now[0])
        await speaker.initialize()
        client.on_read = lambda: now.__setitem__(0, 2.)
        assert not await speaker.announce(1.)
        assert not await speaker.announce(1.)
        client.state = 1
        with pytest.raises(RuntimeError, match="disarmed"):
            await speaker.announce(3.)
        assert [p[1] for p in client.writes] == [PacketType.STOP]
    asyncio.run(scenario())


def test_demo_all_states_and_cli_artifacts(tmp_path):
    p = Preview()
    decisions = [p.update(*step) for step in steps()]
    assert {d.state for d in decisions} >= {"EXPLORE", "OBSERVE", "ANNOUNCE", "HOLD", "STOPPED"}
    assert sum(d.announcement is not None for d in decisions) == 1
    assert not any(d.motor_output_enabled for d in decisions)
    result = subprocess.run([sys.executable, "-m", "navigation", "--demo", "--output-dir", str(tmp_path)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    records = [json.loads(line) for line in (tmp_path / "decisions.jsonl").read_text().splitlines()]
    assert all(r["source_mode"] == "SYNTHETIC" and not r["motor_output_enabled"] for r in records)
    assert (tmp_path / "map.svg").read_text().startswith("<svg")


@pytest.mark.parametrize("args", [["--demo", "--ble-speech"], ["--demo", "--seconds", "nan"],
                                  ["--run-dir", "/tmp", "--source-mode", "REPLAY", "--ble-speech"]])
def test_cli_rejects_invalid_or_simulated_hardware_use(args):
    result = subprocess.run([sys.executable, "-m", "navigation", *args], capture_output=True, timeout=10)
    assert result.returncode == 2
