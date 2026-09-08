"""test_reveal_policy — hidden 只在被問才透露、FACT_CONTRADICTION 更正輪次、PREVISIT 解鎖順序、不迎合/不改事實 (offline)."""
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


def _valid():
    return make_one("SP-001", "DAILY_DIET", 0)


def test_reveal_policy_structure_valid():
    p = _valid()
    rp = p["reveal_policy"]
    assert rp["disclosure_rule"] == "on_direct_question_only"
    assert rp["allow_voluntary_disclosure"] is False
    assert 1 <= rp["correction_turn"] <= 6
    assert isinstance(rp["previsit_unlock_order"], list) and len(rp["previsit_unlock_order"]) >= 1
    kb = rp["knowledge_boundary"]
    assert kb["knows_medical_answer"] is False
    assert kb["will_accommodate_system_error"] is False
    assert kb["will_alter_facts"] is False
    errs = vp.validate_one(p, 0)
    assert errs == []


def test_hidden_only_on_direct_question():
    p = _valid()
    errs = vp.validate_one(p, 0)
    assert not any("disclosure_rule" in e for e in errs)
    p2 = _valid()
    p2["reveal_policy"]["disclosure_rule"] = "always_volunteer"
    errs2 = vp.validate_one(p2, 0)
    assert any("disclosure_rule" in e for e in errs2)
    p3 = _valid()
    p3["reveal_policy"]["disclosure_rule"] = "on_direct_question_only"
    p3["reveal_policy"]["allow_voluntary_disclosure"] = True
    errs3 = vp.validate_one(p3, 0)
    assert any("allow_voluntary_disclosure" in e for e in errs3)


def test_allow_voluntary_must_be_false():
    p = _valid()
    p["reveal_policy"]["allow_voluntary_disclosure"] = True
    errs = vp.validate_one(p, 0)
    assert any("allow_voluntary_disclosure" in e for e in errs)
    p["reveal_policy"]["allow_voluntary_disclosure"] = False
    errs2 = vp.validate_one(p, 0)
    assert not any("allow_voluntary_disclosure" in e for e in errs2)


def test_fact_contradiction_correction_turn():
    # For FACT_CONTRADICTION scenario, correction_turn must be 1-6
    p = make_one("SP-011", "FACT_CONTRADICTION", 10)
    assert 1 <= p["reveal_policy"]["correction_turn"] <= 6
    errs = vp.validate_one(p, 0)
    assert not any("correction_turn" in e for e in errs)
    for bad in [0, 7, "2", None]:
        p2 = _valid()
        p2["reveal_policy"]["correction_turn"] = bad
        errs2 = vp.validate_one(p2, 0)
        assert any("correction_turn" in e for e in errs2), f"should fail for {bad!r}"


def test_previsit_unlock_order_required():
    p = _valid()
    p["reveal_policy"]["previsit_unlock_order"] = []
    errs = vp.validate_one(p, 0)
    assert any("previsit_unlock_order" in e for e in errs)
    p2 = _valid()
    p2["reveal_policy"]["previsit_unlock_order"] = ["chief_complaint"]
    errs2 = vp.validate_one(p2, 0)
    assert not any("previsit_unlock_order" in e for e in errs2)
    # PREVISIT scenario should have meaningful order
    p3 = make_one("SP-009", "PREVISIT_SUMMARY", 8)
    assert len(p3["reveal_policy"]["previsit_unlock_order"]) >= 1
    errs3 = vp.validate_one(p3, 0)
    assert not any("previsit_unlock_order" in e for e in errs3)


def test_patient_does_not_know_answer():
    p = _valid()
    p["reveal_policy"]["knowledge_boundary"]["knows_medical_answer"] = True
    errs = vp.validate_one(p, 0)
    assert any("knows_medical_answer" in e for e in errs)


def test_patient_does_not_accommodate_system_error():
    p = _valid()
    p["reveal_policy"]["knowledge_boundary"]["will_accommodate_system_error"] = True
    errs = vp.validate_one(p, 0)
    assert any("will_accommodate_system_error" in e for e in errs)


def test_patient_does_not_alter_facts():
    p = _valid()
    p["reveal_policy"]["knowledge_boundary"]["will_alter_facts"] = True
    errs = vp.validate_one(p, 0)
    assert any("will_alter_facts" in e for e in errs)


def test_all_three_knowledge_boundaries_must_be_false():
    p = _valid()
    kb = p["reveal_policy"]["knowledge_boundary"]
    assert kb["knows_medical_answer"] is False
    assert kb["will_accommodate_system_error"] is False
    assert kb["will_alter_facts"] is False
    # any True fails
    for key in ["knows_medical_answer", "will_accommodate_system_error", "will_alter_facts"]:
        p2 = _valid()
        p2["reveal_policy"]["knowledge_boundary"][key] = True
        errs = vp.validate_one(p2, 0)
        assert any(key in e for e in errs)


def test_reveal_policy_missing_field_fails():
    for field in ["disclosure_rule", "allow_voluntary_disclosure", "correction_turn", "previsit_unlock_order", "knowledge_boundary"]:
        p = _valid()
        del p["reveal_policy"][field]
        errs = vp.validate_one(p, 0)
        assert any(field in e for e in errs), f"missing {field} should fail"


def test_all_valid_12_reveal_ok():
    profiles = make_valid_12()
    errs = vp.validate_all(profiles)
    assert not any("reveal_policy" in e or "knowledge_boundary" in e for e in errs)
    assert not any("disclosure" in e for e in errs)
