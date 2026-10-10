"""Operator-laptop hub CLI (Milestone A: rover-to-laptop link without a frontend).

    uv run python -m bobapp.hub serve  [--hub-config F]      # sync rover (+ SAMPLE edge) and serve the frontend API
    uv run python -m bobapp.hub sync   [--hub-config F]      # long-running: replicate the rover store only
    uv run python -m bobapp.hub status [--hub-config F]      # link state, per-lane lag, gaps, evidence
    uv run python -m bobapp.hub tail   [--hub-config F] [--lane control] [--follow]

`status` and `tail` read the replica only; they never contact the rover. Hub times are laptop clock;
rover times are never subtracted from them.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import signal
import time
from pathlib import Path
from typing import Any

from bobapp.contracts import Lane, Record
from bobapp.edge.api.auth import load_token

from .config import http_base, load_hub_config, replica_path, sample_replica_path
from .replica import Replica
from .sync import HubSyncClient


def _ago(wall_ns: Any) -> str:
    return "never" if not wall_ns else f"{(time.time_ns() - wall_ns) / 1e9:.1f} s ago (laptop clock)"


def cmd_sync(config: dict[str, Any]) -> None:
    replica = Replica(replica_path(config))
    token = load_token(config["token_env"])

    def on_event(kind: str, data: Any) -> None:
        if kind == "connected":
            ws = data["workspace"]
            print(f"[hub] connected to {ws.edge_id} epoch {ws.store_epoch}"
                  + (" — NEW STORE (previous replica archived)" if data["new_store"] else "")
                  + (f" — gaps before sync: {dict((k.value, v) for k, v in data['gaps'].items())}" if data["gaps"] else ""),
                  flush=True)
        elif kind == "disconnected":
            print(f"[hub] DISCONNECTED ({data}) — rover state unknown since last contact; retrying", flush=True)

    async def main() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        client = HubSyncClient(replica, config, token, config["edge_url"], http_base(config["edge_url"]), on_event)
        print(f"[hub] {config['hub_id']} -> {config['edge_url']} replica {replica.path}", flush=True)
        await client.run(stop)

    asyncio.run(main())


def cmd_serve(config: dict[str, Any]) -> None:
    import uvicorn

    from bobapp.edge.api.auth import resolve_bind

    from .api import create_hub_app
    token = load_token(config["api"]["token_env"])
    host, warning = resolve_bind(None, config["api"]["host"], token)
    if warning:
        print(f"[hub] WARNING: {warning}", flush=True)
    edges = {"rover": (config["edge_url"], config["token_env"], replica_path(config))}
    sample = config.get("sample") or {}
    if sample.get("edge_url"):
        edges["sample"] = (sample["edge_url"], sample["token_env"], sample_replica_path(config))

    async def background(stop: asyncio.Event) -> None:
        def log(name: str) -> Any:
            def on_event(kind: str, data: Any) -> None:
                if kind == "connected":
                    print(f"[hub:{name}] connected to {data['workspace'].edge_id}"
                          + (" — NEW STORE" if data["new_store"] else ""), flush=True)
                elif kind == "disconnected":
                    print(f"[hub:{name}] DISCONNECTED ({data}) — rover state unknown since last contact", flush=True)
            return on_event

        clients = [HubSyncClient(Replica(path), config, load_token(token_env), url, http_base(url), log(name))
                   for name, (url, token_env, path) in edges.items()]
        await asyncio.gather(*(c.run(stop) for c in clients))

    app = create_hub_app(config, token, {name: path for name, (_, _, path) in edges.items()}, background,
                         edge=(http_base(config["edge_url"]), load_token(config["token_env"])))
    print(f"[hub] API on {host or 'all interfaces'}:{config['api']['port']} — workspaces {list(edges)}", flush=True)
    uvicorn.run(app, host=host, port=config["api"]["port"], log_level="warning", ws="websockets-sansio")


def cmd_status(config: dict[str, Any]) -> None:
    replica = Replica(replica_path(config))
    link = replica.get_link() or {"state": "DISCONNECTED", "lanes": {}}
    print(f"link      {link['state']}   last contact {_ago(link.get('last_contact_wall_ns'))}")
    if link["state"] == "DISCONNECTED":
        print("          rover state since then: UNKNOWN (not stopped, not idle)")
    if link.get("last_error"):
        print(f"          last error: {link['last_error']}")
    for ws in replica.workspaces():
        counts = replica.counts(ws)
        print(f"workspace {ws.edge_id} epoch {ws.store_epoch} {'(archived, read-only)' if ws.archived else '(active)'}")
        cursors = replica.cursors(ws)
        for lane in Lane:
            lag = link.get("lanes", {}).get(lane.value, {}).get("behind") if not ws.archived else None
            print(f"  {lane.value:<11} {counts.get(lane.value, 0):>7} records   committed seq {cursors[lane]:>7}"
                  + (f"   behind {lag}" if lag is not None else ""))
        for gap in replica.gaps(ws):
            print(f"  GAP {gap['lane']} seq {gap['first_seq']}–{gap['last_seq']} ({gap['reason']})")
    print(f"evidence  {replica.blob_counts() or 'none'}")
    live_json, rx, _, preview_sha = replica.get_live()
    if live_json:
        live = json.loads(live_json)
        print(f"live      received {_ago(rx)}   source {live['source_mode'] or 'no run publishing'}   "
              f"preview {'yes' if preview_sha else 'no'}")


def _describe(record: Record) -> str:
    body = record.body
    if body.kind == "observation":
        e = body.event
        return (f"frame seq {e.seq_id} {len(e.boxes)} boxes pose_valid={e.pose_valid} "
                f"{ {k: v.value for k, v in body.frame_verdicts.items()} }")
    if body.kind == "track_point":
        return f"track session {str(body.session_id)[:8]} seg {body.segment} x={body.pose.x_m:.2f} z={body.pose.z_m:.2f}"
    if body.kind == "evidence":
        return f"evidence {body.sha256[:12]} {body.reason.value} {body.rules}"
    if body.kind == "gap":
        return f"GAP {body.lane.value} {body.first_seq}–{body.last_seq} {body.reason.value}"
    return body.kind + " " + body.model_dump_json(exclude={"kind"})[:120]


def cmd_tail(config: dict[str, Any], lane: str | None, follow: bool) -> None:
    replica = Replica(replica_path(config))
    last = 0
    while True:
        ws = replica.active_workspace()
        rows = replica.records(ws, Lane(lane) if lane else None, after_rowid=last) if ws else []
        for rowid, delivery, text in rows:
            record = Record.model_validate_json(text)
            print(f"{record.lane.value:<11} {record.seq:>6} {record.source_mode.value:<6} {delivery:<10} {_describe(record)}")
            last = rowid
        if not follow:
            return
        time.sleep(0.5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("serve", "sync", "status", "tail"))
    parser.add_argument("--hub-config", type=Path)
    parser.add_argument("--lane", choices=[lane.value for lane in Lane])
    parser.add_argument("--follow", action="store_true")
    args = parser.parse_args()
    config = load_hub_config(args.hub_config)
    if args.command == "serve":
        cmd_serve(config)
    elif args.command == "sync":
        cmd_sync(config)
    elif args.command == "status":
        cmd_status(config)
    else:
        cmd_tail(config, args.lane, args.follow)


if __name__ == "__main__":
    main()
