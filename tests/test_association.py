"""Step 7: pose <-> detection association on synthetic timelines (no phone, no model).

Messages go through FrameServer.admit — the exact admission step of the live server and of
tools/replay_detect — then the frame is associated when it is "processed". Each timeline is built to
trip one rule.
"""

import math
from uuid import uuid4

import numpy as np
import pytest

from vision.association import Associator, associate
from vision.config import load_config
from vision.schema import SCHEMA_VERSION, FramePacket, PosePacket
from vision.server.transport import FrameServer

CONFIG = load_config()
MS = 1_000_000
STALE_MS = CONFIG["timing"]["stale_ms"]
_JPEG = b"\xff\xd8" + b"\x00" * 16


def _transform(yaw_deg=0.0, xyz=(0.0, 0.0, 0.0), pitch_up_deg=0.0):
    """Column-major ARKit transform: yaw about +Y (left = positive), then pitch about +X."""
    a, p = math.radians(yaw_deg), math.radians(pitch_up_deg)
    yaw = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    pitch = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    m = np.eye(4)
    m[:3, :3] = yaw @ pitch
    m[:3, 3] = xyz
    return m.T.reshape(-1).tolist()


def F(session, seq, t_ms, state="normal", **pose):
    reason = "insufficient_features" if state == "limited" else None
    return FramePacket(
        schema_version=SCHEMA_VERSION, msg_type="frame", session_id=session, seq_id=seq,
        iphone_frame_ts_ns=int(t_ms * MS), tracking_state=state, tracking_reason=reason,
        camera_transform=_transform(**pose),
        image={"width": 64, "height": 48, "encoding": "jpeg", "device_orientation": "landscape_left",
               "byte_length": len(_JPEG)},
    )


def P(session, seq, t_ms, state="normal"):
    reason = "insufficient_features" if state == "limited" else None
    return PosePacket(
        schema_version=SCHEMA_VERSION, msg_type="pose", session_id=session, seq_id=seq,
        iphone_frame_ts_ns=int(t_ms * MS), tracking_state=state, tracking_reason=reason,
        camera_transform=_transform(),
    )


def play(messages, server=None):
    """Admit messages in order, associating each frame right away. Returns {seq: reason or 'valid'}."""
    server = server or FrameServer(CONFIG)
    out = {}
    for msg in messages:
        frame = server.admit(msg, _JPEG if isinstance(msg, FramePacket) else b"", 0)
        if frame is not None:
            a = server.associator.associate(frame.packet, frame.gap_ns)
            out[msg.seq_id] = "valid" if a.pose_valid else a.reason.value
    return out


S = uuid4()


def test_normal_stream_all_valid_with_exact_pose():
    timeline = [F(S, 0, 0), P(S, 1, 50), F(S, 2, 100), P(S, 3, 150), F(S, 4, 200)]
    assert play(timeline) == {0: "valid", 2: "valid", 4: "valid"}


def test_pose_is_the_frames_own_not_the_latest():
    """A pose packet arriving after the frame (rover turned) must not leak into the frame's event."""
    server = FrameServer(CONFIG)
    frame = server.admit(F(S, 0, 0, yaw_deg=10.0), _JPEG, 0)
    server.admit(P(S, 1, 50), b"", 0)  # identity pose = yaw 0, the "latest" one
    a = server.associator.associate(frame.packet, frame.gap_ns)
    assert a.pose_valid and a.pose_dt_ms == 0.0
    assert math.degrees(a.pose.yaw_rad) == pytest.approx(10.0)


def test_limited_stretch_invalidates_only_its_frames():
    timeline = [F(S, 0, 0), F(S, 1, 100, "limited"), P(S, 2, 150, "limited"), F(S, 3, 200, "limited"), F(S, 4, 300)]
    assert play(timeline) == {0: "valid", 1: "tracking_not_normal", 3: "tracking_not_normal", 4: "valid"}


def test_not_available_is_invalid():
    assert play([F(S, 0, 0, "not_available")]) == {0: "tracking_not_normal"}


@pytest.mark.parametrize("gap_ms, expected", [(STALE_MS, "valid"), (STALE_MS + 0.001, "stale"), (300, "stale")])
def test_stale_boundary_on_iphone_clock(gap_ms, expected):
    assert play([F(S, 0, 0), F(S, 1, gap_ms)])[1] == expected


def test_gap_then_recovery():
    """Only the first message after the gap is stale; the stream is fresh again right after."""
    timeline = [F(S, 0, 0), P(S, 1, 400), F(S, 2, 450)]
    server = FrameServer(CONFIG)
    assert play(timeline, server) == {0: "valid", 2: "valid"}  # the pose absorbed the gap
    assert play([F(S, 3, 1000)], server) == {3: "stale"}


