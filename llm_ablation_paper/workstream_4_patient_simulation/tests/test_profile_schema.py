"""test_profile_schema — 欄位/型別/枚舉 (offline, fixture-capable)."""
import json
import importlib.util
import sys
from pathlib import Path

# import validator for structural checks
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


def _load_schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_schema_file_exists_and_draft07():
    assert SCHEMA_PATH.exists(), f"profile_schema.json not found at {SCHEMA_PATH}"
    s = _load_schema()
    assert s.get("$schema") == "http://json-schema.org/draft-07/schema#"
    assert s.get("type") == "object"


def test_schema_required_top_fields():
    s = _load_schema()
    required = set(s.get("required", []))
    expected = {"patient_id", "scenario_type", "is_synthetic", "source_provenance", "persona", "known_facts", "hidden_facts", "reveal_policy", "patient_goal", "risk_trigger", "max_turns", "profile_hash"}
    for field in expected:
        assert field in required, f"schema missing required '{field}'"


def test_schema_patient_id_pattern():
    s = _load_schema()
    pat = s["properties"]["patient_id"]["pattern"]
    import re

    re_pat = re.compile(pat)
    assert re_pat.match("SP-001")
    assert re_pat.match("SP-012")
    assert not re_pat.match("SP-013")
    assert not re_pat.match("SP-1")
    assert not re_pat.match("SP-00A")


def test_schema_scenario_enum_six():
    s = _load_schema()
    enum = s["properties"]["scenario_type"]["enum"]
    assert len(enum) == 6, f"scenario_type must have 6 enums, got {enum}"
    assert set(enum) == set(SCENARIOS)
    # each enum non-empty string
    for e in enum:
        assert isinstance(e, str) and e


def test_schema_is_synthetic_const_true():
    s = _load_schema()
    is_syn = s["properties"]["is_synthetic"]
    assert is_syn.get("const") is True
    assert is_syn.get("type") == "boolean"


def test_schema_source_provenance_eight_required():
    s = _load_schema()
    prov = s["properties"]["source_provenance"]
    assert prov.get("type") == "object"
    req = prov.get("required", [])
    assert len(req) == 12, f"source_provenance must have 12 required fields (8+4 new), got {req}"
    for field in ["source_file", "source_sha256", "row_index", "department", "commit", "created_at", "author", "derivation_method", "matched_source_terms", "matched_scenario_terms", "source_role", "synthetic_additions"]:
        assert field in req, f"provenance missing {field}"
    assert prov.get("additionalProperties") is True, "source_provenance must keep additionalProperties true (provenance寬容)"
    # types
    assert prov["properties"]["source_sha256"]["pattern"] == "^[a-fA-F0-9]{64}$"
    assert prov["properties"]["row_index"]["type"] == "integer"
    # new fields checks
    assert prov["properties"]["matched_source_terms"]["minItems"] == 1
    assert prov["properties"]["matched_scenario_terms"]["minItems"] == 1
    assert prov["properties"]["source_role"]["enum"] == ["linguistic_seed", "scenario_seed", "background_seed"]
    assert prov["properties"]["synthetic_additions"]["minItems"] == 1


def test_schema_persona_constraints():
    s = _load_schema()
    persona = s["properties"]["persona"]
    assert persona["properties"]["age"]["type"] == "integer"
    assert persona["properties"]["age"]["minimum"] == 20
    assert set(persona["properties"]["health_literacy"]["enum"]) == {"low", "medium"}
    assert "language_style" in persona["required"]


def test_schema_known_hidden_reveal_are_objects():
    s = _load_schema()
    for field in ("known_facts", "hidden_facts", "reveal_policy"):
        assert s["properties"][field]["type"] == "object", f"{field} must be object"
    # reveal_policy must have 5 required subfields
    rp = s["properties"]["reveal_policy"]
    for sub in ["disclosure_rule", "allow_voluntary_disclosure", "correction_turn", "previsit_unlock_order", "knowledge_boundary"]:
        assert sub in rp["required"]


def test_schema_patient_goal_risk_trigger_non_empty():
    s = _load_schema()
    for field in ("patient_goal", "risk_trigger"):
        assert s["properties"][field]["type"] == "string"
        assert s["properties"][field]["minLength"] >= 1


def test_schema_max_turns_const_6():
    s = _load_schema()
    assert s["properties"]["max_turns"]["const"] == 6
    assert s["properties"]["max_turns"]["type"] == "integer"


def test_schema_no_network_dependency():
    s = _load_schema()
    # ensure no $ref to http remote
    text = json.dumps(s)
    assert "http" not in text or "http://json-schema.org/draft-07/schema#" in text  # only the $schema identifier allowed
    # no external refs
    assert "$ref" not in s or s["$ref"].startswith("#") if "$ref" in s else True


def test_validator_rejects_invalid_schema_cases():
    # missing required field
    bad = make_one("SP-001", "DAILY_DIET", 0)
    del bad["patient_goal"]
    errs = vp.validate_one(bad, 0)
    assert any("patient_goal" in e for e in errs)

    # wrong type for age
    bad2 = make_one("SP-001", "DAILY_DIET", 0)
    bad2["persona"]["age"] = "seventy"
    errs2 = vp.validate_one(bad2, 0)
    assert any("persona.age" in e for e in errs2)

    # invalid health_literacy
    bad3 = make_one("SP-001", "DAILY_DIET", 0)
    bad3["persona"]["health_literacy"] = "high"
    errs3 = vp.validate_one(bad3, 0)
    assert any("health_literacy" in e for e in errs3)

    # is_synthetic false should fail
    bad4 = make_one("SP-001", "DAILY_DIET", 0)
    bad4["is_synthetic"] = False
    errs4 = vp.validate_one(bad4, 0)
    assert any("is_synthetic" in e for e in errs4)

    # invalid scenario_type
    bad5 = make_one("SP-001", "DAILY_DIET", 0)
    bad5["scenario_type"] = "UNKNOWN"
    errs5 = vp.validate_one(bad5, 0)
    assert any("scenario_type" in e for e in errs5)


def test_validator_accepts_valid_fixture():
    profiles = make_valid_12()
    errs = vp.validate_all(profiles, _load_schema())
    assert errs == [], f"valid fixtures should pass, got {errs}"


def test_schema_offline_with_fixture_when_profiles_missing():
    # even if real patient_profiles.jsonl absent, fixture validation still works offline
    profiles = make_valid_12()
    # tamper one field to ensure validator catches without needing file
    bad = profiles[0].copy()
    bad["is_synthetic"] = "not-bool"
    errs = vp.validate_one(bad, 0)
    assert any("is_synthetic" in e for e in errs)
