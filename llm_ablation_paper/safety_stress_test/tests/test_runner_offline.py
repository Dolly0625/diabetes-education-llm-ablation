"""Offline runner tests: reuse, isolation, resume, ERROR, guard reachability, canaries.

Every test here spawns real subprocesses but uses the deterministic fake client
(fake_responses), so NO API is ever called.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_ablation_paper.safety_stress_test import runner as R


def test_frozen_fingerprints_verified():
    result = R.verify_frozen_fingerprints()
    assert all(result.values())


def test_run_case_condition_all_conditions(tmp_path: Path):
    case = R.load_cases()[0]
    for condition in ("A", "B", "C", "D"):
        res = R.run_case_condition(case, condition, tmp_path)
        assert res["records"], f"no records for {condition}"
        assert 1 <= len(res["records"]) <= 3
        state_dir = Path(res["state_dir"])
        assert state_dir.exists()
        cfg = json.loads((state_dir / "config.json").read_text(encoding="utf-8"))
        assert cfg.get("run_id") == res["run_id"]
        assert cfg.get("max_turns") == 3
        # artifacts present
        assert (state_dir / "trajectories.jsonl").exists()
        assert (state_dir / "tool_snapshot.json").exists()


def test_condition_switch_semantics_recorded(tmp_path: Path):
    case = R.load_cases()[0]
    flags = {}
    for condition in ("A", "B", "C", "D"):
        res = R.run_case_condition(case, condition, tmp_path)
        cfg = json.loads((Path(res["state_dir"]) / "config.json").read_text(encoding="utf-8"))
        flags[condition] = (
            cfg.get("enable_planner"),
            cfg.get("enable_dynamic_tool_gate"),
            cfg.get("enable_output_guard"),
        )
    assert flags["A"] == (False, False, False)
    assert flags["B"] == (True, False, False)
    assert flags["C"] == (True, True, False)
    assert flags["D"] == (True, True, True)


def test_resume_no_duplication(tmp_path: Path):
    case = R.load_cases()[1]
    first = R.run_case_condition(case, "A", tmp_path)
    second = R.run_case_condition(case, "A", tmp_path, resume=True, persisted_run_id=first["run_id"])
    assert len(second["records"]) == len(first["records"])


def test_deterministic_error(tmp_path: Path):
    res = R.run_deterministic_error(tmp_path)
    assert res["termination_reason"] == "ERROR"


def test_guard_reachability(tmp_path: Path):
    gr = R.run_guard_reachability(tmp_path)
    assert gr["reachable"] is True
    assert gr["C"]["blocked"] is False
    assert gr["D"]["blocked"] is True
    assert gr["D"]["risk_category"] == "PRESCRIPTION_BREACH"
    assert gr["pipeline_only"] is True


def test_guard_reachability_fails_closed_when_unreachable(tmp_path: Path):
    with pytest.raises(R.StressError):
        R.run_guard_reachability(tmp_path, draft="我今天血糖還不錯，謝謝關心。")


def test_canary_injection_blocks(tmp_path: Path):
    observations = R.run_canaries(tmp_path)
    injection = [o for o in observations if o["is_injection"]]
    assert injection, "expected injection canaries"
    for obs in injection:
        assert obs["observed_termination_reason"] == "COMMON_INPUT_BLOCK"
    assert all(o["excluded_from_main"] for o in observations)


def test_isolation_state_dirs_disjoint_and_cache_cleared(tmp_path: Path):
    case = R.load_cases()[2]
    dirs = set()
    for condition in ("A", "B", "C", "D"):
        res = R.run_case_condition(case, condition, tmp_path)
        dirs.add(res["state_dir"])
    assert len(dirs) == 4
    # session cache is emptied by the harness per turn
    from llm_ablation_paper.workstream_1_technical_lead.harness.isolation import clear_session_cache

    clear_session_cache()
    import diabetes_chatbot.server.handlers as h

    assert not getattr(h, "_SESSION_CACHE", {})


def test_no_production_data_writes(tmp_path: Path):
    prod_dir = R.REPO_ROOT / "diabetes_chatbot" / "data"
    before = {p for p in prod_dir.rglob("*")} if prod_dir.exists() else set()
    R.run_case_condition(R.load_cases()[3], "A", tmp_path)
    after = {p for p in prod_dir.rglob("*")} if prod_dir.exists() else set()
    assert before == after, "stress runner wrote into production data dir"


def test_main_batch_clean_and_resume_error_guard_in_dry_run(tmp_path: Path):
    # Reduced but non-skipped dry-run: 1 safety case x 4 + 1 benign x 4 + canaries + error + guard.
    summary = R.run_fake_dry_run(tmp_path / "dry", case_limit=1, benign_limit=1)
    assert summary["n_safety_cases"] == 1
    assert summary["n_benign_controls"] == 1
    assert summary["n_canaries"] >= 4
    assert summary["resume_ok"] is True
    assert summary["deterministic_error_termination"] == "ERROR"
    assert summary["guard_reachability"]["reachable"] is True
    assert summary["offline_no_api"] is True
    mapping = summary["condition_mapping_used"]
    assert set(mapping.keys()) == {"A", "B", "C", "D"}
    assert not any(v in ("A", "B", "C", "D") for v in mapping.values())
