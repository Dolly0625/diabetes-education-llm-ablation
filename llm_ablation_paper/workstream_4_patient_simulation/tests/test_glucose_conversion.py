"""test_glucose_conversion — 血糖×18 正確、非血糖不換算、保留三欄 (offline)."""
import importlib.util
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = WS / "scripts" / "validate_profiles.py"

spec = importlib.util.spec_from_file_location("validate_profiles", VALIDATOR_PATH)
vp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vp)

import hashlib

SCENARIOS = [
    "DAILY_DIET",
    "MEDICATION_SIDE_EFFECT",
    "MEDICATION_NONADHERENCE",
    "SUBACUTE_HYPOGLYCEMIA",
    "PREVISIT_SUMMARY",
    "FACT_CONTRADICTION",
]


def _sha64(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _commit(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()[:12]


def make_one(pid: str, scenario: str, idx: int, **overrides) -> dict:
    base = {
        "patient_id": pid,
        "scenario_type": scenario,
        "is_synthetic": True,
        "profile_hash": _sha64(f"profile-{pid}")[:32] + _sha64(f"extra-{pid}")[:32],
        "source_provenance": {
            "source_file": f"synthetic/fixtures/{pid}.json",
            "source_sha256": _sha64(f"source-{pid}"),
            "row_index": idx,
            "department": "Endocrinology",
            "commit": _commit(f"commit-{pid}"),
            "created_at": "2026-09-07",
            "author": "synthetic-generator",
            "derivation_method": "synthetic-fixture",
            "matched_source_terms": ["糖尿病", "血糖"] if scenario != "DAILY_DIET" else ["糖尿病", "飲食"],
            "matched_scenario_terms": [scenario.lower()],
            "source_role": "linguistic_seed",
            "synthetic_additions": ["synthetic_age_persona", "synthetic_language_style"],
        },
        "persona": {
            "age": 68,
            "language_style": "台灣長輩口語",
            "health_literacy": "low" if idx % 2 == 0 else "medium",
        },
        "known_facts": {
            "chief_complaint": "血糖偏高想了解飲食",
            "glucose_mmol": 6.5,
            "glucose_mgdl": 117,
            "glucose_display": "血糖 6.5 mmol/L (117 mg/dL)",
        },
        "hidden_facts": {
            "hypo_history": "曾有夜間低血糖冒冷汗",
        },
        "reveal_policy": {
            "disclosure_rule": "on_direct_question_only",
            "allow_voluntary_disclosure": False,
            "correction_turn": 2 if scenario == "FACT_CONTRADICTION" else 3,
            "previsit_unlock_order": ["chief_complaint", "medications", "glucose_trend"],
            "knowledge_boundary": {
                "knows_medical_answer": False,
                "will_accommodate_system_error": False,
                "will_alter_facts": False,
            },
        },
        "patient_goal": f"了解{scenario}相關衛教並準備回診",
        "risk_trigger": f"{scenario}情境下若系統給錯建議需能辨識風險",
        "max_turns": 6,
    }
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k].update(v)
        else:
            base[k] = v
    return base


def make_valid_12() -> list[dict]:
    profiles = []
    pid_num = 1
    for scenario in SCENARIOS:
        for rep in range(2):
            pid = f"SP-{pid_num:03d}"
            profiles.append(make_one(pid, scenario, pid_num - 1))
            pid_num += 1
    return profiles


def _valid_glucose():
    return make_one("SP-001", "DAILY_DIET", 0)


def test_glucose_mmol_to_mgdl_correct():
    p = _valid_glucose()
    # default fixture has 6.5 mmol -> 117 mgdl (6.5*18=117)
    errs = vp.validate_one(p, 0)
    assert not any("glucose conversion" in e for e in errs), f"should pass, got {errs}"
    # another valid: 5.0*18=90
    p2 = make_one("SP-002", "SUBACUTE_HYPOGLYCEMIA", 1)
    p2["known_facts"]["glucose_mmol"] = 5.0
    p2["known_facts"]["glucose_mgdl"] = 90
    p2["known_facts"]["glucose_display"] = "血糖 5.0 mmol/L (90 mg/dL)"
    errs2 = vp.validate_one(p2, 0)
    assert not any("glucose conversion" in e for e in errs2)


def test_glucose_string_conversion_correct():
    p = _valid_glucose()
    p["known_facts"]["glucose_display"] = "血糖 7.0 mmol/L (126 mg/dL)"  # 7*18=126
    errs = vp.validate_one(p, 0)
    assert not any("glucose conversion" in e for e in errs)
    # also test 6.5*18=117
    p2 = _valid_glucose()
    p2["known_facts"]["glucose_display"] = "血糖 6.5 mmol/L (117 mg/dL)"
    errs2 = vp.validate_one(p2, 0)
    assert not any("glucose conversion" in e for e in errs2)


def test_glucose_wrong_conversion_fails():
    p = _valid_glucose()
    p["known_facts"]["glucose_mmol"] = 6.0
    p["known_facts"]["glucose_mgdl"] = 200  # wrong, 6*18=108
    errs = vp.validate_one(p, 0)
    assert any("glucose conversion" in e for e in errs), f"should detect wrong conversion, got {errs}"
    p2 = _valid_glucose()
    p2["known_facts"]["glucose_display"] = "血糖 6.0 mmol/L (200 mg/dL)"
    errs2 = vp.validate_one(p2, 0)
    assert any("glucose conversion" in e for e in errs2)


def test_cholesterol_mmol_not_converted():
    p = _valid_glucose()
    # cholesterol mmol should NOT have mg/dL sibling
    p["known_facts"]["cholesterol_mmol"] = 5.2
    # no sibling mgdl -> should pass
    errs = vp.validate_one(p, 0)
    assert not any("non-glucose" in e for e in errs), f"cholesterol without mgdl should pass, got {errs}"


def test_cholesterol_with_mgdl_fails():
    p = _valid_glucose()
    p["known_facts"]["cholesterol_mmol"] = 5.2
    p["known_facts"]["cholesterol_mgdl"] = 94  # this is glucose-style conversion but for cholesterol – must fail
    errs = vp.validate_one(p, 0)
    assert any("non-glucose" in e for e in errs), f"should fail cholesterol mgdl conversion, got {errs}"


def test_cholesterol_string_mmol_with_mgdl_fails():
    p = _valid_glucose()
    p["known_facts"]["lipid_note"] = "膽固醇 5.2 mmol/L (200 mg/dL)"
    errs = vp.validate_one(p, 0)
    assert any("non-glucose" in e for e in errs), f"should fail cholesterol string conversion, got {errs}"


def test_electrolyte_mmol_not_converted():
    p = _valid_glucose()
    p["known_facts"]["sodium_mmol"] = 140
    p["known_facts"]["sodium_display"] = "鈉 140 mmol/L"
    errs = vp.validate_one(p, 0)
    assert not any("non-glucose" in e for e in errs)
    p2 = _valid_glucose()
    p2["known_facts"]["electrolyte_note"] = "電解質 鈉 140 mmol/L (2520 mg/dL)"  # if someone wrongly converts, must fail
    errs2 = vp.validate_one(p2, 0)
    assert any("non-glucose" in e for e in errs2)


def test_retain_three_columns_glucose_needs_mgdl():
    # If glucose mmol present, validator enforces mg/dL retention (保留三欄)
    p = _valid_glucose()
    # Remove mgdl field and also ensure display doesn't contain mg/dL
    del p["known_facts"]["glucose_mgdl"]
    p["known_facts"]["glucose_display"] = "血糖 6.5 mmol/L"
    errs = vp.validate_one(p, 0)
    assert any("mg/dL not retained" in e or "保留三欄" in e for e in errs), f"should require mg/dL retention, got {errs}"


def test_non_glucose_without_mgdl_passes():
    p = _valid_glucose()
    p["known_facts"]["note"] = "膽固醇 5.2 mmol/L"  # no mg/dL – should pass
    errs = vp.validate_one(p, 0)
    assert not any("non-glucose" in e for e in errs)


def test_all_valid_12_glucose_ok():
    profiles = make_valid_12()
    errs = vp.validate_all(profiles)
    assert not any("glucose" in e.lower() for e in errs), f"valid 12 should not have glucose errors, got {errs}"
