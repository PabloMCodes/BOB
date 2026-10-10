"""Dashboard Step 4: edge API — exact route list (no motion authority), token, sync resume/priority/
backfill/tail/acks, epoch change, bandwidth cap, inspection commands, blobs, honest idle state."""

import json
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from bobapp.contracts import APP_VERSION, Lane, Record, SourceMode, WorksiteProfile, parse_app_message
from bobapp.edge.api.app import ROUTES, create_app
from bobapp.edge.api.auth import resolve_bind
from bobapp.edge.config import load_edge_config
from bobapp.edge.store import EdgeStore

FIXTURES = Path(__file__).parent / "fixtures" / "app" / "valid"
TOKEN = "test-token-not-secret"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def body(name):
    return Record.model_validate_json((FIXTURES / f"record_{name}.json").read_text()).body


OBS, TRACK, NOTICE = body("observation_live"), body("track_point"), body("notice_assessment_unavailable")
PROFILE = WorksiteProfile.build("site-a", 1, "Site A", {"eyewear": True, "helmet": True, "gloves": False,
                                                       "vest": False, "boots": True})


@pytest.fixture
def edge(tmp_path):
    config = load_edge_config()
    path = tmp_path / "edge"
    writer = EdgeStore(path, "rover-test")
    app = create_app(path, "rover-test", config, TOKEN)
    with TestClient(app) as client:
        yield client, writer, config
    writer.close()


def _hello(cursors=None, epoch=None):
    return json.dumps({"app_version": APP_VERSION, "msg_type": "sync_hello", "hub_id": "hub-test",
                       "store_epoch": None if epoch is None else str(epoch),
                       "cursors": cursors or {"control": 0, "track": 0, "observation": 0}})


def _receive_until(ws, predicate, limit=50):
    seen = []
    for _ in range(limit):
        msg = parse_app_message(ws.receive_text())
        seen.append(msg)
        if predicate(msg, seen):
            return seen
    raise AssertionError(f"condition not met in {limit} messages: {[m.msg_type for m in seen]}")


def _batches(seen):
    return [m for m in seen if m.msg_type == "sync_batch"]


# --- authority and auth --------------------------------------------------------------------------

def test_route_list_is_exact_and_has_no_motion_authority(edge):
    client, _, _ = edge
    routes = {(("WEBSOCKET",) if not getattr(r, "methods", None) else tuple(sorted(r.methods - {"HEAD"})))[0] + "|" + r.path
              for r in client.app.routes if r.path.startswith("/v1")}
    assert routes == {f"{m}|{p}" for m, p in ROUTES}
    forbidden = ("move", "drive", "motor", "arm", "stop", "fault", "clear", "throttle", "esp32", "ble", "speed")
    assert not [r for r in routes if any(w in r.lower() for w in forbidden)]


