"""Step 4: recording format, Swift golden file, and the inspection tool."""

import math
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import pytest

from tools.inspect_recording import inspect, render
from vision.recording import RecordingError, iter_records, write_record
from vision.schema import SCHEMA_VERSION, FramePacket, PosePacket, decode, encode

GOLDEN = Path(__file__).parent / "fixtures" / "recordings" / "swift_golden.bobrec"


def _rot_y(deg, t=(0.0, 0.0, 0.0)):
    a = math.radians(deg)
    m = np.eye(4)
    m[:3, :3] = [[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]]
    m[:3, 3] = t
    return m.T.reshape(-1).tolist()


def _jpeg(w=64, h=48):
    ok, buf = cv2.imencode(".jpg", np.full((h, w, 3), 120, np.uint8))
    return buf.tobytes()


def _frame(session, seq, ts, yaw=0.0, width=64, payload=None, orientation="portrait"):
    payload = payload or _jpeg()
    msg = FramePacket(
        schema_version=SCHEMA_VERSION, msg_type="frame", session_id=session, seq_id=seq,
        iphone_frame_ts_ns=ts, tracking_state="normal", camera_transform=_rot_y(yaw),
        image={"width": width, "height": 48, "encoding": "jpeg", "device_orientation": orientation,
               "byte_length": len(payload)},
    )
    return encode(msg, payload)


def _pose(session, seq, ts, yaw=0.0, state="normal", reason=None):
    msg = PosePacket(
        schema_version=SCHEMA_VERSION, msg_type="pose", session_id=session, seq_id=seq,
        iphone_frame_ts_ns=ts, tracking_state=state, tracking_reason=reason, camera_transform=_rot_y(yaw),
    )
    return encode(msg)


def test_swift_golden_recording_decodes_in_python():
    """Real Swift encoder output (BOBCaptureTests.testExportGoldenRecording) passes the strict schema."""
    msgs = [decode(raw) for raw in iter_records(GOLDEN)]
    (frame, jpeg), (pose, empty) = msgs
    assert frame.msg_type == "frame" and pose.msg_type == "pose" and empty == b""
    assert cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR).shape[:2] == (48, 64)
    assert math.degrees(frame.pose.yaw_rad) == pytest.approx(90.0, abs=1e-3)  # Swift column-major is right
    assert (frame.pose.x_m, frame.pose.z_m) == pytest.approx((1.0, -2.0))
    assert pose.tracking_reason.value == "excessive_motion"
    assert frame.intrinsics.ref_width == 1920


def test_write_and_iter_roundtrip(tmp_path):
    path = tmp_path / "r.bobrec"
    with open(path, "wb") as fh:
        write_record(fh, b"abc")
        write_record(fh, b"")
    assert list(iter_records(path)) == [b"abc", b""]


def test_truncated_recording_raises(tmp_path):
    path = tmp_path / "r.bobrec"
    path.write_bytes(b"\x00\x00\x00\x05ab")
    with pytest.raises(RecordingError, match="truncated"):
        list(iter_records(path))


def _recording(tmp_path):
    a, b = uuid4(), uuid4()
    path = tmp_path / "bob_test.bobrec"
    with open(path, "wb") as fh:
        # session A: 2 s, turning left 0 -> 40 deg, seq 3 missing, one undecodable message
        for i, seq in enumerate([0, 1, 2, 4, 5]):
            ts = 1_000_000_000 + i * 500_000_000
            write_record(fh, _frame(a, seq, ts, yaw=i * 10) if i % 2 == 0 else _pose(a, seq, ts, yaw=i * 10))
        write_record(fh, b"\x00\x00\x00\x02{}")
        # session B: after reset, limited tracking, header width lies about the JPEG
        write_record(fh, _pose(b, 0, 9_000_000_000, state="limited", reason="relocalizing"))
        write_record(fh, _frame(b, 1, 9_100_000_000, width=99))
    return path


def test_inspect_reports_rates_gaps_sessions_and_yaw(tmp_path):
    summary = inspect(_recording(tmp_path), tmp_path / "out", sample_frames=2)
    assert summary["records"] == 8 and len(summary["errors"]) == 1
    a, b = summary["sessions"]
    assert (a.frames, a.poses, a.seq_gaps, a.out_of_order) == (3, 2, 1, 0)
    assert a.duration_s == pytest.approx(2.0)
    assert a.yaw_change_deg == pytest.approx(40.0)
    assert a.orientations == {"portrait": 3}
    assert b.tracking == {"limited": 1, "normal": 1}
    assert b.dim_mismatches == 1 and a.dim_mismatches == 0
    assert len(summary["saved"]) == 2 and all(p.exists() for p in summary["saved"])
    # portrait frames are rotated 90 deg clockwise: 64x48 sensor image -> 48x64 upright
    assert cv2.imread(str(summary["saved"][0])).shape[:2] == (64, 48)
    text = render(summary)
    assert "seq gaps 1" in text and "+40 deg" in text


def test_yaw_unwraps_across_180(tmp_path):
    s = uuid4()
    path = tmp_path / "wrap.bobrec"
    with open(path, "wb") as fh:
        for i, yaw in enumerate([170, 178, -175, -168]):
            write_record(fh, _pose(s, i, 1_000_000_000 + i * 600_000_000, yaw=yaw))
    (session,) = inspect(path)["sessions"]
    assert session.yaw_change_deg == pytest.approx(22.0)
