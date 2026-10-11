"""Dashboard Step 9: Twin backend (plan §7) — projection, sessions, track segments, pins, unlocalized
items, honest marker, debug SVG. The physical forward / left / right / Reset walk stays a manual gate."""

import math
import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from bobapp.contracts import Delivery, Lane, Record, SourceMode, TrackPointBody
from bobapp.edge.store import EdgeStore
from bobapp.hub.api import create_hub_app
from bobapp.hub.config import load_hub_config
from bobapp.hub.replica import Replica
from bobapp.hub.twin.projection import east_north, svg_heading
from bobapp.sample.builder import SESSION, build
from tests.test_hub_api import replicate
from vision.schema import Pose, PoseInvalidReason

TOKEN = "twin-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
FIXTURES = Path(__file__).parent / "fixtures" / "app" / "valid"
EVIDENCE = Record.model_validate_json((FIXTURES / "record_evidence.json").read_text()).body


def test_projection_forward_is_up_and_left_turn_points_west():
    assert east_north(Pose(x_m=0, y_m=1.5, z_m=-2, yaw_rad=0)) == (0, 2)        # walked forward: north, height ignored
    hx, hy = svg_heading(0.0)
    assert (round(hx, 6), round(hy, 6)) == (0, -1)                               # up on screen
    hx, hy = svg_heading(math.pi / 2)                                            # turned left 90°
    assert (round(hx, 6), round(hy, 6)) == (-1, 0)                               # west, not mirrored
    hx, _ = svg_heading(-math.pi / 2)
    assert round(hx, 6) == 1                                                     # turned right: east


@pytest.fixture
def twin(tmp_path):
    sample_store, rover_store = EdgeStore(tmp_path / "sample", "sample-edge"), EdgeStore(tmp_path / "edge", "rover-test")
    build(sample_store)
    s1, s2 = uuid4(), uuid4()
    for i in range(5):                                                            # session 1: realtime
        rover_store.append(TrackPointBody(kind="track_point", session_id=s1, segment=0, seq_id=i, iphone_ts_ns=i * 10**8,
                                          packet="frame", pose=Pose(x_m=0, y_m=0, z_m=-0.1 * i, yaw_rad=0)), SourceMode.LIVE)
    rover_store.append(EVIDENCE.model_copy(update={"session_id": s1, "sha256": rover_store.put_blob(b"a")}), SourceMode.LIVE)
    rover_store.append(EVIDENCE.model_copy(update={"session_id": s1, "sha256": rover_store.put_blob(b"b"), "pose": None,
                                                   "pose_valid": False, "pose_invalid_reason": PoseInvalidReason.STALE}), SourceMode.LIVE)
    sample, rover = Replica(tmp_path / "hub-sample"), Replica(tmp_path / "hub")
    replicate(sample_store, sample)
    replicate(rover_store, rover)
    for i in range(3):                                                            # session 2 (ARKit reset), backfilled
        rover_store.append(TrackPointBody(kind="track_point", session_id=s2, segment=0, seq_id=i, iphone_ts_ns=10**10 + i,
                                          packet="pose", pose=Pose(x_m=5, y_m=0, z_m=5 + i, yaw_rad=1)), SourceMode.LIVE)
    replicate(rover_store, rover, delivery=Delivery.BACKFILLED)
    app = create_hub_app(load_hub_config(), TOKEN, {"rover": tmp_path / "hub", "sample": tmp_path / "hub-sample"})
    with TestClient(app) as client:
        yield {"client": client, "rover": rover, "s1": s1, "s2": s2}


