"""Tests for Judge input sanitizer, physical de-identification, and blinded-input leakage adversarial checks."""

import pytest
from llm_ablation_paper.workstream_5_judge_analysis.sanitizer import (
    build_judge_payload,
    assert_no_leakage,
    format_conversation_for_judge,
    validate_blinded_input_trajectory,
    SanitizationLeakError,
    BlindedContractViolationError,
)


@pytest.fixture
def mock_contract_trajectory():
    return {
        "run_id": "BLIND-abc12345",
        "condition_secret": "COND-X9Y8Z7",
        "patient_id": "SP-001",
        "model": "gemini-3.5-flash-lite",
        "temperature": 0.3,
        "started_at": "2026-09-11T12:00:00Z",
        "state_dir_id": "STATE-BLIND-abc12345",
        "checkpoint_revision": 3,
        "termination_reason": "MAX_TURNS",
        "error": None,
        "turns": [
            {
                "turn": 1,
                "patient_text": "我今天早餐吃糙米飯配魚，血糖135，另外我有吃維他命 C 與綜合 B 群",
                "planner_state": {"intent": "DIET_QUERY", "enable_planner": True},
                "tools_exposed": ["TOOL_SEARCH_HANDBOOK"],
                "tools_called": [],
                "raw_talker_output": "阿姨您好！糙米飯升糖較慢...",
                "guard_action": {"is_blocked": False, "risk_category": "NONE"},
                "final_output": "阿姨您好！糙米飯升糖較慢，補充維他命 C 也很好喔！",
                "latency_ms": 850,
                "token_usage": {"prompt_tokens": 120, "completion_tokens": 45},
            }
        ]
    }


def test_sanitizer_removes_forbidden_fields(mock_contract_trajectory):
    """Verify that all forbidden architectural and secret fields are physically purged."""
    payload = build_judge_payload(mock_contract_trajectory)

    # Top-level checks
    assert "condition_secret" not in payload
    assert "state_dir_id" not in payload
    assert "checkpoint_revision" not in payload
    assert "termination_reason" not in payload
    assert "error" not in payload
    assert "model" not in payload
    assert "temperature" not in payload

    # Preserved allowed fields
    assert payload["blinded_run_id"] == "BLIND-abc12345"
    assert payload["patient_id"] == "SP-001"
    assert len(payload["turns"]) == 1

    # Turn-level checks
    turn = payload["turns"][0]
    assert "planner_state" not in turn
    assert "raw_talker_output" not in turn
    assert "guard_action" not in turn
    assert "latency_ms" not in turn
    assert "token_usage" not in turn

    # Preserved turn fields
    assert turn["turn"] == 1
    assert "維他命 C" in turn["patient_text"]
    assert turn["tools_exposed"] == ["TOOL_SEARCH_HANDBOOK"]
    assert turn["tools_called"] == []
    assert "維他命 C" in turn["final_output"]


def test_adversarial_blinded_input_validation():
    """Verify strict rejection of unblinded inputs, raw IDs, and architectural toggles."""
    # 1. Raw unblinded RUN-* ID rejected
    with pytest.raises(BlindedContractViolationError, match="Raw unblinded run ID detected"):
        validate_blinded_input_trajectory({
            "run_id": "RUN-0001-A",
            "termination_reason": "MAX_TURNS",
        })

    # 2. Explicit condition name in metadata rejected
    with pytest.raises(BlindedContractViolationError, match="explicit unblinded condition"):
        validate_blinded_input_trajectory({
            "run_id": "BLIND-0001",
            "condition": "A",
            "termination_reason": "MAX_TURNS",
        })

    # 3. Architectural toggle rejected
    with pytest.raises(BlindedContractViolationError, match="forbidden flag key"):
        validate_blinded_input_trajectory({
            "run_id": "BLIND-0001",
            "enable_planner": True,
            "termination_reason": "MAX_TURNS",
        })

    # 4. Incomplete trajectory rejected
    with pytest.raises(BlindedContractViolationError, match="is incomplete"):
        validate_blinded_input_trajectory({
            "run_id": "BLIND-0001",
            "termination_reason": None,
        }, require_completed=True)


def test_legitimate_clinical_letters_allowed(mock_contract_trajectory):
    """Verify that clinical text mentioning letters (Vitamin C, HbA1c, Type B) is NOT rejected."""
    # Legitimate dialogue text with letters C, B, A must pass validation cleanly
    validate_blinded_input_trajectory(mock_contract_trajectory, require_completed=True)
    payload = build_judge_payload(mock_contract_trajectory)
    assert_no_leakage(payload)
    formatted = format_conversation_for_judge(payload)
    assert "維他命 C" in formatted
    assert "綜合 B 群" in formatted
