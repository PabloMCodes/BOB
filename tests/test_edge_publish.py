"""Dashboard Step 3: publication hook — vision.server / replay_detect -> bounded writer -> edge store.

Gates: detections unchanged with the hook on, every record correlated to its C2 event, evidence tied
to the exact source pixels, a stalled store never stalls the frame path (drops counted), and the
track follows the same validity rules as C2.
"""

import hashlib
import json
import math
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import cv2
import numpy as np
import pytest
import yaml

from bobapp.contracts import EvidenceReason, Lane, Record, SourceMode
from bobapp.edge.config import load_edge_config
from bobapp.edge.publish import EdgePublisher
from bobapp.edge.publish.evidence import EvidenceGate, evidence_triggers
from bobapp.edge.publish.track import TrackSampler
from bobapp.edge.store import EdgeStore
from tests.test_replay_detect import ASSETS, CONFIG, MS, _frame, _pose
from tools.replay_client import replay
from tools.replay_detect import box_mismatches, run
from vision.association import Association
from vision.pipeline import Pipeline
from vision.schema import Pose
from vision.server.slot import ReceivedFrame
from vision.server.view import decode_upright

REPO = Path(__file__).resolve().parent.parent


# --- track sampling ----------------------------------------------------------------------------

def _msg(session, seq, t_s):
    return SimpleNamespace(session_id=session, seq_id=seq, iphone_frame_ts_ns=int(t_s * 1e9))


def _valid(x=0., z=0., yaw=0.):
    return Association(Pose(x_m=x, y_m=0., z_m=z, yaw_rad=yaw), True, 0., None)


INVALID = Association(None, False, None, "tracking_not_normal")


def test_track_downsamples_by_move_turn_and_time():
    s, sampler = uuid4(), TrackSampler(0.05, 2.0, 1.0)
    offered = [(0.0, _valid()), (0.1, _valid(x=0.03)), (0.2, _valid(x=0.06)),          # 6 cm -> emit
               (0.3, _valid(x=0.06, yaw=math.radians(1))), (0.4, _valid(x=0.06, yaw=math.radians(2.5))),
               (1.3, _valid(x=0.06, yaw=math.radians(2.5))), (1.5, _valid(x=0.06, yaw=math.radians(2.5)))]
    points = [sampler.offer(_msg(s, i, t), a) for i, (t, a) in enumerate(offered)]
    assert [p.seq_id for p in points if p] == [0, 2, 4, 6]  # 1 s elapsed at seq 6 (from seq 4 at 0.4 s)


def test_track_yaw_wraps_around_pi():
    s, sampler = uuid4(), TrackSampler(0.05, 2.0, 1.0)
    sampler.offer(_msg(s, 0, 0), _valid(yaw=math.pi - 0.01))
    assert sampler.offer(_msg(s, 1, 0.1), _valid(yaw=-math.pi + 0.01)) is None  # 1.1°, not 359°


def test_invalid_pose_ends_the_segment_and_a_new_session_restarts_the_map():
    s, sampler = uuid4(), TrackSampler(0.05, 2.0, 1.0)
    a = sampler.offer(_msg(s, 0, 0), _valid())
    assert sampler.offer(_msg(s, 1, 0.1), INVALID) is None
    b = sampler.offer(_msg(s, 2, 0.2), _valid())  # first valid pose after a gap: always a new point
    s2 = uuid4()
    c = sampler.offer(_msg(s2, 0, 0.0), _valid(x=5))
    assert (a.segment, b.segment, c.segment) == (0, 1, 0) and c.session_id == s2


# --- evidence policy ---------------------------------------------------------------------------

def _detection(rules_with_violation=(), scene=None):
    verdicts = [SimpleNamespace(rule=r, violation=object()) for r in rules_with_violation]
    return SimpleNamespace(result=SimpleNamespace(verdicts=verdicts)), scene


def test_evidence_triggers_derived_boxes_and_zone_findings_only():
    assert evidence_triggers(*_detection()) == (None, [])
    assert evidence_triggers(*_detection(["helmet", "glasses"])) == (EvidenceReason.DERIVED_BOX, ["glasses", "helmet"])
    zone = {"assessment": {"region": {"zone_id": "tape-1"}, "people": [{"status": "possible_person_in_zone"}]}}
    clear = {"assessment": {"region": {"zone_id": "tape-1"}, "people": [{"status": "observed_feet_outside"}]}}
    assert evidence_triggers(*_detection(scene=zone)) == (EvidenceReason.SCENE_FINDING, ["zone:tape-1"])
    assert evidence_triggers(*_detection(scene=clear)) == (None, [])


