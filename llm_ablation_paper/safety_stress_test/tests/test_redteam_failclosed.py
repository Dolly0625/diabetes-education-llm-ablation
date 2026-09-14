"""Adversarial fail-closed tests required by the red-team audit (Agent D)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from llm_ablation_paper.safety_stress_test import runner as R
from llm_ablation_paper.safety_stress_test import validate_cases as V
from llm_ablation_paper.workstream_1_technical_lead.harness import validate_condition_mapping


def test_none_mapping_hard_fails():
    with pytest.raises(R.FrozenConfigError):
        R.resolve_stress_mapping(None)


def test_wrong_mapping_hard_fails():
    with pytest.raises(ValueError):
        validate_condition_mapping({"A": "COND-X", "B": "COND-X", "C": "COND-Y", "D": "COND-Z"})  # duplicate
    with pytest.raises(ValueError):
        validate_condition_mapping({"A": "A", "B": "B", "C": "C", "D": "D"})  # non-opaque
    with pytest.raises(ValueError):
        validate_condition_mapping({"A": "COND-1", "B": "COND-2", "C": "COND-3"})  # missing key
    # valid opaque mapping passes
    ok = validate_condition_mapping(R.generate_random_condition_mapping())
    assert set(ok.keys()) == {"A", "B", "C", "D"}
    assert not any(v in ("A", "B", "C", "D") for v in ok.values())


def test_missing_frozen_config_hard_fails(monkeypatch):
    broken = dict(R.FROZEN_FINGERPRINTS)
    broken["talker_base_prompt_sha256"] = "0" * 64
    monkeypatch.setattr(R, "FROZEN_FINGERPRINTS", broken)
    with pytest.raises(R.FrozenConfigError):
        R.verify_frozen_fingerprints()


def test_contaminated_state_dir_hard_fails(tmp_path: Path):
    case = R.load_cases()[0]
    first = R.run_case_condition(case, "A", tmp_path)
    from llm_ablation_paper.workstream_1_technical_lead.harness.isolation import ensure_state_dir_empty

    with pytest.raises(FileExistsError):
        ensure_state_dir_empty(Path(first["state_dir"]), resume=False, run_id=first["run_id"])
    with pytest.raises(RuntimeError) as exc:
        R.run_case_condition(case, "A", tmp_path, persisted_run_id=first["run_id"])
    assert "already contains" in str(exc.value)


def test_canary_mixed_into_main_hard_fails():
    with pytest.raises(R.CanaryMixingError):
        V.assert_canary_excluded_from_main([{"run_id": "CANARY-INJ-DIRECT", "patient_id": "SP-CANARY"}])
    with pytest.raises(R.CanaryMixingError):
        V.assert_canary_excluded_from_main([{"run_id": "STRESS-X", "expected_failure_types": ["CF_MIRACLE_CLAIM"]}])


def test_unknown_cf_code_hard_fails():
    with pytest.raises(V.CaseSchemaError):
        V.validate_unknown_cf_code(["CF_NEW_RISK"])


def test_judge_payload_leak_hard_fails():
    from llm_ablation_paper.workstream_5_judge_analysis.sanitizer import SanitizationLeakError, assert_no_leakage

    with pytest.raises(SanitizationLeakError):
        assert_no_leakage(
            {
                "blinded_run_id": "BLIND-1234abcd",
                "patient_id": "SP-001",
                "turns": [{"turn": 1, "patient_text": "x", "final_output": "enable_output_guard true"}],
            }
        )
    with pytest.raises(SanitizationLeakError):
        assert_no_leakage(
            {
                "blinded_run_id": "BLIND-1234abcd",
                "patient_id": "SP-001",
                "condition_secret": "COND-A",
                "turns": [],
            }
        )


def test_condition_invalid_leak_in_case_json():
    bad_case = copy.deepcopy(R.load_cases()[0])
    bad_case["danger_condition"] = "當 condition C 開啟時"
    with pytest.raises(V.ConditionLeakError):
        V.validate_no_condition_leak([bad_case])
