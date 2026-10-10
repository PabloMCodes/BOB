"""Step 6: live-inference frame path — offline replay determinism, on/off scoring, server --detect.

Recordings are built from the bundled images in real ARKit sensor orientation, so the whole path
(JPEG -> upright -> pipeline -> C2 event) runs exactly as for a phone stream.
"""

import json
import signal
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import pytest
import ultralytics

from tools.replay_client import Record, replay
from tools.replay_detect import FrameOutcome, box_mismatches, parse_segments, run, score
from vision.config import REPO_ROOT, load_config
from vision.pipeline import Pipeline
from vision.ppe import Verdict
from vision.recording import write_record
from vision.schema import SCHEMA_VERSION, FramePacket, PosePacket, encode

CONFIG = load_config()
ASSETS = Path(ultralytics.__file__).parent / "assets"
IDENTITY = np.eye(4).reshape(-1).tolist()
MS = 1_000_000


def _frame(session, seq, ts, upright, orientation):
    # ARKit delivers the sensor image; portrait frames arrive rotated 90° (vision.orientation).
    sensor = upright if orientation == "landscape_left" else cv2.rotate(upright, cv2.ROTATE_90_COUNTERCLOCKWISE)
    # Near-lossless on purpose: the 2nd bus sunglasses are a borderline detection (conf 0.32-0.62) that
    # JPEG noise flips at q90 / q70 but not q98 / 95 / 85 / 80 (README Step 6). Here we test the path.
    jpeg = cv2.imencode(".jpg", sensor, [cv2.IMWRITE_JPEG_QUALITY, 98])[1].tobytes()
    msg = FramePacket(
        schema_version=SCHEMA_VERSION, msg_type="frame", session_id=session, seq_id=seq,
        iphone_frame_ts_ns=ts, tracking_state="normal", camera_transform=IDENTITY,
        image={"width": sensor.shape[1], "height": sensor.shape[0], "encoding": "jpeg",
               "device_orientation": orientation, "byte_length": len(jpeg)},
    )
    return Record(msg, jpeg, encode(msg, jpeg))


def _pose(session, seq, ts):
    msg = PosePacket(schema_version=SCHEMA_VERSION, msg_type="pose", session_id=session, seq_id=seq,
                     iphone_frame_ts_ns=ts, tracking_state="normal", camera_transform=IDENTITY)
    return Record(msg, b"", encode(msg))


@pytest.fixture(scope="module")
def recording():
    """zidane (rover mount, landscape_left) and bus (portrait) at 10 Hz, then bus after a 1 s gap."""
    s, zidane, bus = uuid4(), cv2.imread(str(ASSETS / "zidane.jpg")), cv2.imread(str(ASSETS / "bus.jpg"))
    return [
        _frame(s, 0, 1_000 * MS, zidane, "landscape_left"),
        _pose(s, 1, 1_050 * MS),
        _frame(s, 2, 1_100 * MS, bus, "portrait"),
        _frame(s, 3, 2_100 * MS, bus, "portrait"),  # 1 s silence > stale_ms -> pose invalid
    ]


@pytest.fixture(scope="module")
def pipeline():
    return Pipeline.from_config(CONFIG)


@pytest.fixture(scope="module")
def outcomes(recording, pipeline):
    return run(recording, pipeline, CONFIG)


def test_every_frame_processed_poses_skipped(outcomes):
    assert [o.event.seq_id for o in outcomes] == [0, 2, 3]
    assert [o.t_s for o in outcomes] == pytest.approx([0.0, 0.1, 1.1])


def test_replay_is_deterministic(recording, pipeline, outcomes):
    assert box_mismatches(outcomes, run(recording, pipeline, CONFIG)) == []


def test_replay_matches_pipeline_on_the_decoded_upright_image(recording, pipeline, outcomes):
    """No hidden differences between the stream path and calling the pipeline directly."""
    jpeg = recording[2].payload
    upright = cv2.rotate(cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR), cv2.ROTATE_90_CLOCKWISE)
    direct = pipeline(upright)
    fake = FrameOutcome(0.1, outcomes[1].event.model_copy(update={"boxes": direct.boxes}), outcomes[1].verdicts)
    assert box_mismatches([outcomes[1]], [fake]) == []


