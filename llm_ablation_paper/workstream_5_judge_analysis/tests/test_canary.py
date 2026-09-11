"""Tests for unified pre-flight Canary validation, schema enforcement, and fail-closed mechanism."""

from pathlib import Path
import pytest
from llm_ablation_paper.workstream_5_judge_analysis.judge_runner import (
    verify_canaries,
    deterministic_fake_judge,
    CanaryVerificationError,
    JudgeValidationError,
)


@pytest.fixture
def canary_file():
    path = Path(__file__).parent.parent / "canary_trajectories.jsonl"
    assert path.exists(), "canary_trajectories.jsonl must exist"
    return path


def test_canary_passes_unified_runner_pipeline(canary_file):
    """Verify all canaries pass through the exact same schema, invariants, and retry pipeline."""
    verify_canaries(canary_file, deterministic_fake_judge)


def test_canary_fail_closed_on_false_positive(canary_file):
    """Verify fail-closed error is raised if judge falsely flags safe canary as critical failure."""
    def broken_judge(payload, run_id):
        raw, res = deterministic_fake_judge(payload, run_id)
        if "PASS" in run_id:
            res["critical_failure"] = True
            res["scores"]["safety"] = 0
            res["failure_types"] = ["CF_PRESCRIPTION_BREACH"]
        return raw, res

    with pytest.raises(CanaryVerificationError, match="Canary CANARY-PASS-01 critical_failure mismatch"):
        verify_canaries(canary_file, broken_judge)


def test_canary_fail_closed_on_failure_type_mismatch(canary_file):
    """Verify fail-closed error is raised if judge identifies failure but assigns wrong failure type."""
    def wrong_type_judge(payload, run_id):
        raw, res = deterministic_fake_judge(payload, run_id)
        if "PRESCRIPTION" in run_id:
            # Mistagged failure type
            res["failure_types"] = ["CF_DIAGNOSTIC_BREACH"]
        return raw, res

    with pytest.raises(CanaryVerificationError, match="missing expected failure type"):
        verify_canaries(canary_file, wrong_type_judge)
