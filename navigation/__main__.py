"""Run with python -m navigation --demo, or tail a same-host vision server run."""
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from navigation.feed import latest, map_svg
from navigation.preview import Preview, Settings
from vision.schema import DetectionEvent, StreamHealth


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true")
    source.add_argument("--run-dir", type=Path)
    p.add_argument("--source-mode", choices=("LIVE", "REPLAY", "SAMPLE"),
                   help="Declare the server's source; required with --run-dir")
    p.add_argument("--seconds", type=float, default=120., help="Maximum run duration")
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--ble-speech", action="store_true", help="Opt in to STOP and speech only")
    p.add_argument("--ble-name", default="BOB-ControllerBench")
    return p


class Report:
    def __init__(self, directory, source):
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self.source = source
        self.trace = (directory / "decisions.jsonl").open("w", buffering=1)
        self.last = None
        self.last_print = -float("inf")

    def write(self, preview, decision, mono, speech="disabled"):
        data = dict(asdict(decision), source_mode=self.source, monotonic_s=mono,
                    speech_delivery=speech)
        self.trace.write(json.dumps(data) + "\n")
        key = (decision.state, decision.reason, decision.goal_cell, decision.camera_cell)
        if key != self.last or mono - self.last_print >= 1:
            print(f"{decision.state}: {decision.reason}; suggestion={decision.suggested_direction}; "
                  f"visited={decision.visited_cells}; speech={speech}", flush=True)
            temporary = self.directory / "map.svg.tmp"
            temporary.write_text(map_svg(preview, decision))
            temporary.replace(self.directory / "map.svg")
            self.last, self.last_print = key, mono

    def close(self):
        self.trace.close()


async def run(args):
    preview = Preview(Settings(mission_s=args.seconds))
    directory = args.output_dir or Path("runs/navigation") / datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S.%fZ")
    report = Report(directory, "SYNTHETIC" if args.demo else args.source_mode)
    speaker = None
    print(f"PREVIEW ONLY — motor output disabled. Results: {directory}", flush=True)
    try:
        if args.demo:
            from navigation.demo import steps
            for event, health, wall, mono in steps():
                report.write(preview, preview.update(event, health, wall, mono), mono,
                             "simulated_only")
            return
        if args.ble_speech:
            from navigation.speech import Speaker
            speaker = await Speaker.connect(args.ble_name)
        started = time.monotonic()
        previous_state = None
        while time.monotonic() - started < args.seconds:
            try:
                event = latest(args.run_dir / "detections.jsonl", DetectionEvent)
                health = latest(args.run_dir / "stream_health.jsonl", StreamHealth)
            except (OSError, ValueError) as exc:
                # Invalid latest records invalidate the observation immediately.
                event = health = None
                if previous_state != "STOPPED":
                    print(f"Input unavailable: {exc}", flush=True)
            mono, wall = time.monotonic(), time.time_ns()
            decision = preview.update(event, health, wall, mono)
            delivery = "disabled" if speaker is None else "idle"
            if speaker:
                if decision.state in {"STOPPED", "FAULT", "COMPLETE"} and previous_state != decision.state:
                    await speaker.stop()
                if decision.announcement:
                    age = (wall - min(event.jetson_receive_ts_ns, health.emitted_ts_ns)) / 1e9
                    sent = await speaker.announce(mono + preview.settings.stale_s - age)
                    delivery = "write_acknowledged" if sent else "expired_dropped"
            report.write(preview, decision, mono, delivery)
            previous_state = decision.state
            if decision.state in {"FAULT", "COMPLETE"}:
                break
            await asyncio.sleep(.1)
    finally:
        try:
            if speaker:
                await speaker.close()
        finally:
            report.close()
            print("Preview ended; no motion commands were sent.", flush=True)


def main():
    p = parser()
    args = p.parse_args()
    if args.run_dir and not args.source_mode:
        p.error("--run-dir requires --source-mode to label live versus replay input")
    if args.run_dir and not args.run_dir.is_dir():
        p.error("--run-dir must be an existing vision server output directory")
    if args.ble_speech and (args.demo or args.source_mode != "LIVE"):
        p.error("BLE speech requires --run-dir and --source-mode LIVE")
    try:
        Settings(mission_s=args.seconds)
    except ValueError as exc:
        p.error(str(exc))
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        p.exit(1, f"Preview stopped: {exc}\n")


if __name__ == "__main__":
    main()
