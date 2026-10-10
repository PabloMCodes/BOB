"""Dashboard Step 6: hub frontend API (C10) + SAMPLE workspace.

Gates: responses match the committed OpenAPI, SAMPLE records never appear in rover views (separate
database), every item states source_mode / delivery / clock domains, a slow or closed browser never
affects the hub, and the route list has no motion authority.
"""

import asyncio
import json
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient
from websockets.asyncio.client import connect

from bobapp.contracts import Delivery, Lane, Record, SourceMode
from bobapp.edge.api.live import build_live_state
from bobapp.edge.store import EdgeStore
from bobapp.hub.api import HUB_ROUTES, create_hub_app
from bobapp.hub.config import load_hub_config
from bobapp.hub.replica import Replica
from bobapp.sample.builder import SESSION, build
from tools.export_hub_openapi import OPENAPI_FILE, hub_openapi

FIXTURES = Path(__file__).parent / "fixtures" / "app" / "valid"
TOKEN = "hub-api-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
OBS = Record.model_validate_json((FIXTURES / "record_observation_live.json").read_text()).body.model_copy(update={"assessment": None})
EVIDENCE = Record.model_validate_json((FIXTURES / "record_evidence.json").read_text()).body


def replicate(store, replica, delivery=Delivery.REALTIME, connected=True):
    ws, _ = replica.adopt(store.edge_id, store.store_epoch)
    for lane in Lane:
        records = [Record.model_validate_json(r.json) for r in store.read(lane, replica.cursors(ws)[lane], 10_000)]
        if records:
            replica.commit(ws, lane, records, delivery)
    live, preview = build_live_state(store)
    replica.set_live(live.model_dump_json())
    if preview:
        replica.set_live_preview(preview, live.preview.sha256)
    replica.set_link({"state": "CONNECTED" if connected else "DISCONNECTED", "edge_id": store.edge_id,
                      "lanes": {lane.value: {"committed": replica.cursors(ws)[lane], "head_known": replica.cursors(ws)[lane],
                                             "behind": 0} for lane in Lane}})
    return ws


@pytest.fixture
def hub(tmp_path):
    rover_store, sample_store = EdgeStore(tmp_path / "edge", "rover-test"), EdgeStore(tmp_path / "sample", "sample-edge")
    for _ in range(5):
        rover_store.append(OBS, SourceMode.LIVE)
    good = rover_store.put_blob(b"\xff\xd8 rover evidence")
    rover_store.append(EVIDENCE.model_copy(update={"sha256": good}), SourceMode.LIVE)
    pending = rover_store.put_blob(b"\xff\xd8 not fetched yet")
    rover_store.append(EVIDENCE.model_copy(update={"sha256": pending}), SourceMode.LIVE)
    build(sample_store)
    rover, sample = Replica(tmp_path / "hub"), Replica(tmp_path / "hub-sample")
    replicate(rover_store, rover)
    rover.store_blob(good, rover_store.blob_file(good).read_bytes())
    replicate(sample_store, sample)
    for sha in sample.pending_blobs():
        sample.store_blob(sha, sample_store.blob_file(sha).read_bytes())
    app = create_hub_app(load_hub_config(), TOKEN, {"rover": tmp_path / "hub", "sample": tmp_path / "hub-sample"})
    with TestClient(app) as client:
        yield {"client": client, "rover": rover, "sample": sample, "rover_store": rover_store, "good": good,
               "pending": pending, "tmp": tmp_path}


