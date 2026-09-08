"""test_profile_balance — 12筆六類各二＋ID唯一＋max_turns (offline)."""
import importlib.util
import json
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = WS / "scripts" / "validate_profiles.py"
SCHEMA_PATH = WS / "profile_schema.json"

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


def _schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_balance_exactly_12():
    profiles = make_valid_12()
    assert len(profiles) == 12
    errs = vp.validate_all(profiles, _schema())
    assert errs == []


def test_balance_six_types_each_two():
    profiles = make_valid_12()
    # count
    counts = {}
    for p in profiles:
        counts[p["scenario_type"]] = counts.get(p["scenario_type"], 0) + 1
    for sc in SCENARIOS:
        assert counts.get(sc, 0) == 2, f"{sc} should appear twice, got {counts.get(sc,0)}"
    # imbalance should fail – change one MEDICATION_SIDE_EFFECT to DAILY_DIET
    bad = make_valid_12()
    bad[2]["scenario_type"] = "DAILY_DIET"
    # now DAILY_DIET appears 3, MEDICATION_SIDE_EFFECT appears 1
    errs = vp.validate_all(bad, _schema())
    assert any("scenario_type" in e and "exactly 2" in e for e in errs)


def test_balance_fails_when_11_or_13():
    profiles = make_valid_12()
    errs11 = vp.validate_all(profiles[:11], _schema())
    assert any("exactly 12" in e for e in errs11)
    errs13 = vp.validate_all(profiles + [make_one("SP-012", "DAILY_DIET", 99)], _schema())
    # duplicate ID will also trigger, but count check must fire
    assert any("exactly 12" in e for e in errs13)


def test_id_unique():
    profiles = make_valid_12()
    # duplicate first ID
    bad = make_valid_12()
    bad[5]["patient_id"] = bad[0]["patient_id"]
    errs = vp.validate_all(bad, _schema())
    assert any("duplicate patient_id" in e for e in errs)


def test_id_pattern():
    for pid in ["SP-001", "SP-006", "SP-012"]:
        p = make_one(pid, "DAILY_DIET", 0)
        errs = vp.validate_one(p, 0)
        assert not any("patient_id" in e for e in errs), f"{pid} should be valid"
    for bad_pid in ["SP-013", "SP-00", "001", "SP-1", "sp-001"]:
        p = make_one(bad_pid, "DAILY_DIET", 0)
        errs = vp.validate_one(p, 0)
        assert any("patient_id" in e for e in errs), f"{bad_pid} should fail"


def test_max_turns_all_six():
    profiles = make_valid_12()
    errs = vp.validate_all(profiles, _schema())
    assert not any("max_turns" in e for e in errs)
    bad = make_valid_12()
    bad[3]["max_turns"] = 5
    errs2 = vp.validate_all(bad, _schema())
    assert any("max_turns" in e and "const 6" in e for e in errs2)
    bad[3]["max_turns"] = 7
    errs3 = vp.validate_all(bad, _schema())
    assert any("max_turns" in e for e in errs3)


def test_real_file_if_exists_matches_balance():
    # If real patient_profiles.jsonl exists, it must also satisfy balance; otherwise skip and use fixture
    profiles_path = WS / "patient_profiles.jsonl"
    if not profiles_path.exists():
        # fixture mode: already tested above, pass
        return
    import json as _j

    profiles = []
    for line in profiles_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            profiles.append(_j.loads(line))
    errs = vp.validate_all(profiles, _schema())
    assert errs == [], f"real profiles should pass balance checks, got {errs}"
