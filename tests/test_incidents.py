"""Dashboard Step 8: incident policy — §8.6 synthetic timelines (same style as test_association.py).

10 Hz frames on the iPhone clock; P / N / U = positive (not wearing) / negative (wearing) / neutral.
"""

from uuid import UUID, uuid4

import pytest

from bobapp.contracts import Hazard, IncidentEndReason, IncidentTransition as T
from bobapp.incidents import FrameClass, FrameInput, IncidentPolicy, PolicyParams, Subject, incident_body
from bobapp.incidents.calibration import evaluate
from vision.schema import Pose

PARAMS = PolicyParams.load()
GLASSES = Subject(Hazard.PPE, rule="glasses")
ZONE = Subject(Hazard.RESTRICTED_ZONE, zone_id="tape-1", zone_profile_sha256="a" * 64)
CLS = {"P": FrameClass.POSITIVE, "N": FrameClass.NEGATIVE, "U": FrameClass.NEUTRAL}
INSPECTION = UUID("00000000-0000-4000-8000-0000000000a1")
S1, S2 = UUID("00000000-0000-4000-8000-000000000001"), UUID("00000000-0000-4000-8000-000000000002")
POSE = Pose(x_m=1.0, y_m=0.0, z_m=-2.0, yaw_rad=0.5)


def frame(t_s, value, session=S1, subject=GLASSES, inspection=INSPECTION, retired=False, conf=0.6, pose=POSE):
    values = {} if value is None else {subject: CLS[value]}
    return FrameInput(event_id=uuid4(), session_id=session, ts_ns=int(t_s * 1e9), inspection_id=inspection,
                      profile_revision=1 if inspection else None, retired=retired, pose=pose,
                      unlocalized_reason=None if pose else "tracking_not_normal", values=values,
                      confidence={subject: conf} if value == "P" else {})


def play(policy, pattern, start=0.0, hz=10.0, **kw):
    """pattern: a string of P/N/U ('.' = no frame at that tick)."""
    out = []
    for i, c in enumerate(pattern):
        if c != ".":
            r = policy.step(frame(start + i / hz, c, **kw))
            out += [(round(t.ts_ns / 1e9 - 0, 2), t.kind, t.end_reason) for t in r.transitions]
    return out


def kinds(events):
    return [(k.value if hasattr(k, "value") else k) + (f":{r.value}" if r else "") for _, k, r in events]


def test_a_single_noisy_frame_confirms_nothing():
    p = IncidentPolicy(PARAMS)
    assert kinds(play(p, "N" * 10 + "P" + "N" * 30)) == ["candidate", "discarded"]


def test_alternating_sixty_percent_positive_never_confirms():
    p = IncidentPolicy(PARAMS)
    assert "confirmed" not in kinds(play(p, "PPPNN" * 12))


def test_sustained_positives_confirm_after_five_frames():
    p = IncidentPolicy(PARAMS)
    events = play(p, "P" * 10)
    assert kinds(events) == ["candidate", "confirmed"] and events[1][0] == 0.4  # 5th positive frame


def test_neutral_frames_count_neither_way():
    p = IncidentPolicy(PARAMS)
    events = play(p, "PUPUPUPUP")
    assert kinds(events) == ["candidate", "confirmed"] and events[1][0] == 0.8
    p2 = IncidentPolicy(PARAMS)
    assert "ended:condition_not_observed" not in kinds(play(p2, "P" * 6 + "U" * 40))   # unverified never clears


def test_lost_after_five_seconds_without_a_judged_frame():
    p = IncidentPolicy(PARAMS)
    events = play(p, "P" * 6 + "U" * 60)
    assert kinds(events) == ["candidate", "confirmed", "ended:not_assessed"] and events[-1][0] == pytest.approx(5.5)


