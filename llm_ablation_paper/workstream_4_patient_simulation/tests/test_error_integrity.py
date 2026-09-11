"""Tests for WS4 ERROR and COMMON_INPUT_BLOCK integrity and clean validator (PHASE M4.1).

Requirements:
1. When harness_turn.termination_reason in {ERROR, COMMON_INPUT_BLOCK}, run-level error_metadata
   must capture stage="harness", turn, and harness error/retry metadata.
2. Checkpoint and roleplay_result.json must persist this error_metadata.
3. Resume path must preserve saved error_metadata when saved termination_reason == "ERROR".
4. Formal clean validator recursively rejects nested harness ERROR, non-null error, or non-transient retry errors.
5. Clean payloads and valid transient retries pass validation.
"""

import json
import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation import (
    DeterministicPatientAgent,
    RoleplayRunner,
    load_profiles,
    validate_clean_execution,
    validate_clean_run,
    validate_clean_trajectory,
)


def _dummy_profile() -> dict[str, Any]:
    return load_profiles()["SP-001"]


def test_harness_error_bubbles_up_run_level_error_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify harness termination_reason=ERROR produces structured run-level error_metadata in result & checkpoint."""
    profile = _dummy_profile()
    runner = RoleplayRunner(patient_agent=DeterministicPatientAgent(), output_root=tmp_path)

    expected_error = {"code": 500, "message": "talker model internal failure"}

    def fake_harness_error(**kwargs: Any) -> list[dict[str, Any]]:
        return [{
            "turn_index": 0,
            "user_message": kwargs["messages"][-1],
            "assistant_response": "系統發生錯誤。",
            "termination_reason": "ERROR",
            "error": expected_error,
            "retry_metadata": [{"attempt": 1, "outcome": "retry", "error": "timeout"}],
        }]

    monkeypatch.setattr(runner, "_call_harness", fake_harness_error)

    result = runner.run_condition(
        profile=profile,
        condition="A",
        fake_talker_responses=["dummy"] * 6,
    )

    assert result["termination_reason"] == "ERROR"
    assert result["error_metadata"] is not None
    assert result["error_metadata"]["stage"] == "harness"
    assert result["error_metadata"]["turn"] == 1
    assert result["error_metadata"]["termination_reason"] == "ERROR"
    assert result["error_metadata"]["error"] == expected_error
    assert result["error_metadata"]["retry_metadata"] is not None

    # Verify checkpoint on disk preserves error_metadata
    checkpoint_path = tmp_path / result["run_id"] / "ws4_runner_checkpoint.json"
    assert checkpoint_path.exists()
    checkpoint_data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint_data["termination_reason"] == "ERROR"
    assert checkpoint_data["error_metadata"] == result["error_metadata"]

    # Verify roleplay_result.json on disk preserves error_metadata
    roleplay_path = tmp_path / result["run_id"] / "roleplay_result.json"
    assert roleplay_path.exists()
    roleplay_data = json.loads(roleplay_path.read_text(encoding="utf-8"))
    assert roleplay_data["error_metadata"] == result["error_metadata"]


def test_harness_common_input_block_bubbles_up_run_level_error_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify harness termination_reason=COMMON_INPUT_BLOCK produces run-level error_metadata in result & checkpoint."""
    profile = _dummy_profile()
    runner = RoleplayRunner(patient_agent=DeterministicPatientAgent(), output_root=tmp_path)

    def fake_harness_blocked(**kwargs: Any) -> list[dict[str, Any]]:
        return [{
            "turn_index": 0,
            "user_message": kwargs["messages"][-1],
            "assistant_response": "【系統安全提示】本系統為醫療衛教助理...",
            "termination_reason": "COMMON_INPUT_BLOCK",
            "error": None,
            "retry_metadata": None,
        }]

    monkeypatch.setattr(runner, "_call_harness", fake_harness_blocked)

    result = runner.run_condition(
        profile=profile,
        condition="A",
        fake_talker_responses=["dummy"] * 6,
    )

    assert result["termination_reason"] == "COMMON_INPUT_BLOCK"
    assert result["error_metadata"] is not None
    assert result["error_metadata"]["stage"] == "harness"
    assert result["error_metadata"]["turn"] == 1
    assert result["error_metadata"]["termination_reason"] == "COMMON_INPUT_BLOCK"

    # Verify checkpoint on disk
    checkpoint_path = tmp_path / result["run_id"] / "ws4_runner_checkpoint.json"
    checkpoint_data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint_data["termination_reason"] == "COMMON_INPUT_BLOCK"
    assert checkpoint_data["error_metadata"] == result["error_metadata"]


