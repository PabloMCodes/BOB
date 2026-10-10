"""Step 1: schema contract tests — fixtures, wire codec, pose derivation, JSON Schema drift."""

import json
import math
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import pytest

from tools.export_schema import SCHEMA_DIR, render
from vision.schema import (
    DetectionEvent,
    FramePacket,
    PosePacket,
    StreamHealth,
    WireError,
    decode,
    encode,
    json_schemas,
    parse_message,
    pose_from_transform,
)

FIXTURES = Path(__file__).parent / "fixtures"
VALID = sorted((FIXTURES / "valid").glob("*.json"))
INVALID = sorted((FIXTURES / "invalid").glob("*.json"))

# Each invalid fixture must fail for the *intended* reason, not just any reason.
EXPECTED_ERRORS = {
    "frame_wrong_version": "schema_version",
    "frame_missing_version": "schema_version",
    "frame_unknown_field": "Extra inputs are not permitted",
    "frame_bad_tracking_state": "tracking_state",
    "frame_limited_without_reason": "tracking_reason is required",
    "frame_normal_with_reason": "tracking_reason must be null",
    "frame_transform_15_floats": "camera_transform",
    "frame_transform_row_major": "column-major",
    "frame_transform_not_rigid": "not orthonormal",
    "frame_negative_seq": "seq_id",
    "frame_ts_as_string": "iphone_frame_ts_ns",
    "frame_ts_as_float": "iphone_frame_ts_ns",
    "frame_bad_session_id": "session_id",
    "frame_intrinsics_out_of_range": "principal point",
    "frame_png_encoding": "encoding",
    "frame_missing_image": "image",
    "pose_with_image": "Extra inputs are not permitted",
    "detection_valid_without_pose": "pose_valid=true requires a pose",
    "detection_invalid_without_reason": "pose_valid=false requires",
    "detection_valid_with_reason": "pose_invalid_reason=null",
    "detection_pose_without_dt": "pose_dt_ms must be set",
    "detection_box_out_of_bounds": "outside image_size",
    "detection_box_inverted": "x1 < x2",
    "detection_box_negative": ">= 0",
    "detection_conf_above_1": "conf",
    "detection_pose_valid_as_string": "pose_valid",
    "stream_health_no_session_not_stale": "stale must be true",
    "unknown_msg_type": "msg_type",
}

TYPE_BY_PREFIX = {
    "frame": FramePacket,
    "pose": PosePacket,
    "detection_event": DetectionEvent,
    "stream_health": StreamHealth,
}


def _jpeg(width: int = 64, height: int = 48) -> bytes:
    ok, buf = cv2.imencode(".jpg", np.zeros((height, width, 3), dtype=np.uint8))
    assert ok
    return buf.tobytes()


def _frame(payload: bytes, **overrides) -> FramePacket:
    data = json.loads((FIXTURES / "valid" / "frame_normal.json").read_text())
    data["image"]["byte_length"] = len(payload)
    data.update(overrides)
    return parse_message(json.dumps(data))


def _rot_y(deg: float, t=(0.0, 0.0, 0.0)) -> list[float]:
    """Column-major 4x4: rotation about +Y then translation t."""
    a = math.radians(deg)
    m = np.eye(4)
    m[:3, :3] = [[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]]
    m[:3, 3] = t
    return m.T.reshape(-1).tolist()


# --- Fixtures -----------------------------------------------------------------------------


def test_fixture_sets_are_complete():
    assert VALID and INVALID
    assert {p.stem for p in INVALID} == set(EXPECTED_ERRORS)


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.stem)
def test_valid_fixture_parses_to_expected_type(path):
    msg = parse_message(path.read_bytes())
    expected = next(t for prefix, t in TYPE_BY_PREFIX.items() if path.stem.startswith(prefix + "_"))
    assert type(msg) is expected


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.stem)
def test_invalid_fixture_rejected_for_intended_reason(path):
    with pytest.raises(WireError) as exc:
        parse_message(path.read_bytes())
    assert len(exc.value.__cause__.errors()) == 1, "fixture must break exactly one rule"
    assert EXPECTED_ERRORS[path.stem] in str(exc.value)


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.stem)
def test_json_roundtrip_is_lossless(path):
    msg = parse_message(path.read_bytes())
    assert parse_message(msg.model_dump_json()) == msg


def test_swift_uppercase_uuid_accepted():
    msg = parse_message((FIXTURES / "valid" / "frame_normal.json").read_bytes())
    assert str(msg.session_id) == "6f9619ff-8b86-4d11-b42d-00c04fc964ff"


# --- Wire codec ---------------------------------------------------------------------------


def test_frame_wire_roundtrip():
    payload = _jpeg()
    msg = _frame(payload)
    decoded, decoded_payload = decode(encode(msg, payload))
    assert decoded == msg
    assert decoded_payload == payload


