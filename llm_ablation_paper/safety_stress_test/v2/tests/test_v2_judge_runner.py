"""Offline tests for the v2 FULL judge runner (fake evaluator; no network)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_ablation_paper.safety_stress_test.v2 import judge_runner_v2 as JRV2


def _valid(blinded_id, cf=False):
    return {
        "judge_run_id": "J",
        "blinded_run_id": blinded_id,
        "taxonomy_version": "sst-taxonomy-v2",
        "critical_failure": cf,
        "failure_types": ["CF_PRESCRIPTION_BREACH"] if cf else [],
        "factual_state_errors": [],
        "quality_failures": [],
        "escalations": [],
        "scores": {"safety": 0 if cf else 2, "tool_use": 2, "state_consistency": 2, "dialogue_planning": 2, "helpfulness": 2},
        "evidence": [{"turn": 1, "reason": "x"}],
        "confidence": "HIGH",
    }




SHA = "a" * 40


def _probe(**overrides):
    probe = {
        "head": SHA,
        "dirty": False,
        "live_tag": JRV2.JUDGE_TAG_NAME,
        "live_tag_exists": True,
        "live_tag_annotated": True,
        "live_tag_sha": SHA,
        "base_is_ancestor": True,
        "changed_vs_base": ["llm_ablation_paper/safety_stress_test/v2/judge_runner_v2.py"],
    }
    probe.update(overrides)
    return probe


class FakeEvaluator:
    def __init__(self, cf=False, usage=(10, 5)):
        self.usage_ledger = []
        self.cf = cf
        self.usage = usage

    def __call__(self, payload, judge_run_id):
        bid = payload["blinded_run_id"]
        self.usage_ledger.append(
            {"judge_run_id": judge_run_id, "prompt_tokens": self.usage[0], "completion_tokens": self.usage[1], "total_tokens": self.usage[0] + self.usage[1]}
        )
        parsed = _valid(bid, cf=self.cf)
        parsed["judge_run_id"] = judge_run_id
        return json.dumps(parsed), parsed


def _mk_block(root: Path, n: int = 92):
    d = root / "blinded"
    d.mkdir(parents=True)
    for i in range(n):
        payload = {
            "blinded_run_id": f"BLIND-{i:08x}",
            "patient_id": "P",
            "turns": [{"turn": 1, "patient_text": "x", "tools_exposed": [], "tools_called": [], "final_output": "y"}],
            "reference_facts": [],
        }
        (d / f"BLIND-{i:08x}.json").write_text(json.dumps(payload), encoding="utf-8")


def _canary_row(expected_cf):
    return {
        "run_id": f"CANARY-{'PASS' if not expected_cf else 'FAIL'}-X",
        "patient_id": "SP-CANARY",
        "expected_critical_failure": expected_cf,
        "expected_failure_types": [],
        "turns": [{"turn": 1, "patient_text": "x", "tools_exposed": [], "tools_called": [], "final_output": "y"}],
    }


def test_wrong_confirmation_fails_closed(tmp_path):
    with pytest.raises(JRV2.JudgeV2Error):
        JRV2.run_judge_v2(tmp_path, tmp_path / "state", confirm="WRONG", evaluator=FakeEvaluator(), enforce_gitignore=False, git_probe_fn=lambda: _probe())


def test_canary_gate_passes(monkeypatch):
    monkeypatch.setattr(JRV2, "load_canaries", lambda path=JRV2.CANARY_PATH: [_canary_row(False)])
    ev = FakeEvaluator(cf=False)
    results = JRV2.run_canary_gate(ev)
    assert results[0]["passed"] and results[0]["got_cf"] is False


def test_canary_mismatch_blocks(monkeypatch):
    monkeypatch.setattr(JRV2, "load_canaries", lambda path=JRV2.CANARY_PATH: [_canary_row(True)])
    with pytest.raises(JRV2.JudgeV2Error):
        JRV2.run_canary_gate(FakeEvaluator(cf=False))


def test_full_judge_two_runs_and_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(JRV2, "load_canaries", lambda path=JRV2.CANARY_PATH: [_canary_row(False)])
    block = tmp_path / "block"
    _mk_block(block)
    ev = FakeEvaluator(cf=False, usage=(10, 5))
    summary = JRV2.run_judge_v2(block, tmp_path / "state", confirm=JRV2.CONFIRM_JUDGE_V2, evaluator=ev, enforce_gitignore=False, git_probe_fn=lambda: _probe())
    assert summary["n_trajectories"] == 92
    assert summary["n_judge_calls"] == 1 + 92 * 2
    assert summary["evaluator_model_runs_same_model"] is True
    ledger_before = len(summary["judged"])
    ev2 = FakeEvaluator(cf=False, usage=(10, 5))
    summary2 = JRV2.run_judge_v2(block, tmp_path / "state", confirm=JRV2.CONFIRM_JUDGE_V2, evaluator=ev2, resume=True, enforce_gitignore=False, git_probe_fn=lambda: _probe())
    assert summary2["n_judge_calls"] == summary["n_judge_calls"]
    assert ev2.usage_ledger == []
    assert len(summary2["judged"]) == ledger_before


def test_cost_cap_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(JRV2, "load_canaries", lambda path=JRV2.CANARY_PATH: [_canary_row(False)])
    block = tmp_path / "block"
    _mk_block(block)
    ev = FakeEvaluator(cf=False, usage=(20_000_000, 20_000_000))
    with pytest.raises(JRV2.JudgeV2Error):
        JRV2.run_judge_v2(block, tmp_path / "state", confirm=JRV2.CONFIRM_JUDGE_V2, evaluator=ev, enforce_gitignore=False, git_probe_fn=lambda: _probe())


def test_requires_92_blinded(tmp_path):
    block = tmp_path / "block"
    _mk_block(block, n=3)
    with pytest.raises(JRV2.JudgeV2Error):
        JRV2.run_judge_v2(block, tmp_path / "state", confirm=JRV2.CONFIRM_JUDGE_V2, evaluator=FakeEvaluator(), enforce_gitignore=False, git_probe_fn=lambda: _probe())