def test_resume_preserves_existing_error_metadata(tmp_path: Path):
    """Verify resume path preserves saved error_metadata when saved termination_reason is ERROR."""
    profile = _dummy_profile()
    runner = RoleplayRunner(patient_agent=DeterministicPatientAgent(), output_root=tmp_path)
    run_id = "WS4-FAKE-SP-001-A"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = run_dir / "ws4_runner_checkpoint.json"

    saved_error_meta = {
        "stage": "harness",
        "turn": 6,
        "termination_reason": "ERROR",
        "error": {"code": 503, "msg": "service temporarily unavailable"},
        "retry_metadata": [],
    }
    dummy_record = {
        "turn": 1,
        "patient_turn": {"patient_utterance": "你好", "should_end": False, "termination_reason": "MAX_TURNS", "disclosed_facts": [], "evidence": "e"},
        "harness_turn": {"assistant_response": "您好", "termination_reason": None, "error": None},
        "patient_retry_metadata": [],
        "retry_metadata": [],
    }
    saved_checkpoint = {
        "run_id": run_id,
        "patient_id": "SP-001",
        "condition": "A",
        "user_id": "ws4_sp-001_a_fake",
        "records": [dict(dummy_record, turn=i) for i in range(1, 7)],
        "pending_patient_turn": None,
        "pending_patient_retry_metadata": [],
        "terminal_patient_turn": None,
        "termination_reason": "ERROR",
        "error_metadata": saved_error_meta,
    }
    checkpoint_path.write_text(json.dumps(saved_checkpoint), encoding="utf-8")

    result = runner.run_condition(
        profile=profile,
        condition="A",
        resume=True,
    )

    assert result["termination_reason"] == "ERROR"
    assert result["error_metadata"] == saved_error_meta


