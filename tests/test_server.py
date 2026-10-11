"""Step 5: WebSocket transport — latest-frame-wins, stream health, record/replay, kill tests.

Everything runs against a real server on localhost driven by tools/replay_client (never a live phone).
"""

import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from tools.replay_client import Record, load, replay
from vision.config import REPO_ROOT, load_config
from vision.recording import iter_records, write_record
from vision.schema import SCHEMA_VERSION, FramePacket, PosePacket, decode, encode
from vision.server import FrameServer, LatestSlot, ReceivedFrame, ServerThread, StreamMonitor, upright_view

CONFIG = load_config()
GOLDEN = Path(__file__).parent / "fixtures" / "recordings" / "swift_golden.bobrec"
IDENTITY = np.eye(4).reshape(-1).tolist()
_JPEG = cv2.imencode(".jpg", np.full((48, 64, 3), 120, np.uint8))[1].tobytes()
MS = 1_000_000


def frame(session, seq, ts_ns, payload=_JPEG):
    msg = FramePacket(
        schema_version=SCHEMA_VERSION, msg_type="frame", session_id=session, seq_id=seq,
        iphone_frame_ts_ns=ts_ns, tracking_state="normal", camera_transform=IDENTITY,
        image={"width": 64, "height": 48, "encoding": "jpeg", "device_orientation": "portrait",
               "byte_length": len(payload)},
    )
    return Record(msg, payload, encode(msg, payload))


def pose(session, seq, ts_ns):
    msg = PosePacket(
        schema_version=SCHEMA_VERSION, msg_type="pose", session_id=session, seq_id=seq,
        iphone_frame_ts_ns=ts_ns, tracking_state="normal", camera_transform=IDENTITY,
    )
    return Record(msg, b"", encode(msg))


def stream(n_frames, hz=10.0, session=None, poses=True):
    """Phone-like stream: frame, pose, frame, ... at `hz` frames/s, shared seq counter."""
    session, out, seq = session or uuid4(), [], 0
    for i in range(n_frames):
        ts = 1_000_000_000 + int(i * 1e9 / hz)
        out.append(frame(session, seq, ts))
        seq += 1
        if poses:
            out.append(pose(session, seq, ts + int(0.5e9 / hz)))
            seq += 1
    return out


def wait_for(pred, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.005)
    return pred()


@pytest.fixture
def server():
    srv = FrameServer(CONFIG)
    thread = ServerThread(srv, "127.0.0.1", 0)
    port = thread.start()
    srv.uri = f"ws://127.0.0.1:{port}"
    yield srv
    thread.stop()


def run(coro):
    return asyncio.run(coro)


# --- LatestSlot ------------------------------------------------------------------------------

def test_slot_keeps_only_latest_and_reports_drop():
    slot = LatestSlot()
    assert slot.put(1) is False
    assert slot.put(2) is True  # 1 was never taken -> dropped
    assert slot.take(0) == 2 and slot.take(0) is None


def test_slot_take_wakes_on_put():
    slot = LatestSlot()
    threading.Timer(0.05, slot.put, args=("x",)).start()
    assert slot.take(timeout=2.0) == "x"


# --- StreamMonitor (fake clock, deterministic) ------------------------------------------------

def test_monitor_counts_gaps_and_drops_out_of_order():
    m, s = StreamMonitor(stale_ms=250), uuid4()
    assert m.accept(frame(s, 0, 0).msg, 0) == (True, True)
    assert m.accept(frame(s, 3, 1).msg, 1) == (True, False)    # seq 1, 2 skipped by the phone
    assert m.accept(pose(s, 2, 2).msg, 2) == (False, False)    # older than seq 3 -> dropped
    st = m.stats(2)
    assert (st.frames, st.poses, st.seq_gaps, st.out_of_order) == (2, 0, 2, 1)
    assert m.health(2).dropped_count == 2


