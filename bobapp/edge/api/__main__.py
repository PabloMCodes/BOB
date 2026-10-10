"""Run the edge API (separate process from vision.server; reads the same store).

    uv run python -m bobapp.edge.api [--edge-config F] [--host H] [--port P]

Token: `BOB_EDGE_TOKEN` (configs/edge.yaml api.token_env) from the environment or `.env`. Without it,
the API listens on loopback only. Default host "" binds every interface with one IPv4 and one IPv6
socket (asyncio makes a "::" socket IPv6-only) — the Step 5 hotspot handed out IPv6 only.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from bobapp.edge.config import load_edge_config, store_path

from .app import create_app
from .auth import load_token, resolve_bind


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--edge-config", type=Path)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    config = load_edge_config(args.edge_config)
    token = load_token(config["api"]["token_env"])
    host, warning = resolve_bind(args.host, config["api"]["host"], token)
    if warning:
        print(f"[edge-api] WARNING: {warning}", flush=True)
    port = config["api"]["port"] if args.port is None else args.port
    app = create_app(store_path(config), config["edge_id"], config, token, config["clock_synced"])
    print(f"[edge-api] {config['edge_id']} store {store_path(config)} on {host or 'all interfaces'}:{port} "
          f"({'token required' if token else 'no token, loopback only'})", flush=True)
    uvicorn.run(app, host=host, port=port, log_level="warning", ws="websockets-sansio")


if __name__ == "__main__":
    main()
