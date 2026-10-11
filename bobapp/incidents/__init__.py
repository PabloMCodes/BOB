"""Incident confirmation policy (plan §8, D7) — application layer, runs on the rover (D3).

Layout:
  params.py       configs/incidents.yaml (+ hash recorded with every incident)
  classify.py     per-frame inputs: assessment / C7 record -> positive / negative / neutral per subject
  policy.py       the deterministic state machine (candidate, confirmed, discarded, ended, reopened)
  records.py      transition -> bob-app incident record
  calibration.py  §8.6 acceptance over a labeled recording
"""

from .classify import FrameClass, FrameInput, Subject, frame_input
from .params import PolicyParams
from .policy import FrameRef, IncidentPolicy, StepResult, Transition
from .records import incident_body, subject_label

__all__ = ["FrameClass", "FrameInput", "FrameRef", "IncidentPolicy", "PolicyParams", "StepResult", "Subject",
           "Transition", "frame_input", "incident_body", "subject_label"]
