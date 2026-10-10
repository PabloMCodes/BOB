"""Stream a .bobrec recording to the vision server the way the iPhone would (Step 5+).

    uv run python -m tools.replay_client path/to/file.bobrec [--uri ws://127.0.0.1:8765] [--speed 1] [--loops 1]

--speed 1 replays with the original timing (from iphone_frame_ts_ns), 2 = twice as fast, 0 = as fast
as possible. --loops N repeats the file; every pass after the first gets a fresh session_id, like an
ARKit restart — resending the same session/seq would (correctly) be dropped as out of order.
Messages are re-validated on load, so a corrupt recording fails before anything is sent.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Union
from uuid import UUID, uuid4

from websockets.asyncio.client import connect

from vision.recording import iter_records
from vision.schema import FramePacket, PosePacket, decode, encode

PhonePacket = Union[FramePacket, PosePacket]


@dataclass(frozen=True)
class Record:
    msg: PhonePacket
    payload: bytes
    raw: bytes


@dataclass(frozen=True)
class ReplayResult:
    sent: int
    seconds: float


def load(path: Path | str) -> list[Record]:
    records = []
    for raw in iter_records(path):
        msg, payload = decode(raw)
        if not isinstance(msg, (FramePacket, PosePacket)):
            raise ValueError(f"{path}: {msg.msg_type!r} is not a phone message")
        records.append(Record(msg, payload, raw))
    return records


def with_session(records: list[Record], session_map: dict[UUID, UUID]) -> list[Record]:
    """Re-encode records with session ids replaced (one fresh id per original session)."""
    out = []
    for r in records:
        new = session_map.setdefault(r.msg.session_id, uuid4())
        msg = r.msg.model_copy(update={"session_id": new})
        out.append(Record(msg, r.payload, encode(msg, r.payload)))
    return out


async def replay(records: Iterable[Record], uri: str, speed: float = 1.0, loops: int = 1) -> ReplayResult:
    records = list(records)
    started, sent = time.monotonic(), 0
    async with connect(uri, compression=None, max_size=None) as ws:
        for n in range(loops):
            batch = records if n == 0 else with_session(records, {})
            t0, ts0 = time.monotonic(), None
            for r in batch:
                ts = r.msg.iphone_frame_ts_ns
                if speed > 0:
                    if ts0 is None or ts < ts0:
                        t0, ts0 = time.monotonic(), ts  # first message, or the clock went backwards
                    delay = t0 + (ts - ts0) / 1e9 / speed - time.monotonic()
                    if delay > 0:
                        await asyncio.sleep(delay)
                await ws.send(r.raw)
                sent += 1
    return ReplayResult(sent, time.monotonic() - started)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--uri", default="ws://127.0.0.1:8765")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--loops", type=int, default=1)
    args = parser.parse_args()
    records = load(args.recording)
    result = asyncio.run(replay(records, args.uri, args.speed, args.loops))
    print(f"sent {result.sent} messages in {result.seconds:.1f} s")


if __name__ == "__main__":
    main()