def test_gap_uses_iphone_clock_not_arrival_time():
    """Arrival (receiver) times are irrelevant: a burst that arrives late but was captured 100 ms apart
    is fresh; messages that arrive back to back but were captured 400 ms apart are stale."""
    server = FrameServer(CONFIG)
    for t in (0, 100):
        server.admit(F(S, t // 100, t), _JPEG, rx_ns=5_000 * MS)  # same arrival time
    late = server.admit(F(S, 2, 500), _JPEG, rx_ns=5_000 * MS)
    assert late.gap_ns == 400 * MS
    assert server.associator.associate(late.packet, late.gap_ns).reason.value == "stale"


def test_first_frame_of_new_session_is_not_stale():
    """10 s after session a, session b starts: its first frame has no gap (new origin, new clock run)."""
    a, b = uuid4(), uuid4()
    server = FrameServer(CONFIG)
    play([F(a, 0, 0)], server)
    frame = server.admit(F(b, 0, 10_000), _JPEG, 0)
    assert frame.gap_ns is None
    assert server.associator.associate(frame.packet, frame.gap_ns).pose_valid


def test_reset_mid_stream_then_late_old_frame_is_dropped_never_associated():
    a, b = uuid4(), uuid4()
    server = FrameServer(CONFIG)
    play([F(a, 0, 0), F(a, 1, 100)], server)
    assert play([F(b, 0, 150)], server) == {0: "valid"}
    assert server.admit(F(a, 2, 200), _JPEG, 0) is None  # rule 5: old world origin, dropped at admission
    assert server.monitor.stats().retired_drops == 1


def test_frame_processed_after_a_newer_session_arrived_is_session_mismatch():
    """The frame was taken for inference, then ARKit reset: its pose belongs to the old origin."""
    a, b = uuid4(), uuid4()
    server = FrameServer(CONFIG)
    in_flight = server.admit(F(a, 0, 0), _JPEG, 0)
    server.admit(P(b, 0, 40), b"", 0)  # reset arrives while the model is still running
    assn = server.associator.associate(in_flight.packet, in_flight.gap_ns)
    assert not assn.pose_valid and assn.reason.value == "session_mismatch" and assn.pose is None


def test_session_mismatch_wins_over_other_reasons():
    a, b = uuid4(), uuid4()
    assn = associate(F(a, 0, 0, "limited"), 999 * MS, b, STALE_MS * MS)
    assert assn.reason.value == "session_mismatch"


def test_stale_wins_over_tracking():
    assert associate(F(S, 0, 0, "limited"), 999 * MS, S, STALE_MS * MS).reason.value == "stale"


def test_out_of_order_and_duplicate_seq_dropped():
    server = FrameServer(CONFIG)
    assert play([F(S, 0, 0), F(S, 2, 200)], server) == {0: "valid", 2: "valid"}
    assert server.admit(F(S, 1, 100), _JPEG, 0) is None  # older than seq 2
    assert server.admit(F(S, 2, 200), _JPEG, 0) is None  # duplicate
    assert server.monitor.stats().out_of_order == 2


def test_timestamp_going_backwards_is_not_stale_and_keeps_its_pose():
    """iPhone clock can't go backwards within a session; if it ever does, a negative gap is not 'stale'."""
    assert play([F(S, 0, 1000), F(S, 1, 900)]) == {0: "valid", 1: "valid"}


@pytest.mark.parametrize("pitch", [90.0, -90.0])
def test_camera_straight_up_or_down_is_no_pose_but_still_associated(pitch):
    assert play([F(S, 0, 0, pitch_up_deg=pitch)]) == {0: "no_pose"}


def test_tilted_up_rover_mount_has_a_valid_pose():
    """The rover mount looks up ~15°: yaw stays defined."""
    assn = associate(F(S, 0, 0, yaw_deg=30.0, pitch_up_deg=15.0), None, S, STALE_MS * MS)
    assert assn.pose_valid and math.degrees(assn.pose.yaw_rad) == pytest.approx(30.0)


def test_associator_is_independent_of_poses_from_other_sessions():
    a = Associator(STALE_MS)
    assert a.observe(P(S, 0, 0)) is None
    assert a.observe(P(S, 1, 50)) == 50 * MS
    other = uuid4()
    assert a.observe(P(other, 0, 60)) is None and a.current_session == other


def test_pose_timeline_reports_sessions_and_invalid_stretches():
    """The live-acceptance tool: a lens cover and a Reset show up as stretches / sessions."""
    from tools.pose_timeline import build, render
    from tools.replay_client import Record
    from vision.schema import encode

    a, b = uuid4(), uuid4()
    msgs = [F(a, i, i * 100) for i in range(5)]                                  # 0.0-0.4 s valid
    msgs += [F(a, i, i * 100, "limited") for i in range(5, 35)]                  # 0.5-3.4 s lens covered
    msgs += [F(a, i, i * 100) for i in range(35, 40)]                            # valid again
    msgs += [F(b, i, 4_000 + i * 100, "limited") for i in range(0, 10)]          # Reset: initialising
    msgs += [F(b, i, 4_000 + i * 100) for i in range(10, 15)]
    msgs.append(F(a, 40, 3_950))                                                 # late frame, old origin
    records = [Record(m, _JPEG, encode(m, _JPEG)) for m in msgs]
    timeline = build(records, CONFIG)
    first, second = timeline.sessions
    assert timeline.dropped == 1
    assert first.verdicts == {"valid": 10, "tracking_not_normal (insufficient_features)": 30}
    (cover,) = first.invalid
    assert (cover.start_s, cover.end_s, cover.frames) == pytest.approx((0.5, 3.4, 30))
    assert second.start_s == pytest.approx(4.0) and second.invalid[0].frames == 10
    assert "sessions 2" in render(timeline)
