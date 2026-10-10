"""Build the SAMPLE edge store: a short, clearly labeled story for every dashboard view.

Everything is `source_mode = SAMPLE` in its own store (edge_id `sample-edge`), served by the normal
edge API and replicated by the hub into its own database, so it can never be counted as live or drawn
on a real pose. Producers that do not exist (person in path, walkway) appear only here.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any
from uuid import UUID

import cv2
import numpy as np

from bobapp.contracts import (
    APP_VERSION,
    EvidenceBody,
    EvidenceReason,
    FrameAssessment,
    FrameCounts,
    Hazard,
    IncidentBody,
    IncidentEndReason,
    IncidentKey,
    IncidentLocation,
    IncidentTransition,
    NoticeBody,
    ObservationBody,
    Record,
    RequirementAssessment,
    SourceMode,
    TrackPointBody,
    WorksiteProfile,
)
from bobapp.edge.publish.live import producers
from bobapp.edge.store import EdgeStore
from vision.schema import DetectionEvent, Pose

SAMPLE = SourceMode.SAMPLE
TEMPLATE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "app" / "valid" / "record_observation_live.json"
SESSION = UUID("5a3b1e00-0000-4000-8000-000000000001")
INSPECTION = UUID("5a3b1e00-0000-4000-8000-0000000000a1")
POLICY_SHA = hashlib.sha256(b"sample incident policy (not calibrated)").hexdigest()
ZONE_SHA = hashlib.sha256(b"sample zone profile").hexdigest()
T0 = 1_000_000_000_000  # iPhone clock of the first sample frame


def sample_path() -> list[tuple[float, Pose, bool]]:
    """(t_s, pose, valid): 3 m forward (-z), a 90° left turn, 2 m left (-x), then 1 s of lost tracking
    and 1 m more — two segments."""
    points = []
    for i in range(31):
        points.append((i * 0.2, Pose(x_m=0.0, y_m=0.0, z_m=-0.1 * i, yaw_rad=0.0), True))
    for i in range(1, 10):
        points.append((6.0 + i * 0.2, Pose(x_m=0.0, y_m=0.0, z_m=-3.0, yaw_rad=math.radians(10 * i)), True))
    for i in range(1, 21):
        points.append((8.0 + i * 0.2, Pose(x_m=-0.1 * i, y_m=0.0, z_m=-3.0, yaw_rad=math.pi / 2), True))
    for i in range(1, 6):
        points.append((12.0 + i * 0.2, Pose(x_m=-2.0, y_m=0.0, z_m=-3.0, yaw_rad=math.pi / 2), False))
    for i in range(1, 11):
        points.append((13.0 + i * 0.2, Pose(x_m=-2.0 - 0.1 * i, y_m=0.0, z_m=-3.0, yaw_rad=math.pi / 2), True))
    return points


def sample_jpeg(text: str) -> tuple[bytes, np.ndarray]:
    image = np.full((640, 480, 3), 40, np.uint8)
    for y, line in ((300, "SAMPLE"), (340, "not a real observation"), (380, text)):
        cv2.putText(image, line, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 255), 2)
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes(), image


def build(store: EdgeStore) -> dict[str, Any]:
    template = Record.model_validate_json(TEMPLATE.read_text()).body
    profile = WorksiteProfile.build("site-sample", 1, "SAMPLE worksite",
                                    {"eyewear": True, "helmet": True, "gloves": False, "vest": True, "boots": True})
    store.start_inspection(profile, SAMPLE, requested_by="sample builder", inspection_id=INSPECTION)
    store.append(NoticeBody(kind="notice", code="assessment_unavailable",
                            message="Required — assessment unavailable: boots (model has no safety-boots class)",
                            details={"requirement": "boots", "rule": "boots", "missing_classes": ["safety-boots"]}), SAMPLE)
    jpeg, pixels = sample_jpeg("no-safety-glasses")
    blob = store.put_blob(jpeg)
    pixels_sha = hashlib.sha256(pixels.tobytes()).hexdigest()
    segment, open_segment, events = 0, False, []
    for seq, (t, pose, valid) in enumerate(sample_path()):
        ts = T0 + int(t * 1e9)
        if not valid:
            segment, open_segment = (segment + 1 if open_segment else segment), False
        else:
            open_segment = True
            store.append(TrackPointBody(kind="track_point", session_id=SESSION, segment=segment, seq_id=seq,
                                        iphone_ts_ns=ts, packet="frame", pose=pose), SAMPLE)
        if seq % 5:
            continue  # one observed frame per second
        event = DetectionEvent.model_validate({**template.event.model_dump(), **{
            "event_id": UUID(int=0x5A3B1E00_0000_4000_8000_000000100000 + seq), "session_id": SESSION, "seq_id": seq,
            "iphone_frame_ts_ns": ts, "pose": pose if valid else None, "pose_valid": valid,
            "pose_dt_ms": 0.0 if valid else None, "pose_invalid_reason": None if valid else "tracking_not_normal",
            "tracking_state": "normal" if valid else "limited"}})  # validated: pose/reason consistency
        violation = seq in (20, 25, 30)
        assessment = FrameAssessment(inspection_id=INSPECTION, worksite_id="site-sample", profile_revision=1,
                                     no_requirements_selected=False, requirements=[
            RequirementAssessment(requirement="eyewear", status="not_detected" if violation else "detected"),
            RequirementAssessment(requirement="helmet", status="detected"),
            RequirementAssessment(requirement="gloves", status="not_required"),
            RequirementAssessment(requirement="vest", status="not_assessed", reason="no judged subject"),
            RequirementAssessment(requirement="boots", status="assessment_unavailable",
                                  reason="rule boots inactive: model lacks safety-boots")])
        frame_verdicts = {**template.frame_verdicts, "glasses": "not_wearing" if violation else "wearing"}
        evidence = blob if seq == 25 else None
        if evidence:
            store.append(EvidenceBody(kind="evidence", sha256=blob, size_bytes=len(jpeg), media_type="image/jpeg",
                                      image_pixels_sha256=pixels_sha, event_id=event.event_id, session_id=SESSION,
                                      seq_id=seq, iphone_frame_ts_ns=ts, model_id=event.model_id,
                                      image_size=event.image_size, reason=EvidenceReason.DERIVED_BOX,
                                      rules=["glasses"], pose=pose, pose_valid=True), SAMPLE)
        store.append(ObservationBody(kind="observation", event=event, rules=template.rules,
                                     verdicts=template.verdicts if violation else [], frame_verdicts=frame_verdicts,
                                     image_pixels_sha256=pixels_sha, evidence_sha256=evidence, scene=None,
                                     assessment=assessment), SAMPLE)
        events.append((seq, event, pose if valid else None))
    by_seq = {seq: (event, pose) for seq, event, pose in events}

    def incident(uid: int, transition: str, hazard: Hazard, seq: int, **extra: Any) -> IncidentBody:
        event, pose = by_seq[seq]
        key = {Hazard.PPE: {"rule": "glasses"}, Hazard.RESTRICTED_ZONE: {"zone_id": "tape-1", "zone_profile_sha256": ZONE_SHA},
               Hazard.WALKWAY: {"zone_id": "walkway-a"}}.get(hazard, {})
        return IncidentBody(
            kind="incident", incident_id=UUID(int=0x5A3B1E00_0000_4000_8000_000000200000 + uid),
            transition=IncidentTransition(transition), key=IncidentKey(inspection_id=INSPECTION, profile_revision=1,
                                                                        session_id=SESSION, hazard=hazard, **key),
            policy_version=1, policy_params_sha256=POLICY_SHA, calibrated=False,
            observed_iphone_ts_ns=event.iphone_frame_ts_ns, counts=FrameCounts(positive=5, negative=1, neutral=2),
            event_ids=[event.event_id], location=IncidentLocation(event_id=event.event_id, pose=pose) if pose
            else IncidentLocation(event_id=event.event_id, unlocalized_reason="tracking_not_normal"), **extra)

    for body in (incident(1, "candidate", Hazard.PPE, 20), incident(1, "confirmed", Hazard.PPE, 25, evidence_sha256=[blob]),
                 incident(1, "ended", Hazard.PPE, 35, end_reason=IncidentEndReason.CONDITION_NOT_OBSERVED),
                 incident(2, "candidate", Hazard.RESTRICTED_ZONE, 40), incident(2, "confirmed", Hazard.RESTRICTED_ZONE, 45),
                 incident(3, "confirmed", Hazard.PERSON_IN_PATH, 50),
                 incident(4, "candidate", Hazard.WALKWAY, 60), incident(4, "discarded", Hazard.WALKWAY, 65)):
        store.append(body, SAMPLE)
    preview_jpeg, _ = sample_jpeg("preview")
    store.put_live({
        "running": True, "run_id": "sample", "source_mode": "SAMPLE",
        "feeds_mono_ns": {"video": None, "results": None, "pose": None, "health": None},
        "pose": None, "health": None,
        "preview": {"event_id": str(by_seq[25][0].event_id), "session_id": str(SESSION), "seq_id": 25,
                    "image_size": {"width": 480, "height": 640}, "source_image_size": {"width": 480, "height": 640},
                    "sha256": hashlib.sha256(preview_jpeg).hexdigest()},
        "capabilities": {"model_id": "sample", "rules": [r.model_dump(mode="json") for r in template.rules],
                         "producers": [{**p.model_dump(mode="json"), "note": "SAMPLE data only — " + (p.note or p.status.value)}
                                       for p in producers(zones_enabled=True)]},
        "edge": None}, preview_jpeg, hashlib.sha256(preview_jpeg).hexdigest())
    return {"app_version": APP_VERSION, "store_epoch": str(store.store_epoch),
            "lanes": {lane.value: info.head_seq for lane, info in store.lane_info().items()}}