def test_clearing_needs_stronger_evidence_than_confirming():
    p = IncidentPolicy(PARAMS)
    events = play(p, "P" * 10 + "N" * 40)
    assert kinds(events) == ["candidate", "confirmed", "ended:condition_not_observed"]
    # The trailing 3 s still holds the positives: 80 % negatives is reached at 3.3 s, 2.3 s after the
    # PPE went back on (inside the agreed clear_window_s + 1 s).
    assert events[-1][0] == pytest.approx(3.3)
    p2 = IncidentPolicy(PARAMS)
    assert kinds(play(p2, "P" * 10 + "NNNPP" * 8))[-1] == "confirmed"   # 60 % negatives: still open


def test_session_change_ends_and_a_new_session_confirms_separately():
    p = IncidentPolicy(PARAMS)
    first = play(p, "P" * 6)
    second = play(p, "P" * 6, start=10.0, session=S2)
    assert kinds(first) == ["candidate", "confirmed"]
    assert kinds(second) == ["ended:session_changed", "candidate", "confirmed"]
    ended, new = [t for t in p.episodes.values()], second
    assert len(ended) == 1 and ended[0].session_id == S2


def test_retired_session_frames_never_open_or_extend():
    p = IncidentPolicy(PARAMS)
    assert play(p, "P" * 10, retired=True) == []


def test_reopen_within_merge_gap_keeps_the_incident_id_after_it_a_new_one():
    p = IncidentPolicy(PARAMS)
    ids = []
    for start, pattern in ((0.0, "P" * 6 + "N" * 25), (5.5, "P" * 6), (6.1, "N" * 40), (30.0, "P" * 6)):
        for i, c in enumerate(pattern):
            ids += [(t.kind, t.incident_id, t.interruption_ns) for t in p.step(frame(start + i / 10, c)).transitions]
    assert [k.value for k, _, _ in ids] == ["candidate", "confirmed", "ended", "reopened", "ended", "candidate", "confirmed"]
    assert ids[3][1] == ids[0][1] and ids[3][2] > 0             # same incident, interruption recorded
    assert ids[5][1] != ids[0][1]                               # > merge_gap_s later: a new incident


def test_inspection_end_and_source_stop_close_open_incidents():
    p = IncidentPolicy(PARAMS)
    play(p, "P" * 6)
    no_inspection = p.step(frame(1.0, "P", inspection=None)).transitions
    assert [(t.kind, t.end_reason) for t in no_inspection] == [(T.ENDED, IncidentEndReason.INSPECTION_ENDED)]
    p2 = IncidentPolicy(PARAMS)
    play(p2, "P" * 6)
    play(p2, "P", start=5.0, subject=ZONE)
    closed = p2.end_inspection(IncidentEndReason.SOURCE_STOPPED).transitions
    assert sorted((t.kind.value, t.subject.hazard.value) for t in closed) == [("discarded", "restricted_zone"),
                                                                             ("ended", "ppe")]


def test_replayed_frames_never_create_extra_incidents():
    p = IncidentPolicy(PARAMS)
    frames = [frame(i / 10, "P") for i in range(10)]
    first = [t for f in frames for t in p.step(f).transitions]
    again = [t for f in frames for t in p.step(f).transitions]
    assert len(first) == 2 and again == []
    p2 = IncidentPolicy(PARAMS)
    three = [frame(i / 10, "P") for i in range(3)]       # 3 distinct positives: below confirm_min_frames
    replayed = [t.kind.value for _ in range(3) for f in three for t in p2.step(f).transitions]
    assert replayed == ["candidate"]                      # duplicates never add up to a confirmation
    assert p2.episodes and list(p2.episodes.values())[0].counts == [3, 0, 0]


def test_low_processing_rate_is_reported_not_hidden():
    p = IncidentPolicy(PARAMS)
    notices = [n for i in range(30) for n in p.step(frame(i * 0.5, "P")).notices]  # 2 Hz < 2.5 Hz
    assert [n[0] for n in notices] == ["confirmation_unavailable_rate"]
    notices = [n for i in range(40) for n in p.step(frame(20 + i / 10, "P")).notices]
    assert [n[0] for n in notices] == ["confirmation_rate_recovered"]


