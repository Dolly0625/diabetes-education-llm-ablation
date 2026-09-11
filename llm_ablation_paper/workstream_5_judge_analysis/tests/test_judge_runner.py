"""Tests for JudgeRunner dual evaluation, disagreement tie-breaker, retry, and checkpointing."""

import json
from pathlib import Path
import pytest
from llm_ablation_paper.workstream_5_judge_analysis.judge_runner import (
    JudgeRunner,
    deterministic_fake_judge,
    execute_judge_with_retry,
    JudgeExecutionError,
)


@pytest.fixture
def mock_trajectory():
    return {
        "run_id": "BLIND-001",
        "patient_id": "SP-001",
        "termination_reason": "MAX_TURNS",
        "turns": [
            {
                "turn": 1,
                "patient_text": "今天早餐吃了一碗麵",
                "tools_exposed": [],
                "tools_called": [],
                "final_output": "好的，麵食升糖較快，要注意份量喔！",
            }
        ]
    }


def test_dual_evaluation_consensus_agreement(mock_trajectory):
    """Verify dual evaluation produces consensus when Run 1 and Run 2 agree."""
    runner = JudgeRunner(evaluator_fn=deterministic_fake_judge)
    result = runner.evaluate_trajectory_dual(mock_trajectory)

    assert result["blinded_run_id"] == "BLIND-001"
    assert result["critical_failure_consensus"] is False
    assert result["disagreement"] is False
    assert result["evaluations"]["run_1"] is not None
    assert result["evaluations"]["run_2"] is not None
    assert result["evaluations"]["run_3_tiebreak"] is None


def test_dual_evaluation_disagreement_triggers_tiebreaker(mock_trajectory):
    """Verify disagreement on critical_failure triggers Run 3 tie-breaker and preserves all runs."""
    call_count = 0

    def flipping_judge(payload, judge_run_id):
        nonlocal call_count
        call_count += 1
        res = deterministic_fake_judge(payload, judge_run_id)
        if call_count == 1:
            # Run 1: CF True
            res["critical_failure"] = True
            res["scores"]["safety"] = 0
        elif call_count == 2:
            # Run 2: CF False
            res["critical_failure"] = False
            res["scores"]["safety"] = 2
        elif call_count == 3:
            # Run 3 Tie-breaker: CF True
            res["critical_failure"] = True
            res["scores"]["safety"] = 0
        return res

    runner = JudgeRunner(evaluator_fn=flipping_judge)
    result = runner.evaluate_trajectory_dual(mock_trajectory)

    assert result["disagreement"] is True
    assert result["evaluations"]["run_3_tiebreak"] is not None
    # 2 vs 1 -> consensus True
    assert result["critical_failure_consensus"] is True
    assert call_count == 3


def test_retry_on_transient_failure():
    """Verify execute_judge_with_retry succeeds after transient error."""
    attempts = 0

    def flaky_eval(payload, run_id):
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ConnectionError("Transient network drop")
        return deterministic_fake_judge(payload, run_id)

    payload = {"blinded_run_id": "BLIND-TEST", "patient_id": "SP-1", "turns": []}
    res = execute_judge_with_retry(flaky_eval, payload, "JUDGE-RETRY-01", max_retries=3)
    assert res["blinded_run_id"] == "BLIND-TEST"
    assert attempts == 2


def test_retry_exhaustion_raises_error():
    """Verify permanent failure raises JudgeExecutionError."""
    def always_fail(payload, run_id):
        raise RuntimeError("Permanent API outage")

    payload = {"blinded_run_id": "BLIND-TEST", "patient_id": "SP-1", "turns": []}
    with pytest.raises(JudgeExecutionError):
        execute_judge_with_retry(always_fail, payload, "JUDGE-FAIL-01", max_retries=2)


def test_checkpointing_and_exclusion(tmp_path, mock_trajectory):
    """Verify checkpoints are written and excluded runs are handled cleanly."""
    runner = JudgeRunner(evaluator_fn=deterministic_fake_judge, checkpoint_dir=tmp_path)

    trajectories = [
        mock_trajectory,
        {
            "run_id": "BLIND-002",
            "patient_id": "SP-002",
            "termination_reason": "COMMON_INPUT_BLOCK",  # Should be excluded
            "turns": [],
        },
        {
            "run_id": "BLIND-003",
            "patient_id": "SP-003",
            "termination_reason": "ERROR",  # Should be excluded
            "turns": [],
        }
    ]

    results = runner.run_batch(trajectories)
    assert len(results) == 3

    assert results[0]["excluded"] is False
    assert results[1]["excluded"] is True
    assert results[1]["exclusion_reason"] == "COMMON_INPUT_BLOCK"
    assert results[2]["excluded"] is True
    assert results[2]["exclusion_reason"] == "ERROR"

    # Checkpoint exists for valid run
    ckpt_file = tmp_path / "BLIND-001.json"
    assert ckpt_file.exists()
