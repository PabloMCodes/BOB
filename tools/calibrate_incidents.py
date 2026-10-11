"""Calibrate the incident policy (plan §8.6) on a labeled recording.

    uv run python -m tools.calibrate_incidents runs/server/<time>/stream.bobrec --rule glasses \\
        --segments "wearing:0-10,not_wearing:12-24,wearing:26-36" [--config F] [--incidents-config F]

Runs the recording through the shared frame path (tools.replay_detect.run), assesses every frame
under a synthetic inspection that requires only `--rule`, feeds the same policy the rover runs and
checks the agreed targets (bobapp/incidents/calibration.py). Segments are seconds from the first frame.
Exit status 1 when a target fails. Passing on recordings is a precondition for `calibrated: true`,
not proof of worksite performance.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

from bobapp.contracts import REQUIREMENT_RULES, SourceMode, WorksiteProfile
from bobapp.edge.publish.assessment import assess
from bobapp.edge.publish.observation import rule_statuses
from bobapp.edge.store import ActiveInspection
from bobapp.incidents import IncidentPolicy, PolicyParams, frame_input
from bobapp.incidents.calibration import evaluate
from tools.replay_client import load
from tools.replay_detect import parse_segments, run
from vision.config import REPO_ROOT, load_config
from vision.pipeline import Pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--rule", required=True, choices=sorted(REQUIREMENT_RULES.values()))
    parser.add_argument("--segments", required=True, help='e.g. "wearing:0-10,not_wearing:12-24"')
    parser.add_argument("--config", type=Path)
    parser.add_argument("--incidents-config", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    config, params = load_config(args.config), PolicyParams.load(args.incidents_config)
    segments = [(v.value, a, b) for v, a, b in parse_segments(args.segments)]
    pipeline = Pipeline.from_config(config)
    rules = rule_statuses(pipeline)
    if not any(r.name == args.rule and r.active for r in rules):
        raise SystemExit(f"rule {args.rule!r} is inactive for {pipeline.model_id}: nothing to calibrate")
    requirement = next(req for req, rule in REQUIREMENT_RULES.items() if rule == args.rule)
    profile = WorksiteProfile.build("calibration", 1, "calibration", {r: r == requirement for r in REQUIREMENT_RULES})
    inspection = ActiveInspection(uuid4(), "calibration", 1, profile.sha256, SourceMode.REPLAY, profile)
    policy, frames, transitions = IncidentPolicy(params), [], []

    def on_frame(outcome, detection):
        conf = {v.rule: v.violation.conf for v in detection.result.verdicts if v.violation is not None}
        frame = frame_input(detection.event, assess(detection.verdicts, rules, inspection), None, conf)
        frames.append(frame)
        transitions.extend(policy.step(frame).transitions)

    run(load(args.recording), pipeline, config, on_frame=on_frame)
    transitions.extend(policy.end_inspection().transitions)
    t0 = frames[0].ts_ns if frames else 0
    result = evaluate(frames, transitions, segments, params)
    result.update(recording=str(args.recording), rule=args.rule, model_id=pipeline.model_id, frames=len(frames),
                  calibrated_flag_in_config=params.calibrated,
                  transitions=[{"t_s": round((t.ts_ns - t0) / 1e9, 2), "transition": t.kind.value,
                                "end_reason": t.end_reason.value if t.end_reason else None,
                                "incident": str(t.incident_id)[:8]} for t in transitions])
    out = args.out or REPO_ROOT / "runs" / "calibrate_incidents" / f"{args.recording.stem}_{time.strftime('%Y%m%d_%H%M%S')}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"-> {out}")
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