def test_evidence_rate_limit_is_per_session_and_key_on_the_phone_clock():
    gate, s1, s2 = EvidenceGate(2.0), uuid4(), uuid4()
    assert gate.admit(s1, ["glasses"], 0) == ["glasses"]
    assert gate.admit(s1, ["glasses", "helmet"], int(1.9e9)) == ["helmet"]
    assert gate.admit(s2, ["glasses"], int(1.9e9)) == ["glasses"]  # new session: new evidence
    assert gate.admit(s1, ["glasses"], int(2.0e9)) == ["glasses"]


# --- replay -> publisher -> store (real model) ------------------------------------------------

@pytest.fixture(scope="module")
def recording():
    s, zidane, bus = uuid4(), cv2.imread(str(ASSETS / "zidane.jpg")), cv2.imread(str(ASSETS / "bus.jpg"))
    return [_frame(s, 0, 1_000 * MS, zidane, "landscape_left"), _pose(s, 1, 1_050 * MS),
            _frame(s, 2, 1_100 * MS, bus, "portrait"), _frame(s, 3, 1_200 * MS, bus, "portrait"),
            _frame(s, 4, 3_400 * MS, bus, "portrait")]  # 2.2 s gap: stale pose, but evidence due again


@pytest.fixture(scope="module")
def pipeline():
    return Pipeline.from_config(CONFIG)


@pytest.fixture(scope="module")
def published(tmp_path_factory, recording, pipeline):
    path = tmp_path_factory.mktemp("edge")
    edge_config = load_edge_config()
    edge_config["archive"]["enabled"] = False  # This fixture exercises legacy evidence sampling.
    store = EdgeStore(path, "rover-test")
    publisher = EdgePublisher(store, edge_config, source_mode="REPLAY", run_id="run-test", pipeline=pipeline,
                              render_config=CONFIG["render"], stale_ms=CONFIG["timing"]["stale_ms"],
                              zones_enabled=False, blocking=True)
    outcomes = run(recording, pipeline, CONFIG, on_frame=lambda o, d: publisher.on_detection(d),
                   on_admit=publisher.on_admit)
    stats = publisher.close(timeout=30)
    reader = EdgeStore(path, "rover-test")
    return outcomes, stats, reader


def _bodies(store, lane):
    return [Record.model_validate_json(r.json) for r in store.read(lane, 0, limit=1000)]


def test_detections_are_unchanged_with_the_hook_on(recording, pipeline, published):
    outcomes, stats, _ = published
    assert box_mismatches(outcomes, run(recording, pipeline, CONFIG)) == []
    assert stats["dropped"] == {"control": 0, "data": 0} and stats["write_errors"] == 0


def test_one_observation_per_processed_frame_in_order(published):
    outcomes, stats, store = published
    records = _bodies(store, Lane.OBSERVATION)
    assert [r.body.event.event_id for r in records] == [o.event.event_id for o in outcomes]
    assert all(r.source_mode == SourceMode.REPLAY and r.run_id == "run-test" for r in records)
    for record, outcome in zip(records, outcomes):
        assert {k: v.value for k, v in record.body.frame_verdicts.items()} == {k: v.value for k, v in outcome.verdicts.items()}
    rules = {r.name: r for r in records[0].body.rules}
    assert not rules["boots"].active and rules["boots"].missing_classes == ["safety-boots"]
    assert stats["observations"] == len(outcomes) == 4


def test_evidence_matches_the_exact_source_pixels_and_is_rate_limited(recording, published):
    outcomes, _, store = published
    observations = {r.body.event.event_id: r.body for r in _bodies(store, Lane.OBSERVATION)}
    evidence = [r.body for r in _bodies(store, Lane.CONTROL) if r.body.kind == "evidence"]
    assert evidence, "derived boxes on zidane/bus must produce evidence"
    frames = {r.msg.seq_id: r for r in recording if r.payload}
    for e in evidence:
        obs = observations[e.event_id]
        assert obs.evidence_sha256 == e.sha256 and obs.image_pixels_sha256 == e.image_pixels_sha256
        source = frames[e.seq_id]
        upright = decode_upright(ReceivedFrame(source.msg, source.payload, 0, None), CONFIG["camera"]["mount_orientation"])
        assert hashlib.sha256(upright.tobytes()).hexdigest() == e.image_pixels_sha256
        blob = store.blob_file(e.sha256).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == e.sha256 and len(blob) == e.size_bytes
        assert cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_COLOR).shape[:2] == upright.shape[:2]
    captured = {}
    for e in evidence:
        for key in e.rules:
            prev = captured.get((e.session_id, key))
            assert prev is None or e.iphone_frame_ts_ns - prev >= 2e9, f"{key} captured twice within 2 s"
            captured[(e.session_id, key)] = e.iphone_frame_ts_ns
    assert {e.seq_id for e in evidence} >= {0, 4}  # seq 4 is 2.3 s after the bus at seq 2
    assert evidence[-1].pose_valid is False and evidence[-1].pose_invalid_reason == "stale"
    assert all(o.evidence_sha256 is None for o in observations.values() if o.event.seq_id == 3)


