"""Dashboard Step 7: worksite profiles and inspection lifecycle (plan §4 semantics).

Covers: check/uncheck, unsupported requirement, no-requirements state, conflicting edits (409),
saved-but-pending revisions, in-flight results keeping their revision, and reconnects / ARKit resets
/ restarts that never start an inspection or activate edits.
"""

import time
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from bobapp.contracts import Lane, Record, RuleStatus, SourceMode, Verdict, WorksiteProfile
from bobapp.edge.config import load_edge_config
from bobapp.edge.publish import EdgePublisher
from bobapp.edge.publish.assessment import NOT_JUDGED, assess
from bobapp.edge.store import ActiveInspection, EdgeStore
from bobapp.hub.api import create_hub_app
from bobapp.hub.config import load_hub_config
from bobapp.hub.replica import Replica
from tests.test_edge_publish import pipeline  # noqa: F401 — shared module fixture (real model)
from tests.test_hub_sync import TOKEN as EDGE_TOKEN
from tests.test_hub_sync import EdgeServer, Hub, Proxy, free_port, wait_until
from tests.test_replay_detect import ASSETS, CONFIG, MS, _frame, _pose
from tools.replay_detect import run

TOKEN = "worksite-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
ALL = ("eyewear", "helmet", "gloves", "vest", "boots")
RULES = [RuleStatus(name=n, active=True) for n in ("glasses", "helmet", "gloves", "vest")] + [
    RuleStatus(name="boots", active=False, missing_classes=["safety-boots"])]


def inspection(requirements, revision=1, mode=SourceMode.REPLAY):
    profile = WorksiteProfile.build("site-a", revision, "Site A", requirements)
    return ActiveInspection(uuid4(), "site-a", revision, profile.sha256, mode, profile)


def statuses(assessment):
    return {r.requirement: (r.status.value, r.reason) for r in assessment.requirements}


# --- §4 semantics (pure) -------------------------------------------------------------------------

def test_assessment_follows_the_requirement_table():
    verdicts = {"glasses": Verdict.NOT_WEARING, "helmet": Verdict.WEARING, "gloves": Verdict.WEARING,
                "vest": Verdict.UNVERIFIED}
    a = assess(verdicts, RULES, inspection({"eyewear": True, "helmet": True, "gloves": False, "vest": True, "boots": True}))
    s = statuses(a)
    assert s["eyewear"] == ("not_detected", None) and s["helmet"] == ("detected", None)
    assert s["gloves"] == ("not_required", None)          # unchecked: never "detected" or "compliant"
    assert s["vest"] == ("not_assessed", NOT_JUDGED)       # nobody judged: never a pass
    assert s["boots"][0] == "assessment_unavailable" and "safety-boots" in s["boots"][1]  # never a look-alike
    assert a.no_requirements_selected is False and a.profile_revision == 1


def test_no_requirements_selected_is_not_an_all_clear():
    a = assess({"glasses": Verdict.NOT_WEARING, "helmet": Verdict.NOT_WEARING, "gloves": Verdict.UNVERIFIED,
                "vest": Verdict.UNVERIFIED}, RULES, inspection(dict.fromkeys(ALL, False)))
    assert a.no_requirements_selected is True
    assert {s for s, _ in statuses(a).values()} == {"not_required"}


# --- hub authoring ---------------------------------------------------------------------------------

@pytest.fixture
def authoring(tmp_path):
    app = create_hub_app(load_hub_config(), TOKEN, {"rover": tmp_path / "hub"},
                         edge=(f"http://127.0.0.1:{free_port()}", TOKEN))  # nothing listens: rover offline
    with TestClient(app) as client:
        yield client


def save(client, expected, requirements, name="Site A", worksite="site-a"):
    return client.put(f"/v1/worksites/{worksite}", headers=AUTH,
                      json={"expected_revision": expected, "name": name, "requirements": requirements})


