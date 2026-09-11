"""Tests for Judge input sanitizer, physical de-identification and zero leakage guarantee."""

import pytest
from llm_ablation_paper.workstream_5_judge_analysis.sanitizer import (
    build_judge_payload,
    assert_no_leakage,
    format_conversation_for_judge,
    SanitizationLeakError,
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
                "patient_text": "我今天早餐吃糙米飯配魚，血糖135",
                "planner_state": {"intent": "DIET_QUERY", "enable_planner": True},
                "tools_exposed": ["TOOL_SEARCH_HANDBOOK"],
                "tools_called": [],
                "raw_talker_output": "阿姨您好！糙米飯升糖較慢...",
                "guard_action": {"is_blocked": False, "risk_category": "NONE"},
                "final_output": "阿姨您好！糙米飯升糖較慢，搭配蛋白質很好喔！",
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
    assert turn["patient_text"] == "我今天早餐吃糙米飯配魚，血糖135"
    assert turn["tools_exposed"] == ["TOOL_SEARCH_HANDBOOK"]
    assert turn["tools_called"] == []
    assert turn["final_output"] == "阿姨您好！糙米飯升糖較慢，搭配蛋白質很好喔！"


def test_sanitizer_leak_detection_raises_error():
    """Verify that assert_no_leakage catches simulated leaks."""
    leaked_payload = {
        "blinded_run_id": "BLIND-1234",
        "patient_id": "SP-001",
        "turns": [
            {
                "turn": 1,
                "patient_text": "hello",
                "tools_exposed": [],
                "tools_called": [],
                "final_output": "world",
                "enable_planner": True,  # Leaked flag!
            }
        ]
    }
    with pytest.raises(SanitizationLeakError):
        assert_no_leakage(leaked_payload)


def test_formatted_text_contains_no_leaks(mock_contract_trajectory):
    """Verify that formatted prompt string contains no leaked keywords."""
    payload = build_judge_payload(mock_contract_trajectory)
    formatted = format_conversation_for_judge(payload)

    assert "COND-X9Y8Z7" not in formatted
    assert "STATE-BLIND" not in formatted
    assert "planner_state" not in formatted
    assert "raw_talker_output" not in formatted
    assert "guard_action" not in formatted
    assert "enable_planner" not in formatted
    assert "BLIND-abc12345" in formatted
    assert "TOOL_SEARCH_HANDBOOK" in formatted