def test_new_session_resets_and_retires_previous():
    m, a, b = StreamMonitor(stale_ms=250), uuid4(), uuid4()
    m.accept(frame(a, 0, 0).msg, 0)
    m.accept(frame(a, 5, 0).msg, 0)
    assert m.accept(frame(b, 0, 0).msg, 1) == (True, True)
    assert m.stats(1).seq_gaps == 0 and m.stats(1).frames == 1
    assert m.accept(frame(a, 6, 0).msg, 2) == (False, False)   # late message from the old origin
    assert m.stats(2).retired_drops == 1 and m.health(2).session_id == b


def test_health_stale_boundary_and_no_session():
    m, s = StreamMonitor(stale_ms=250), uuid4()
    h = m.health(0)
    assert h.stale and h.session_id is None and h.dropped_count == 0
    m.accept(pose(s, 0, 0).msg, 1000 * MS)
    assert not m.health(1250 * MS).stale
    assert m.health(1251 * MS).stale
    assert m.health(1251 * MS).tracking_state.value == "normal"


def test_added_latency_is_relative_to_best_offset():
    # Phone clock is unrelated (offset 5 s); frames 2 and 3 arrive 40 / 80 ms "late".
    m, s = StreamMonitor(stale_ms=250), uuid4()
    for seq, extra in enumerate([0, 0, 40, 80]):
        ts = seq * 100 * MS
        m.accept(frame(s, seq, ts).msg, 5_000 * MS + ts + extra * MS)
    st = m.stats()
    assert st.added_latency_p50_ms == pytest.approx(20.0)
    assert st.added_latency_p95_ms == pytest.approx(74.0)


# --- Live server via the replay client --------------------------------------------------------

def test_swift_golden_recording_replays(server):
    result = run(replay(load(GOLDEN), server.uri, speed=0))
    assert result.sent == 2
    assert wait_for(lambda: server.monitor.stats().frames + server.monitor.stats().poses == 2)
    st = server.monitor.stats()
    assert (st.frames, st.poses, st.decode_errors, st.seq_gaps) == (1, 1, 0, 0)
    got = server.slot.take(0)
    assert got.packet.image.width == 64 and got.jpeg.startswith(b"\xff\xd8")


def test_latest_frame_wins_without_consumer(server):
    records = stream(30, poses=False)
    run(replay(records, server.uri, speed=0))
    assert wait_for(lambda: server.monitor.stats().frames == 30)
    assert server.monitor.stats().slot_drops == 29
    assert server.slot.take(0).packet.seq_id == 29  # newest survives, nothing queued behind it
    assert server.slot.take(0) is None


def test_slow_consumer_drops_frames_and_latency_does_not_accumulate(server):
    """20 Hz stream, 100 ms consumer: about half the frames must be dropped, and rx -> done stays
    bounded by ~one frame of work instead of growing with the stream length (AGENTS rule 6)."""
    done = threading.Event()

    def consumer():
        while not done.is_set():
            f = server.slot.take(timeout=0.05)
            if f is not None:
                time.sleep(0.1)
                server.monitor.processed(f)

    worker = threading.Thread(target=consumer)
    worker.start()
    try:
        run(replay(stream(30, hz=20.0, poses=False), server.uri, speed=1.0))
        time.sleep(0.2)
    finally:
        done.set()
        worker.join()
    st = server.monitor.stats()
    assert st.frames == 30 and st.slot_drops >= 10
    assert st.process_p95_ms < 250, st


def test_original_timing_is_respected(server):
    records = stream(10, hz=20.0)  # 0.5 s of stream
    fast = run(replay(records, server.uri, speed=0)).seconds
    real = run(replay(records, server.uri, speed=1.0, loops=1)).seconds
    assert real == pytest.approx(0.475, abs=0.1) and fast < 0.2


