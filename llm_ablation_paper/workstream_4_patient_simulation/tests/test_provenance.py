"""test_provenance — 每筆 sha/file/row_index/department/commit 可追溯，is_synthetic true (offline)."""
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


def test_every_profile_has_hash_and_is_synthetic():
    profiles = make_valid_12()
    for idx, p in enumerate(profiles):
        assert "profile_hash" in p, f"profile {idx} missing profile_hash"
        assert p["is_synthetic"] is True, f"profile {idx} is_synthetic must be true"
        errs = vp.validate_one(p, idx)
        assert not any("profile_hash" in e or "is_synthetic" in e for e in errs)


def test_provenance_eight_fields_present():
    p = make_one("SP-001", "DAILY_DIET", 0)
    prov = p["source_provenance"]
    required = ["source_file", "source_sha256", "row_index", "department", "commit", "created_at", "author", "derivation_method", "matched_source_terms", "matched_scenario_terms", "source_role", "synthetic_additions"]
    for f in required:
        assert f in prov
    assert len([k for k in required if k in prov]) == 12
    # additionalProperties true 保留，允許額外欄位
    errs = vp.validate_one(p, 0)
    assert errs == []


def test_provenance_missing_field_fails():
    for missing in ["source_file", "source_sha256", "row_index", "department", "commit"]:
        p = make_one("SP-001", "DAILY_DIET", 0)
        del p["source_provenance"][missing]
        errs = vp.validate_one(p, 0)
        assert any(missing in e for e in errs), f"should fail when missing {missing}, got {errs}"


def test_provenance_sha_format():
    p = make_one("SP-001", "DAILY_DIET", 0)
    # valid 64 hex
    errs = vp.validate_one(p, 0)
    assert not any("source_sha256" in e for e in errs)
    p["source_provenance"]["source_sha256"] = "not-a-hash"
    errs2 = vp.validate_one(p, 0)
    assert any("source_sha256" in e for e in errs2)
    p["source_provenance"]["source_sha256"] = "abc123"  # too short
    errs3 = vp.validate_one(p, 0)
    assert any("source_sha256" in e for e in errs3)


def test_provenance_commit_and_row_index():
    p = make_one("SP-001", "DAILY_DIET", 0)
    p["source_provenance"]["row_index"] = -1
    errs = vp.validate_one(p, 0)
    assert any("row_index" in e for e in errs)
    p = make_one("SP-001", "DAILY_DIET", 0)
    p["source_provenance"]["commit"] = "zzz"
    errs2 = vp.validate_one(p, 0)
    assert any("commit" in e for e in errs2)


def test_provenance_file_and_department_nonempty():
    p = make_one("SP-001", "DAILY_DIET", 0)
    p["source_provenance"]["source_file"] = ""
    errs = vp.validate_one(p, 0)
    assert any("source_file" in e for e in errs)
    p = make_one("SP-002", "DAILY_DIET", 1)
    p["source_provenance"]["department"] = ""
    errs2 = vp.validate_one(p, 0)
    assert any("department" in e for e in errs2)


def test_synthetic_fixture_label():
    profiles = make_valid_12()
    for p in profiles:
        assert p["source_provenance"]["derivation_method"] == "synthetic-fixture"
    # validator should accept synthetic-fixture but reject empty derivation
    p = make_one("SP-001", "DAILY_DIET", 0)
    p["source_provenance"]["derivation_method"] = ""
    errs = vp.validate_one(p, 0)
    assert any("derivation_method" in e for e in errs)


def test_is_synthetic_false_fails_provenance():
    p = make_one("SP-001", "DAILY_DIET", 0)
    p["is_synthetic"] = False
    errs = vp.validate_one(p, 0)
    assert any("is_synthetic" in e for e in errs)
    p["is_synthetic"] = "true"
    errs2 = vp.validate_one(p, 0)
    assert any("is_synthetic" in e for e in errs2)


def test_provenance_five_major_fields_plus_hash():
    # Every profile must have profile_hash + is_synthetic + persona/known/hidden/reveal/goal (5 major)
    profiles = make_valid_12()
    errs = vp.validate_all(profiles, _schema())
    assert errs == []
    # remove one major
    bad = make_valid_12()
    del bad[0]["persona"]
    errs2 = vp.validate_all(bad, _schema())
    assert any("persona" in e or "major" in e for e in errs2)


def test_offline_fixture_when_no_real_file():
    # This test must pass even when patient_profiles.jsonl absent
    WS_profiles = WS / "patient_profiles.jsonl"
    # We don't require file; just validate fixture alone
    profiles = make_valid_12()
    errs = vp.validate_all(profiles, _schema())
    assert errs == []
