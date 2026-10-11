"""Synthetic admitted-event examples: no phone, models, BLE, or actuators."""
from uuid import UUID

from vision.schema import DetectionEvent, StreamHealth


SESSION = UUID("00000000-0000-0000-0000-000000000001")


def observation(seq, seconds, *, boxes=(), x=0., z=0., yaw=0., session=SESSION):
    wall_ns = 1_800_000_000_000_000_000 + round(seconds * 1e9)
    event = DetectionEvent(
        schema_version=2, msg_type="detection_event", event_id=UUID(int=seq + 1),
        session_id=session, seq_id=seq, iphone_frame_ts_ns=1_000_000_000 + round(seconds * 1e9),
        jetson_receive_ts_ns=wall_ns, inference_latency_ms=20., model_id="SYNTHETIC",
        image_size={"width": 640, "height": 480}, tracking_state="normal", boxes=list(boxes),
        pose={"x_m": x, "y_m": 0., "z_m": z, "yaw_rad": yaw},
        pose_valid=True, pose_dt_ms=0.,
    )
    health = StreamHealth(
        schema_version=2, msg_type="stream_health", emitted_ts_ns=wall_ns,
        session_id=session, stale=False, last_seq_id=seq, last_rx_ts_ns=wall_ns,
        dropped_count=0, tracking_state="normal",
    )
    return event, health, wall_ns, seconds


PERSON = dict(source="model", cls_id=0, cls_name="person", conf=.9,
              xyxy=(100., 50., 300., 450.))
MISSING = dict(source="derived", cls_id=None, cls_name="no-helmet", conf=.9,
               xyxy=(140., 60., 240., 140.))


def steps():
    yield observation(0, 0.)
    yield observation(1, .2, z=-.5)
    for seq, t in enumerate((.4, .7, 1.), 2):
        yield observation(seq, t, boxes=(PERSON, MISSING), z=-.5)
    for seq, tick in enumerate(range(12, 121, 2), 5):
        t = tick / 10
        yield observation(seq, t, z=-.5)
    event, health, wall, mono = observation(100, 13., z=-.5)
    yield event, health, wall + 2_000_000_000, mono + 2
    yield observation(0, 16., session=UUID(int=2))
