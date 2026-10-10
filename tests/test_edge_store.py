"""Dashboard Step 2: edge store + bounded writer — restart continuity, crash safety, full disk,
blocked writer, retention and disk-pressure pruning with explicit gaps."""

import json
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from bobapp.contracts import Lane, Record, SourceMode
from bobapp.edge.store import EdgeStore, StoreError
from bobapp.edge.writer import EdgeWriter

FIXTURES = Path(__file__).parent / "fixtures" / "app" / "valid"
REPO = Path(__file__).resolve().parent.parent


def body(name):
    return Record.model_validate_json((FIXTURES / f"record_{name}.json").read_text()).body


OBS, TRACK, EVIDENCE, NOTICE = (body("observation_live"), body("track_point"), body("evidence"),
                                body("notice_assessment_unavailable"))
LIVE = SourceMode.LIVE


@pytest.fixture
def store(tmp_path):
    s = EdgeStore(tmp_path / "edge", "rover-test")
    yield s
    s.close()


def test_epoch_is_stable_per_store_and_new_for_a_new_store(tmp_path):
    a = EdgeStore(tmp_path / "a", "rover-test")
    epoch = a.store_epoch
    a.close()
    assert EdgeStore(tmp_path / "a", "rover-test").store_epoch == epoch
    assert EdgeStore(tmp_path / "b", "rover-test").store_epoch != epoch
    with pytest.raises(StoreError, match="belongs to edge"):
        EdgeStore(tmp_path / "a", "another-rover")


def test_bodies_go_to_their_lane_with_per_lane_seq(store):
    records = [store.append(b, LIVE, "run-1") for b in (OBS, TRACK, NOTICE, OBS, NOTICE)]
    assert [(r.lane, r.seq) for r in records] == [
        (Lane.OBSERVATION, 1), (Lane.TRACK, 1), (Lane.CONTROL, 1), (Lane.OBSERVATION, 2), (Lane.CONTROL, 2)]
    assert all(r.store_epoch == store.store_epoch and r.edge_id == "rover-test" for r in records)
    raw = store.read(Lane.OBSERVATION, 0)
    assert [r.seq for r in raw] == [1, 2] and Record.model_validate_json(raw[0].json) == records[0]
    assert store.read(Lane.OBSERVATION, 1, limit=10)[0].seq == 2


def test_restart_never_reuses_a_seq_even_after_the_lane_was_pruned_empty(tmp_path):
    s = EdgeStore(tmp_path / "edge", "rover-test")
    for _ in range(3):
        s.append(OBS, LIVE)
    s.ack("hub", Lane.OBSERVATION, 3)
    assert s.prune(acked_max_age_s=0, max_store_bytes=1 << 40, min_free_disk_bytes=0,
                   now_wall_ns=time.time_ns() + 1)["retention"] == 3
    assert s.lane_info()[Lane.OBSERVATION].oldest_seq is None
    s.close()
    s = EdgeStore(tmp_path / "edge", "rover-test")
    assert s.append(OBS, LIVE).seq == 4
    assert s.lane_info()[Lane.OBSERVATION].head_seq == 4


CRASH = """
import os, sys
from pathlib import Path
from bobapp.contracts import Record, SourceMode
from bobapp.edge.store import EdgeStore
s = EdgeStore(Path(sys.argv[1]), "rover-test")
body = Record.model_validate_json(Path(sys.argv[2]).read_text()).body
s.append(body, SourceMode.LIVE)
s.db.execute("BEGIN IMMEDIATE")
s.append_in_tx(body, SourceMode.LIVE)                 # written but never committed
(s.blob_dir / "ab").mkdir(exist_ok=True)
(s.blob_dir / "ab" / "half-written.123.tmp").write_bytes(b"partial")
os._exit(1)                                           # crash: no commit, no cleanup
"""