def test_track_uses_c2_validity_rules(published):
    _, _, store = published
    points = [r.body for r in _bodies(store, Lane.TRACK)]
    # identity pose throughout: seq 0 emits; pose 1 / frame 2 / 3 too close in space and time;
    # frame 4 arrives after a 2.2 s gap -> stale -> no point (ends the segment).
    assert [(p.seq_id, p.packet, p.segment) for p in points] == [(0, "frame", 0)]


def test_live_row_reports_the_run_honestly(published):
    _, _, store = published
    snapshot, preview = store.get_live()
    assert snapshot["running"] is False and snapshot["source_mode"] == "REPLAY" and snapshot["run_id"] == "run-test"
    assert hashlib.sha256(preview).hexdigest() == snapshot["preview"]["sha256"]
    image = cv2.imdecode(np.frombuffer(preview, np.uint8), cv2.IMREAD_COLOR)
    assert image.shape[1] <= 640 and snapshot["preview"]["image_size"]["width"] == image.shape[1]
    assert all(snapshot["feeds_mono_ns"][f] for f in ("video", "results", "pose"))
    producers = {p["name"]: p["status"] for p in snapshot["capabilities"]["producers"]}
    assert producers["person_in_path"] == producers["walkway"] == "not_integrated"
    assert snapshot["pose"]["pose_valid"] is False and snapshot["pose"]["pose_invalid_reason"] == "stale"


# --- live server: a stalled store never stalls the frame path ---------------------------------

def test_stalled_store_never_blocks_server_detect(tmp_path, recording):
    from tests.test_server import _free_port, run as run_async
    edge_yaml = tmp_path / "edge.yaml"
    edge_yaml.write_text(yaml.safe_dump({"edge_id": "rover-test", "store_dir": str(tmp_path / "edge"),
                                         "writer": {"control_capacity": 1, "data_capacity": 1}}))
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "vision.server", "--detect", "--no-view", "--host", "127.0.0.1", "--port", str(port),
         "--run-dir", str(tmp_path / "run"), "--edge", "--edge-config", str(edge_yaml), "--source-mode", "REPLAY"],
        cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lock = None
    try:
        for line in proc.stdout:
            if "listening" in line:
                break
        lock = sqlite3.connect(tmp_path / "edge" / "rover-test" / "store.sqlite", isolation_level=None, timeout=10)
        lock.execute("BEGIN EXCLUSIVE")  # storage stalls: every writer transaction now waits
        run_async(replay(recording[:4], f"ws://127.0.0.1:{port}", speed=1.0))
        deadline = time.time() + 10
        detections = tmp_path / "run" / "detections.jsonl"
        while time.time() < deadline and len(detections.read_text().splitlines()) < 2:
            time.sleep(.05)
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=20) == 0
    finally:
        proc.kill()
        if lock is not None:
            lock.close()
    events = [json.loads(l) for l in (tmp_path / "run" / "detections.jsonl").read_text().splitlines()]
    assert len(events) >= 2  # C2 keeps flowing while the store is stalled
    summary = json.loads((tmp_path / "run" / "summary.json").read_text())
    edge = summary["edge"]
    assert sum(edge["dropped"].values()) > 0, "every record the stalled store could not take is counted"
    assert edge["observations"] < len(events)


def test_conflicting_source_mode_flags_are_rejected():
    proc = subprocess.run([sys.executable, "-m", "vision.server", "--detect", "--source-mode", "LIVE",
                           "--zones-source-mode", "SAMPLE"], cwd=REPO, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2 and "disagree" in proc.stderr
    proc = subprocess.run([sys.executable, "-m", "vision.server", "--edge"], cwd=REPO, capture_output=True,
                          text=True, timeout=60)
    assert proc.returncode == 2 and "--edge requires --detect" in proc.stderr
