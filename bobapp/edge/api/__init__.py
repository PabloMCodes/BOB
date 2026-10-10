"""Edge API (C9): rover-side sync and command service, a separate process over the edge store.

Layout:
  app.py       FastAPI app and the exact route set (no motion, arming or fault endpoints)
  sync.py      WS /v1/sync session: hello/welcome, live, prioritized throttled backfill, tail, acks
  live.py      LiveState from the store's live row (ages, unknown = null + reason)
  auth.py      pre-shared token and the loopback-only rule without one
  __main__.py  `uv run python -m bobapp.edge.api`
"""
