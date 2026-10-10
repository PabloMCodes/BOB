"""Message union and binary wire codec.

Wire format (one WebSocket binary message):
  [uint32 big-endian header_len][header: UTF-8 JSON][payload: JPEG bytes, frame messages only]
"""

from __future__ import annotations

import struct
from typing import Annotated, Any, Union

from pydantic import Field, TypeAdapter, ValidationError

from .common import WireError, _Model
from .events import DetectionEvent, StreamHealth
from .phone import FramePacket, PosePacket

_HEADER_LEN = struct.Struct(">I")
MAX_HEADER_BYTES = 64 * 1024
_JPEG_MAGIC = b"\xff\xd8"

Message = Annotated[
    Union[FramePacket, PosePacket, DetectionEvent, StreamHealth],
    Field(discriminator="msg_type"),
]
_MESSAGE = TypeAdapter(Message)

MESSAGE_MODELS: dict[str, type[_Model]] = {
    "frame": FramePacket,
    "pose": PosePacket,
    "detection_event": DetectionEvent,
    "stream_health": StreamHealth,
}


def parse_message(header_json: bytes | str) -> Message:
    """Validate a JSON header into the matching message model."""
    try:
        return _MESSAGE.validate_json(header_json)
    except ValidationError as e:
        raise WireError(f"invalid header: {e}") from e


def _check_payload(msg: Message, payload: bytes) -> None:
    if isinstance(msg, FramePacket):
        if len(payload) != msg.image.byte_length:
            raise WireError(
                f"payload is {len(payload)} bytes but image.byte_length is {msg.image.byte_length}"
            )
        if not payload.startswith(_JPEG_MAGIC):
            raise WireError("payload is not a JPEG (missing FF D8 marker)")
    elif payload:
        raise WireError(f"msg_type {msg.msg_type!r} must not carry a payload")


def encode(msg: Message, payload: bytes = b"") -> bytes:
    header = msg.model_dump_json().encode("utf-8")
    if len(header) > MAX_HEADER_BYTES:
        raise WireError(f"header is {len(header)} bytes (max {MAX_HEADER_BYTES})")
    _check_payload(msg, payload)
    return _HEADER_LEN.pack(len(header)) + header + payload


def decode(data: bytes) -> tuple[Message, bytes]:
    if len(data) < _HEADER_LEN.size:
        raise WireError("truncated message: missing header length")
    (header_len,) = _HEADER_LEN.unpack_from(data)
    if header_len == 0 or header_len > MAX_HEADER_BYTES:
        raise WireError(f"header length {header_len} out of range (1..{MAX_HEADER_BYTES})")
    end = _HEADER_LEN.size + header_len
    if len(data) < end:
        raise WireError("truncated message: header shorter than declared length")
    msg = parse_message(data[_HEADER_LEN.size:end])
    payload = data[end:]
    _check_payload(msg, payload)
    return msg, payload


def json_schemas() -> dict[str, dict[str, Any]]:
    """Language-neutral JSON Schema per message type (written to schema/ by tools/export_schema).

    JSON Schema cannot express the cross-field rules (rigid transform, box bounds,
    pose_valid consistency); those are covered by the shared fixtures in tests/fixtures/.
    """
    return {
        f"{name}.schema.json": model.model_json_schema(mode="validation")
        for name, model in MESSAGE_MODELS.items()
    }