def test_crash_mid_write_leaves_no_partial_record_or_blob(tmp_path):
    path = tmp_path / "edge"
    proc = subprocess.run([sys.executable, "-c", CRASH, str(path), str(FIXTURES / "record_observation_live.json")],
                          cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 1, proc.stderr
    s = EdgeStore(path, "rover-test")
    assert [r.seq for r in s.read(Lane.OBSERVATION, 0)] == [1]
    assert s.lane_info()[Lane.OBSERVATION].head_seq == 1
    assert s.append(OBS, LIVE).seq == 2
    assert not list(s.blob_dir.glob("**/*.tmp"))


def test_blobs_are_content_addressed_and_written_atomically(store):
    sha = store.put_blob(b"\xff\xd8 jpeg bytes")
    assert store.has_blob(sha) and store.blob_file(sha).read_bytes() == b"\xff\xd8 jpeg bytes"
    assert store.put_blob(b"\xff\xd8 jpeg bytes") == sha
    assert not store.has_blob("0" * 64)


def test_acks_only_move_forward_and_never_past_the_head(store):
    for _ in range(3):
        store.append(NOTICE, LIVE)
    store.ack("hub", Lane.CONTROL, 3)
    store.ack("hub", Lane.CONTROL, 1)  # a replayed old ack
    assert store.acked_seq(Lane.CONTROL) == 3
    with pytest.raises(StoreError, match="beyond head"):
        store.ack("hub", Lane.CONTROL, 4)


def test_retention_prunes_only_acknowledged_old_records_and_their_blobs(store):
    sha = store.put_blob(b"evidence")
    evidence = EVIDENCE.model_copy(update={"sha256": sha})
    store.append(evidence, LIVE)
    store.append(NOTICE, LIVE)
    later = time.time_ns() + 10**9
    assert store.prune(0, 1 << 40, 0, now_wall_ns=later)["retention"] == 0      # nothing acknowledged
    store.ack("hub", Lane.CONTROL, 1)
    assert store.prune(3600, 1 << 40, 0, now_wall_ns=later)["retention"] == 0   # acknowledged but young
    assert store.prune(0, 1 << 40, 0, now_wall_ns=later)["retention"] == 1
    assert [r.seq for r in store.read(Lane.CONTROL, 0)] == [2]
    assert not store.has_blob(sha) and not store.blob_file(sha).exists()


def test_disk_pressure_prunes_observations_first_with_an_explicit_gap(store):
    for _ in range(5):
        store.append(OBS, LIVE)
    store.append(TRACK, LIVE)
    store.append(NOTICE, LIVE)
    store.ack("hub", Lane.OBSERVATION, 2)
    removed = store.prune(acked_max_age_s=1e9, max_store_bytes=0, min_free_disk_bytes=0)
    assert removed["pressure"] == 6
    assert store.read(Lane.OBSERVATION, 0) == [] and store.read(Lane.TRACK, 0) == []
    control = [Record.model_validate_json(r.json).body for r in store.read(Lane.CONTROL, 0)]
    gaps = [b for b in control if b.kind == "gap"]
    assert control[0].kind == "notice"  # control records are never pruned unacknowledged
    assert [(g.lane, g.first_seq, g.last_seq, g.reason.value) for g in gaps] == [
        (Lane.OBSERVATION, 3, 5, "pruned_disk_pressure"), (Lane.TRACK, 1, 1, "pruned_disk_pressure")]


def test_blocked_writer_never_blocks_the_caller_and_counts_every_drop(store):
    release = threading.Event()
    writer = EdgeWriter(store, LIVE, "run-1", control_capacity=2, data_capacity=3)
    writer.submit_data(lambda s: release.wait(5))   # storage stalls on the first item
    time.sleep(.1)
    start = time.perf_counter()
    accepted = [writer.submit_data(lambda s: s.append(OBS, LIVE)) for _ in range(20)]
    elapsed = time.perf_counter() - start
    assert elapsed < .05, "submit must never wait for storage"
    assert accepted.count(True) == 3 and writer.stats()["dropped"]["data"] == 17
    release.set()
    deadline = time.time() + 3
    while time.time() < deadline and not store.read(Lane.CONTROL, 0):
        time.sleep(.02)
    stats = writer.close()
    assert len(store.read(Lane.OBSERVATION, 0)) == 3
    notice = Record.model_validate_json(store.read(Lane.CONTROL, 0)[0].json).body
    assert notice.code == "writer_dropped" and notice.details["dropped_since_last_notice"] == {"control": 0, "data": 17}
    assert stats["dropped"] == {"control": 0, "data": 17} and stats["write_errors"] == 0


def test_control_items_go_before_queued_data(store):
    release = threading.Event()
    writer = EdgeWriter(store, LIVE)
    writer.submit_data(lambda s: release.wait(5))
    time.sleep(.05)
    writer.submit_data(lambda s: s.append(OBS, LIVE))
    writer.submit_control(lambda s: s.append(NOTICE, LIVE))
    release.set()
    writer.close()
    obs, notice = store.read(Lane.OBSERVATION, 0)[0], store.read(Lane.CONTROL, 0)[0]
    assert json.loads(notice.json)["rover"]["mono_ns"] < json.loads(obs.json)["rover"]["mono_ns"]


def test_full_disk_is_a_visible_error_never_an_exception_upstream(store, monkeypatch):
    def full(*_a, **_k):
        raise sqlite3.OperationalError("database or disk is full")
    monkeypatch.setattr(store, "append", full)
    writer = EdgeWriter(store, LIVE)
    for _ in range(5):
        writer.submit_data(lambda s: s.append(OBS, LIVE))
    stats = writer.close()
    assert stats["write_errors"] == 5 and "disk is full" in stats["last_error"] and stats["written"] == 0


def test_closed_writer_refuses_work(store):
    writer = EdgeWriter(store, LIVE)
    writer.close()
    with pytest.raises(RuntimeError, match="closed"):
        writer.submit_data(lambda s: None)
