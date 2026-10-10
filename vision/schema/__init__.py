"""Wire contract between the iPhone app, the vision server, and downstream consumers.

Frozen per AGENTS.md rule 3. Any change must, in the same PR:
  1. bump SCHEMA_VERSION and SchemaVersion together (common.py),
  2. update the Swift mirror in ios/ and the fixtures in tests/fixtures/,
  3. regenerate schema/*.schema.json:  uv run python -m tools.export_schema

Layout:
  common.py  shared base model, enums, strict types, WireError
  pose.py    Pose + derivation from ARKit camera.transform
  phone.py   C1  iPhone -> vision: FramePacket, PosePacket
  events.py  C2/C3  vision -> consumers: DetectionEvent, StreamHealth
  wire.py    message union, encode/decode, JSON Schema export
"""

from .common import (
    SCHEMA_VERSION,
    DeviceOrientation,
    PoseInvalidReason,
    TrackingReason,
    TrackingState,
    WireError,
)
from .events import Box, DetectionEvent, ImageSize, StreamHealth
from .phone import FramePacket, ImageInfo, Intrinsics, PosePacket
from .pose import Pose, pose_from_transform, transform_matrix
from .wire import MESSAGE_MODELS, Message, decode, encode, json_schemas, parse_message

__all__ = [
    "SCHEMA_VERSION",
    "Box",
    "DetectionEvent",
    "DeviceOrientation",
    "FramePacket",
    "ImageInfo",
    "ImageSize",
    "Intrinsics",
    "MESSAGE_MODELS",
    "Message",
    "Pose",
    "PoseInvalidReason",
    "PosePacket",
    "StreamHealth",
    "TrackingReason",
    "TrackingState",
    "WireError",
    "decode",
    "encode",
    "json_schemas",
    "parse_message",
    "pose_from_transform",
    "transform_matrix",
]
