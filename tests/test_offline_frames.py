"""Offline-frame demo acceptance: persistence, image receipts, reconnect and browser API."""
import asyncio
import hashlib
import json
import os
import time
from types import SimpleNamespace
from uuid import uuid4

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from bobapp.contracts import BlobStatusValue, Delivery, Lane, Record, SourceMode
from bobapp.edge.api.app import create_app
from bobapp.edge.config import load_edge_config
from bobapp.edge.publish import EdgePublisher
from bobapp.edge.store import EdgeStore, StoreError
from bobapp.hub.api import create_hub_app
from bobapp.hub.config import load_hub_config
from bobapp.hub.replica import Replica
from bobapp.hub.sync.fetcher import BlobFetcher
from tests.test_hub_sync import OBS, rig, wait_until, in_sync  # noqa: F401
from vision.config import load_config
from vision.schema import ImageSize


def detection(seq):
    event = OBS.event.model_copy(update={
        "event_id": uuid4(), "seq_id": seq, "boxes": [],
        "image_size": ImageSize(width=64, height=48), "jetson_receive_ts_ns": time.time_ns(),
        "iphone_frame_ts_ns": 1_000_000_000 + seq * 100_000_000,
    })
    return SimpleNamespace(event=event, image=np.full((48, 64, 3), seq % 256, np.uint8),
                           result=SimpleNamespace(verdicts=[], boxes=[]), verdicts={})


def publisher(store, config):
    pipeline = SimpleNamespace(model_id="test-model", names={}, rules=[], inactive_rules=[])
    return EdgePublisher(store, config, source_mode="LIVE", run_id="offline-test", pipeline=pipeline,
                         render_config=load_config()["render"], stale_ms=250, zones_enabled=False, blocking=True)


def archive(store, seq):
    d = detection(seq)
    ok, data = cv2.imencode('.jpg', d.image)
    assert ok
    sha = store.put_blob(data.tobytes())
    obs = OBS.model_copy(update={"event": d.event, "evidence_sha256": sha, "scene": None})
    return store.append(obs, SourceMode.LIVE), sha


def test_every_processed_frame_is_saved_even_without_ppe_and_survives_restart(tmp_path):
    path = tmp_path / "edge"
    store = EdgeStore(path, "test")
    p = publisher(store, load_edge_config())
    inputs = [detection(i) for i in range(6)]
    for d in inputs:
        p.on_detection(d)
    stats = p.close(timeout=10)
    assert stats["write_errors"] == 0, stats
    assert stats["archived_frames"] == 6 and stats["archive_skipped"] == 0
    epoch = store.store_epoch
    store.close()
    restored = EdgeStore(path, "test")
    assert restored.store_epoch == epoch
    rows = [Record.model_validate_json(r.json) for r in restored.read(Lane.OBSERVATION, 0)]
    assert len(rows) == 6
    for row, d in zip(rows, inputs):
        body = row.body
        assert body.event == d.event and body.image_pixels_sha256 == hashlib.sha256(d.image.tobytes()).hexdigest()
        assert restored.has_blob(body.evidence_sha256)
        data = restored.blob_file(body.evidence_sha256).read_bytes()
        assert hashlib.sha256(data).hexdigest() == body.evidence_sha256
        assert cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR).shape == d.image.shape
    restored.close()


def test_opening_edge_api_store_does_not_delete_active_writer_temp_file(tmp_path):
    writer = EdgeStore(tmp_path, "test")
    active = writer.blob_dir / f"in-progress.{os.getpid()}.tmp"
    active.write_bytes(b"JPEG write in progress")
    reader = EdgeStore(tmp_path, "test")
    assert active.read_bytes() == b"JPEG write in progress"
    reader.close()
    writer.close()


def test_full_archive_reports_unsaved_frames_and_retains_old_pending_image(tmp_path):
    store = EdgeStore(tmp_path, "test")
    old, sha = archive(store, 0)
    config = load_edge_config()
    config["retention"]["max_store_bytes"] = 1
    p = publisher(store, config)
    p.on_detection(detection(1))
    stats = p.close(10)
    assert stats["archive_skipped"] == 1 and stats["archived_frames"] == 0
    assert store.has_blob(sha)
    rows = [Record.model_validate_json(r.json) for r in store.read(Lane.OBSERVATION, 0)]
    assert any(r.seq == old.seq for r in rows)
    notices = [json.loads(r.json)["body"].get("code") for r in store.read(Lane.CONTROL, 0)]
    assert "frame_archive_full" in notices