def get(client, path, **params):
    response = client.get(path, params=params, headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def test_route_list_is_exact_and_has_no_motion_authority(hub):
    routes = {(("WEBSOCKET",) if not getattr(r, "methods", None) else tuple(sorted(r.methods - {"HEAD"})))[0] + "|" + r.path
              for r in hub["client"].app.routes if r.path.startswith("/v1")}
    assert routes == {f"{m}|{p}" for m, p in HUB_ROUTES}
    forbidden = ("move", "drive", "motor", "arm", "stop", "fault", "clear", "throttle", "esp32", "ble", "speed")
    assert not [r for r in routes if any(w in r.lower() for w in forbidden)]


def test_committed_openapi_matches_the_code():
    assert json.loads(OPENAPI_FILE.read_text()) == hub_openapi(), "run uv run python -m tools.export_hub_openapi"
    for path, methods in hub_openapi()["paths"].items():
        assert "200" in methods["get"]["responses"], path


def test_token_by_header_or_query(hub):
    client = hub["client"]
    assert client.get("/v1/status").status_code == 401
    assert client.get("/v1/status", params={"token": "wrong"}).status_code == 401
    assert client.get("/v1/status", params={"token": TOKEN}).status_code == 200
    assert client.get(f"/v1/evidence/{hub['good']}", params={"token": TOKEN}).status_code == 200  # <img src=…>


def test_sample_never_enters_rover_views(hub):
    client = hub["client"]
    rover, sample = get(client, "/v1/status"), get(client, "/v1/status", workspace="sample")
    assert rover["workspace"] == "rover" and rover["lanes"]["observation"]["records"] == 5
    assert rover["lanes"]["track"]["records"] == 0 and rover["source_mode"] is None
    assert sample["source_mode"] == "SAMPLE" and sample["lanes"]["track"]["records"] == 70
    rover_items = get(client, "/v1/observations", limit=1000)["items"]
    assert len(rover_items) == 5 and {i["record"]["source_mode"] for i in rover_items} == {"LIVE"}
    assert all(i["record"]["edge_id"] == "rover-test" for i in rover_items)
    sample_items = get(client, "/v1/observations", workspace="sample", limit=1000)["items"]
    assert sample_items and {i["record"]["source_mode"] for i in sample_items} == {"SAMPLE"}
    assert get(client, "/v1/incidents")["items"] == []                      # nothing real to confirm
    hazards = {i["record"]["body"]["key"]["hazard"] for i in get(client, "/v1/incidents", workspace="sample")["items"]}
    assert hazards == {"ppe", "restricted_zone", "person_in_path", "walkway"}
    producers = {p["name"]: p for p in sample["live"]["capabilities"]["producers"]}
    assert producers["person_in_path"]["status"] == "not_integrated" and "SAMPLE" in producers["person_in_path"]["note"]


def test_every_item_states_source_delivery_and_clock_domains(hub):
    page = get(hub["client"], "/v1/observations", workspace="sample", limit=3)
    assert "hub_rx_wall_ns" in " ".join(page["clock_domains"]) and "iPhone" in " ".join(page["clock_domains"].values())
    for item in page["items"]:
        assert item["delivery"] in ("realtime", "backfilled") and item["record"]["source_mode"] == "SAMPLE"
        assert item["record"]["rover"]["clock_synced"] is None and item["hub_rx_wall_ns"] > 0


def test_paging_and_filters(hub):
    client = hub["client"]
    first = get(client, "/v1/observations", workspace="sample", limit=4)
    second = get(client, "/v1/observations", workspace="sample", limit=4, after=first["next_after"])
    seqs = [i["record"]["body"]["event"]["seq_id"] for i in first["items"] + second["items"]]
    assert seqs == sorted(seqs) and len(set(seqs)) == 8
    assert len(get(client, "/v1/observations", workspace="sample", session_id=str(SESSION), limit=1000)["items"]) == 15
    assert get(client, "/v1/observations", workspace="sample", session_id="00000000-0000-4000-8000-000000000000")["items"] == []
    assert get(client, "/v1/observations", workspace="sample", delivery="backfilled")["items"] == []
    ppe = get(client, "/v1/incidents", workspace="sample", hazard="ppe")["items"]
    assert [i["record"]["body"]["transition"] for i in ppe] == ["candidate", "confirmed", "ended"]
    assert ppe[-1]["record"]["body"]["end_reason"] == "condition_not_observed"


def test_inspections_and_assessments(hub):
    client = hub["client"]
    inspections = get(client, "/v1/inspections", workspace="sample")["items"]
    assert len(inspections) == 1 and inspections[0]["ended"] is None and inspections[0]["source_mode"] == "SAMPLE"
    assessments = get(client, "/v1/assessments", workspace="sample", inspection_id=inspections[0]["inspection_id"])["items"]
    assert len(assessments) == 15
    statuses = {r["requirement"]: r["status"] for r in assessments[0]["assessment"]["requirements"]}
    assert statuses["gloves"] == "not_required" and statuses["boots"] == "assessment_unavailable"
    unlocalized = [a for a in assessments if not a["pose_valid"]]
    assert unlocalized and all(a["pose"] is None and a["pose_invalid_reason"] for a in unlocalized)
    assert get(client, "/v1/assessments")["items"] == []  # no inspection on the rover: observations only


def test_evidence_states(hub):
    client = hub["client"]
    ok = client.get(f"/v1/evidence/{hub['good']}", headers=AUTH)
    assert ok.status_code == 200 and ok.content == b"\xff\xd8 rover evidence"
    pending = client.get(f"/v1/evidence/{hub['pending']}", headers=AUTH)
    assert pending.status_code == 202 and pending.json()["status"] == "pending_sync"
    unknown = client.get(f"/v1/evidence/{'1' * 64}", headers=AUTH)
    assert unknown.status_code == 404 and unknown.json()["status"] == "missing"
    assert client.get(f"/v1/preview/latest", params={"workspace": "sample"}, headers=AUTH).status_code == 200


def test_disconnected_link_means_last_known_not_current(hub):
    hub["rover"].set_link({"state": "DISCONNECTED", "lanes": {}, "rover_state": "unknown since last contact"})
    status = get(hub["client"], "/v1/status")
    assert status["live_is_current"] is False and status["link"]["rover_state"] == "unknown since last contact"
    assert all(lane["behind"] is None for lane in status["lanes"].values())


def test_live_websocket_snapshot_then_record_deltas(hub):
    client, rover, store = hub["client"], hub["rover"], hub["rover_store"]
    with client.websocket_connect(f"/v1/live?token={TOKEN}") as ws:
        snapshot = json.loads(ws.receive_text())
        assert snapshot["type"] == "snapshot" and snapshot["records"] == [] and snapshot["status"]["workspace"] == "rover"
        store.append(OBS, SourceMode.LIVE)
        replicate(store, rover)
        for _ in range(20):
            update = json.loads(ws.receive_text())
            if update["records"]:
                break
        assert update["type"] == "update"
        assert [(r["lane"], r["seq"], r["kind"], r["source_mode"]) for r in update["records"]] == [("observation", 6, "observation", "LIVE")]
    with pytest.raises(Exception):
        with client.websocket_connect("/v1/live") as ws:
            ws.receive_text()


def test_slow_or_closed_browsers_never_affect_the_hub(hub, tmp_path):
    config = load_hub_config()
    config["api"] = {**config["api"], "live_interval_s": 0.02, "send_timeout_s": 1.0}
    app = create_hub_app(config, TOKEN, {"rover": hub["tmp"] / "hub", "sample": hub["tmp"] / "hub-sample"})
    port = __import__("tests.test_hub_sync", fromlist=["free_port"]).free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", ws="websockets-sansio"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.02)

    async def scenario():
        url = f"ws://127.0.0.1:{port}/v1/live?workspace=sample&token={TOKEN}"
        stuck = await connect(url, max_queue=1, close_timeout=0.2)  # never reads: a frozen browser tab
        closed = await connect(url)
        await closed.recv()
        closed.transport.abort()                          # a tab closed without a goodbye
        healthy = await connect(url)
        received = 0
        start = time.monotonic()
        while time.monotonic() - start < 2.0:
            await asyncio.wait_for(healthy.recv(), timeout=1.0)
            received += 1
        rest = []
        for _ in range(10):
            t = time.monotonic()
            await asyncio.to_thread(lambda: __import__("urllib.request", fromlist=["urlopen"]).urlopen(
                __import__("urllib.request", fromlist=["Request"]).Request(
                    f"http://127.0.0.1:{port}/v1/status?workspace=sample", headers=AUTH), timeout=2).read())
            rest.append(time.monotonic() - t)
        await healthy.close()
        await stuck.close()
        return received, max(rest)

    try:
        received, slowest_rest = asyncio.run(scenario())
    finally:
        server.should_exit = True
        thread.join(5)
    assert received >= 20, "a healthy browser keeps getting updates next to a stuck one"
    assert slowest_rest < 0.5
