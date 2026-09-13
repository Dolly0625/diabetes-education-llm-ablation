"""Offline tests for the v2 FULL-batch runner (mock client; no network)."""
from __future__ import annotations

import json
import stat

import pytest

from llm_ablation_paper.safety_stress_test import live_runner as L1
from llm_ablation_paper.safety_stress_test.v2 import full_runner_v2 as F2
from llm_ablation_paper.safety_stress_test.v2 import runner_v2 as RV2

SHA = "a" * 40


def _probe(**overrides):
    probe = {
        "head": SHA,
        "dirty": False,
        "full_tag": F2.FULL_TAG_NAME,
        "full_tag_exists": True,
        "full_tag_annotated": True,
        "full_tag_sha": SHA,
        "base_tag_sha": F2.EXPECTED_BASE_SHA,
        "base_is_ancestor": True,
        "changed_vs_base": ["llm_ablation_paper/safety_stress_test/v2/full_runner_v2.py"],
    }
    probe.update(overrides)
    return probe


def test_expected_counts_and_cost_estimate():
    grouped = F2._all_cases()
    assert len(grouped["main_safety"]) == 12
    assert len(grouped["factual_state_probe"]) == 2
    assert len(grouped["benign_control"]) == 9
    assert F2.COST_CAP_USD == 1.00
    assert F2.estimate_full_cost_usd() <= F2.COST_CAP_USD


def test_preflight_blocked_before_tag(tmp_path):
    report = F2.preflight_full(
        tmp_path,
        require_key=False,
        enforce_gitignore=False,
        git_probe_fn=lambda: _probe(full_tag_exists=False, full_tag_sha=""),
    )
    assert report["preflight"] == "BLOCKED"
    assert report["reason"] == "NOT_FROZEN"


def test_preflight_passes_offline_with_stub(tmp_path):
    report = F2.preflight_full(tmp_path, require_key=False, enforce_gitignore=False, git_probe_fn=lambda: _probe())
    assert report["preflight"] == "PASS"
    assert report["counts"] == {"main_safety": 12, "factual_state_probe": 2, "benign_control": 9}
    assert report["expected_runs"] == 92


def test_preflight_rejects_out_of_scope_change(tmp_path):
    with pytest.raises(F2.FullV2Error):
        F2.preflight_full(
            tmp_path,
            require_key=False,
            enforce_gitignore=False,
            git_probe_fn=lambda: _probe(changed_vs_base=["diabetes_chatbot/planner.py"]),
        )


def test_wrong_confirmation_fails_closed(tmp_path):
    with pytest.raises(F2.FullV2Error):
        F2.run_full_v2(tmp_path / "full", confirm="WRONG", client_factory=L1.offline_safe_client_factory, git_probe_fn=lambda: _probe())
    assert not (tmp_path / "full").exists()


def test_upsert_and_ledger_sum():
    led = F2._upsert_entry([], {"key": "SAFETY-RX-01-v2|A", "condition": "A", "cost_usd": 0.1})
    led = F2._upsert_entry(led, {"key": "SAFETY-RX-01-v2|A", "condition": "A", "cost_usd": 0.2})
    assert len(led) == 1 and F2._ledger_sum(led) == 0.2


def test_mock_full_run_completes_and_blinds(tmp_path):
    root = tmp_path / "full"
    summary = F2.run_full_v2(
        root,
        confirm=F2.CONFIRM_FULL_V2,
        client_factory=L1.offline_safe_client_factory,
        enforce_gitignore=False,
        git_probe_fn=lambda: _probe(),
    )
    assert summary["completed"] is True
    assert summary["n_runs"] == 92
    assert summary["n_blinded"] == 92
    assert summary["n_turns_total"] == 204
    assert summary["judge_used"] is False
    for p in (root / "blinded").glob("BLIND-*.json"):
        payload = json.loads(p.read_text(encoding="utf-8"))
        RV2.assert_payload_clean_v2(payload)
    for sub in ("blinded", "scanner_v2", "quarantine"):
        assert stat.S_IMODE((root / sub).stat().st_mode) == 0o700
    for name in ("v2_full_manifest.json", "v2_full_summary.json", "v2_full_usage_ledger.json"):
        assert stat.S_IMODE((root / name).stat().st_mode) == 0o600
    ledger = json.loads((root / "v2_full_usage_ledger.json").read_text(encoding="utf-8"))
    assert len(ledger) == 92
    assert (root / "v2_full_summary.json").exists()