def test_token_is_required_on_every_route(edge):
    client, _, _ = edge
    assert client.get("/v1/live").status_code == 401
    assert client.get("/v1/live", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/v1/live", headers=AUTH).status_code == 200
    with pytest.raises(Exception):
        with client.websocket_connect("/v1/sync") as ws:
            ws.receive_text()


def test_without_a_token_only_loopback_is_allowed():
    assert resolve_bind(None, "", "tok") == ("", None)
    host, warning = resolve_bind(None, "", None)
    assert host == "127.0.0.1" and "loopback" in warning
    assert resolve_bind("::1", "", None)[0] == "::1"
    for host in ("0.0.0.0", "::", ""):
        with pytest.raises(SystemExit, match="without a token"):
            resolve_bind(host, "", None)


# --- sync ----------------------------------------------------------------------------------------

def test_sync_sends_live_first_then_backfill_by_lane_priority_then_tails(edge):
    client, writer, _ = edge
    for b in (OBS, OBS, TRACK, NOTICE):
        writer.append(b, SourceMode.LIVE)
    with client.websocket_connect("/v1/sync", headers=AUTH) as ws:
        ws.send_text(_hello())
        welcome = parse_app_message(ws.receive_text())
        assert welcome.msg_type == "sync_welcome" and welcome.store_epoch == writer.store_epoch
        assert welcome.lanes[Lane.OBSERVATION].head_seq == 2
        seen = _receive_until(ws, lambda m, s: len(_batches(s)) == 3)
        assert seen[0].msg_type == "sync_live"
        assert [(b.lane, [r.seq for r in b.records], b.backfill) for b in _batches(seen)] == [
            (Lane.CONTROL, [1], True), (Lane.TRACK, [1], True), (Lane.OBSERVATION, [1, 2], True)]
        writer.append(NOTICE, SourceMode.LIVE)  # written while connected: tail, not backfill
        tail = _batches(_receive_until(ws, lambda m, s: m.msg_type == "sync_batch"))[0]
        assert (tail.lane, [r.seq for r in tail.records], tail.backfill) == (Lane.CONTROL, [2], False)
        ws.send_text(json.dumps({"app_version": APP_VERSION, "msg_type": "sync_ack",
                                 "store_epoch": str(writer.store_epoch), "lane": "control", "seq": 2}))
        deadline = time.time() + 3
        while writer.acked_seq(Lane.CONTROL) != 2 and time.time() < deadline:
            time.sleep(.02)
    assert writer.acked_seq(Lane.CONTROL) == 2


def test_sync_resumes_from_the_hubs_committed_cursor(edge):
    client, writer, _ = edge
    for _ in range(4):
        writer.append(NOTICE, SourceMode.LIVE)
    with client.websocket_connect("/v1/sync", headers=AUTH) as ws:
        ws.send_text(_hello({"control": 2, "track": 0, "observation": 0}, writer.store_epoch))
        ws.receive_text()
        batch = _batches(_receive_until(ws, lambda m, s: m.msg_type == "sync_batch"))[0]
    assert [r.seq for r in batch.records] == [3, 4]


def test_a_hello_from_another_store_epoch_starts_from_zero(edge):
    client, writer, _ = edge
    for _ in range(3):
        writer.append(NOTICE, SourceMode.LIVE)
    with client.websocket_connect("/v1/sync", headers=AUTH) as ws:
        ws.send_text(_hello({"control": 3, "track": 0, "observation": 0}, uuid4()))
        welcome = parse_app_message(ws.receive_text())
        batch = _batches(_receive_until(ws, lambda m, s: m.msg_type == "sync_batch"))[0]
    assert welcome.store_epoch == writer.store_epoch and [r.seq for r in batch.records] == [1, 2, 3]


def test_acks_for_another_epoch_never_touch_this_store(edge):
    client, writer, _ = edge
    writer.append(NOTICE, SourceMode.LIVE)
    with client.websocket_connect("/v1/sync", headers=AUTH) as ws:
        ws.send_text(_hello())
        ws.receive_text()
        ws.send_text(json.dumps({"app_version": APP_VERSION, "msg_type": "sync_ack", "store_epoch": str(uuid4()),
                                 "lane": "control", "seq": 1}))
        _receive_until(ws, lambda m, s: m.msg_type == "sync_batch")
    assert writer.acked_seq(Lane.CONTROL) == 0


def test_backfill_obeys_the_byte_rate_cap(tmp_path):
    config = load_edge_config()
    config["sync"] = {**config["sync"], "batch_records": 1, "max_bytes_per_s": 20_000}
    writer = EdgeStore(tmp_path / "edge", "rover-test")
    for _ in range(6):
        writer.append(OBS, SourceMode.LIVE)
    with TestClient(create_app(tmp_path / "edge", "rover-test", config, TOKEN)) as client:
        with client.websocket_connect("/v1/sync", headers=AUTH) as ws:
            ws.send_text(_hello())
            ws.receive_text()
            start = time.monotonic()
            seen = _receive_until(ws, lambda m, s: len(_batches(s)) == 6)
            elapsed = time.monotonic() - start
    sent = sum(len(b.model_dump_json()) for b in _batches(seen)[:5])  # the 6th batch's pause is after it
    assert elapsed >= 0.9 * sent / 20_000


def test_a_stalled_api_reader_never_blocks_the_writer(tmp_path):
    """WAL: a reader holding a snapshot (a slow/stuck edge API) does not delay appends."""
    writer = EdgeStore(tmp_path / "edge", "rover-test")
    reader = sqlite3.connect(tmp_path / "edge" / "store.sqlite", isolation_level=None)
    reader.execute("BEGIN")
    reader.execute("SELECT COUNT(*) FROM records").fetchone()
    start = time.perf_counter()
    for _ in range(20):
        writer.append(OBS, SourceMode.LIVE)
    assert time.perf_counter() - start < 1.0
    reader.close()


# --- commands ------------------------------------------------------------------------------------

def test_inspection_lifecycle_and_conflicts(edge):
    client, writer, _ = edge
    start = {"profile": PROFILE.model_dump(mode="json"), "requested_by": "hub-test"}
    assert client.post("/v1/inspections", json=start, headers=AUTH).status_code == 409  # no run, no mode
    started = client.post("/v1/inspections", json={**start, "source_mode": "REPLAY"}, headers=AUTH)
    assert started.status_code == 201
    inspection_id = started.json()["body"]["inspection_id"]
    assert client.post("/v1/inspections", json={**start, "source_mode": "REPLAY"}, headers=AUTH).status_code == 409
    assert client.get("/v1/live", headers=AUTH).json()["active_inspection_id"] == inspection_id
    assert client.post(f"/v1/inspections/{inspection_id}/end", headers=AUTH).status_code == 200
    assert client.post(f"/v1/inspections/{inspection_id}/end", headers=AUTH).status_code == 409
    assert client.post(f"/v1/inspections/{uuid4()}/end", headers=AUTH).status_code == 404
    kinds = [Record.model_validate_json(r.json).body.kind for r in writer.read(Lane.CONTROL, 0)]
    assert kinds == ["profile_revision", "inspection_started", "inspection_ended"]
    assert all(i["source_mode"] == "REPLAY" for i in client.get("/v1/inspections", headers=AUTH).json())


def test_profile_revisions_are_immutable(edge):
    client, _, _ = edge
    deliver = {"profile": PROFILE.model_dump(mode="json")}
    assert client.post("/v1/profiles", json=deliver, headers=AUTH).status_code == 201
    assert client.post("/v1/profiles", json=deliver, headers=AUTH).status_code == 200   # idempotent
    changed = WorksiteProfile.build("site-a", 1, "Site A", {**PROFILE.requirements, "gloves": True})
    assert client.post("/v1/profiles", json={"profile": changed.model_dump(mode="json")}, headers=AUTH).status_code == 409
    tampered = {**PROFILE.model_dump(mode="json"), "requirements": {**PROFILE.requirements, "gloves": True}}
    assert client.post("/v1/profiles", json={"profile": tampered}, headers=AUTH).status_code == 422  # hash re-verified


def test_blobs_by_hash_with_explicit_missing_status(edge):
    client, writer, _ = edge
    sha = writer.put_blob(b"\xff\xd8 evidence")
    ok = client.get(f"/v1/blobs/{sha}", headers=AUTH)
    assert ok.status_code == 200 and ok.content == b"\xff\xd8 evidence"
    missing = client.get(f"/v1/blobs/{'0' * 64}", headers=AUTH)
    assert missing.status_code == 404 and missing.json()["status"] == "missing"
    assert client.get("/v1/blobs/not-a-hash", headers=AUTH).status_code == 422


def test_idle_store_reports_unknown_not_zero(edge):
    client, _, _ = edge
    live = parse_app_message(json.dumps(client.get("/v1/live", headers=AUTH).json()))
    assert live.source_mode is None and live.run_id is None and live.preview is None
    assert live.freshness.video.age_ms is None and "no vision.server run" in live.freshness.video.reason
    assert live.edge.writer_dropped is None and live.edge.store_bytes > 0
    assert client.get("/v1/preview/latest", headers=AUTH).status_code == 404
