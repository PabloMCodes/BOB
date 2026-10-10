"""Hub sync: the laptop side of C9.

Layout:
  client.py   HubSyncClient — connect, resume per lane, commit then acknowledge, epoch/gap handling
  link.py     link state machine (CONNECTED / CATCHING_UP / DISCONNECTED / NEW_STORE)
  fetcher.py  rate-capped, hash-verified evidence prefetch
  http.py     stdlib authenticated GET
"""

from .client import HubSyncClient
from .link import LinkState, LinkTracker

__all__ = ["HubSyncClient", "LinkState", "LinkTracker"]