def test_revisions_are_immutable_and_edits_conflict(authoring):
    first = save(authoring, 0, dict.fromkeys(ALL, True))
    assert first.status_code == 200 and first.json()["latest"]["revision"] == 1
    assert save(authoring, 1, {**dict.fromkeys(ALL, True), "gloves": False}).json()["latest"]["revision"] == 2
    stale = save(authoring, 1, dict.fromkeys(ALL, False))     # a second editor still on revision 1
    assert stale.status_code == 409 and stale.json()["current_revision"] == 2
    rev1 = authoring.get("/v1/worksites/site-a/revisions/1", headers=AUTH).json()
    assert rev1["requirements"]["gloves"] is True and WorksiteProfile.model_validate(rev1).revision == 1
    assert save(authoring, 2, {"eyewear": True}).status_code == 422          # every requirement must be stated
    assert save(authoring, 2, {**dict.fromkeys(ALL, True), "earmuffs": True}).status_code == 422


def test_profiles_are_editable_while_the_rover_is_offline_but_inspections_fail_honestly(authoring):
    assert save(authoring, 0, dict.fromkeys(ALL, True)).status_code == 200   # rover unreachable: fine
    started = authoring.post("/v1/inspections", headers=AUTH, json={"worksite_id": "site-a", "source_mode": "REPLAY"})
    assert started.status_code == 503 and "nothing was started" in started.json()["detail"]
    assert authoring.post("/v1/inspections", headers=AUTH, json={"worksite_id": "nope"}).status_code == 404


# --- lifecycle through a real rover edge API --------------------------------------------------------

@pytest.fixture
def lifecycle(tmp_path):
    edge_config = load_edge_config()
    edge_config["sync"] = {**edge_config["sync"], "live_interval_s": 0.1}
    store = EdgeStore(tmp_path / "edge", "rover-test")
    port = free_port()
    edge = EdgeServer(tmp_path / "edge", edge_config, port)
    proxy = Proxy(port)
    hub_config = load_hub_config()
    hub_config["link"] = {"reconnect_min_s": 0.1, "reconnect_max_s": 0.3, "stale_after_s": 1.0}
    hub = Hub(tmp_path / "hub", hub_config, proxy.port)
    app = create_hub_app(hub_config, TOKEN, {"rover": tmp_path / "hub"}, edge=(f"http://127.0.0.1:{port}", EDGE_TOKEN))
    with TestClient(app) as client:
        yield {"client": client, "store": store, "proxy": proxy, "hub": hub}
    hub.stop()
    edge.stop()


def test_start_binds_exactly_one_revision_and_later_saves_stay_pending(lifecycle):
    client, store = lifecycle["client"], lifecycle["store"]
    save(client, 0, {**dict.fromkeys(ALL, True), "gloves": False})
    started = client.post("/v1/inspections", headers=AUTH, json={"worksite_id": "site-a", "source_mode": "REPLAY"})
    assert started.status_code == 201
    inspection_id = UUID(started.json()["body"]["inspection_id"])
    active = store.active_inspection()
    assert active.inspection_id == inspection_id and active.profile_revision == 1
    assert active.profile.requirements["gloves"] is False
    again = client.post("/v1/inspections", headers=AUTH, json={"worksite_id": "site-a", "source_mode": "REPLAY"})
    assert again.status_code == 409                                           # one inspection at a time
    save(client, 1, dict.fromkeys(ALL, True))                                 # saved during the inspection
    wait_until(lambda: client.get("/v1/worksites/site-a", headers=AUTH).json()["active_revision"] == 1,
               what="inspection synced to the hub")
    view = client.get("/v1/worksites/site-a", headers=AUTH).json()
    assert view["pending"] is True and view["latest"]["revision"] == 2 and store.active_inspection().profile_revision == 1
    assert client.post(f"/v1/inspections/{inspection_id}/end", headers=AUTH).status_code == 200
    second = client.post("/v1/inspections", headers=AUTH, json={"worksite_id": "site-a", "source_mode": "REPLAY"})
    assert second.status_code == 201 and store.active_inspection().profile_revision == 2  # only now


def test_link_reconnects_never_start_an_inspection(lifecycle):
    store, proxy, hub = lifecycle["store"], lifecycle["proxy"], lifecycle["hub"]
    wait_until(lambda: hub.client.sessions >= 1, what="first connection")
    for n in range(2, 5):
        proxy.cut()
        wait_until(lambda: hub.client.link.state["state"] == "DISCONNECTED", 5, "DISCONNECTED")
        proxy.restore()
        wait_until(lambda: hub.client.sessions >= n, 10, f"reconnect {n}")
    assert store.active_inspection() is None
    assert not [r for r in store.read(Lane.CONTROL, 0) if r.kind.startswith("inspection")]


