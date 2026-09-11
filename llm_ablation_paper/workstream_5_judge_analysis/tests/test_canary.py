"""Tests for pre-flight Canary validation and fail-closed mechanism."""

from pathlib import Path
import pytest
from llm_ablation_paper.workstream_5_judge_analysis.judge_runner import (
    verify_canaries,
    deterministic_fake_judge,
    CanaryVerificationError,
)


@pytest.fixture
def canary_file():
    path = Path(__file__).parent.parent / "canary_trajectories.jsonl"
    assert path.exists(), "canary_trajectories.jsonl must exist"
    return path


def test_canary_passes_with_fake_judge(canary_file):
    """Verify that all canary cases pass pre-flight verification with the deterministic judge."""
    verify_canaries(canary_file, deterministic_fake_judge)


def test_canary_fail_closed_on_false_positive(canary_file):
    """Verify fail-closed error is raised if judge falsely flags a safe canary as critical failure."""
    def broken_judge(payload, run_id):
        res = deterministic_fake_judge(payload, run_id)
        # Force false positive on PASS
        if "PASS" in run_id:
            res["critical_failure"] = True
            res["scores"]["safety"] = 0
        return res

    with pytest.raises(CanaryVerificationError, match="Canary PASS"):
        verify_canaries(canary_file, broken_judge)


def test_canary_fail_closed_on_false_negative(canary_file):
    """Verify fail-closed error is raised if judge misses an obvious critical failure."""
    def blind_judge(payload, run_id):
        res = deterministic_fake_judge(payload, run_id)
        # Miss all failures
        res["critical_failure"] = False
        res["scores"]["safety"] = 2
        return res

    with pytest.raises(CanaryVerificationError, match="Canary FAIL"):
        verify_canaries(canary_file, blind_judge)
