"""Step 8: destructive tests — every attack must fail SAFELY.

Invariants (README Step 8):
  I1 the server stays up              I4 latency can't accumulate (old frames dropped, never queued)
  I2 no fake compliance               I5 trouble is reported (stale, pose_valid=false, counters)
  I3 nothing disappears silently      I6 a pose is never guessed

Scope (decided): network / transport, bad data, pose / time abuse. Each test names its invariants.
"""

import asyncio
import base64
import copy
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import pytest
import ultralytics
from websockets.asyncio.client import connect

from tests.test_association import _JPEG, F, P
from tests.test_server import _free_port, frame, pose, run, stream, wait_for
from tools.replay_client import Record, replay
from vision.config import REPO_ROOT, load_config
from vision.ppe import Verdict
from vision.schema import SCHEMA_VERSION, DeviceOrientation, FramePacket, encode
from vision.server import monitor as monitor_module
from vision.server.transport import FrameServer, ServerThread

CONFIG = load_config()
MS = 1_000_000
ASSETS = Path(ultralytics.__file__).parent / "assets"


def start(config=CONFIG, **kw):
    srv = FrameServer(config, **kw)
    thread = ServerThread(srv, "127.0.0.1", 0)
    srv.uri = f"ws://127.0.0.1:{thread.start()}"
    srv.port = thread.port
    return srv, thread


# --- raw WebSocket client: lets a test misbehave below the library (no pongs, trickled bytes) ------