def test_loops_get_fresh_sessions(server):
    run(replay(stream(5), server.uri, speed=0, loops=3))
    assert wait_for(lambda: server.monitor.stats().frames == 5)
    st = server.monitor.stats()
    assert st.out_of_order == 0 and st.retired_drops == 0  # each pass is a new session, not a replay


def test_bad_messages_are_counted_and_connection_survives(server):
    s = uuid4()
    detection_like = (Path(__file__).parent / "fixtures" / "valid" / "stream_health_stale.json").read_bytes()

    async def send():
        async with connect(server.uri) as ws:
            await ws.send(b"garbage")                                     # bad framing
            await ws.send("text frames are not part of the protocol")      # text
            await ws.send(len(detection_like).to_bytes(4, "big") + detection_like)  # wrong direction
            await ws.send(frame(s, 0, 0).raw)
    run(send())
    assert wait_for(lambda: server.monitor.stats().frames == 1)
    assert server.monitor.stats().decode_errors == 3


def test_oversized_message_closes_only_that_connection(server):
    async def send_big():
        ws = await connect(server.uri, max_size=None)
        await ws.send(b"\x00" * (CONFIG["server"]["max_message_bytes"] + 1))
        try:
            await ws.recv()
        except ConnectionClosed as e:  # the server already closed it; nothing left to close
            return e.rcvd.code
    assert run(send_big()) == 1009  # "message too big"
    run(replay(stream(1), server.uri, speed=0))
    assert wait_for(lambda: server.monitor.stats().frames == 1)


def test_stale_reported_soon_after_phone_vanishes():
    events = []
    srv = FrameServer(CONFIG, on_health=lambda h: events.append((time.time_ns(), h)))
    thread = ServerThread(srv, "127.0.0.1", 0)
    port = thread.start()
    try:
        run(replay(stream(5, hz=20.0), f"ws://127.0.0.1:{port}", speed=1.0))
        assert wait_for(lambda: any(h.stale and h.session_id for _, h in events), timeout=2.0)
        last_rx = srv.monitor.health().last_rx_ts_ns
        first_stale = next(t for t, h in events if h.stale and h.session_id and t > last_rx)
        limit = CONFIG["timing"]["stale_ms"] + CONFIG["timing"]["health_interval_ms"] + 50
        assert (first_stale - last_rx) / MS <= limit
    finally:
        thread.stop()


def test_abrupt_client_death_does_not_wedge_server(server):
    async def die():
        ws = await connect(server.uri)
        await ws.send(frame(uuid4(), 0, 0).raw)
        ws.transport.abort()  # no close frame: like the app being killed / Wi-Fi gone
    run(die())
    assert wait_for(lambda: server.monitor.stats().connections == 0)
    run(replay(stream(2), server.uri, speed=0))
    assert wait_for(lambda: server.monitor.stats().frames == 2)


def test_server_records_exactly_what_it_received(tmp_path):
    path = tmp_path / "stream.bobrec"
    records = stream(4)
    with open(path, "wb") as fh:
        srv = FrameServer(CONFIG, record=fh)
        thread = ServerThread(srv, "127.0.0.1", 0)
        port = thread.start()
        run(replay(records, f"ws://127.0.0.1:{port}", speed=0))
        wait_for(lambda: srv.monitor.stats().poses == 4)
        thread.stop()
    assert list(iter_records(path)) == [r.raw for r in records]
    assert [r.msg for r in load(path)] == [r.msg for r in records]  # replayable


def test_upright_view_rotates_and_overlays():
    jpeg = cv2.imencode(".jpg", np.zeros((48, 64, 3), np.uint8))[1].tobytes()
    rec = frame(uuid4(), 0, 0, payload=jpeg)
    image = upright_view(ReceivedFrame(rec.msg, rec.payload, 0), "portrait", ["live"])
    assert image.shape[:2] == (64, 48)  # sensor landscape -> upright portrait
    assert image.max() > 0              # overlay text drawn