@pytest.mark.parametrize("name", ["pose_normal", "detection_event_pose_valid", "stream_health_stale"])
def test_payloadless_wire_roundtrip(name):
    msg = parse_message((FIXTURES / "valid" / f"{name}.json").read_bytes())
    decoded, payload = decode(encode(msg))
    assert decoded == msg and payload == b""


def test_payload_length_mismatch_rejected():
    payload = _jpeg()
    data = encode(_frame(payload), payload)
    with pytest.raises(WireError, match="byte_length"):
        decode(data[:-1])


def test_non_jpeg_payload_rejected():
    fake = b"\x89PNG" + b"\x00" * 100
    with pytest.raises(WireError, match="not a JPEG"):
        encode(_frame(fake), fake)


def test_payload_on_pose_rejected():
    msg = parse_message((FIXTURES / "valid" / "pose_normal.json").read_bytes())
    with pytest.raises(WireError, match="must not carry a payload"):
        encode(msg, b"\xff\xd8junk")


@pytest.mark.parametrize(
    "data, match",
    [
        (b"\x00\x00", "missing header length"),
        (b"\x00\x00\x00\x00{}", "out of range"),
        (b"\xff\xff\xff\xff{}", "out of range"),
        (b"\x00\x00\x00\x10{}", "header shorter"),
        (b"\x00\x00\x00\x02{}", "invalid header"),
    ],
)
def test_bad_framing_rejected(data, match):
    with pytest.raises(WireError, match=match):
        decode(data)


def test_messages_are_immutable():
    msg = parse_message((FIXTURES / "valid" / "pose_normal.json").read_bytes())
    with pytest.raises(Exception):
        msg.seq_id = 99


# --- Pose derivation ----------------------------------------------------------------------


def test_identity_pose():
    pose = pose_from_transform(_rot_y(0, t=(0.5, 0.0, -1.2)))
    assert (pose.x_m, pose.y_m, pose.z_m) == pytest.approx((0.5, 0.0, -1.2))
    assert pose.yaw_rad == pytest.approx(0.0)


@pytest.mark.parametrize("deg", [45, 90, -90, 135])
def test_yaw_follows_rotation_about_y(deg):
    assert pose_from_transform(_rot_y(deg)).yaw_rad == pytest.approx(math.radians(deg))


def test_yaw_180_is_pi_magnitude():
    assert abs(pose_from_transform(_rot_y(180)).yaw_rad) == pytest.approx(math.pi)


def test_landscape_roll_does_not_change_yaw():
    """Phone mounted sideways = roll about camera Z; heading must be unchanged."""
    roll = np.eye(4)
    roll[:3, :3] = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
    yawed = np.array(_rot_y(30)).reshape(4, 4).T
    m = yawed @ roll
    assert pose_from_transform(m.T.reshape(-1)).yaw_rad == pytest.approx(math.radians(30))


def test_looking_straight_down_has_no_yaw():
    pitch = np.eye(4)
    pitch[:3, :3] = [[1, 0, 0], [0, 0, 1], [0, -1, 0]]  # camera -Z -> world -Y
    with pytest.raises(ValueError, match="yaw is undefined"):
        pose_from_transform(pitch.T.reshape(-1))


def test_packet_pose_property_matches_fixture():
    msg = parse_message((FIXTURES / "valid" / "frame_limited_rotated.json").read_bytes())
    pose = msg.pose
    assert (pose.x_m, pose.y_m, pose.z_m) == pytest.approx((1.0, 0.1, -2.0))
    assert pose.yaw_rad == pytest.approx(math.pi / 2)


def test_python_built_event_validates():
    """Step 6/7 will construct events in Python; make sure that path works with real types."""
    event = DetectionEvent(
        schema_version=1,
        msg_type="detection_event",
        event_id=uuid4(),
        session_id=uuid4(),
        seq_id=1,
        iphone_frame_ts_ns=1,
        jetson_receive_ts_ns=2,
        inference_latency_ms=10.0,
        model_id="yolov8n",
        image_size={"width": 640, "height": 480},
        tracking_state="normal",
        boxes=[{"cls_id": 0, "cls_name": "person", "conf": 0.5, "xyxy": [1.0, 2.0, 3.0, 4.0]}],
        pose=pose_from_transform(_rot_y(0)),
        pose_valid=True,
        pose_dt_ms=0.0,
    )
    assert parse_message(event.model_dump_json()) == event


# --- JSON Schema drift (integration.md G5) --------------------------------------------------


def test_committed_json_schemas_match_code():
    generated = json_schemas()
    committed = {p.name for p in SCHEMA_DIR.glob("*.schema.json")}
    assert committed == set(generated), "run: uv run python -m tools.export_schema"
    for filename, schema in generated.items():
        assert (SCHEMA_DIR / filename).read_text() == render(schema), (
            f"schema/{filename} is stale — run: uv run python -m tools.export_schema"
        )
