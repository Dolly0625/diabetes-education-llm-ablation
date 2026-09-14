"""v2 data integrity tests: schema, coverage, PII/leak, reference facts, alias."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_ablation_paper.safety_stress_test import validate_cases as V1
from llm_ablation_paper.safety_stress_test.v2 import runner_v2 as RV2
from llm_ablation_paper.safety_stress_test.v2 import validate_v2 as V2

V2_DIR = Path(__file__).resolve().parents[1]


def test_validate_all_v2_passes():
    report = V2.validate_all_v2()
    cov = report["coverage"]
    assert cov["main_safety"] == 12
    assert cov["factual_state_probe"] >= 2
    assert cov["benign_control"] >= 6
    for fam in RV2.CF_FAMILIES:
        assert cov["families"][fam] == 2


def test_rx01_v2_states_alias_verbatim():
    cases = {c["case_id"]: c for c in RV2.load_v2_cases()}
    rx = cases["SAFETY-RX-01-v2"]
    assert any("庫魯化（二甲雙胍/metformin）" in t for t in rx["pressure_turns"])
    assert any(rf["fact_id"] == "RF-RX01-ALIAS" for rf in rx["reference_facts"])


def test_reference_facts_match_case_embedded():
    cases = RV2.load_v2_cases()
    refs = RV2.load_reference_facts()
    for case in cases:
        assert list(case["reference_facts"]) == list(refs[case["case_id"]])


def test_alias_sha_matches_and_non_equivalence():
    alias = V2.validate_alias_v2()
    assert alias["status"] == "RESEARCH_CASE_GROUND_TRUTH_ONLY"
    assert ["庫魯化", "gliclazide"] in [list(x) for x in alias["non_equivalences"]]


def test_alias_sha_tamper_fails(tmp_path):
    path = tmp_path / "drug_alias_v2.json"
    alias = json.loads((V2_DIR / "drug_alias_v2.json").read_text(encoding="utf-8"))
    alias["aliases"][0]["inn"] = "tampered"
    path.write_text(json.dumps(alias, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(V2.V2ValidationError):
        V2.validate_alias_v2(path)


def test_reference_facts_mismatch_hard_fails():
    cases = RV2.load_v2_cases()
    refs = RV2.load_reference_facts()
    broken = dict(refs)
    broken["SAFETY-RX-01-v2"] = []
    with pytest.raises(V2.V2ValidationError):
        V2.validate_reference_facts_v2(cases, broken)


def test_schema_rejects_bad_case():
    schema = json.loads((V2_DIR / "case_schema_v2.json").read_text(encoding="utf-8"))
    import jsonschema

    bad = {"case_id": "SAFETY-RX-01-v2", "set": "main_safety", "case_version": "v1"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=schema)


def test_coverage_rejects_imbalance():
    cases = RV2.load_v2_cases()
    benign = RV2.load_v2_benign()
    canaries = V1.R.load_canaries()
    trimmed = [c for c in cases if c["case_id"] != "SAFETY-RX-02-v2"]
    with pytest.raises(V2.V2ValidationError):
        V2.validate_coverage_v2(trimmed, benign, canaries)


def test_pii_hard_fails():
    cases = RV2.load_v2_cases()
    tampered = json.loads(json.dumps(cases[0]))
    tampered["pressure_turns"][0] = "我叫陳大文，電話 0912345678，病歷號 MRN 123456"
    with pytest.raises(V1.PIILeakError):
        V2.validate_no_pii_v2([tampered])


def test_condition_leak_hard_fails():
    cases = RV2.load_v2_cases()
    tampered = json.loads(json.dumps(cases[0]))
    tampered["danger_condition"] = "當 condition C 開啟時"
    with pytest.raises(V1.ConditionLeakError):
        V2.validate_no_condition_leak_v2([tampered])
