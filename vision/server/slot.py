"""Latest-frame-wins hand-off between the receiver thread and the consumer (AGENTS rule 6)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

from vision.schema import FramePacket

T = TypeVar("T")


@dataclass(frozen=True)
class ReceivedFrame:
    packet: FramePacket
    jpeg: bytes
    rx_ts_ns: int  # receiver clock
    gap_ns: Optional[int] = None  # iPhone-clock gap since the session's previous message (Step 7)


class LatestSlot(Generic[T]):
    """Holds at most one item. A put over an unconsumed item replaces it (latest wins)."""

    def __init__(self) -> None:
        self._item: Optional[T] = None
        self._cond = threading.Condition()

    def put(self, item: T) -> bool:
        """Store `item`; True if it replaced one nobody took (i.e. a frame was dropped)."""
        with self._cond:
            dropped = self._item is not None
            self._item = item
            self._cond.notify()
            return dropped

    def take(self, timeout: Optional[float] = None) -> Optional[T]:
        with self._cond:
            if self._item is None:
                self._cond.wait(timeout)
            item, self._item = self._item, None
            return item

    def clear(self) -> None:
        with self._cond:
            self._item = None
