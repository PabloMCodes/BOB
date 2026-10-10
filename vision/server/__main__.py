"""Run the stream server with the upright debug view.

    uv run python -m vision.server [--record] [--no-view] [--port 8765] [--run-dir DIR]

Writes <run_dir>/stream_health.jsonl (C3, every timing.health_interval_ms), summary.json on exit,
and stream.bobrec with --record (replayable with tools/replay_client).
"""

from __future__ import annotations

import argparse
import json
import signal
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from vision.config import REPO_ROOT, load_config
from vision.schema import StreamHealth

from .transport import FrameServer, ServerThread
from .view import stats_lines, upright_view


def main() -> None:
    config = load_config()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=config["server"]["host"])
    parser.add_argument("--port", type=int, default=config["server"]["port"])
    parser.add_argument("--record", action="store_true", help="save every received message to stream.bobrec")
    parser.add_argument("--no-view", action="store_true", help="headless: decode frames, no window")
    parser.add_argument("--run-dir", type=Path, default=None, help="default: server.run_dir/<time>")
    args = parser.parse_args()

    run_dir = args.run_dir or REPO_ROOT / config["server"]["run_dir"] / time.strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    health_file = open(run_dir / "stream_health.jsonl", "w")
    record = open(run_dir / "stream.bobrec", "wb") if args.record else None

    def on_health(h: StreamHealth) -> None:
        health_file.write(h.model_dump_json() + "\n")

    def shutdown(signum: int, _frame: Any) -> None:
        # SIGTERM (systemd on the Jetson) / SIGINT, also when started in the background. Only the
        # first signal interrupts; repeats (e.g. `uv run` forwarding it) must not abort the cleanup.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    server = FrameServer(config, record=record, on_health=on_health)
    thread = ServerThread(server, args.host, args.port)
    port = thread.start()
    print(f"[server] listening on ws://{args.host}:{port}  -> {run_dir}", flush=True)

    mount = config["camera"]["mount_orientation"]
    last_print = 0.0
    try:
        if not args.no_view:
            import cv2
        while True:
            frame = server.slot.take(timeout=0.05)
            if frame is not None:
                image = upright_view(frame, mount, stats_lines(server.monitor.stats()))
                if image is not None and not args.no_view:
                    cv2.imshow("BOB stream", image)
                server.monitor.processed(frame)
            if not args.no_view and (cv2.waitKey(1) & 0xFF) == ord("q"):
                break
            if time.monotonic() - last_print >= 1.0:
                last_print = time.monotonic()
                print("[server] " + " | ".join(stats_lines(server.monitor.stats())), flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        thread.stop()
        final = server.monitor.stats()
        (run_dir / "summary.json").write_text(json.dumps(
            {k: (str(v) if isinstance(v, UUID) else v) for k, v in final.__dict__.items()}, indent=2
        ))
        health_file.close()
        if record is not None:
            record.close()
        print("[server] final: " + " | ".join(stats_lines(final)), flush=True)


if __name__ == "__main__":
    main()