def get(client, path, **params):
    r = client.get(path, params=params, headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def test_sample_session_track_has_two_segments_split_by_lost_tracking(twin):
    client = twin["client"]
    sessions = get(client, "/v1/twin/sessions", workspace="sample")
    (s,) = sessions["sessions"]
    assert s["session_id"] == str(SESSION) and s["track_points"] == 70 and s["segments"] == 2
    assert sessions["projection"]["not_compass_north"] is True
    track = get(client, f"/v1/twin/sessions/{SESSION}/track", workspace="sample")
    first, second = track["segments"]
    end = first["points"][-1]
    assert (round(end["east_m"], 2), round(end["north_m"], 2)) == (-2.0, 3.0)    # 3 m forward, then 2 m left = west
    assert second["points"][0]["east_m"] < end["east_m"]                        # never joined across the gap


def test_sample_pins_and_unlocalized_items(twin):
    pins = get(twin["client"], f"/v1/twin/sessions/{SESSION}/pins", workspace="sample")
    incidents = {p["hazard"]: p for p in pins["pins"] if p["kind"] == "incident"}
    assert set(incidents) == {"ppe", "restricted_zone", "person_in_path"}
    assert incidents["ppe"]["state"] == "ended" and incidents["ppe"]["end_reason"] == "condition_not_observed"
    assert all(p["source_mode"] == "SAMPLE" and "observed from here" in p["meaning"] for p in pins["pins"])
    walkway = [u for u in pins["unlocalized"] if u["label"].startswith("walkway")]
    assert walkway and walkway[0]["reason"] == "tracking_not_normal"             # its frame had no valid pose
    assert pins["marker"]["label"] == "Phone camera" and pins["marker"]["status"] == "last_known"


def test_invalid_association_stays_unlocalized_never_the_latest_pose(twin):
    pins = get(twin["client"], f"/v1/twin/sessions/{twin['s1']}/pins")
    assert len(pins["pins"]) == 1 and pins["pins"][0]["kind"] == "evidence"
    assert [(u["kind"], u["reason"]) for u in pins["unlocalized"]] == [("evidence", "stale")]


def test_new_session_is_a_new_map_and_backfill_is_labeled(twin):
    client, s1, s2 = twin["client"], twin["s1"], twin["s2"]
    sessions = {s["session_id"]: s for s in get(client, "/v1/twin/sessions")["sessions"]}
    assert set(sessions) == {str(s1), str(s2)}                                   # never merged
    assert sessions[str(s2)]["backfilled_points"] == 3 and sessions[str(s1)]["backfilled_points"] == 0
    assert get(client, f"/v1/twin/sessions/{s2}/track")["segments"][0]["delivery"] == "backfilled"
    assert get(client, f"/v1/twin/sessions/{s2}/pins")["pins"] == []             # s1's evidence stays on s1's map
    assert str(SESSION) not in sessions                                          # SAMPLE never on the rover map


def test_disconnected_link_marker_is_unknown_not_stopped(twin):
    rover, client, s1 = twin["rover"], twin["client"], twin["s1"]
    live_json, _, _, _ = rover.get_live()
    import json
    live = json.loads(live_json)
    live["pose"] = {"session_id": str(s1), "seq_id": 4, "iphone_ts_ns": 4 * 10**8, "pose_valid": True,
                    "pose": {"x_m": 0, "y_m": 0, "z_m": -0.4, "yaw_rad": 0}, "pose_invalid_reason": None}
    live["freshness"]["pose"] = {"age_ms": 100.0, "reason": None}
    rover.set_live(json.dumps(live))
    assert get(client, f"/v1/twin/sessions/{s1}/pins")["marker"]["status"] == "current"
    rover.set_link({**rover.get_link(), "state": "DISCONNECTED"})
    marker = get(client, f"/v1/twin/sessions/{s1}/pins")["marker"]
    assert marker["status"] == "unknown" and "position since then unknown" in marker["note"]


def test_debug_svg_is_valid_labeled_and_styles_backfill(twin):
    client = twin["client"]
    r = client.get(f"/v1/twin/sessions/{SESSION}/map.svg", params={"workspace": "sample", "token": TOKEN})
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")
    root = ET.fromstring(r.text)
    text = " ".join(t.text or "" for t in root.iter("{http://www.w3.org/2000/svg}text"))
    assert "SAMPLE" in text and "not compass north" in text and "not person or hazard positions" in text
    backfilled = client.get(f"/v1/twin/sessions/{twin['s2']}/map.svg", headers=AUTH).text
    assert 'class="segment-backfilled"' in backfilled and "stroke-dasharray" in backfilled
