"""Dashboard Step 8 on the rover: real frames -> assessment -> policy -> incident records + evidence.

zidane.jpg: eyewear judged missing (positive); bus.jpg: eyewear judged present (negative). Gates:
deterministic replay, evidence = the exact source pixels, labeled uncalibrated, restart recovery
(source_stopped), and no incident without an inspection.
"""

import hashlib
from uuid import uuid4

import cv2
import pytest

from bobapp.contracts import Lane, Record, SourceMode, WorksiteProfile
from bobapp.edge.config import load_edge_config
from bobapp.edge.publish import EdgePublisher
from bobapp.edge.store import EdgeStore
from bobapp.incidents import PolicyParams
from tests.test_edge_publish import pipeline  # noqa: F401 — shared module fixture (real model)
from tests.test_replay_detect import ASSETS, CONFIG, MS, _frame
from tools.replay_detect import run
from vision.server.slot import ReceivedFrame
from vision.server.view import decode_upright

ALL = ("eyewear", "helmet", "gloves", "vest", "boots")
EYEWEAR_ONLY = {r: r == "eyewear" for r in ALL}


@pytest.fixture(scope="module")
def onoff():
    """0.0–0.7 s without eyewear (zidane), then 3.5 s with it (bus) — one ARKit session at 10 Hz."""
    s, zidane, bus = uuid4(), cv2.imread(str(ASSETS / "zidane.jpg")), cv2.imread(str(ASSETS / "bus.jpg"))
    return ([_frame(s, i, 1_000 * MS + i * 100 * MS, zidane, "landscape_left") for i in range(8)]
            + [_frame(s, 8 + i, 1_800 * MS + i * 100 * MS, bus, "portrait") for i in range(35)])


def replay(store, pipeline, records, inspection=True):  # noqa: F811
    if inspection:
        store.start_inspection(WorksiteProfile.build("site-a", 1, "A", EYEWEAR_ONLY), SourceMode.REPLAY)
    publisher = EdgePublisher(store, load_edge_config(), source_mode="REPLAY", run_id=f"run-{uuid4().hex[:6]}",
                              pipeline=pipeline, render_config=CONFIG["render"], stale_ms=CONFIG["timing"]["stale_ms"],
                              zones_enabled=False, blocking=True)
    run(records, pipeline, CONFIG, on_frame=lambda o, d: publisher.on_detection(d), on_admit=publisher.on_admit)
    return publisher.close(timeout=60)


def control(store, kind):
    return [Record.model_validate_json(r.json).body for r in store.read(Lane.CONTROL, 0, 10_000) if r.kind == kind]


def test_confirmed_then_no_longer_observed_with_source_evidence(tmp_path, pipeline, onoff):  # noqa: F811
    store = EdgeStore(tmp_path / "edge", "rover-test")
    stats = replay(store, pipeline, onoff)
    incidents = control(store, "incident")
    assert [(i.transition.value, i.end_reason.value if i.end_reason else None) for i in incidents] == [
        ("candidate", None), ("confirmed", None), ("ended", "condition_not_observed")]
    confirmed = incidents[1]
    assert confirmed.key.hazard.value == "ppe" and confirmed.key.rule == "glasses" and confirmed.key.profile_revision == 1
    assert confirmed.calibrated is False and confirmed.policy_params_sha256 == PolicyParams.load().sha256
    assert confirmed.location.pose is not None                                  # "observed from here"
    assert {i.key.rule for i in incidents} == {"glasses"}                       # helmet not required: no incident
    evidence = {e.sha256: e for e in control(store, "evidence") if e.reason.value == "incident"}
    assert 2 <= len(confirmed.evidence_sha256) <= 10 and set(confirmed.evidence_sha256) <= set(evidence)
    frames = {r.msg.seq_id: r for r in onoff}
    for sha in incidents[-1].evidence_sha256:                                   # first, confirm, best, last
        e = evidence[sha]
        upright = decode_upright(ReceivedFrame(frames[e.seq_id].msg, frames[e.seq_id].payload, 0, None),
                                 CONFIG["camera"]["mount_orientation"])
        assert hashlib.sha256(upright.tobytes()).hexdigest() == e.image_pixels_sha256
        assert hashlib.sha256(store.blob_file(sha).read_bytes()).hexdigest() == sha
        assert e.seq_id < 8                                                      # only frames without eyewear
    assert stats["evidence_unavailable"] == 0 and stats["transitions"] == 3


def test_replay_gives_the_same_incidents(tmp_path, pipeline, onoff):  # noqa: F811
    a, b = EdgeStore(tmp_path / "a", "rover-test"), EdgeStore(tmp_path / "b", "rover-test")
    replay(a, pipeline, onoff)
    replay(b, pipeline, onoff)
    key = lambda s: [(i.transition, i.observed_iphone_ts_ns, i.counts) for i in control(s, "incident")]  # noqa: E731
    assert key(a) == key(b) and key(a)


def test_stop_mid_incident_ends_source_stopped_and_restart_never_resumes(tmp_path, pipeline, onoff):  # noqa: F811
    store = EdgeStore(tmp_path / "edge", "rover-test")
    replay(store, pipeline, onoff[:8])                                           # stops while confirmed
    assert [(i.transition.value, i.end_reason) for i in control(store, "incident")][-1] == ("ended", "source_stopped")
    # A crash leaves an incident open (no close): the next run closes it at startup.
    open_body = control(store, "incident")[1].model_copy(update={"incident_id": uuid4()})
    store.append(open_body, SourceMode.REPLAY)
    replay(store, pipeline, [], inspection=False)
    last = control(store, "incident")[-1]
    assert last.incident_id == open_body.incident_id and last.transition.value == "ended"
    assert last.end_reason.value == "source_stopped"
    assert "incidents_closed_at_startup" in [n.code for n in control(store, "notice")]


def test_no_inspection_no_incident(tmp_path, pipeline, onoff):  # noqa: F811
    store = EdgeStore(tmp_path / "edge", "rover-test")
    replay(store, pipeline, onoff[:12], inspection=False)
    assert control(store, "incident") == [] and len(store.read(Lane.OBSERVATION, 0)) == 12


def test_calibration_cli_runs_on_a_labeled_recording(tmp_path, onoff):
    import json
    import subprocess
    import sys

    from vision.recording import write_record
    recording = tmp_path / "onoff.bobrec"
    with open(recording, "wb") as fh:
        for r in onoff:
            write_record(fh, r.raw)
    proc = subprocess.run([sys.executable, "-m", "tools.calibrate_incidents", str(recording), "--rule", "glasses",
                           "--segments", "not_wearing:0-0.8,wearing:0.8-4.3", "--out", str(tmp_path / "cal")],
                          capture_output=True, text=True, timeout=300)
    summary = json.loads((tmp_path / "cal" / "summary.json").read_text())
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    assert summary["passed"] and summary["frames"] == 43 and summary["calibrated_flag_in_config"] is False
    assert [c["check"] for c in summary["checks"]] == ["ends within 4 s of PPE on", "no confirmation while wearing"]
