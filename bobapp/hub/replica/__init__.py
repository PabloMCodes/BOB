"""Hub replica (laptop): the rover's records, evidence copies, link and live state.

Layout:
  schema.py  SQLite tables (one DB; rover data keyed by workspace = (edge_id, store_epoch))
  core.py    workspaces, idempotent commits, contiguous cursors, gap rows, reads
  blobs.py   evidence copies: hash-verified, atomic, explicit status
  state.py   link state + latest live state and preview
"""

from .blobs import BlobsMixin
from .core import PRUNED_BEFORE_SYNC, CommitResult, ReplicaCore, Workspace
from .state import StateMixin


class Replica(StateMixin, BlobsMixin, ReplicaCore):
    """One connection per thread."""


__all__ = ["PRUNED_BEFORE_SYNC", "CommitResult", "Replica", "Workspace"]
