"""Short, operator-authorized camera-guided steps. Dry run unless --execute.

Run on the Jetson in an interactive terminal. No raw camera decoder or second
model: this consumes the same admitted C2/C3 events as the navigation preview.
"""
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import sys
import termios
import time
import tty

from navigation.feed import latest, map_svg
from navigation.run_source import read_run_info
from navigation.step import StepSettings, StepSupervisor
from vision.schema import DetectionEvent, StreamHealth


class Keyboard:
    """Read current input only. Stop/quit takes priority over any queued spaces."""
    def __init__(self, on_input):
        self.on_input = on_input
        self.fd = sys.stdin.fileno()
        self.saved = None

    def __enter__(self):
        self.saved = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        termios.tcflush(self.fd, termios.TCIFLUSH)
        asyncio.get_running_loop().add_reader(self.fd, self.read)
        return self

    def read(self):
        data = os.read(self.fd, 128)
        self.on_input(data.decode("ascii", errors="ignore") if data else "q")

    def __exit__(self, *_):
        asyncio.get_running_loop().remove_reader(self.fd)
        termios.tcsetattr(self.fd, termios.TCSANOW, self.saved)


def input_action(keys):
    keys = keys.lower()
    if "q" in keys or "\x03" in keys or "\x04" in keys:
        return "quit"
    if "s" in keys or "\x1b" in keys:
        return "stop"
    if "r" in keys:
        return "resume"  # Never combine R and SPACE into a motion authorization.
    if " " in keys:
        return "step"
    return None


