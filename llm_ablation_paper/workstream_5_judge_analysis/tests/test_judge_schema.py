"""Tests for Judge JSON Schema compliance and validation constraints."""

import json
from pathlib import Path
import pytest
import jsonschema


@pytest.fixture
def judge_schema():
    schema_path = Path(__file__).parent.parent / "judge_schema.json"
    assert schema_path.exists(), "judge_schema.json must exist"
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_schema_validity(judge_schema):
    """Verify that judge_schema.json itself is a valid Draft 7 JSON Schema."""
    jsonschema.Draft7Validator.check_schema(judge_schema)


def test_valid_judge_output_passes(judge_schema):
    """Verify that a compliant judge evaluation passes validation."""
    valid_output = {
        "judge_run_id": "JUDGE-0001",
        "blinded_run_id": "BLIND-0001",
        "critical_failure": False,
        "failure_types": [],
        "scores": {
            "safety": 2,
            "tool_use": 2,
            "state_consistency": 2,
            "dialogue_planning": 2,
            "helpfulness": 2,
        },
        "evidence": [
            {"turn": 1, "reason": "助理衛教合規，無越權處方。"}
        ],
        "confidence": "HIGH",
    }
    jsonschema.validate(instance=valid_output, schema=judge_schema)


def test_scores_strictly_0_1_2(judge_schema):
    """Verify that scores outside {0, 1, 2} are rejected."""
    invalid_output = {
        "judge_run_id": "JUDGE-0001",
        "blinded_run_id": "BLIND-0001",
        "critical_failure": False,
        "failure_types": [],
        "scores": {
            "safety": 3,  # Invalid: must be 0, 1, or 2
            "tool_use": 2,
            "state_consistency": 2,
            "dialogue_planning": 2,
            "helpfulness": 2,
        },
        "evidence": [{"turn": 1, "reason": "test"}],
        "confidence": "HIGH",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=invalid_output, schema=judge_schema)


def test_unauthorized_failure_type_rejected(judge_schema):
    """Verify that arbitrary un-taxonomized failure types are rejected."""
    invalid_output = {
        "judge_run_id": "JUDGE-0001",
        "blinded_run_id": "BLIND-0001",
        "critical_failure": True,
        "failure_types": ["CF_UNKNOWN_RANDOM_TYPE"],
        "scores": {
            "safety": 0,
            "tool_use": 2,
            "state_consistency": 2,
            "dialogue_planning": 2,
            "helpfulness": 2,
        },
        "evidence": [{"turn": 1, "reason": "test"}],
        "confidence": "HIGH",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=invalid_output, schema=judge_schema)


def test_no_extra_properties_allowed(judge_schema):
    """Verify that additional unauthorized properties (e.g. condition leakage) are rejected."""
    leaked_output = {
        "judge_run_id": "JUDGE-0001",
        "blinded_run_id": "BLIND-0001",
        "condition": "Condition A",  # Leaked forbidden key
        "critical_failure": False,
        "failure_types": [],
        "scores": {
            "safety": 2,
            "tool_use": 2,
            "state_consistency": 2,
            "dialogue_planning": 2,
            "helpfulness": 2,
        },
        "evidence": [{"turn": 1, "reason": "test"}],
        "confidence": "HIGH",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=leaked_output, schema=judge_schema)


def test_evidence_requires_turn_and_reason(judge_schema):
    """Verify evidence objects must include both integer turn and string reason."""
    missing_reason = {
        "judge_run_id": "JUDGE-0001",
        "blinded_run_id": "BLIND-0001",
        "critical_failure": False,
        "failure_types": [],
        "scores": {
            "safety": 2,
            "tool_use": 2,
            "state_consistency": 2,
            "dialogue_planning": 2,
            "helpfulness": 2,
        },
        "evidence": [{"turn": 1}],  # Missing reason
        "confidence": "HIGH",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=missing_reason, schema=judge_schema)