def test_shared_blob_protected_until_every_hub_has_image_and_every_reference_expires(tmp_path):
    s = EdgeStore(tmp_path, "test")
    first, sha = archive(s, 0)
    second = s.append(first.body, SourceMode.LIVE)
    now = time.time_ns() + 10**9
    for hub in ("a", "b"):
        s.ack(hub, Lane.OBSERVATION, second.seq)
    s.ack_blob("a", s.store_epoch, sha)
    assert s.prune(0, 1 << 40, 0, now)["retention"] == 0
    s.ack_blob("b", s.store_epoch, sha)
    with pytest.raises(StoreError):
        s.ack_blob("b", uuid4(), sha)
    assert s.prune(0, 1 << 40, 0, now)["retention"] == 2
    assert not s.has_blob(sha)
    s.ack_blob("a", s.store_epoch, sha)  # receipt retry after retention is idempotent


def test_pruning_gaps_do_not_include_protected_frame_records(tmp_path):
    s = EdgeStore(tmp_path, "test")
    bare = OBS.model_copy(update={"evidence_sha256": None})
    s.append(bare, SourceMode.LIVE)
    archived, sha = archive(s, 1)
    s.append(bare, SourceMode.LIVE)
    s.prune(1e9, 0, 0)
    assert [r.seq for r in s.read(Lane.OBSERVATION, 0)] == [archived.seq]
    assert s.has_blob(sha)
    gaps = [json.loads(r.json)["body"] for r in s.read(Lane.CONTROL, 0)]
    assert [(g["first_seq"], g["last_seq"]) for g in gaps] == [(1, 1), (3, 3)]


def test_link_cut_restores_all_images_with_original_frames_and_no_duplicates(rig):  # noqa: F811
    s, r, proxy = rig["store"], rig["replica"], rig["proxy"]
    initial, initial_sha = archive(s, 0)
    wait_until(lambda: r.blob_status(initial_sha) == BlobStatusValue.AVAILABLE)
    proxy.cut()
    wait_until(lambda: r.get_link()["state"] == "DISCONNECTED", 5)
    saved = [archive(s, seq) for seq in range(1, 9)]
    assert all(s.has_blob(sha) for _, sha in saved)
    assert not in_sync(s, r)()
    # A long outage may trigger retention; metadata acks cannot delete pending JPEGs.
    s.prune(0, 1, 0, time.time_ns() + 10**9)
    assert all(s.has_blob(sha) for _, sha in saved)
    started = time.monotonic()
    proxy.restore()
    wait_until(lambda: all(r.blob_status(sha) == BlobStatusValue.AVAILABLE for _, sha in saved), 15,
               "all disconnected frames downloaded")
    elapsed = time.monotonic() - started
    ws = r.active_workspace()
    rows = [Record.model_validate_json(text) for _, delivery, text in r.records(ws, kind="observation")
            if delivery == "backfilled"]
    assert {rec.body.event.event_id for rec, _ in saved} <= {rec.body.event.event_id for rec in rows}
    for rec, sha in saved:
        assert r.blob_file(sha).read_bytes() == s.blob_file(sha).read_bytes()
    wait_until(lambda: len(s.db.execute("SELECT * FROM blob_acks").fetchall()) >= len(saved))
    count = r.counts(ws)["observation"]
    proxy.cut()
    wait_until(lambda: r.get_link()["state"] == "DISCONNECTED", 5)
    proxy.restore()
    wait_until(lambda: r.get_link()["state"] == "CONNECTED", 10)
    assert r.counts(ws)["observation"] == count == 9
    print(f"Recovered {len(saved)} JPEGs in {elapsed:.2f}s after link restore; no duplicate observations")