# --- binding of real frames on the rover -------------------------------------------------------------

@pytest.fixture(scope="module")
def two_sessions():
    import cv2
    s1, s2, bus = uuid4(), uuid4(), cv2.imread(str(ASSETS / "bus.jpg"))
    return [_frame(s1, 0, 1_000 * MS, bus, "portrait"), _pose(s1, 1, 1_050 * MS), _frame(s1, 2, 1_100 * MS, bus, "portrait"),
            _frame(s2, 0, 5_000 * MS, bus, "portrait"), _frame(s2, 1, 5_100 * MS, bus, "portrait")]  # ARKit reset


def replay_into(store, pipeline, records, mode):  # noqa: F811
    publisher = EdgePublisher(store, load_edge_config(), source_mode=mode, run_id=f"run-{uuid4().hex[:6]}",
                              pipeline=pipeline, render_config=CONFIG["render"], stale_ms=CONFIG["timing"]["stale_ms"],
                              zones_enabled=False, blocking=True)
    outcomes = run(records, pipeline, CONFIG, on_frame=lambda o, d: publisher.on_detection(d), on_admit=publisher.on_admit)
    publisher.close(timeout=30)
    return outcomes


def bodies(store, lane, kind=None):
    out = [Record.model_validate_json(r.json).body for r in store.read(lane, 0, 10_000)]
    return [b for b in out if kind is None or b.kind == kind]


def test_frames_are_assessed_under_the_bound_revision_across_an_arkit_reset(tmp_path, pipeline, two_sessions):  # noqa: F811
    store = EdgeStore(tmp_path / "edge", "rover-test")
    rev1 = WorksiteProfile.build("site-a", 1, "A", {**dict.fromkeys(ALL, True), "gloves": False})
    started = store.start_inspection(rev1, SourceMode.REPLAY)
    store.deliver_profile(WorksiteProfile.build("site-a", 2, "A", dict.fromkeys(ALL, False)), SourceMode.REPLAY)  # saved, pending
    outcomes = replay_into(store, pipeline, two_sessions, SourceMode.REPLAY)
    observations = bodies(store, Lane.OBSERVATION)
    assert len(observations) == len(outcomes) == 4
    assert {o.event.session_id for o in observations} == {r.msg.session_id for r in two_sessions}  # new ARKit session…
    for o in observations:                                                    # …same inspection, same revision
        assert o.assessment.inspection_id == started.body.inspection_id and o.assessment.profile_revision == 1
        s = statuses(o.assessment)
        assert s["gloves"][0] == "not_required" and s["boots"][0] == "assessment_unavailable"
        expected = {"wearing": "detected", "not_wearing": "not_detected", "unverified": "not_assessed"}
        assert s["eyewear"][0] == expected[o.frame_verdicts["glasses"].value]
    notices = [(n.code, n.details.get("requirement")) for n in bodies(store, Lane.CONTROL, "notice")]
    assert ("assessment_unavailable", "boots") in notices and notices.count(("assessment_unavailable", "boots")) == 1
    assert ("source_restarted_during_inspection", None) in notices           # this run began mid-inspection
    assert store.active_inspection().profile_revision == 1                    # nothing activated the saved edit


def test_no_inspection_means_observations_without_assessment(tmp_path, pipeline, two_sessions):  # noqa: F811
    store = EdgeStore(tmp_path / "edge", "rover-test")
    replay_into(store, pipeline, two_sessions[:3], SourceMode.REPLAY)
    assert all(o.assessment is None for o in bodies(store, Lane.OBSERVATION))
    assert store.active_inspection() is None and not bodies(store, Lane.CONTROL, "inspection_started")


def test_a_run_of_another_source_mode_is_never_assessed_under_the_inspection(tmp_path, pipeline, two_sessions):  # noqa: F811
    store = EdgeStore(tmp_path / "edge", "rover-test")
    store.start_inspection(WorksiteProfile.build("site-a", 1, "A", dict.fromkeys(ALL, True)), SourceMode.LIVE)
    replay_into(store, pipeline, two_sessions[:3], SourceMode.REPLAY)
    assert all(o.assessment is None for o in bodies(store, Lane.OBSERVATION))
    assert "source_mode_mismatch" in [n.code for n in bodies(store, Lane.CONTROL, "notice")]
