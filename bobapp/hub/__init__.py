"""Operator-laptop hub: replica of the rover store (C9 client) and, from Step 6, the frontend API (C10).

Layout:
  config.py   configs/hub.yaml (+ hub.local.yaml)
  replica/    SQLite replica: workspaces per rover store epoch, cursors, gaps, evidence, link/live
  sync/       sync client, link state machine, evidence prefetch
  __main__.py `uv run python -m bobapp.hub sync|status|tail`
"""
