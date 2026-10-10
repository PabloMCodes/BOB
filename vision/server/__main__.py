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

import numpy as np

from vision.config import REPO_ROOT, load_config
from vision.schema import StreamHealth

from .transport import FrameServer, ServerThread
from .view import decode_upright, overlay_stats, stats_lines


def main() -> None:
    config = load_config()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, help="runtime override, e.g. configs/footwear.yaml")
    parser.add_argument("--detect", action="store_true", help="run shared PPE pipeline, draw boxes and write C2 JSONL")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--record", action="store_true", help="save every received message to stream.bobrec")
    parser.add_argument("--no-view", action="store_true", help="headless: decode frames, no window")
    parser.add_argument("--run-dir", type=Path, default=None, help="default: server.run_dir/<time>")
    args = parser.parse_args()
    config = load_config(args.config)
    args.host = args.host or config["server"]["host"]
    args.port = config["server"]["port"] if args.port is None else args.port
    pipeline = None
    if args.detect:
        from vision.pipeline import Pipeline
        from vision.render import draw
        from .detection import detect_frame
        pipeline = Pipeline.from_config(config)
        print(f"[server] detection enabled: {pipeline.model_id}", flush=True)

    run_dir = args.run_dir or REPO_ROOT / config["server"]["run_dir"] / time.strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    health_file = open(run_dir / "stream_health.jsonl", "w")
    record = open(run_dir / "stream.bobrec", "wb") if args.record else None
    detections = open(run_dir / "detections.jsonl", "w") if pipeline is not None else None
    if pipeline is not None:
        (run_dir / "model.json").write_text(json.dumps({
            "model_id": pipeline.model_id, "names": pipeline.names,
            "model": config["model"], "footwear_model": config.get("footwear_model"),
        }, indent=2))

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
    inference_ms: list[float] = []
    last_print = 0.0
    try:
        if not args.no_view:
            import cv2
        while True:
            frame = server.slot.take(timeout=0.05)
            if frame is not None:
                lines, image = [], None
                if pipeline is not None:
                    state = server.monitor.stats()
                    detection = detect_frame(frame, pipeline, mount, state.session_id, state.stale)
                    if detection is not None:
                        event, result = detection.event, detection.result
                        detections.write(event.model_dump_json() + "\n")
                        detections.flush()
                        inference_ms.append(result.inference_ms)
                        image = draw(detection.image, result.boxes, config["render"]["categories"],
                                     hide=config["render"]["hide"])
                        lines.append(f"CV {result.inference_ms:.0f} ms | {len(result.boxes)} boxes | pose {event.pose_valid}")
                        lines.append("  ".join(f"{k} {v.value}" for k, v in detection.verdicts.items()))
                else:
                    image = decode_upright(frame, mount)
                if image is not None:
                    if not args.no_view:
                        image = overlay_stats(image, stats_lines(server.monitor.stats()) + lines)
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
        summary = {k: (str(v) if isinstance(v, UUID) else v) for k, v in final.__dict__.items()}
        if pipeline is not None:
            # process_* = rx -> DetectionEvent written (the Step 6 latency); inference = model passes only.
            summary.update(detected_frames=len(inference_ms),
                           inference_p50_ms=float(np.percentile(inference_ms, 50)) if inference_ms else None,
                           inference_p95_ms=float(np.percentile(inference_ms, 95)) if inference_ms else None)
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        health_file.close()
        if detections is not None:
            detections.close()
        if record is not None:
            record.close()
        print("[server] final: " + " | ".join(stats_lines(final)), flush=True)


if __name__ == "__main__":
    main()