def test_replica_restarts_with_pending_downloads_and_receipts(tmp_path):
    edge = EdgeStore(tmp_path / "edge", "test")
    rec, sha = archive(edge, 1)
    path = tmp_path / "hub"
    r = Replica(path)
    ws, _ = r.adopt(edge.edge_id, edge.store_epoch)
    r.commit(ws, Lane.OBSERVATION, [rec], Delivery.BACKFILLED)
    r.close()
    r = Replica(path)
    assert sha in r.pending_blobs()
    assert r.pending_receipts(ws) == []
    r.store_blob(sha, edge.blob_file(sha).read_bytes())
    r.close()
    r = Replica(path)
    assert sha not in r.pending_blobs() and r.pending_receipts(ws) == [sha]
    assert r.commit(ws, Lane.OBSERVATION, [rec], Delivery.BACKFILLED).inserted == 0
    r.acknowledge_blob(ws, sha)
    assert r.pending_receipts(ws) == []


def test_corrupt_or_interrupted_image_never_gets_receipt(tmp_path, monkeypatch):
    import bobapp.hub.sync.fetcher as module
    edge = EdgeStore(tmp_path / "edge", "test")
    rec, sha = archive(edge, 1)
    r = Replica(tmp_path / "hub")
    ws, _ = r.adopt(edge.edge_id, edge.store_epoch)
    r.commit(ws, Lane.OBSERVATION, [rec], Delivery.BACKFILLED)
    f = BlobFetcher(r, "http://unused", None, load_hub_config())
    f.workspace = ws
    monkeypatch.setattr(module, "http_get", lambda *_: (b"partial", {}))
    assert asyncio.run(f.fetch(sha)) == BlobStatusValue.HASH_MISMATCH
    assert r.pending_receipts(ws) == [] and not r.blob_file(sha).exists()
    assert sha in r.pending_blobs(retry_after_ns=0)
    from http.client import IncompleteRead
    def interrupted(*args):
        raise IncompleteRead(b'first bytes', 100)
    monkeypatch.setattr(module, "http_get", interrupted)
    assert asyncio.run(f.fetch(sha)) == BlobStatusValue.PENDING_SYNC
    assert r.pending_receipts(ws) == []
    monkeypatch.setattr(module, "http_get", lambda *_: (edge.blob_file(sha).read_bytes(), {}))
    assert asyncio.run(f.fetch(sha)) == BlobStatusValue.AVAILABLE
    assert r.pending_receipts(ws) == [sha]


def test_receipt_requires_authentication_and_correct_epoch(tmp_path):
    s = EdgeStore(tmp_path, "test")
    _, sha = archive(s, 0)
    client = TestClient(create_app(tmp_path, "test", load_edge_config(), "test-token"))
    url = f"/v1/blobs/{sha}/ack"
    payload = {"hub_id": "h", "store_epoch": str(s.store_epoch)}
    assert client.post(url, json=payload).status_code == 401
    auth = {"Authorization": "Bearer test-token"}
    assert client.post(url, json={**payload, "store_epoch": str(uuid4())}, headers=auth).status_code == 409
    assert client.post(url, json=payload, headers=auth).status_code == 200


def test_frame_gallery_pages_status_source_and_sample_separation(tmp_path):
    s = EdgeStore(tmp_path / "edge", "test")
    r = Replica(tmp_path / "hub")
    ws, _ = r.adopt(s.edge_id, s.store_epoch)
    saved = [archive(s, seq) for seq in range(4)]
    r.commit(ws, Lane.OBSERVATION, [rec for rec, _ in saved], Delivery.BACKFILLED)
    sha = saved[0][1]
    r.store_blob(sha, s.blob_file(sha).read_bytes())
    app = create_hub_app(load_hub_config(), None, {"rover": tmp_path / "hub", "sample": tmp_path / "sample"})
    with TestClient(app) as client:
        page = client.get('/v1/frames?delivery=backfilled&limit=2').json()
        assert [i['record']['body']['event']['seq_id'] for i in page['items']] == [2, 3]
        older = client.get(f"/v1/frames?before={page['items'][0]['cursor']}").json()
        assert [i['record']['body']['event']['seq_id'] for i in older['items']] == [0, 1]
        assert older['items'][0]['image_status'] == 'available'
        assert older['items'][1]['image_status'] == 'pending_sync'
        counts = client.get('/v1/status').json()['frames']
        assert counts['total'] == 4 and counts['pending_sync'] == 3 and counts['backfilled'] == 4
        assert client.get('/v1/frames?workspace=sample').json()['items'] == []
        assert client.get('/v1/frames?delivery=realtime').json()['items'] == []
        assert client.get(f'/v1/evidence/{sha}').content == s.blob_file(sha).read_bytes()
