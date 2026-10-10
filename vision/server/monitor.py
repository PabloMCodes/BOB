"""Per-session stream bookkeeping: seq gaps, drops, rates, latency, and C3 StreamHealth.

Latency: iPhone timestamps are seconds since phone boot, unrelated to the Mac clock, so the absolute
network delay can't be known without a round trip. We measure *added* latency instead: per session,
offset = rx_ts - iphone_ts and added = offset - min(offset). A growing value means latency is
accumulating (queueing). Clock drift between the two devices adds a few ms per minute.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Callable, Optional, Union
from uuid import UUID

import numpy as np

from vision.schema import SCHEMA_VERSION, FramePacket, PosePacket, StreamHealth

from .slot import ReceivedFrame

PhonePacket = Union[FramePacket, PosePacket]
Clock = Callable[[], int]
# Retired session ids kept to drop their late messages. Bounded: a Reset every frame must not grow memory
# forever (Step 8). Late messages arrive within seconds; 10k sessions is hours of resets every frame.
MAX_RETIRED_SESSIONS = 10_000


def _percentile(values: deque, q: float) -> Optional[float]:
    return float(np.percentile(list(values), q)) if values else None


def _rate_hz(times: deque, now_ns: int, window_ns: int = 2_000_000_000) -> float:
    while times and now_ns - times[0] > window_ns:
        times.popleft()
    return len(times) / (window_ns / 1e9)


@dataclass
class _Session:
    session_id: UUID
    window: int
    frames: int = 0
    poses: int = 0
    last_seq: Optional[int] = None
    last_rx_ns: Optional[int] = None
    tracking_state: Optional[str] = None
    seq_gaps: int = 0          # messages the phone skipped (sender busy / disconnected)
    out_of_order: int = 0      # older than one already seen -> dropped
    slot_drops: int = 0        # frames replaced in the slot before the consumer took them
    undecodable: int = 0       # frames whose JPEG didn't decode: never analysed, counted (Step 8)
    min_offset_ns: Optional[int] = None
    added_ms: deque = field(default_factory=deque)
    process_ms: deque = field(default_factory=deque)
    frame_rx: deque = field(default_factory=deque)
    pose_rx: deque = field(default_factory=deque)

    def __post_init__(self) -> None:
        self.added_ms = deque(maxlen=self.window)
        self.process_ms = deque(maxlen=self.window)


@dataclass(frozen=True)
class StreamStats:
    connections: int
    session_id: Optional[UUID]
    stale: bool
    tracking_state: Optional[str]
    frames: int
    poses: int
    frame_hz: float
    pose_hz: float
    seq_gaps: int
    out_of_order: int
    slot_drops: int
    undecodable: int
    retired_drops: int         # late messages from a previous session (all sessions)
    decode_errors: int         # all sessions
    added_latency_p50_ms: Optional[float]
    added_latency_p95_ms: Optional[float]
    process_p50_ms: Optional[float]
    process_p95_ms: Optional[float]


class StreamMonitor:
    """Thread-safe: fed by the receiver thread, read by the consumer and the health loop.

    A new session_id invalidates the previous session (AGENTS rule 5): its counters are reset and
    any of its messages that still arrive are dropped.
    """

    def __init__(self, stale_ms: float, window: int = 100, clock: Clock = time.time_ns) -> None:
        self.stale_ns = int(stale_ms * 1e6)
        self.window = window
        self.clock = clock
        self._lock = threading.Lock()
        self._session: Optional[_Session] = None
        self._retired: OrderedDict[UUID, None] = OrderedDict()
        self._connections = 0
        self.decode_errors = 0
        self.retired_drops = 0

    def connection(self, delta: int) -> None:
        with self._lock:
            self._connections += delta

    def decode_error(self) -> None:
        with self._lock:
            self.decode_errors += 1

    def accept(self, msg: PhonePacket, rx_ns: int) -> tuple[bool, bool]:
        """Record a phone message. Returns (keep, new_session); keep=False means drop it."""
        with self._lock:
            new_session = False
            if msg.session_id in self._retired:
                self.retired_drops += 1
                return False, False
            s = self._session
            if s is None or s.session_id != msg.session_id:
                if s is not None:
                    self._retired[s.session_id] = None
                    if len(self._retired) > MAX_RETIRED_SESSIONS:
                        self._retired.popitem(last=False)
                s = self._session = _Session(msg.session_id, self.window)
                new_session = True
            if s.last_seq is not None and msg.seq_id <= s.last_seq:
                s.out_of_order += 1
                return False, new_session
            if s.last_seq is not None:
                s.seq_gaps += msg.seq_id - s.last_seq - 1
            s.last_seq, s.last_rx_ns = msg.seq_id, rx_ns
            s.tracking_state = msg.tracking_state.value
            if isinstance(msg, FramePacket):
                s.frames += 1
                s.frame_rx.append(rx_ns)
                offset = rx_ns - msg.iphone_frame_ts_ns
                s.min_offset_ns = offset if s.min_offset_ns is None else min(s.min_offset_ns, offset)
                s.added_ms.append((offset - s.min_offset_ns) / 1e6)
            else:
                s.poses += 1
                s.pose_rx.append(rx_ns)
            return True, new_session

    def slot_drop(self, frame: ReceivedFrame) -> None:
        with self._lock:
            if self._session is not None and self._session.session_id == frame.packet.session_id:
                self._session.slot_drops += 1

    def undecodable(self, frame: ReceivedFrame) -> None:
        """The consumer couldn't decode the frame's JPEG: count it so it is never silently lost."""
        with self._lock:
            if self._session is not None and self._session.session_id == frame.packet.session_id:
                self._session.undecodable += 1

    def processed(self, frame: ReceivedFrame, done_ns: Optional[int] = None) -> None:
        """The consumer finished a frame: records rx -> done time (Mac side only)."""
        done_ns = self.clock() if done_ns is None else done_ns
        with self._lock:
            if self._session is not None and self._session.session_id == frame.packet.session_id:
                self._session.process_ms.append((done_ns - frame.rx_ts_ns) / 1e6)

    def _stale(self, now_ns: int) -> bool:
        s = self._session
        return s is None or s.last_rx_ns is None or now_ns - s.last_rx_ns > self.stale_ns

    def health(self, now_ns: Optional[int] = None) -> StreamHealth:
        now_ns = self.clock() if now_ns is None else now_ns
        with self._lock:
            s = self._session
            return StreamHealth(
                schema_version=SCHEMA_VERSION,
                msg_type="stream_health",
                emitted_ts_ns=now_ns,
                session_id=s.session_id if s else None,
                stale=self._stale(now_ns),
                last_seq_id=s.last_seq if s else None,
                last_rx_ts_ns=s.last_rx_ns if s else None,
                # Frames never analysed this session: skipped by the phone, replaced here, undecodable.
                dropped_count=(s.seq_gaps + s.slot_drops + s.undecodable) if s else 0,
                tracking_state=s.tracking_state if s else None,
            )

    def stats(self, now_ns: Optional[int] = None) -> StreamStats:
        now_ns = self.clock() if now_ns is None else now_ns
        with self._lock:
            s = self._session
            empty: deque = deque()
            return StreamStats(
                connections=self._connections,
                session_id=s.session_id if s else None,
                stale=self._stale(now_ns),
                tracking_state=s.tracking_state if s else None,
                frames=s.frames if s else 0,
                poses=s.poses if s else 0,
                frame_hz=_rate_hz(s.frame_rx, now_ns) if s else 0.0,
                pose_hz=_rate_hz(s.pose_rx, now_ns) if s else 0.0,
                seq_gaps=s.seq_gaps if s else 0,
                out_of_order=s.out_of_order if s else 0,
                slot_drops=s.slot_drops if s else 0,
                undecodable=s.undecodable if s else 0,
                retired_drops=self.retired_drops,
                decode_errors=self.decode_errors,
                added_latency_p50_ms=_percentile(s.added_ms if s else empty, 50),
                added_latency_p95_ms=_percentile(s.added_ms if s else empty, 95),
                process_p50_ms=_percentile(s.process_ms if s else empty, 50),
                process_p95_ms=_percentile(s.process_ms if s else empty, 95),
            )