async def run(args):
    info = read_run_info(args.run_dir)
    if args.execute and info["source_mode"] != "LIVE":
        raise ValueError("physical execution requires a vision server declared LIVE")
    settings = StepSettings(args.seconds, args.steps, args.pulse_ms)
    # Connect before starting the short mission clock. Startup sends STOP only.
    link = None
    if args.execute:
        from navigation.drive import PulseLink
        print("Connecting to ESP32; startup remains stopped...", flush=True)
        link = await PulseLink.connect(args.ble_name)
    supervisor = StepSupervisor(settings, started=time.monotonic())
    directory = args.output_dir or Path("runs/navigation") / (
        "supervised_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ"))
    trace = None
    task = None
    abort = asyncio.Event()
    quit_requested = False
    last_print = None
    pending_stop = False
    loop = asyncio.get_running_loop()

    def record(kind, **extra):
        trace.write(json.dumps(dict(kind=kind, wall_ts_ns=time.time_ns(),
                    monotonic_s=time.monotonic(), mode="EXECUTE" if link else "DRY_RUN",
                    source_mode=info["source_mode"], run_id=info["run_id"],
                    measured_wheel_velocity=None, **extra)) + "\n")

    async def step(request):
        try:
            record("step_requested", request=asdict(request))
            if link:
                sent = await link.pulse(request,
                    lambda: supervisor.allowed(request, time.monotonic()), abort)
                record("step_finished", motion_write_acknowledged=sent,
                       controller_status=asdict(link.last_status))
            else:
                await asyncio.sleep(request.pulse_ms / 1000)
                record("step_finished", motion_write_acknowledged=False, simulated=True)
        finally:
            supervisor.finished(time.time_ns(), time.monotonic())

    async def speech(deadline):
        sent = await link.announce(deadline, lambda: not abort.is_set()
                                   and not supervisor.paused and not supervisor.fault)
        record("speech", write_acknowledged=sent, audible_playback_verified=False)

    def on_input(keys):
        nonlocal task, quit_requested, pending_stop
        action = input_action(keys)
        if action in {"stop", "quit"}:
            supervisor.pause("operator stop")
            abort.set()
            pending_stop = True
            quit_requested = quit_requested or action == "quit"
        elif action == "resume":
            record("resume", accepted=supervisor.resume())
        elif action == "step":
            # This callback never queues commands. A busy/settling/blocked
            # space is discarded, and the caller must press again when READY.
            request = supervisor.request() if task is None else None
            if request is not None:
                abort.clear()
                task = asyncio.create_task(step(request))
            else:
                record("step_refused", phase=supervisor.phase())

    def shutdown():
        on_input("q")

    try:
        directory.mkdir(parents=True, exist_ok=True)
        trace = (directory / "steps.jsonl").open("w", buffering=1)
        (directory / "settings.json").write_text(json.dumps(
            dict(asdict(settings), execute=args.execute, speech=args.speech, run_info=info), indent=2))
        print(f"{'PHYSICAL STEPS' if link else 'DRY RUN: motors disabled'} — {info['source_mode']}. "
              f"Logs: {directory}\nR: release host pause (no movement). SPACE: one suggested step. "
              "S/ESC: stop and pause. Q/Ctrl-C: stop and quit.\n"
              f"Each step: {settings.pulse_ms} ms, then at least 1 s stopped. "
              "Check the displayed direction and wheel sweep before each SPACE.\n"
              "Open-loop PWM up to 85/255; speed/stopping distance unmeasured. "
              "No automatic obstacle or edge avoidance.", flush=True)
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            loop.add_signal_handler(sig, shutdown)
        with Keyboard(on_input):
            while not quit_requested:
                if task is not None and task.done():
                    try:
                        task.result()
                    except Exception as exc:
                        supervisor.fail(f"{type(exc).__name__}: {exc}")
                    task = None
                if pending_stop and task is None:
                    if link:
                        # Serialize ALL radio operations, including stops, so
                        # keyboard callbacks cannot arm during a pending STOP.
                        task = asyncio.create_task(link.stop())
                    pending_stop = False
                try:
                    if read_run_info(args.run_dir) != info:
                        supervisor.fail("vision server run changed; restart required")
                    event = latest(args.run_dir / "detections.jsonl", DetectionEvent)
                    health = latest(args.run_dir / "stream_health.jsonl", StreamHealth)
                    if event and event.jetson_receive_ts_ns < info["started_ts_ns"]:
                        raise ValueError("detection predates current server run")
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    event = health = None
                    supervisor.pause(f"invalid camera input: {exc}")
                mono, wall = time.monotonic(), time.time_ns()
                decision = supervisor.update(event, health, wall, mono)
                if supervisor.active and not supervisor.allowed(supervisor.active, mono):
                    abort.set()
                if supervisor.paused or supervisor.fault or decision.state in {"STOPPED", "FAULT", "COMPLETE"}:
                    abort.set()
                    if last_print is not None and last_print[0] not in {"PAUSED", "FAULT", "COMPLETE"}:
                        pending_stop = True
                if (decision.announcement and args.speech and link and task is None
                        and not supervisor.paused and not supervisor.fault):
                    abort.clear()
                    age = (wall - min(event.jetson_receive_ts_ns, health.emitted_ts_ns)) / 1e9
                    task = asyncio.create_task(speech(mono + supervisor.preview.settings.stale_s - age))
                phase = supervisor.phase()
                record("observation", phase=phase, advisory=asdict(decision), attempts=supervisor.attempts)
                if phase != last_print:
                    print(f"{phase[0]}: {phase[1]} [{supervisor.attempts}/{settings.max_steps} steps]", flush=True)
                    # Keep the existing map honestly labeled as advisory only.
                    advisory_map = map_svg(supervisor.preview, decision).replace(
                        "PREVIEW: motors disabled; obstacle clearance unknown",
                        "ADVISORY camera trail; clearance unknown; see steps.jsonl")
                    (directory / "map.svg").write_text(advisory_map)
                    last_print = phase
                if phase[0] in {"FAULT", "COMPLETE"}:
                    break
                await asyncio.sleep(.025)
    finally:
        abort.set()
        try:
            if task:
                await task  # Finite BLE timeouts; let pulse finally send STOP.
        finally:
            try:
                if link:
                    await link.close()
            finally:
                if trace:
                    trace.close()
                for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                    loop.remove_signal_handler(sig)
                print("Test ended; " + ("STOP and disconnect requested." if link
                                           else "no BLE connection was opened."), flush=True)
    if supervisor.fault:
        raise RuntimeError(supervisor.fault)
    return directory


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir", type=Path, required=True, help="current same-host vision.server output")
    p.add_argument("--execute", action="store_true", help="enable one physical pulse per SPACE; LIVE only")
    p.add_argument("--speech", action="store_true", help="speak confirmed Missing PPE while stopped")
    p.add_argument("--seconds", type=float, default=60.)
    p.add_argument("--steps", type=int, default=20)
    p.add_argument("--pulse-ms", type=int, default=100)
    p.add_argument("--ble-name", default="BOB-ControllerBench")
    p.add_argument("--output-dir", type=Path)
    args = p.parse_args()
    try:
        StepSettings(args.seconds, args.steps, args.pulse_ms)
        info = read_run_info(args.run_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        p.error(f"{exc}. Use the current server's run directory (restart an older server).")
    if args.execute and info["source_mode"] != "LIVE":
        p.error("--execute refuses REPLAY/SAMPLE server runs")
    if args.speech and not args.execute:
        p.error("--speech requires --execute")
    if not sys.stdin.isatty():
        p.error("an interactive terminal is required; use ssh -t, never nohup for driving")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        p.exit(1, f"Supervised test stopped: {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
