"""WebSocket receiver: validates C1 messages, fills the latest-frame slot, emits StreamHealth.

The asyncio server runs in a background thread (ServerThread) so the consumer keeps the main
thread — OpenCV windows on macOS must live there.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, BinaryIO, Callable, Optional

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from vision.association import Associator
from vision.recording import write_record
from vision.schema import FramePacket, PosePacket, StreamHealth, WireError, decode

from .monitor import Clock, StreamMonitor
from .slot import LatestSlot, ReceivedFrame


class FrameServer:
    """Receives C1 messages, keeps the latest frame in `slot`, emits StreamHealth every interval."""

    def __init__(
        self,
        config: dict[str, Any],
        record: Optional[BinaryIO] = None,
        on_health: Optional[Callable[[StreamHealth], None]] = None,
        clock: Clock = time.time_ns,
        on_admit: Optional[Callable[[FramePacket | PosePacket, Optional[int], int], None]] = None,
    ) -> None:
        timing, server = config["timing"], config["server"]
        self.clock = clock
        self.monitor = StreamMonitor(timing["stale_ms"], timing["latency_window"], clock)
        self.slot: LatestSlot[ReceivedFrame] = LatestSlot()
        self.associator = Associator(timing["stale_ms"])
        self.health_interval_s = timing["health_interval_ms"] / 1000
        self.max_message_bytes = server["max_message_bytes"]
        self.ping_interval_s = server["ping_interval_s"]
        self.record = record
        self.on_health = on_health
        self.on_admit = on_admit  # optional publication hook; must only enqueue (receive thread)
        self.latest_health: Optional[StreamHealth] = None

    async def handle(self, ws: ServerConnection) -> None:
        self.monitor.connection(+1)
        try:
            async for data in ws:
                rx_ns = self.clock()
                if isinstance(data, str):
                    self.monitor.decode_error()  # the protocol is binary-only
                    continue
                try:
                    msg, payload = decode(data)
                except WireError:
                    self.monitor.decode_error()
                    continue
                if not isinstance(msg, (FramePacket, PosePacket)):
                    self.monitor.decode_error()  # C2/C3 flow vision -> consumers, never phone -> vision
                    continue
                if self.record is not None:
                    write_record(self.record, data)
                frame = self.admit(msg, payload, rx_ns)
                if frame is not None and self.slot.put(frame):
                    self.monitor.slot_drop(frame)
        except ConnectionClosed:
            pass
        finally:
            self.monitor.connection(-1)

    def admit(self, msg: FramePacket | PosePacket, payload: bytes, rx_ns: int) -> Optional[ReceivedFrame]:
        """Book-keep one phone message; return the frame to process, if it is one we keep.

        The single admission step for the live stream and tools/replay_detect: stream monitor (drops
        late / old-session messages) then the Step 7 associator (iPhone-clock gaps), always in this order.
        """
        keep, new_session = self.monitor.accept(msg, rx_ns)
        if new_session:
            self.slot.clear()  # never process a frame from the previous world origin
        if not keep:
            return None
        gap_ns = self.associator.observe(msg)
        if self.on_admit is not None:
            self.on_admit(msg, gap_ns, rx_ns)
        return ReceivedFrame(msg, payload, rx_ns, gap_ns) if isinstance(msg, FramePacket) else None

    async def health_loop(self) -> None:
        while True:
            await asyncio.sleep(self.health_interval_s)
            self.latest_health = self.monitor.health()
            if self.on_health is not None:
                self.on_health(self.latest_health)

    async def run(self, host: str, port: int, ready: Callable[[int], None], stop: asyncio.Future) -> None:
        async with serve(
            self.handle, host, port,
            max_size=self.max_message_bytes,
            compression=None,  # JPEG doesn't compress; deflate would only cost CPU
            ping_interval=self.ping_interval_s, ping_timeout=self.ping_interval_s,
            # A vanished phone never answers the close handshake either: without this the dead
            # connection lingers for the library default of 10 s (found in Step 8).
            close_timeout=self.ping_interval_s,
        ) as server:
            health = asyncio.create_task(self.health_loop())
            ready(server.sockets[0].getsockname()[1])
            try:
                await stop
            finally:
                health.cancel()


class ServerThread:
    """Runs a FrameServer's event loop in a background thread (the consumer keeps the main thread)."""

    def __init__(self, server: FrameServer, host: str, port: int) -> None:
        self.server, self.host, self.port = server, host, port
        self._thread = threading.Thread(target=self._main, name="bob-ws", daemon=True)
        self._ready = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop: Optional[asyncio.Future] = None
        self._error: Optional[BaseException] = None

    def _main(self) -> None:
        async def main() -> None:
            self._loop = asyncio.get_running_loop()
            self._stop = self._loop.create_future()

            def ready(port: int) -> None:
                self.port = port
                self._ready.set()

            await self.server.run(self.host, self.port, ready, self._stop)

        try:
            asyncio.run(main())
        except BaseException as e:  # surfaced by start()
            self._error = e
            self._ready.set()

    def start(self, timeout: float = 5.0) -> int:
        """Start serving; returns the bound port (pass port 0 to pick a free one)."""
        self._thread.start()
        if not self._ready.wait(timeout) or self._error is not None:
            raise RuntimeError(f"server failed to start on {self.host}:{self.port}") from self._error
        return self.port

    def stop(self, timeout: float = 5.0) -> None:
        if self._loop is not None and self._stop is not None:
            self._loop.call_soon_threadsafe(lambda: self._stop.done() or self._stop.set_result(None))
        self._thread.join(timeout)