def test_resume_retries_and_records_new_error_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify resume on incomplete ERROR run executes next turn and captures new error_metadata if error recurs."""
    profile = _dummy_profile()
    runner = RoleplayRunner(patient_agent=DeterministicPatientAgent(), output_root=tmp_path)
    run_id = "WS4-FAKE-SP-001-A"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = run_dir / "ws4_runner_checkpoint.json"

    saved_checkpoint = {
        "run_id": run_id,
        "patient_id": "SP-001",
        "condition": "A",
        "user_id": "ws4_sp-001_a_fake",
        "records": [{
            "turn": 1,
            "patient_turn": {"patient_utterance": "你好", "should_end": False, "termination_reason": "MAX_TURNS", "disclosed_facts": [], "evidence": "e"},
            "harness_turn": {"assistant_response": "您好", "termination_reason": None, "error": None},
            "patient_retry_metadata": [],
            "retry_metadata": [],
        }],
        "pending_patient_turn": None,
        "pending_patient_retry_metadata": [],
        "terminal_patient_turn": None,
        "termination_reason": "ERROR",
        "error_metadata": {"stage": "harness", "turn": 1},
    }
    checkpoint_path.write_text(json.dumps(saved_checkpoint), encoding="utf-8")

    # Second turn harness returns ERROR
    def fake_turn2(**kwargs: Any) -> list[dict[str, Any]]:
        return [{
            "turn_index": 1,
            "user_message": kwargs["messages"][-1],
            "assistant_response": "發生錯誤",
            "termination_reason": "ERROR",
            "error": {"detail": "turn2 failed"},
            "retry_metadata": [],
        }]

    monkeypatch.setattr(runner, "_call_harness", fake_turn2)

    result = runner.run_condition(
        profile=profile,
        condition="A",
        fake_talker_responses=["t1", "t2", "t3", "t4", "t5", "t6"],
        resume=True,
    )

    assert result["termination_reason"] == "ERROR"
    assert result["error_metadata"]["stage"] == "harness"
    assert result["error_metadata"]["turn"] == 2
    assert result["error_metadata"]["error"] == {"detail": "turn2 failed"}


def test_clean_validator_rejects_nested_harness_error():
    """Verify validate_clean_execution recursively rejects nested harness_turn errors."""
    # 1. Reject harness_turn termination_reason == ERROR
    bad_payload_term = {
        "run_id": "RUN-01",
        "termination_reason": "MAX_TURNS",
        "error_metadata": None,
        "records": [{
            "turn": 1,
            "harness_turn": {"termination_reason": "ERROR", "error": None},
        }],
    }
    with pytest.raises(ValueError, match="harness_turn termination_reason is ERROR"):
        validate_clean_execution(bad_payload_term)

    # 2. Reject harness_turn non-null error
    bad_payload_err = {
        "run_id": "RUN-02",
        "termination_reason": "MAX_TURNS",
        "error_metadata": None,
        "records": [{
            "turn": 1,
            "harness_turn": {"termination_reason": None, "error": "some unhandled error"},
        }],
    }
    with pytest.raises(ValueError, match="harness_turn error is non-null"):
        validate_clean_execution(bad_payload_err)

    # 3. Reject run-level termination_reason == ERROR
    bad_payload_top = {
        "run_id": "RUN-03",
        "termination_reason": "ERROR",
        "error_metadata": {"stage": "harness"},
        "records": [],
    }
    with pytest.raises(ValueError, match="termination_reason is ERROR"):
        validate_clean_execution(bad_payload_top)


def test_clean_validator_rejects_non_transient_retries():
    """Verify validate_clean_execution rejects retry_metadata containing non-transient failures."""
    # Non-transient ValueError in retry_metadata
    bad_retry_meta = {
        "run_id": "RUN-04",
        "termination_reason": "MAX_TURNS",
        "error_metadata": None,
        "records": [{
            "turn": 1,
            "harness_turn": {"termination_reason": None, "error": None},
            "retry_metadata": [
                {"attempt": 1, "outcome": "retry", "error_type": "ValueError", "error": "invalid configuration"},
                {"attempt": 2, "outcome": "success"},
            ],
        }],
    }
    with pytest.raises(ValueError, match="contains non-transient error"):
        validate_clean_execution(bad_retry_meta)

    # Non-transient 400 Bad Request in harness retry_metadata
    bad_http_status = {
        "run_id": "RUN-05",
        "termination_reason": "MAX_TURNS",
        "error_metadata": None,
        "records": [{
            "turn": 1,
            "harness_turn": {
                "termination_reason": None,
                "error": None,
                "retry_metadata": [{"attempt": 1, "outcome": "retry", "status_code": 400, "error": "Bad Request"}],
            },
        }],
    }
    with pytest.raises(ValueError, match="contains non-transient error"):
        validate_clean_execution(bad_http_status)


def test_clean_validator_accepts_clean_runs_and_transient_retries():
    """Verify clean execution and valid transient retries pass clean validation without error."""
    clean_payload = {
        "run_id": "RUN-CLEAN-01",
        "termination_reason": "MAX_TURNS",
        "error_metadata": None,
        "records": [
            {
                "turn": 1,
                "harness_turn": {"termination_reason": None, "error": None},
                "patient_retry_metadata": [
                    {"attempt": 1, "outcome": "retry", "error_type": "PatientAgentContractError", "error": "transient malformed JSON"},
                    {"attempt": 2, "outcome": "success"},
                ],
                "retry_metadata": [
                    {"attempt": 1, "outcome": "retry", "error_type": "APITimeoutError", "error": "Request timed out"},
                    {"attempt": 2, "outcome": "success"},
                ],
            },
            {
                "turn": 2,
                "harness_turn": {"termination_reason": "MAX_TURNS", "error": None},
                "patient_retry_metadata": [{"attempt": 1, "outcome": "success"}],
                "retry_metadata": [{"attempt": 1, "outcome": "success"}],
            },
        ],
    }

    # Single run dict
    validate_clean_execution(clean_payload)
    validate_clean_run(clean_payload)
    validate_clean_trajectory(clean_payload)

    # Summary with multiple runs list
    summary = {
        "execution_mode": "formal_pilot",
        "runs": [clean_payload],
    }
    validate_clean_execution(summary)
