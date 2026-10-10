"""Dashboard Step 5: hub sync client + replica over a real edge API and a cuttable TCP proxy.

Gates (plan Step 5): after a timed link cut the replica equals the edge store record-for-record,
counts are not inflated, records written during the cut arrive labeled backfilled, gaps appear when
the rover prunes before sync, a new rover store epoch is detected and the old replica kept apart,
evidence is prefetched and hash-verified, and every acknowledgment follows a commit.
"""

import asyncio
import hashlib
import shutil
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from bobapp.contracts import BlobStatusValue, Delivery, Lane, Record, SourceMode
from bobapp.edge.api.app import create_app
from bobapp.edge.config import load_edge_config
from bobapp.edge.store import EdgeStore
from bobapp.hub.config import load_hub_config
from bobapp.hub.replica import Replica
from bobapp.hub.sync import HubSyncClient

FIXTURES = Path(__file__).parent / "fixtures" / "app" / "valid"
TOKEN = "hub-test-token"
LIVE = SourceMode.LIVE


def body(name):
    return Record.model_validate_json((FIXTURES / f"record_{name}.json").read_text()).body


OBS, TRACK, NOTICE, EVIDENCE = (body("observation_live"), body("track_point"), body("notice_assessment_unavailable"),
                                body("evidence"))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_until(predicate, timeout=15.0, what="condition"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


class Proxy:
    """TCP relay that can cut every connection and refuse new ones for a while."""

    def __init__(self, target_port):
        self.target_port, self.port, self.down = target_port, free_port(), False
        self.conns, self.loop = set(), None
        ready = threading.Event()
        threading.Thread(target=self._main, args=(ready,), daemon=True).start()
        ready.wait(5)

    def _main(self, ready):
        async def main():
            self.loop = asyncio.get_running_loop()
            await asyncio.start_server(self._handle, "127.0.0.1", self.port)
            ready.set()
            await asyncio.Event().wait()
        asyncio.run(main())

    async def _handle(self, reader, writer):
        if self.down:
            writer.close()
            return
        try:
            up_reader, up_writer = await asyncio.open_connection("127.0.0.1", self.target_port)
        except OSError:
            writer.close()
            return
        self.conns |= {writer, up_writer}

        async def pipe(src, dst):
            try:
                while data := await src.read(65536):
                    dst.write(data)
                    await dst.drain()
            except (OSError, ConnectionError):
                pass
            finally:
                dst.close()
        await asyncio.gather(pipe(reader, up_writer), pipe(up_reader, writer))

    def cut(self):
        def go():
            self.down = True
            for w in list(self.conns):
                w.transport.abort()
            self.conns.clear()
        self.loop.call_soon_threadsafe(go)

    def restore(self):
        self.down = False


class EdgeServer:
    def __init__(self, store_path, config, port):
        app = create_app(store_path, "rover-test", config, TOKEN)
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error",
                                                    ws="websockets-sansio"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        wait_until(lambda: self.server.started, 10, "edge API start")

    def stop(self):
        self.server.should_exit = True
        self.thread.join(10)


class Hub:
    def __init__(self, path, config, port):
        self.replica = Replica(path)
        self.client = HubSyncClient(self.replica, config, TOKEN, f"ws://127.0.0.1:{port}", f"http://127.0.0.1:{port}")
        self.states, self.loop, self.stop_event = [], None, None
        self.thread = threading.Thread(target=self._main, daemon=True)
        self.thread.start()
        wait_until(lambda: self.loop is not None, 5, "hub loop")

    def _main(self):
        async def main():
            self.loop, self.stop_event = asyncio.get_running_loop(), asyncio.Event()
            watch = asyncio.create_task(self._watch())
            await self.client.run(self.stop_event)
            watch.cancel()
        asyncio.run(main())

    async def _watch(self):
        while True:
            state = self.client.link.state["state"]
            if not self.states or self.states[-1] != state:
                self.states.append(state)
            await asyncio.sleep(0.02)

    def stop(self):
        self.loop.call_soon_threadsafe(self.stop_event.set)
        self.thread.join(10)


@pytest.fixture
def rig(tmp_path):
    edge_config = load_edge_config()
    edge_config["sync"] = {"batch_records": 25, "max_bytes_per_s": 20_000_000, "live_interval_s": 0.1}
    hub_config = load_hub_config()
    hub_config["link"] = {"reconnect_min_s": 0.1, "reconnect_max_s": 0.4, "stale_after_s": 1.0}
    hub_config["blobs"] = {"max_bytes_per_s": 50_000_000, "retry_s": 0.2}
    store = EdgeStore(tmp_path / "edge", "rover-test")
    edge_port = free_port()
    edge = EdgeServer(tmp_path / "edge", edge_config, edge_port)
    proxy = Proxy(edge_port)
    hub = Hub(tmp_path / "hub", hub_config, proxy.port)
    reader = Replica(tmp_path / "hub")
    yield {"store": store, "edge": edge, "proxy": proxy, "hub": hub, "replica": reader, "tmp": tmp_path,
           "edge_config": edge_config, "edge_port": edge_port}
    hub.stop()
    edge.stop()


def edge_records(store):
    return {(lane, r.seq): r.json for lane in Lane for r in store.read(lane, 0, limit=100_000)}


def replica_records(replica):
    ws = replica.active_workspace()
    return {(Record.model_validate_json(j).lane, Record.model_validate_json(j).seq): j
            for _, _, j in replica.records(ws, limit=100_000)} if ws else {}


def in_sync(store, replica):
    return lambda: edge_records(store).keys() == replica_records(replica).keys()


def write(store, n_obs, n_track=0, n_notice=0):
    for i in range(max(n_obs, n_track, n_notice)):
        if i < n_obs:
            store.append(OBS, LIVE)
        if i < n_track:
            store.append(TRACK, LIVE)
        if i < n_notice:
            store.append(NOTICE, LIVE)


def test_link_cut_resyncs_record_for_record_without_duplicates(rig):
    store, replica, proxy, hub = rig["store"], rig["replica"], rig["proxy"], rig["hub"]
    write(store, 60, 20, 10)
    wait_until(in_sync(store, replica), what="initial sync")
    assert replica.get_link()["state"] == "CONNECTED"
    proxy.cut()
    wait_until(lambda: replica.get_link()["state"] == "DISCONNECTED", 5, "DISCONNECTED")
    write(store, 120, 30, 15)  # the rover keeps working while the laptop is away
    time.sleep(0.5)
    proxy.restore()
    wait_until(in_sync(store, replica), what="resync after the cut")
    wait_until(lambda: replica.get_link()["state"] == "CONNECTED", 5, "CONNECTED")
    assert replica_records(replica) == edge_records(store)  # byte-identical, record for record
    ws = replica.active_workspace()
    assert sum(replica.counts(ws).values()) == len(edge_records(store)) == 255
    assert {"CONNECTED", "DISCONNECTED"} <= set(hub.states) and hub.client.sessions >= 2
    deliveries = {Record.model_validate_json(j).seq: d for _, d, j in replica.records(ws, lane=Lane.OBSERVATION, limit=1000)}
    assert all(deliveries[s] == Delivery.BACKFILLED.value for s in range(61, 181))  # written during the cut
    wait_until(lambda: all(store.acked_seq(lane) == replica.cursors(ws)[lane] for lane in Lane), 5, "acks")


def test_replays_never_inflate_the_replica(tmp_path):
    replica = Replica(tmp_path / "hub")
    store = EdgeStore(tmp_path / "edge", "rover-test")
    records = [store.append(NOTICE, LIVE) for _ in range(5)]
    ws, changed = replica.adopt("rover-test", store.store_epoch)
    first = replica.commit(ws, Lane.CONTROL, records, Delivery.REALTIME)
    again = replica.commit(ws, Lane.CONTROL, records[2:], Delivery.BACKFILLED)
    assert (first.inserted, first.committed_seq, again.inserted, again.committed_seq) == (5, 5, 0, 5)
    assert replica.counts(ws) == {"control": 5}
    other = EdgeStore(tmp_path / "other", "rover-test").append(NOTICE, LIVE)
    with pytest.raises(ValueError, match="never merged"):
        replica.commit(ws, Lane.CONTROL, [other], Delivery.REALTIME)


def test_rover_pruning_before_sync_shows_explicit_gaps(rig):
    store, replica, proxy = rig["store"], rig["replica"], rig["proxy"]
    write(store, 10)
    wait_until(in_sync(store, replica), what="initial sync")
    proxy.cut()
    wait_until(lambda: replica.get_link()["state"] == "DISCONNECTED", 5, "DISCONNECTED")
    write(store, 30)                                            # observations 11..40, never seen by the hub
    store.prune(acked_max_age_s=1e9, max_store_bytes=0, min_free_disk_bytes=0)  # disk pressure on the rover
    write(store, 5)                                             # 41..45 after the pruning
    proxy.restore()
    ws = replica.active_workspace()
    wait_until(lambda: replica.cursors(ws)[Lane.OBSERVATION] == 45, what="observation cursor past the gap")
    gaps = replica.gaps(ws)
    assert [(g["lane"], g["first_seq"], g["last_seq"]) for g in gaps] == [("observation", 11, 40)]
    rover_gap = [Record.model_validate_json(j).body for _, _, j in replica.records(ws, kind="gap")]
    assert [(g.first_seq, g.last_seq, g.reason.value) for g in rover_gap] == [(11, 40, "pruned_disk_pressure")]
    seqs = sorted(Record.model_validate_json(j).seq for _, _, j in replica.records(ws, lane=Lane.OBSERVATION))
    assert seqs == list(range(1, 11)) + list(range(41, 46))


def test_new_rover_store_epoch_is_detected_and_never_merged(rig):
    store, replica, edge, tmp = rig["store"], rig["replica"], rig["edge"], rig["tmp"]
    write(store, 8, n_notice=2)
    wait_until(in_sync(store, replica), what="initial sync")
    old_ws, old_epoch = replica.active_workspace(), store.store_epoch
    edge.stop()
    store.close()
    shutil.rmtree(tmp / "edge")                                 # rover store wiped and recreated
    fresh = EdgeStore(tmp / "edge", "rover-test")
    write(fresh, 3)
    rig["edge"] = EdgeServer(tmp / "edge", rig["edge_config"], rig["edge_port"])
    wait_until(lambda: replica.active_workspace() and replica.active_workspace().store_epoch == fresh.store_epoch,
               what="new workspace")
    wait_until(in_sync(fresh, replica), what="new store synced")
    assert "NEW_STORE" in rig["hub"].states or replica.get_link()["new_store_at_wall_ns"]
    archived = [w for w in replica.workspaces() if w.store_epoch == old_epoch]
    assert archived and archived[0].archived and replica.counts(old_ws) == {"observation": 8, "control": 2}
    assert replica.counts(replica.active_workspace()) == {"observation": 3}


def test_evidence_is_prefetched_and_hash_verified(rig):
    store, replica = rig["store"], rig["replica"]
    good = store.put_blob(b"\xff\xd8 evidence one")
    store.append(EVIDENCE.model_copy(update={"sha256": good}), LIVE)
    gone = store.put_blob(b"\xff\xd8 evidence two")
    store.append(EVIDENCE.model_copy(update={"sha256": gone}), LIVE)
    store.blob_file(gone).unlink()                              # e.g. lost on the rover before sync
    wait_until(lambda: replica.blob_status(good) == BlobStatusValue.AVAILABLE, what="evidence fetched")
    wait_until(lambda: replica.blob_status(gone) == BlobStatusValue.MISSING, what="missing evidence marked")
    assert hashlib.sha256(replica.blob_file(good).read_bytes()).hexdigest() == good
    ws = replica.active_workspace()
    assert len(replica.records(ws, kind="evidence")) == 2       # metadata stays visible either way


def test_hash_mismatch_is_never_stored_as_evidence(tmp_path):
    replica = Replica(tmp_path / "hub")
    sha = hashlib.sha256(b"real").hexdigest()
    replica.db.execute("INSERT INTO blobs (sha256, status, updated_wall_ns) VALUES (?, 'pending_sync', 0)", (sha,))
    assert replica.store_blob(sha, b"tampered") == BlobStatusValue.HASH_MISMATCH
    assert not replica.blob_file(sha).exists() and replica.blob_status(sha) == BlobStatusValue.HASH_MISMATCH


def test_live_state_and_preview_follow_the_rover(rig):
    store, replica = rig["store"], rig["replica"]
    jpeg = b"\xff\xd8 preview bytes"
    snapshot = {"running": True, "run_id": "run-1", "source_mode": "REPLAY",
                "feeds_mono_ns": {"video": time.monotonic_ns(), "results": None, "pose": None, "health": None},
                "pose": None, "health": None,
                "preview": {"event_id": str(OBS.event.event_id), "session_id": str(OBS.event.session_id), "seq_id": 1,
                            "image_size": {"width": 64, "height": 48}, "source_image_size": {"width": 480, "height": 640},
                            "sha256": hashlib.sha256(jpeg).hexdigest()},
                "capabilities": {"model_id": "m", "rules": [], "producers": []}, "edge": None}
    store.put_live(snapshot, jpeg, snapshot["preview"]["sha256"])
    wait_until(lambda: replica.get_live()[3] == snapshot["preview"]["sha256"], what="preview copied")
    live_json, rx, preview, _ = replica.get_live()
    assert preview == jpeg and '"source_mode":"REPLAY"' in live_json and rx > 0
