"""Step 5 — iPhone stream server (C1 in, C3 StreamHealth out). Run: `uv run python -m vision.server`.

  slot.py       latest-frame-wins hand-off (AGENTS rule 6) + ReceivedFrame
  monitor.py    per-session counters, added latency, staleness -> StreamHealth (rule 5: new session resets)
  transport.py  WebSocket receiver (FrameServer) + its background thread (ServerThread)
  view.py       upright debug view with stats overlay
  __main__.py   CLI: view loop, stream_health.jsonl, summary.json, optional stream.bobrec
"""

from .monitor import StreamMonitor, StreamStats
from .slot import LatestSlot, ReceivedFrame
from .transport import FrameServer, ServerThread
from .view import stats_lines, upright_view

__all__ = [
    "FrameServer", "LatestSlot", "ReceivedFrame", "ServerThread", "StreamMonitor", "StreamStats",
    "stats_lines", "upright_view",
]
