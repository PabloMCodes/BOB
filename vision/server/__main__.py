"""Run the stream server with the upright debug view.

    uv run python -m vision.server [--record] [--no-view] [--port 8765] [--run-dir DIR]
        [--detect [--zones F] [--edge [--edge-config F]]] [--source-mode LIVE|REPLAY|SAMPLE]

Writes <run_dir>/stream_health.jsonl (C3, every timing.health_interval_ms), summary.json on exit,
and stream.bobrec with --record (replayable with tools/replay_client).

--edge also publishes observations, track, evidence and live state to the rover edge store
(configs/edge.yaml, dashboard plan §5) through a bounded writer that never blocks the frame path.
--source-mode is declared, not inferred: the server cannot tell a replay client from a phone.
"""

from __future__ import annotations

import argparse
import json
import signal
import time
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

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
    parser.add_argument("--zones", type=Path, help="opt-in yellow-tape profile; requires --detect")
    parser.add_argument("--source-mode", choices=("LIVE", "REPLAY", "SAMPLE"), default=None,
                        help="label known replay/sample inputs honestly (default LIVE); applies to C7 and edge records")
    parser.add_argument("--zones-source-mode", choices=("LIVE", "REPLAY", "SAMPLE"), default=None,
                        help="alias of --source-mode (kept for existing commands)")
    parser.add_argument("--edge", action="store_true", help="publish to the rover edge store; requires --detect")
    parser.add_argument("--edge-config", type=Path, help="override of configs/edge.yaml")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--record", action="store_true", help="save every received message to stream.bobrec")
    parser.add_argument("--no-view", action="store_true", help="headless: decode frames, no window")
    parser.add_argument("--run-dir", type=Path, default=None, help="default: server.run_dir/<time>")
    args = parser.parse_args()
    if args.zones and not args.detect:
        parser.error("--zones requires --detect")
    if args.edge and not args.detect:
        parser.error("--edge requires --detect")
    if args.source_mode and args.zones_source_mode and args.source_mode != args.zones_source_mode:
        parser.error("--source-mode and --zones-source-mode disagree")
    source_mode = args.source_mode or args.zones_source_mode or "LIVE"
    inspector = None
    if args.zones:
        from vision.scene import SceneInspector, SceneWriter
        from vision.zones import draw_zone
        inspector = SceneInspector.from_file(args.zones)
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
    health_file = open(run_dir / "stream_health.jsonl", "w", buffering=1)
    record = open(run_dir / "stream.bobrec", "wb") if args.record else None
    detections = open(run_dir / "detections.jsonl", "w") if pipeline is not None else None
    # Local consumer metadata, not a C1/C2/C3 schema change. Write a fresh
    # identity even when a directory is reused; navigation must not resume it.
    run_info = run_dir / "run_info.json.tmp"
    run_info.write_text(json.dumps({
        "run_info_version": 1, "producer": "vision.server", "run_id": str(uuid4()),
        "source_mode": source_mode, "started_ts_ns": time.time_ns(),
    }))
    run_info.replace(run_dir / "run_info.json")
    scene_writer = SceneWriter(open(run_dir / "scene_findings.jsonl", "w")) if inspector else None
    if inspector:
        (run_dir / "zone_profile.json").write_text(inspector.profile.model_dump_json(indent=2))
    if pipeline is not None:
        (run_dir / "model.json").write_text(json.dumps({
            "model_id": pipeline.model_id, "names": pipeline.names,
            "model": config["model"], "footwear_model": config.get("footwear_model"),
        }, indent=2))

    publisher = None
    if args.edge:
        from bobapp.edge.config import load_edge_config, store_path
        from bobapp.edge.publish import EdgePublisher
        from bobapp.edge.store import EdgeStore
        edge_config = load_edge_config(args.edge_config)
        store = EdgeStore(store_path(edge_config), edge_config["edge_id"], edge_config["clock_synced"])
        publisher = EdgePublisher(store, edge_config, source_mode=source_mode, run_id=run_dir.name,
                                  pipeline=pipeline, render_config=config["render"],
                                  stale_ms=config["timing"]["stale_ms"], zones_enabled=inspector is not None)
        print(f"[server] edge store {store.path} epoch {store.store_epoch} ({source_mode})", flush=True)

    def on_health(h: StreamHealth) -> None:
        health_file.write(h.model_dump_json() + "\n")
        if publisher is not None:
            publisher.on_health(h)

    def shutdown(signum: int, _frame: Any) -> None:
        # SIGTERM (systemd on the Jetson) / SIGINT, also when started in the background. Only the
        # first signal interrupts; repeats (e.g. `uv run` forwarding it) must not abort the cleanup.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    server = FrameServer(config, record=record, on_health=on_health,
                         on_admit=publisher.on_admit if publisher is not None else None)
    thread = ServerThread(server, args.host, args.port)
    port = thread.start()
    print(f"[server] listening on ws://{args.host}:{port}  -> {run_dir}", flush=True)

    mount = config["camera"]["mount_orientation"]
    inference_ms: list[float] = []
    # Only the latest scene frame is retained for display; refresh its freshness on idle ticks.
    scene_image, scene_session, scene_rx_ns = None, None, None
    scene_count, scene_total_ms, scene_max_ms = 0, 0., 0.
    last_print = 0.0
    try:
        if not args.no_view:
            import cv2
        while True:
            frame = server.slot.take(timeout=0.05)
            if frame is not None:
                lines, image = [], None
                if pipeline is not None:
                    detection = detect_frame(frame, pipeline, mount, server.associator)
                    if detection is not None:
                        event, result = detection.event, detection.result
                        detections.write(event.model_dump_json() + "\n")
                        detections.flush()
                        inference_ms.append(result.inference_ms)
                        scene_record = None
                        if inspector:
                            scene_record, assessment = inspector.inspect(detection, source_mode)
                            scene_writer.submit(scene_record)
                            scene_count += 1
                            scene_total_ms += scene_record["scene_processing_ms"]
                            scene_max_ms = max(scene_max_ms, scene_record["scene_processing_ms"])
                            if not args.no_view:
                                scene_image = draw_zone(detection.image, assessment)
                                scene_session, scene_rx_ns = event.session_id, frame.rx_ts_ns
                        if publisher is not None:
                            publisher.on_detection(detection, scene_record)
                        image = draw(detection.image, result.boxes, config["render"]["categories"],
                                     hide=config["render"]["hide"])
                        lines.append(f"CV {result.inference_ms:.0f} ms | {len(result.boxes)} boxes | pose {event.pose_valid}")
                        lines.append("  ".join(f"{k} {v.value}" for k, v in detection.verdicts.items()))
                else:
                    image = decode_upright(frame, mount)
                if image is None:
                    server.monitor.undecodable(frame)  # corrupt JPEG: never analysed, but counted (I3)
                elif not args.no_view:
                    image = overlay_stats(image, stats_lines(server.monitor.stats()) + lines)
                    cv2.imshow("BOB stream", image)
                server.monitor.processed(frame)
            if scene_image is not None and not args.no_view:
                if scene_session != server.associator.current_session:
                    shown = np.zeros_like(scene_image)
                    label = f"{source_mode} - session changed; waiting for a current observation"
                else:
                    shown = scene_image.copy()
                    age_ms = (time.time_ns() - scene_rx_ns) / 1e6
                    label = f"{source_mode} - {'STALE last observation' if age_ms > config['timing']['stale_ms'] else 'current observation'} ({age_ms:.0f} ms since receive)"
                cv2.putText(shown, label, (8, shown.shape[0]-16), cv2.FONT_HERSHEY_SIMPLEX,
                            .5, (0, 0, 0), 3)
                cv2.putText(shown, label, (8, shown.shape[0]-16), cv2.FONT_HERSHEY_SIMPLEX,
                            .5, (255, 255, 255), 1)
                cv2.imshow("BOB restricted zones", shown)
            if not args.no_view and (cv2.waitKey(1) & 0xFF) == ord("q"):
                break
            if time.monotonic() - last_print >= 1.0:
                last_print = time.monotonic()
                print("[server] " + " | ".join(stats_lines(server.monitor.stats())), flush=True)
                if scene_writer:
                    print("[zones] " + json.dumps(scene_writer.stats()), flush=True)
                if publisher is not None:
                    print("[edge] " + json.dumps(publisher.writer.stats()), flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        thread.stop()
        final = server.monitor.stats()
        summary = {k: (str(v) if isinstance(v, UUID) else v) for k, v in final.__dict__.items()}
        if pipeline is not None:
            # process_* includes frame-consumer work (C2, optional scene analysis/submission and
            # primary view). Async scene storage and the separate zone window are not included.
            summary.update(detected_frames=len(inference_ms),
                           inference_p50_ms=float(np.percentile(inference_ms, 50)) if inference_ms else None,
                           inference_p95_ms=float(np.percentile(inference_ms, 95)) if inference_ms else None)
        if scene_writer:
            summary["zones"] = {"frames": scene_count, "scene_mean_ms": scene_total_ms / scene_count if scene_count else None,
                                "scene_max_ms": scene_max_ms, "writer": scene_writer.close()}
        if publisher is not None:
            summary["edge"] = publisher.close()  # bounded wait; unfinished work is reported, not hidden
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        health_file.close()
        if detections is not None:
            detections.close()
        if record is not None:
            record.close()
        print("[server] final: " + " | ".join(stats_lines(final)), flush=True)


if __name__ == "__main__":
    main()