def test_deterministic_ids_and_records():
    a, b = IncidentPolicy(PARAMS), IncidentPolicy(PARAMS)
    fa = [frame(i / 10, "P") for i in range(6)]
    fb = [FrameInput(**{**f.__dict__, "event_id": uuid4()}) for f in fa]  # same times, different event ids
    ta = [t for f in fa for t in a.step(f).transitions]
    tb = [t for f in fb for t in b.step(f).transitions]
    assert [(t.incident_id, t.kind, t.ts_ns) for t in ta] == [(t.incident_id, t.kind, t.ts_ns) for t in tb]
    body = incident_body(ta[1], PARAMS, ["b" * 64])
    assert body.key.hazard == Hazard.PPE and body.key.rule == "glasses" and body.calibrated is False
    assert body.location.pose == POSE and body.counts.positive == 5 and body.policy_params_sha256 == PARAMS.sha256


def test_evidence_roles_first_confirm_best_last():
    p = IncidentPolicy(PARAMS)
    frames = [frame(i / 10, "P", conf=c) for i, c in enumerate([0.5, 0.9, 0.6, 0.6, 0.6])] + \
             [frame(0.5 + i / 10, "N") for i in range(30)]
    transitions = [t for f in frames for t in p.step(f).transitions]
    roles = {t.kind.value: [(r, ref.event_id) for r, ref in t.evidence] for t in transitions}
    assert roles["candidate"] == [("first", frames[0].event_id)]
    assert roles["confirmed"] == [("confirm", frames[4].event_id), ("best", frames[1].event_id)]
    assert roles["ended"] == [("last", frames[4].event_id)]


def test_reopen_evidence_frame_is_retained():
    p = IncidentPolicy(PARAMS)
    for i, c in enumerate("P" * 6 + "N" * 25):
        p.step(frame(i / 10, c))
    frames = [frame(5.5 + i / 10, c) for i, c in enumerate("PPPPPU")]
    results = [p.step(f) for f in frames]
    reopen = [t for r in results for t in r.transitions if t.kind == T.REOPENED]
    assert reopen and reopen[0].evidence[0][1].event_id == frames[4].event_id
    assert frames[3].event_id in results[3].retain                # kept between frames while ended


def test_ignored_frames_never_free_images_still_needed():
    p = IncidentPolicy(PARAMS)
    frames = [frame(i / 10, "P") for i in range(6)]
    for f in frames:
        p.step(f)
    needed = p.step(frame(0.5, "P")).retain                       # a replayed frame (same time again)
    assert frames[-1].event_id in needed
    assert frames[-1].event_id in p.step(frame(0.7, "P", retired=True)).retain


def test_unlocalized_frames_stay_unlocalized():
    p = IncidentPolicy(PARAMS)
    t = [t for i in range(6) for t in p.step(frame(i / 10, "P", pose=None)).transitions]
    body = incident_body(t[1], PARAMS, [])
    assert body.location.pose is None and body.location.unlocalized_reason == "tracking_not_normal"


def test_calibration_targets_pass_and_fail():
    p = IncidentPolicy(PARAMS)
    frames = [frame(i / 10, c) for i, c in enumerate("N" * 100 + "P" * 120 + "N" * 100)]  # 10 s / 12 s / 10 s
    transitions = [t for f in frames for t in p.step(f).transitions]
    good = evaluate(frames, transitions, [("wearing", 0, 10), ("not_wearing", 10, 22), ("wearing", 22, 32)], PARAMS)
    assert good["passed"], good
    noisy = IncidentPolicy(PARAMS)
    bad_frames = [frame(i / 10, c) for i, c in enumerate("P" * 10 + "N" * 90)]  # false positives while wearing
    bad_t = [t for f in bad_frames for t in noisy.step(f).transitions]
    result = evaluate(bad_frames, bad_t, [("wearing", 0, 10)], PARAMS)
    assert not result["passed"] and result["checks"][0]["confirmed_at_s"] == [0.4]
