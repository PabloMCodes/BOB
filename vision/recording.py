"""Recording files (.bobrec): a sequence of [uint32 big-endian message_len][wire message].

Written by the iPhone app (ios/BOBCapture/Wire/Recorder.swift) — one record per WebSocket message —
and read here for inspection (Step 4) and replay (Step 5). Each message decodes with
`vision.schema.decode`.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import BinaryIO, Iterator

_LEN = struct.Struct(">I")


class RecordingError(ValueError):
    """The file is truncated or not a recording."""


def write_record(fh: BinaryIO, message: bytes) -> None:
    fh.write(_LEN.pack(len(message)))
    fh.write(message)


def iter_records(path: Path | str) -> Iterator[bytes]:
    """Yield raw wire messages. A truncated final record (app killed mid-write) raises."""
    with open(path, "rb") as fh:
        while True:
            head = fh.read(_LEN.size)
            if not head:
                return
            if len(head) < _LEN.size:
                raise RecordingError("truncated record length")
            (length,) = _LEN.unpack(head)
            body = fh.read(length)
            if len(body) < length:
                raise RecordingError(f"truncated record: expected {length} bytes, got {len(body)}")
            yield body
