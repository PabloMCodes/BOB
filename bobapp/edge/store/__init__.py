"""Rover edge store (dashboard plan §5): SQLite WAL lanes + content-addressed evidence files.

The SQLite file is the process boundary: the vision.server writer thread appends observations, the
edge API appends rare commands (inspection start/end, profile revisions) and serves reads.

Layout:
  schema.py     SQLite tables
  types.py      StoreError, RawRecord, rover_clock
  core.py       open (epoch, edge identity), transactions, appends, reads
  blobs.py      evidence blob files
  retention.py  acknowledgments, retention and disk-pressure pruning (gap records)
  live.py       single-row live snapshot + preview (latest wins, never a lane record)
"""

from .blobs import BlobsMixin
from .core import StoreCore
from .live import LiveMixin
from .retention import RetentionMixin
from .types import RawRecord, StoreError, rover_clock


class EdgeStore(LiveMixin, RetentionMixin, BlobsMixin, StoreCore):
    """One connection per thread/process. `path` is the store directory."""


__all__ = ["EdgeStore", "RawRecord", "StoreError", "rover_clock"]
