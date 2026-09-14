"""v2 runner offline tests (deterministic fake; no API)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_ablation_paper.safety_stress_test import runner as R1
from llm_ablation_paper.safety_stress_test.v2 import analysis_v2 as A2
from llm_ablation_paper.safety_stress_test.v2 import runner_v2 as RV2


@pytest.fixture(scope="module")
def dry_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("v2_dry_run")
    before = R1.workstream1_artifacts_snapshot()
    summary = RV2.run_v2_fake_dry_run(root, case_limit=2, benign_limit=2)
    after = R1.workstream1_artifacts_snapshot()
    return root, summary, before, after


def test_frozen_fingerprints_verified(dry_run):
    assert all(R1.verify_frozen_fingerprints().values())


def test_condition_switch_semantics():
    from llm_ablation_paper.workstream_1_technical_lead.harness import AblationConfig

    flags = {c: (AblationConfig.for_condition(c).enable_planner,
                 AblationConfig.for_condition(c).enable_dynamic_tool_gate,
                 AblationConfig.for_condition(c).enable_output_guard) for c in "ABCD"}
    assert flags["A"] == (False, False, False)
    assert flags["B"] == (True, False, False)
    assert flags["C"] == (True, True, False)
    assert flags["D"] == (True, True, True)


def test_dry_run_blocks_and_resume(dry_run):
    _root, summary, _before, _after = dry_run
    assert summary["n_runs"] == (2 + 2 + 2) * 4
    assert summary["blocks"]["main_safety_blocks"] == 2
    assert summary["blocks"]["factual_state_probe_blocks"] == 2
    assert summary["resume_ok"] is True
    assert summary["deterministic_error_termination"] == "ERROR"
    assert summary["guard_reachability"]["reachable"] is True
    assert summary["guard_reachability"]["pipeline_only"] is True


def test_blinded_payloads_are_clean(dry_run):
    _root, summary, _before, _after = dry_run
    for payload in summary["blinded"]:
        RV2.assert_payload_clean_v2(payload)
        assert set(payload) == {"blinded_run_id", "patient_id", "turns", "reference_facts"}


def test_state_dirs_disjoint(dry_run):
    _root, summary, _before, _after = dry_run
    dirs = {r["run_id"] for r in summary["runs"]}
    assert len(dirs) == len(summary["runs"])


def test_no_workstream1_pollution(dry_run):
    _root, _summary, before, after = dry_run
    assert before == after


def test_analysis_v2_writes_metrics(dry_run):
    root, _summary, _before, _after = dry_run
    metrics = A2.analyze_v2_dry_run(root)
    assert metrics["n_evaluated"] > 0
    for cond in ("A", "B", "C", "D"):
        cell = metrics["per_condition"][cond]
        assert "cfr_strict" in cell and "cfr_composite" in cell
        assert cell["cfr_strict"]["n"] == 2
    assert (root / "v2_metrics.json").exists()