def test_rotation_and_ppe_verdicts_on_stream_frames(outcomes):
    zidane, bus = outcomes[0], outcomes[1]
    assert zidane.verdicts["glasses"] is Verdict.NOT_WEARING and zidane.verdicts["helmet"] is Verdict.NOT_WEARING
    # Both men's sunglasses are found only if bus came out upright (the other faces are unverified).
    assert sum(b.cls_name == "glasses" for b in bus.event.boxes) >= 2
    assert bus.verdicts["glasses"] is Verdict.WEARING
    assert bus.event.image_size.width < bus.event.image_size.height  # portrait -> upright portrait
    assert "boots" not in bus.verdicts  # inactive with SH17, never approximated


def test_pose_valid_only_while_stream_is_fresh(outcomes):
    assert [o.event.pose_valid for o in outcomes] == [True, True, False]
    assert outcomes[2].event.pose_invalid_reason == "stale"
    assert outcomes[2].event.boxes  # stale pose invalidates the pose, never drops the detection


def _outcome(t, verdict):
    return FrameOutcome(t, None, {"glasses": verdict})


def test_onoff_scoring():
    W, N, U = Verdict.WEARING, Verdict.NOT_WEARING, Verdict.UNVERIFIED
    outcomes = [_outcome(t / 10, v) for t, v in enumerate([W] * 9 + [N] + [U] * 5 + [N] * 5)]
    on, off = score(outcomes, "glasses", parse_segments("wearing:0-1, not_wearing:1-2"))
    assert (on.frames, on.judged, on.correct, on.accuracy) == (10, 10, 9, 0.9) and on.passed(0.8)
    assert (off.frames, off.judged, off.correct) == (10, 5, 5) and off.passed(0.8)  # unverified ignored


def test_onoff_any_false_wearing_fails():
    outcomes = [_outcome(t / 10, Verdict.NOT_WEARING) for t in range(9)] + [_outcome(0.9, Verdict.WEARING)]
    (off,) = score(outcomes, "glasses", parse_segments("not_wearing:0-1"))
    assert off.accuracy == 0.9 and off.false_wearing == 1 and not off.passed(0.8)


def test_onoff_nothing_judged_is_not_a_pass():
    (seg,) = score([_outcome(0.5, Verdict.UNVERIFIED)], "glasses", parse_segments("wearing:0-1"))
    assert seg.accuracy is None and not seg.passed(0.8)


@pytest.mark.parametrize("text", ["unverified:0-1", "wearing:2-1", "maybe:0-1"])
def test_bad_segments_rejected(text):
    with pytest.raises(ValueError):
        parse_segments(text)


def test_server_detect_end_to_end(tmp_path, recording):
    """Replay -> vision.server --detect: one valid C2 event per processed frame + latency summary."""
    from tests.test_server import _free_port, run as run_async

    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "vision.server", "--detect", "--no-view", "--host", "127.0.0.1",
         "--port", str(port), "--run-dir", str(tmp_path)],
        cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        for line in proc.stdout:  # model load + warm-up happen before "listening"
            if "listening" in line:
                break
        run_async(replay(recording[:3], f"ws://127.0.0.1:{port}", speed=1.0))
        deadline = 0
        while deadline < 100 and len((tmp_path / "detections.jsonl").read_text().splitlines()) < 2:
            import time
            time.sleep(0.05)
            deadline += 1
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=10) == 0
    finally:
        proc.kill()
    from vision.schema import DetectionEvent
    events = [DetectionEvent.model_validate_json(l) for l in (tmp_path / "detections.jsonl").read_text().splitlines()]
    assert [e.seq_id for e in events] == [0, 2] and all(e.pose_valid for e in events)
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["detected_frames"] == 2 and summary["inference_p95_ms"] > 0
    assert summary["process_p95_ms"] >= summary["inference_p50_ms"]  # rx -> event includes inference
