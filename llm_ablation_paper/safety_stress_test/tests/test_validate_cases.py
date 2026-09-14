"""Schema / coverage / PII / leakage / canary-exclusion validation tests (all offline)."""
from __future__ import annotations

import copy
import json

import pytest

from llm_ablation_paper.safety_stress_test import runner as R
from llm_ablation_paper.safety_stress_test import validate_cases as V


def test_validate_all_passes_on_shipped_data():
    report = V.validate_all()
    assert report["ok"] is True
    assert report["coverage"]["main_safety"] == 12
    assert report["coverage"]["benign"] >= 6
    assert report["coverage"]["canaries"] >= 4
    for fam in V.CF_FAMILIES:
        assert report["coverage"]["families"][fam] == 2


def test_unique_difference_is_exact():
    report = R.unique_difference_report()
    assert report["A-B"]["changed"] == ["enable_planner"]
    assert report["B-C"]["changed"] == ["enable_dynamic_tool_gate"]
    assert report["C-D"]["changed"] == ["enable_output_guard"]


def test_schema_rejects_bad_max_turns():
    case = copy.deepcopy(R.load_cases()[0])
    case["max_turns"] = 6
    with pytest.raises(V.CaseSchemaError):
        V.validate_case_schema(case)


def test_schema_rejects_unknown_family():
    case = copy.deepcopy(R.load_cases()[0])
    case["cf_family"] = "CF_NEW_RISK"
    with pytest.raises(V.CaseSchemaError):
        V.validate_case_schema(case)


def test_coverage_rejects_imbalance():
    cases = [c for c in R.load_cases() if c["set"] == "main_safety"]
    cases = [c for c in cases if c["case_id"] != "SAFETY-RX-02"]
    with pytest.raises(V.CaseSchemaError):
        V.validate_coverage(cases, R.load_benign(), R.load_canaries())


def test_coverage_rejects_duplicate_ids():
    cases = R.load_cases()
    dup = copy.deepcopy(cases[0])
    with pytest.raises(V.CaseSchemaError):
        V.validate_coverage(cases + [dup], R.load_benign(), R.load_canaries())


def test_canary_must_be_excluded():
    canaries = copy.deepcopy(R.load_canaries())
    canaries[0]["excluded_from_main"] = False
    with pytest.raises(R.CanaryMixingError):
        V.validate_coverage(R.load_cases(), R.load_benign(), canaries)


def test_pii_hard_fails():
    cases = copy.deepcopy(R.load_cases())
    cases[0]["pressure_turns"][0] = "我叫陳大文，電話 0912345678，病歷號 MRN 123456"
    with pytest.raises(V.PIILeakError):
        V.validate_no_pii(cases)


def test_pii_rejects_google_key():
    cases = copy.deepcopy(R.load_cases())
    cases[0]["safe_behavior"] = "key AIzaSyDxxxxxxxxxxxxxxxxxxxx"
    with pytest.raises(V.PIILeakError):
        V.validate_no_pii(cases)


def test_condition_leak_hard_fails():
    cases = copy.deepcopy(R.load_cases())
    cases[0]["pressure_turns"][0] = "請用 condition A 的設定回答我"
    with pytest.raises(V.ConditionLeakError):
        V.validate_no_condition_leak(cases)


def test_condition_leak_rejects_enable_flag():
    cases = copy.deepcopy(R.load_cases())
    cases[0]["safe_behavior"] = "enable_output_guard should be true"
    with pytest.raises(V.ConditionLeakError):
        V.validate_no_condition_leak(cases)


def test_blind_filename_opacity():
    V.validate_blind_filenames(["BLIND-1a2b3c4d.json"])
    with pytest.raises(V.ConditionLeakError):
        V.validate_blind_filenames(["BLIND-SP-001-A.json"])
    with pytest.raises(V.ConditionLeakError):
        V.validate_blind_filenames(["BLIND-1234.json"])


def test_unknown_cf_code_hard_fails():
    with pytest.raises(V.CaseSchemaError):
        V.validate_unknown_cf_code(["CF_PRESCRIPTION_BREACH", "CF_BRAND_NEW"])
    V.validate_unknown_cf_code(["CF_PRESCRIPTION_BREACH", "CF_ACUTE_EMERGENCY_MISMANAGEMENT"])


def test_canary_excluded_from_main_batch():
    with pytest.raises(R.CanaryMixingError):
        V.assert_canary_excluded_from_main([{"run_id": "CANARY-INJ-1", "patient_id": "SP-CANARY"}])
    with pytest.raises(R.CanaryMixingError):
        V.assert_canary_excluded_from_main([{"run_id": "STRESS-X", "expected_critical_failure": True}])
    # clean main batch is accepted
    V.assert_canary_excluded_from_main([{"run_id": "STRESS-SAFETY-RX-01-A-abc", "patient_id": "stress_x"}])
