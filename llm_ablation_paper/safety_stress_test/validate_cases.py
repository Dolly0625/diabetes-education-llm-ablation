"""Fail-closed validation for the exploratory safety stress test.

Every failure mode here HARD-FAILS (raises); nothing warns-and-continues and nothing
is silently skipped. Checks implemented per PM self-review of Agent A/C/D findings:
  * JSON-schema conformance (manual, no external dependency)
  * unique IDs / 6-CF-family balance (2 each) / benign >= 6 / canaries >= 4 excluded
  * PII + provider-secret scan
  * condition-leakage scan (A/B/C/D, enable_*, planner/guard internals)
  * base_profile existence
  * frozen fingerprint verification (fail-closed if missing/mismatch)
  * condition mapping fail-closed (None forbidden, opaque enforced)
  * canary exclusion from main comparison
  * unknown CF code rejection
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from llm_ablation_paper.safety_stress_test import runner as R
from llm_ablation_paper.safety_stress_test.rule_based_scanner import CF_FAMILIES

SST_DIR = Path(__file__).resolve().parent
SCENARIOS = {
    "DAILY_DIET",
    "MEDICATION_SIDE_EFFECT",
    "MEDICATION_NONADHERENCE",
    "SUBACUTE_HYPOGLYCEMIA",
    "PREVISIT_SUMMARY",
    "FACT_CONTRADICTION",
}
ALLOWED_FAMILIES = set(CF_FAMILIES) | {"NONE"}

PII_PATTERNS = [
    ("TW_ID", re.compile(r"\b[A-Z][12]\d{8}\b")),
    ("MOBILE", re.compile(r"\b09\d{8}\b")),
    ("LANDLINE", re.compile(r"\b(?:02|03|04|05|06|07|08)\d{7,8}\b")),
    ("MRN", re.compile(r"(?:MRN|病歷號|病歷)\s*[:#]?\s*\d{4,}", re.IGNORECASE)),
    ("EMAIL", re.compile(r"\S+@\S+\.\S+")),
]
SECRET_PATTERNS = [
    ("API_KEY", re.compile(r"(api[_-]?key|apikey|secret|password|authorization|bearer\s+[A-Za-z0-9])", re.IGNORECASE)),
    ("GOOGLE_KEY", re.compile(r"AIza[0-9A-Za-z_\-]{10,}")),
]
CONDITION_LEAK_PATTERNS = [
    ("CONDITION_LETTER", re.compile(r"\bcondition[\s_-]*[a-d]\b", re.IGNORECASE)),
    ("ENABLE_FLAG", re.compile(r"\benable[_ ](?:planner|dynamic[_ ]tool[_ ]gate|output[_ ]guard|forced[_ ]retrieval)")),
    ("CONDITION_SECRET", re.compile(r"condition[_ ]secret")),
    ("RAW_TALKER", re.compile(r"raw[_ ]talker")),
    ("GUARD_ACTION", re.compile(r"guard[_ ]action")),
    ("PLANNER_STATE", re.compile(r"planner[_ ]state")),
]
# Filenames must be opaque (BLIND-<8hex>), never condition-suffixed.
BLIND_FILENAME = re.compile(r"^BLIND-[0-9a-f]{8}\.json$")
CONDITION_SUFFIX_FILENAME = re.compile(r"-(?:A|B|C|D)\.json$")


class ValidationError(RuntimeError):
    pass


class PIILeakError(ValidationError):
    pass


class ConditionLeakError(ValidationError):
    pass


class CaseSchemaError(ValidationError):
    pass


def _text_fields(case: Dict[str, Any]) -> Iterable[str]:
    for key in ("case_id", "cf_family", "paired_cf_family", "scenario_type", "base_profile",
                "danger_condition", "safe_behavior"):
        if key in case and isinstance(case[key], str):
            yield case[key]
    for turn in case.get("pressure_turns", []) or []:
        if isinstance(turn, str):
            yield turn


def _scan_text(text: str, patterns, label: str, exc_type) -> None:
    for name, pat in patterns:
        if pat.search(text):
            raise exc_type(f"{name} pattern matched in {label}: {text[:60]!r}")


def validate_case_schema(case: Dict[str, Any]) -> None:
    required = [
        "case_id", "set", "cf_family", "scenario_type", "base_profile",
        "max_turns", "temporal_progression", "pressure_turns", "danger_condition", "safe_behavior",
    ]
    for key in required:
        if key not in case:
            raise CaseSchemaError(f"case missing required field {key!r}: {case.get('case_id')}")
    if not re.match(r"^(SAFETY|BENIGN)-[A-Z]+-[0-9]{2}$", str(case["case_id"])):
        raise CaseSchemaError(f"bad case_id pattern: {case['case_id']!r}")
    if case["set"] not in ("main_safety", "benign_control"):
        raise CaseSchemaError(f"bad set: {case['set']!r}")
    if case["cf_family"] not in ALLOWED_FAMILIES:
        raise CaseSchemaError(f"unknown cf_family: {case['cf_family']!r}")
    if case["scenario_type"] not in SCENARIOS:
        raise CaseSchemaError(f"unknown scenario_type: {case['scenario_type']!r}")
    if not re.match(r"^SP-0(0[1-9]|1[0-2])$", str(case["base_profile"])):
        raise CaseSchemaError(f"bad base_profile: {case['base_profile']!r}")
    if case["max_turns"] != 3:
        raise CaseSchemaError(f"max_turns must be 3, got {case['max_turns']!r}")
    turns = case["pressure_turns"]
    if not isinstance(turns, list) or not (1 <= len(turns) <= 3):
        raise CaseSchemaError(f"pressure_turns must be 1..3 items: {case['case_id']}")
    if not all(isinstance(t, str) and t.strip() for t in turns):
        raise CaseSchemaError(f"pressure_turns must be non-empty strings: {case['case_id']}")
    if case["set"] == "main_safety" and case["cf_family"] == "NONE":
        raise CaseSchemaError(f"main_safety case must have a CF family: {case['case_id']}")
    if case["set"] == "main_safety" and len(turns) != 3:
        raise CaseSchemaError(f"main_safety case must have exactly 3 pressure turns: {case['case_id']}")
    if case["set"] == "benign_control" and case["cf_family"] != "NONE":
        raise CaseSchemaError(f"benign control must use cf_family NONE: {case['case_id']}")


def validate_no_pii(cases: List[Dict[str, Any]]) -> None:
    for case in cases:
        for text in _text_fields(case):
            _scan_text(text, PII_PATTERNS, case["case_id"], PIILeakError)
            _scan_text(text, SECRET_PATTERNS, case["case_id"], PIILeakError)


def validate_no_condition_leak(cases: List[Dict[str, Any]]) -> None:
    for case in cases:
        for text in _text_fields(case):
            _scan_text(text, CONDITION_LEAK_PATTERNS, case["case_id"], ConditionLeakError)


def validate_coverage(cases: List[Dict[str, Any]], benign: List[Dict[str, Any]], canaries: List[Dict[str, Any]]) -> Dict[str, int]:
    ids: List[str] = [c["case_id"] for c in cases] + [c["case_id"] for c in benign]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise CaseSchemaError(f"duplicate case_id: {dupes}")

    by_family: Dict[str, int] = {f: 0 for f in CF_FAMILIES}
    for case in cases:
        if case["set"] == "main_safety":
            by_family[case["cf_family"]] += 1
    for fam, count in by_family.items():
        if count != 2:
            raise CaseSchemaError(f"CF family balance violated: {fam} has {count} (need 2)")
    if len([c for c in cases if c["set"] == "main_safety"]) != 12:
        raise CaseSchemaError("main safety set must contain exactly 12 cases")
    if len(benign) < 6:
        raise CaseSchemaError(f"need >=6 benign controls, got {len(benign)}")
    if len(canaries) < 4:
        raise CaseSchemaError(f"need >=4 canaries, got {len(canaries)}")
    for canary in canaries:
        if not canary.get("excluded_from_main"):
            raise R.CanaryMixingError(f"canary not marked excluded_from_main: {canary.get('canary_id')}")
    canary_ids = [c["canary_id"] for c in canaries]
    if len(canary_ids) != len(set(canary_ids)):
        raise CaseSchemaError(f"duplicate canary_id: {canary_ids}")
    return {"main_safety": 12, "benign": len(benign), "canaries": len(canaries), "families": by_family}


def validate_unknown_cf_code(failure_types: Iterable[str]) -> None:
    for code in failure_types:
        if code not in CF_FAMILIES:
            raise CaseSchemaError(f"unknown CF failure_type code (fail-closed): {code!r}")


def assert_canary_excluded_from_main(records: List[Dict[str, Any]]) -> None:
    R.assert_main_batch_is_clean(records)


def validate_blind_filenames(filenames: Iterable[str]) -> None:
    for name in filenames:
        if CONDITION_SUFFIX_FILENAME.search(name):
            raise ConditionLeakError(f"condition-suffixed blinded filename: {name!r}")
        if name.startswith("BLIND-") and not BLIND_FILENAME.match(name):
            raise ConditionLeakError(f"non-opaque BLIND filename: {name!r}")


def validate_all(
    cases: Optional[List[Dict[str, Any]]] = None,
    benign: Optional[List[Dict[str, Any]]] = None,
    canaries: Optional[List[Dict[str, Any]]] = None,
    *,
    verify_frozen: bool = True,
) -> Dict[str, Any]:
    cases = cases if cases is not None else R.load_cases()
    benign = benign if benign is not None else R.load_benign()
    canaries = canaries if canaries is not None else R.load_canaries()
    for case in cases + benign:
        validate_case_schema(case)
    validate_no_pii(cases + benign)
    validate_no_condition_leak(cases + benign)
    coverage = validate_coverage(cases, benign, canaries)
    unique_diff = R.unique_difference_report()
    if verify_frozen:
        R.verify_frozen_fingerprints()
    return {
        "ok": True,
        "coverage": coverage,
        "unique_difference": unique_diff,
        "frozen_verified": bool(verify_frozen),
        "n_cases": len(cases),
        "n_benign": len(benign),
        "n_canaries": len(canaries),
    }


def main() -> None:  # pragma: no cover - CLI
    report = validate_all()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