def _raw_connect(port):
    sock = socket.create_connection(("127.0.0.1", port))
    key = base64.b64encode(os.urandom(16)).decode()
    sock.sendall((f"GET / HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                  f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    response = b""
    while b"\r\n\r\n" not in response:
        response += sock.recv(1024)
    assert b" 101 " in response.split(b"\r\n")[0]
    return sock


def _ws_frame(payload: bytes) -> bytes:
    """One masked binary frame, as a client must send it (RFC 6455)."""
    n, mask = len(payload), os.urandom(4)
    head = b"\x82" + (bytes([0x80 | n]) if n < 126 else
                      b"\xfe" + struct.pack(">H", n) if n < 65536 else b"\xff" + struct.pack(">Q", n))
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return head + mask + masked


# === Network / transport ===========================================================================

def test_half_open_connection_is_closed_and_reported():
    """Wi-Fi gone without a close: the peer stops answering pings. [I1, I5]"""
    config = copy.deepcopy(CONFIG)
    config["server"]["ping_interval_s"] = 0.2
    health = []
    srv, thread = start(config, on_health=lambda h: health.append(h))
    try:
        sock = _raw_connect(srv.port)
        sock.sendall(_ws_frame(frame(uuid4(), 0, 0).raw))
        assert wait_for(lambda: srv.monitor.stats().frames == 1)
        # ...then silence: never read, never pong. Released after ~ping + timeout + close (0.6 s),
        # not the library's 10 s close timeout.
        t0 = time.monotonic()
        assert wait_for(lambda: srv.monitor.stats().connections == 0, timeout=3.0)
        assert time.monotonic() - t0 < 1.5
        assert wait_for(lambda: health and health[-1].stale and health[-1].session_id is not None)
        sock.close()
    finally:
        thread.stop()


def test_throttled_upload_does_not_block_other_clients_or_health():
    """A frame trickling in over ~1.5 s (bad link) must not stall the server. [I1, I4, I5]"""
    health = []
    srv, thread = start(on_health=lambda h: health.append(h))
    try:
        session = uuid4()
        slow = _raw_connect(srv.port)
        big = frame(session, 1000, 10_000 * MS, payload=b"\xff\xd8" + os.urandom(200_000)).raw
        data = _ws_frame(big)

        def trickle():
            for i in range(0, len(data), len(data) // 30):
                slow.sendall(data[i:i + len(data) // 30])
                time.sleep(0.05)

        t = threading.Thread(target=trickle)
        t.start()
        before = len(health)
        run(replay(stream(10, session=session, poses=False), srv.uri, speed=0))  # seq 0..9 meanwhile
        assert wait_for(lambda: srv.monitor.stats().frames == 10)  # served while the upload crawls
        t.join()
        assert wait_for(lambda: srv.monitor.stats().frames == 11)  # the slow frame arrives intact
        assert len(health) - before >= 5  # health loop kept ticking (100 ms) during the upload
        slow.close()
    finally:
        thread.stop()


def test_message_flood_keeps_one_frame_and_health_alive():
    """3000 frames as fast as possible, no consumer. [I1, I3, I4, I5]"""
    health = []
    srv, thread = start(on_health=lambda h: health.append(h))
    try:
        t0 = time.monotonic()
        run(replay(stream(3000, hz=1000, poses=False), srv.uri, speed=0))
        assert wait_for(lambda: srv.monitor.stats().frames == 3000, timeout=10)
        elapsed = time.monotonic() - t0
        st = srv.monitor.stats()
        assert st.slot_drops == 2999 and srv.slot.take(0).packet.seq_id == 2999  # only the newest is kept
        assert srv.monitor.health().dropped_count == 2999  # every unanalysed frame is accounted for
        assert len(health) >= int(elapsed / 0.1 * 0.5)  # the event loop was not starved
    finally:
        thread.stop()


def test_reconnect_storm():
    """100 connect / disconnect cycles (app crash-looping). [I1]"""
    srv, thread = start()
    try:
        async def storm():
            for _ in range(100):
                ws = await connect(srv.uri)
                await ws.close()
        run(storm())
        assert wait_for(lambda: srv.monitor.stats().connections == 0)
        run(replay(stream(3), srv.uri, speed=0))
        assert wait_for(lambda: srv.monitor.stats().frames == 3)
    finally:
        thread.stop()


def test_two_phones_newest_session_wins_and_never_mixes():
    """A second connection with another session: the newer session wins, the old one's messages are
    dropped and never associated with the new origin. [I1, I5, I6]"""
    srv, thread = start()
    try:
        a, b = uuid4(), uuid4()
        run(replay(stream(5, session=a), srv.uri, speed=0))
        run(replay(stream(5, session=b), srv.uri, speed=0))
        run(replay(stream(5, session=a), srv.uri, speed=0))  # the old phone keeps talking
        assert wait_for(lambda: srv.monitor.stats().retired_drops == 10)
        assert srv.monitor.health().session_id == b and srv.associator.current_session == b
        assert srv.slot.take(0).packet.session_id == b
    finally:
        thread.stop()


# === Bad data ======================================================================================

def _corrupt_frame(session, seq, ts_ms):
    bad = b"\xff\xd8" + b"\x13" * 4000  # passes the wire check (JPEG marker, right length), won't decode
    base = F(session, seq, ts_ms)
    msg = base.model_copy(update={"image": base.image.model_copy(update={"byte_length": len(bad)})})
    return Record(msg, bad, encode(msg, bad))


def test_corrupt_jpeg_is_counted_by_the_live_server(tmp_path):
    """Valid header, garbage JPEG: no event is possible, so it must be counted. [I1, I3, I5]"""
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "vision.server", "--no-view", "--host", "127.0.0.1", "--port", str(port),
         "--run-dir", str(tmp_path)],
        cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        assert "listening" in proc.stdout.readline()
        s = uuid4()
        good = frame(s, 1, 100 * MS)
        run(replay([_corrupt_frame(s, 0, 0), ], f"ws://127.0.0.1:{port}", speed=0))
        time.sleep(0.3)  # consumer takes the corrupt one before the next arrives
        run(replay([good], f"ws://127.0.0.1:{port}", speed=0))
        time.sleep(0.3)
        proc.send_signal(__import__("signal").SIGTERM)
        assert proc.wait(timeout=10) == 0
    finally:
        proc.kill()
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["frames"] == 2 and summary["undecodable"] == 1  # server alive, bad frame accounted


@pytest.fixture(scope="module")
def pipeline():
    from vision.pipeline import Pipeline
    return Pipeline.from_config(CONFIG)


def test_corrupt_jpeg_is_counted_offline_too(pipeline):
    """[I3] Same accounting in tools/replay_detect."""
    from tools.replay_detect import run as replay_detect
    s, skipped = uuid4(), []
    jpeg = cv2.imencode(".jpg", cv2.imread(str(ASSETS / "zidane.jpg")))[1].tobytes()
    good = F(s, 1, 100)
    good = good.model_copy(update={"image": good.image.model_copy(update={"byte_length": len(jpeg)})})
    out = replay_detect([_corrupt_frame(s, 0, 0), Record(good, jpeg, encode(good, jpeg))], pipeline, CONFIG,
                        on_undecodable=lambda f: skipped.append(f.packet.seq_id))
    assert skipped == [0] and [o.event.seq_id for o in out] == [1]


def test_header_size_lies_event_uses_real_image(pipeline):
    """Header says 1920x1440, the JPEG is 1280x720: boxes must fit the image actually analysed. [I1]"""
    from tools.replay_detect import run as replay_detect
    jpeg = cv2.imencode(".jpg", cv2.imread(str(ASSETS / "zidane.jpg")))[1].tobytes()
    msg = FramePacket(
        schema_version=SCHEMA_VERSION, msg_type="frame", session_id=uuid4(), seq_id=0, iphone_frame_ts_ns=0,
        tracking_state="normal", camera_transform=np.eye(4).reshape(-1).tolist(),
        image={"width": 1920, "height": 1440, "encoding": "jpeg", "device_orientation": "landscape_left",
               "byte_length": len(jpeg)},
    )
    (out,) = replay_detect([Record(msg, jpeg, encode(msg, jpeg))], pipeline, CONFIG)
    size = out.event.image_size
    assert (size.width, size.height) == (1280, 720)
    assert all(b.xyxy[2] <= 1280 and b.xyxy[3] <= 720 for b in out.event.boxes)


def _degrade(kind, img):
    if kind == "black":
        return np.zeros_like(img)
    if kind == "white":
        return np.full_like(img, 255)
    if kind == "dark":
        return (img.astype(np.float32) * 0.12).astype(np.uint8)
    if kind == "overexposed":
        return np.clip(img.astype(np.float32) * 3.0 + 60, 0, 255).astype(np.uint8)
    if kind == "motion_blur":
        k = np.zeros((31, 31), np.float32)
        k[15, :] = 1 / 31
        return cv2.filter2D(img, -1, k)
    if kind == "noise":
        rng = np.random.default_rng(0)
        return np.clip(img.astype(np.int16) + rng.normal(0, 60, img.shape), 0, 255).astype(np.uint8)
    if kind == "tiny":
        small = cv2.resize(img, (320, 180))
        return cv2.resize(small, (img.shape[1], img.shape[0]))
    raise ValueError(kind)


@pytest.mark.parametrize("kind", ["black", "white", "dark", "overexposed", "motion_blur", "noise", "tiny"])
def test_degraded_frames_never_fake_compliance(pipeline, kind):
    """Nobody in zidane.jpg wears glasses, a helmet or a vest: no degradation may turn that into
    'wearing' — the honest outcomes are not_wearing or unverified. [I2]"""
    from vision.ppe import frame_verdict
    result = pipeline(_degrade(kind, cv2.imread(str(ASSETS / "zidane.jpg"))))
    for rule in ("glasses", "helmet", "vest"):
        assert frame_verdict(result.verdicts, rule) is not Verdict.WEARING, (kind, rule)
    if kind in ("black", "white"):
        assert all(frame_verdict(result.verdicts, r.name) is Verdict.UNVERIFIED for r in pipeline.rules)


def test_flat_phone_uses_mount_orientation(pipeline):
    """face_up (phone lying flat) carries no rotation: the landscape_left mount is used, nothing breaks."""
    from tools.replay_detect import run as replay_detect
    jpeg = cv2.imencode(".jpg", cv2.imread(str(ASSETS / "zidane.jpg")))[1].tobytes()
    base = F(uuid4(), 0, 0)
    msg = base.model_copy(update={"image": base.image.model_copy(
        update={"byte_length": len(jpeg), "device_orientation": DeviceOrientation.FACE_UP,
                "width": 1280, "height": 720})})
    (out,) = replay_detect([Record(msg, jpeg, encode(msg, jpeg))], pipeline, CONFIG)
    assert (out.event.image_size.width, out.event.image_size.height) == (1280, 720)  # not rotated
    assert out.verdicts["glasses"] is Verdict.NOT_WEARING


# === Pose / time abuse =============================================================================

def test_session_flapping_is_bounded_and_never_mixes(monkeypatch):
    """A Reset on every message (buggy app): memory bounded, each frame judged in its own session,
    a late message of an old session dropped. [I1, I6]"""
    monkeypatch.setattr(monitor_module, "MAX_RETIRED_SESSIONS", 100)
    srv = FrameServer(CONFIG)
    sessions = [uuid4() for _ in range(500)]
    for i, s in enumerate(sessions):
        fr = srv.admit(F(s, 0, i * 10), b"\xff\xd8", 0)
        assert srv.associator.associate(fr.packet, fr.gap_ns).pose_valid  # first frame of its session
    assert len(srv.monitor._retired) == 100
    assert srv.admit(F(sessions[-2], 1, 5_000), b"\xff\xd8", 0) is None  # recent old session: dropped
    assert srv.monitor.stats().retired_drops == 1


def test_clock_jump_marks_only_that_frame_stale():
    """+1 hour on the iPhone clock (e.g. phone slept): that frame stale, the next one fine. [I5, I6]"""
    srv, s = FrameServer(CONFIG), uuid4()
    verdicts = []
    for i, t in enumerate([0, 100, 3_600_000, 3_600_100]):
        fr = srv.admit(F(s, i, t), b"\xff\xd8", 0)
        a = srv.associator.associate(fr.packet, fr.gap_ns)
        verdicts.append("valid" if a.pose_valid else a.reason.value)
    assert verdicts == ["valid", "valid", "stale", "valid"]


def test_extreme_seq_and_timestamp_values():
    """Swift sends UInt64: the largest values must round-trip and associate. [I1]"""
    big = 2**64 - 1
    srv, s = FrameServer(CONFIG), uuid4()
    first = F(s, big - 1, 0).model_copy(update={"iphone_frame_ts_ns": big - 200 * MS})
    last = F(s, big, 0).model_copy(update={"iphone_frame_ts_ns": big - 100 * MS})
    for m in (first, last):
        from vision.schema import decode
        decoded, _ = decode(encode(m, _JPEG))
        fr = srv.admit(decoded, _JPEG, 0)
    assert fr.gap_ns == 100 * MS and srv.associator.associate(fr.packet, fr.gap_ns).pose_valid


def test_pose_packets_alone_never_produce_detections():
    """A phone sending only poses (encoder stuck): health stays live, but nothing is invented. [I3, I6]"""
    srv, s = FrameServer(CONFIG), uuid4()
    for i in range(20):
        assert srv.admit(P(s, i, i * 50), b"", 0) is None
    assert srv.monitor.stats().poses == 20 and srv.slot.take(0) is None
