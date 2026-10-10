"""Dashboard Step 1: `bob-app` v1 contract — fixtures, one parser for every source, schema drift."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from bobapp.contracts import (
    APP_MESSAGE_MODELS,
    LiveState,
    Record,
    SourceMode,
    WorksiteProfile,
    app_json_schemas,
    parse_app_message,
)
from tools.export_app_schema import APP_SCHEMA_DIR
from tools.export_schema import SCHEMA_DIR, render
from vision.schema import json_schemas

FIXTURES = Path(__file__).parent / "fixtures" / "app"
VALID = sorted((FIXTURES / "valid").glob("*.json"))
INVALID = sorted((FIXTURES / "invalid").glob("*.json"))

# Each invalid fixture must fail for the *intended* reason, not just any reason.
EXPECTED_ERRORS = {
    "record_wrong_app_version": "app_version",
    "record_unknown_field": "Extra inputs are not permitted",
    "record_seq_zero": "seq",
    "record_bad_source_mode": "source_mode",
    "record_observation_in_track_lane": "does not belong in the track lane",
    "record_track_point_in_control_lane": "does not belong in the control lane",
    "observation_scene_other_event": "must reference this observation's event_id",
    "observation_verdict_inactive_rule": "subject verdicts must belong to active rules",
    "observation_missing_frame_verdict": "frame_verdicts must cover exactly the active rules",
    "observation_inactive_rule_without_reason": "inactive rules need missing_classes",
    "observation_not_wearing_without_violation": "violation box is present exactly",
    "assessment_unavailable_without_reason": "reason is required exactly",
    "assessment_none_selected_but_required": "no_requirements_selected must be true exactly",
    "evidence_bad_sha": "String should match pattern",
    "evidence_valid_pose_without_pose": "pose_valid=true needs a pose",
    "incident_ended_without_reason": "end_reason is required exactly",
    "incident_confirmed_with_end_reason": "end_reason is required exactly",
    "incident_reopened_without_interruption": "interruption_ns is required exactly",
    "incident_key_rule_and_zone": "incident key shape",
    "incident_person_in_path_with_rule": "incident key shape",
    "incident_too_much_evidence": "at most 10 items",
    "incident_location_pose_and_reason": "pose or an unlocalized_reason",
    "gap_inverted": "first_seq must be <= last_seq",
    "profile_sha_mismatch": "sha256 does not match the profile content",
    "profile_missing_requirement": "every requirement exactly once",
    "live_state_age_without_reason": "a value or a reason",
    "sync_hello_missing_lane": "every lane exactly once",
    "sync_batch_unordered": "strictly increasing seq",
    "sync_ack_negative_seq": "seq",
    "unknown_msg_type": "msg_type",
}


def test_every_invalid_fixture_has_an_expected_error():
    assert {p.stem for p in INVALID} == set(EXPECTED_ERRORS)


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.stem)
def test_valid_fixture_round_trips(path):
    doc = json.loads(path.read_text())
    msg = parse_app_message(doc)
    assert type(msg) is APP_MESSAGE_MODELS[doc["msg_type"]]
    assert parse_app_message(msg.model_dump_json()) == msg


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.stem)
def test_invalid_fixture_fails_for_its_reason(path):
    with pytest.raises(ValidationError) as err:
        parse_app_message(path.read_text())
    assert EXPECTED_ERRORS[path.stem] in str(err.value)


def test_one_consumer_reads_live_replay_and_sample_without_branching():
    """Step 1 gate: the same parser and the same field access work for every source mode."""
    seen = {}
    for name in ("live", "replay", "sample"):
        record = parse_app_message((FIXTURES / "valid" / f"record_observation_{name}.json").read_text())
        assert isinstance(record, Record)
        seen[record.source_mode] = (record.body.event.event_id, sorted(record.body.frame_verdicts))
    assert set(seen) == set(SourceMode)


def test_unknown_values_are_null_with_a_reason():
    idle = parse_app_message((FIXTURES / "valid" / "live_state_idle.json").read_text())
    assert isinstance(idle, LiveState) and idle.source_mode is None
    for feed in (idle.freshness.video, idle.freshness.results, idle.freshness.pose, idle.freshness.health):
        assert feed.age_ms is None and feed.reason


def test_profile_hash_covers_content():
    a = WorksiteProfile.build("site-a", 1, "A", dict.fromkeys(("eyewear", "helmet", "gloves", "vest", "boots"), False))
    b = WorksiteProfile.build("site-a", 1, "A", {**dict.fromkeys(("eyewear", "helmet", "gloves", "vest"), False), "boots": True})
    assert a.sha256 != b.sha256


def test_committed_app_json_schema_matches_code():
    for filename, schema in app_json_schemas().items():
        path = APP_SCHEMA_DIR / filename
        assert path.exists(), f"missing {path}; run uv run python -m tools.export_app_schema"
        assert path.read_text() == render(schema), f"{filename} drifted; run uv run python -m tools.export_app_schema"


def test_frozen_cv_schema_untouched():
    """`bob-app` must never change the frozen v2 CV contract."""
    for filename, schema in json_schemas().items():
        assert (SCHEMA_DIR / filename).read_text() == render(schema)
    assert not set(app_json_schemas()) & set(json_schemas())