@pytest.mark.parametrize("state,gap_ms,new_session,reason", [
    ("normal", 100, False, None),
    ("not_available", 100, False, "tracking_not_normal"),
    ("normal", 300, False, "stale"),
    ("normal", 100, True, "session_mismatch"),
])
def test_detection_uses_exact_source_frame_pose(state, gap_ms, new_session, reason):
    from vision.association import associate
    from vision.pipeline import FrameResult
    from vision.schema import DetectionEvent, ImageSize
    from vision.server.detection import detection_event
    from vision.server.view import decode_upright

    rec = frame(uuid4(), 4, 123000000)
    packet = rec.msg.model_copy(update={"tracking_state": state})
    received = ReceivedFrame(packet, rec.payload, 999000000, gap_ms * MS)
    clean = decode_upright(received, "portrait")
    assert clean.max() == clean.min()  # no debug text in inference input
    result = FrameResult([], [], ImageSize(width=48, height=64), 12.0, 1, [])
    association = associate(packet, received.gap_ns, uuid4() if new_session else packet.session_id, 250 * MS)
    event = detection_event(received, result, "ensemble", association)
    assert event.iphone_frame_ts_ns == 123000000 and event.seq_id == 4
    assert event.pose_valid == (reason is None)
    assert event.pose_invalid_reason == reason
    assert event.pose_dt_ms == (0.0 if reason is None else None)
    assert DetectionEvent.model_validate_json(event.model_dump_json()) == event


# --- Kill test: SIGKILL the real server process mid-stream -------------------------------------

def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server_process(tmp_path, *extra):
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "vision.server", "--no-view", "--host", "127.0.0.1", "--port", str(port),
         "--run-dir", str(tmp_path), *extra],
        cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    assert "listening" in proc.stdout.readline()
    return proc, port


def test_sigterm_twice_still_writes_summary_and_full_recording(tmp_path):
    """`uv run` forwards signals, so the server can get SIGTERM twice; cleanup must still finish."""
    proc, port = _start_server_process(tmp_path, "--record")
    try:
        records = stream(5)
        run(replay(records, f"ws://127.0.0.1:{port}", speed=0))
        time.sleep(0.2)
        proc.send_signal(signal.SIGTERM)
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=5) == 0, proc.stdout.read()
    finally:
        proc.kill()
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["frames"] == 5 and summary["poses"] == 5
    assert list(iter_records(tmp_path / "stream.bobrec")) == [r.raw for r in records]


def test_health_log_is_readable_while_server_is_running(tmp_path):
    """External preview must see C3 immediately, not only when the buffer closes."""
    from navigation.feed import latest
    from vision.schema import StreamHealth

    proc, port = _start_server_process(tmp_path, "--source-mode", "SAMPLE")
    try:
        from navigation.run_source import read_run_info
        info = read_run_info(tmp_path)
        assert info["source_mode"] == "SAMPLE" and info["started_ts_ns"] <= time.time_ns()
        records = stream(1)
        run(replay(records, f"ws://127.0.0.1:{port}", speed=0))
        path = tmp_path / "stream_health.jsonl"
        assert wait_for(lambda: (h := latest(path, StreamHealth)) is not None
                        and h.session_id == records[0].msg.session_id)
        assert proc.poll() is None
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_kill_server_mid_stream_client_fails_fast(tmp_path):
    proc, port = _start_server_process(tmp_path)
    try:
        killed_at = {}

        def kill():
            killed_at["t"] = time.monotonic()
            os.kill(proc.pid, signal.SIGKILL)

        threading.Timer(0.5, kill).start()
        with pytest.raises((ConnectionClosed, OSError)):
            run(replay(stream(100, hz=20.0), f"ws://127.0.0.1:{port}", speed=1.0))  # 5 s stream
        assert time.monotonic() - killed_at["t"] < 1.0  # sender notices, doesn't hang
        assert (tmp_path / "stream_health.jsonl").exists()
    finally:
        proc.kill()
        proc.wait()
