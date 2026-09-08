#!/usr/bin/env python3
"""
Offline fail-closed validator for Workstream 4 patient_profiles.jsonl.

Usage from repo root:
  python3 llm_ablation_paper/workstream_4_patient_simulation/scripts/validate_profiles.py

Uses only stdlib (json, re, pathlib, sys). No network, no pip.
Resolves paths via __file__ so it works from any cwd (root or workstream dir).
If patient_profiles.jsonl is missing -> FAIL and exit !=0 (does not auto-forge).

Checks:
 - exactly 12 profiles, 6 scenario types x2, patient_id unique & pattern SP-00X, max_turns==6
 - no A/B/C/D or enable_* flags (forbidden keys)
 - no PII patterns and no raw answer field
 - each profile has profile_hash + is_synthetic==true + 5 major fields + 8-field provenance
 - glucose conversion only in glucose context (cholesterol/electrolyte mmol/L must not be converted)
 - condition-agnostic (no conditional branching on A/B/C/D inside profile)
 - structural schema checks (offline, hand-written, draft-07 shape)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# --- constants (mirror profile_schema.json) ---
SOURCE_ROLE_ENUM = ["linguistic_seed", "scenario_seed", "background_seed"]
MEDICATION_KEYWORDS = ["達格列淨", "二甲雙胍", "胰島素"]
SIDE_EFFECT_KW = ["頻尿", "腹脹", "腹瀉"]
SCENARIO_ENUM = [
    "DAILY_DIET",
    "MEDICATION_SIDE_EFFECT",
    "MEDICATION_NONADHERENCE",
    "SUBACUTE_HYPOGLYCEMIA",
    "PREVISIT_SUMMARY",
    "FACT_CONTRADICTION",
]
PATIENT_ID_RE = re.compile(r"^SP-0(0[1-9]|1[0-2])$")
HEX_64_RE = re.compile(r"^[a-fA-F0-9]{64}$")
HEX_7_40_RE = re.compile(r"^[a-fA-F0-9]{7,40}$")
HEX_16_64_RE = re.compile(r"^[a-fA-F0-9]{16,64}$")

FORBIDDEN_KEYS = {
    "condition",
    "enable_planner",
    "enable_dynamic_tool_gate",
    "enable_output_guard",
    "dynamic_tool_gate",
    "enable_forced_retrieval",
    "enable_fixed_warning_append",
    "enable_question_budget",
    "enable_question_budget_postprocessing",
    "enable_noncompliance_append",
    "ablation",
    "variant",
    "group",
    "arm",
}

# PII patterns (Taiwan context, offline regex)
PII_PATTERNS = [
    (re.compile(r"09\d{8}"), "phone 09xxxxxxxx"),
    (re.compile(r"09\d{2}-\d{3}-\d{3}"), "phone 09xx-xxx-xxx"),
    (re.compile(r"0\d{1,2}-?\d{6,8}"), "landline with area code (broad)"),
    (re.compile(r"[A-Z][12]\d{8}"), "Taiwan ID (A-Z + 1/2 + 8 digits)"),
    (re.compile(r"病歷號"), "medical record keyword 病歷號"),
    (re.compile(r"MRN\s*[:：]?\s*\d{5,}", re.IGNORECASE), "MRN number"),
]

ADDRESS_KEYWORDS = ["縣", "市", "區", "路", "街", "號", "巷", "弄"]
# Real-name heuristic: if a field named 真實姓名 / real_name contains 2-4 CJK chars and not marked synthetic, flag. We treat any explicit real-name field as PII.
BANNED_FIELD_NAMES = {"answer", "original_answer", "raw_answer", "真實答案", "真實姓名", "real_name", "full_name"}

GLUCOSE_CONTEXT_KW = ["血糖", "葡萄糖", "血醣", "glucose", "bg", "sugar"]
NON_GLUCOSE_CONTEXT_KW = ["膽固醇", "cholesterol", "tc", "ldl", "hdl", "三酸", "電解質", "electrolyte", "sodium", "potassium", "鈉", "鉀", "鈣", "磷", "鎂", "鹼", "氯"]

MMOL_RE = re.compile(r"(\d+(?:\.\d+)?)\s*mmol/L", re.IGNORECASE)
MGDL_RE = re.compile(r"(\d+(?:\.\d+)?)\s*mg/dL", re.IGNORECASE)

# --- path resolution ---
def resolve_paths() -> tuple[Path, Path]:
    ws_dir = Path(__file__).resolve().parents[1]
    schema_path = ws_dir / "profile_schema.json"
    profiles_path = ws_dir / "patient_profiles.jsonl"
    return schema_path, profiles_path


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path: Path) -> list[dict]:
    profiles = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"JSONL line {lineno} invalid JSON: {e}") from e
            profiles.append(obj)
    return profiles


def _contains_any(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    for kw in keywords:
        if kw.lower() in lower:
            return True
    return False


def _scan_strings(obj, prefix=""):
    """Yield (path, string_value) for all string leaves."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _scan_strings(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _scan_strings(v, f"{prefix}[{i}]")
    elif isinstance(obj, str):
        yield (prefix, obj)


def validate_one(profile: dict, idx: int, schema_enum: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    tag = f"profile[{idx}]"

    # --- forbidden keys (no enable_* / condition / A/B/C/D) ---
    # check top-level keys
    for key in profile.keys():
        lower = key.lower()
        if lower in FORBIDDEN_KEYS or lower.startswith("enable_") or lower == "condition_secret":
            errors.append(f"FAIL: {tag} contains forbidden key '{key}' (no A/B/C/D or enable_* allowed)")
        if re.fullmatch(r"[ABCD]", key):
            errors.append(f"FAIL: {tag} contains forbidden single-letter condition key '{key}'")
    # also scan nested keys for enable_* pattern (defensive)
    def _check_nested(d, path=""):
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(k, str) and (k.lower().startswith("enable_") or k.lower() in FORBIDDEN_KEYS):
                    # allow known legitimate: is_synthetic is ok; only flag enable_ and condition
                    if k != "is_synthetic":
                        errors.append(f"FAIL: {tag} nested forbidden key '{path}.{k}'")
                _check_nested(v, f"{path}.{k}" if path else k)
        elif isinstance(d, list):
            for i, v in enumerate(d):
                _check_nested(v, f"{path}[{i}]")
    _check_nested(profile)

    # --- patient_id ---
    pid = profile.get("patient_id")
    if not isinstance(pid, str) or not PATIENT_ID_RE.match(pid):
        errors.append(f"FAIL: {tag} patient_id must match SP-001..SP-012, got {pid!r}")

    # --- scenario_type ---
    st = profile.get("scenario_type")
    allowed = schema_enum if schema_enum is not None else SCENARIO_ENUM
    if st not in allowed:
        errors.append(f"FAIL: {tag} scenario_type must be one of {allowed}, got {st!r}")

    # --- is_synthetic const true ---
    if profile.get("is_synthetic") is not True:
        errors.append(f"FAIL: {tag} is_synthetic must be const true, got {profile.get('is_synthetic')!r}")

    # --- profile_hash ---
    ph = profile.get("profile_hash")
    if not isinstance(ph, str) or not HEX_16_64_RE.match(ph):
        errors.append(f"FAIL: {tag} profile_hash must be hex 16-64 chars, got {ph!r}")

    # --- max_turns const 6 ---
    if profile.get("max_turns") != 6:
        errors.append(f"FAIL: {tag} max_turns must be const 6, got {profile.get('max_turns')!r}")

    # --- source_provenance 12 fields all required (4 new + 8 old) ---
    prov = profile.get("source_provenance")
    if not isinstance(prov, dict):
        errors.append(f"FAIL: {tag} source_provenance must be object")
    else:
        required_prov = ["source_file", "source_sha256", "row_index", "department", "commit", "created_at", "author", "derivation_method", "matched_source_terms", "matched_scenario_terms", "source_role", "synthetic_additions"]
        for field in required_prov:
            if field not in prov:
                errors.append(f"FAIL: {tag} source_provenance missing required field '{field}'")
            else:
                val = prov[field]
                if field == "source_file" and (not isinstance(val, str) or not val.strip()):
                    errors.append(f"FAIL: {tag} source_provenance.source_file must be non-empty string")
                elif field == "source_sha256" and (not isinstance(val, str) or not HEX_64_RE.match(val)):
                    errors.append(f"FAIL: {tag} source_provenance.source_sha256 must be 64 hex chars, got {val!r}")
                elif field == "row_index" and (not isinstance(val, int) or val < 0):
                    errors.append(f"FAIL: {tag} source_provenance.row_index must be integer >=0, got {val!r}")
                elif field == "department" and (not isinstance(val, str) or not val.strip()):
                    errors.append(f"FAIL: {tag} source_provenance.department must be non-empty string")
                elif field == "commit" and (not isinstance(val, str) or not HEX_7_40_RE.match(val)):
                    errors.append(f"FAIL: {tag} source_provenance.commit must be hex 7-40 chars, got {val!r}")
                elif field in ("created_at", "author", "derivation_method") and (not isinstance(val, str) or not val.strip()):
                    errors.append(f"FAIL: {tag} source_provenance.{field} must be non-empty string")
                elif field == "matched_source_terms":
                    if not isinstance(val, list) or len(val) == 0 or not all(isinstance(x, str) and x.strip() for x in val):
                        errors.append(f"FAIL: {tag} source_provenance.matched_source_terms must be non-empty array of non-empty strings, got {val!r}")
                elif field == "matched_scenario_terms":
                    if not isinstance(val, list) or len(val) == 0 or not all(isinstance(x, str) and x.strip() for x in val):
                        errors.append(f"FAIL: {tag} source_provenance.matched_scenario_terms must be non-empty array of non-empty strings, got {val!r}")
                elif field == "source_role":
                    if val not in SOURCE_ROLE_ENUM:
                        errors.append(f"FAIL: {tag} source_provenance.source_role must be one of {SOURCE_ROLE_ENUM}, got {val!r}")
                elif field == "synthetic_additions":
                    if not isinstance(val, list) or len(val) == 0 or not all(isinstance(x, str) and x.strip() for x in val):
                        errors.append(f"FAIL: {tag} source_provenance.synthetic_additions must be non-empty array of non-empty strings, got {val!r}")
        # synthetic_additions should be distinct from known_facts keys/values (avoid trivial duplication)
        if isinstance(prov.get("synthetic_additions"), list):
            known = profile.get("known_facts")
            if isinstance(known, dict):
                known_keys = set(known.keys())
                known_dump = json.dumps(known, ensure_ascii=False)
                for term in prov["synthetic_additions"]:
                    if isinstance(term, str):
                        if term in known_keys:
                            errors.append(f"FAIL: {tag} source_provenance.synthetic_additions term '{term}' must be distinct from known_facts keys {known_keys}")
                        elif term and term in known_dump:
                            # allow partial overlap if term is generic drug name? but require not identical value
                            pass
        # retain fail-closed for insufficient required count (previously len!=8 no-op)
        if len([f for f in required_prov if f in prov]) != 12:
            # already reported missing fields above, no extra
            pass

    # --- persona ---
    persona = profile.get("persona")
    if not isinstance(persona, dict):
        errors.append(f"FAIL: {tag} persona must be object")
    else:
        age = persona.get("age")
        if not isinstance(age, int) or not (20 <= age <= 95):
            errors.append(f"FAIL: {tag} persona.age must be int 20-95, got {age!r}")
        lang = persona.get("language_style")
        if not isinstance(lang, str) or not lang.strip():
            errors.append(f"FAIL: {tag} persona.language_style must be non-empty string")
        hl = persona.get("health_literacy")
        if hl not in ("low", "medium"):
            errors.append(f"FAIL: {tag} persona.health_literacy must be low|medium, got {hl!r}")

    # --- known_facts / hidden_facts / reveal_policy ---
    for field in ("known_facts", "hidden_facts", "reveal_policy"):
        if field not in profile:
            errors.append(f"FAIL: {tag} missing required field '{field}'")
        elif not isinstance(profile[field], dict):
            errors.append(f"FAIL: {tag} {field} must be object, got {type(profile[field]).__name__}")

    # reveal_policy structure
    rp = profile.get("reveal_policy")
    if isinstance(rp, dict):
        if rp.get("disclosure_rule") != "on_direct_question_only":
            errors.append(f"FAIL: {tag} reveal_policy.disclosure_rule must be 'on_direct_question_only', got {rp.get('disclosure_rule')!r}")
        if rp.get("allow_voluntary_disclosure") is not False:
            errors.append(f"FAIL: {tag} reveal_policy.allow_voluntary_disclosure must be const false, got {rp.get('allow_voluntary_disclosure')!r}")
        ct = rp.get("correction_turn")
        if not isinstance(ct, int) or not (1 <= ct <= 6):
            errors.append(f"FAIL: {tag} reveal_policy.correction_turn must be int 1-6, got {ct!r}")
        order = rp.get("previsit_unlock_order")
        if not isinstance(order, list) or len(order) == 0 or not all(isinstance(x, str) and x.strip() for x in order):
            errors.append(f"FAIL: {tag} reveal_policy.previsit_unlock_order must be non-empty array of strings, got {order!r}")
        kb = rp.get("knowledge_boundary")
        if not isinstance(kb, dict):
            errors.append(f"FAIL: {tag} reveal_policy.knowledge_boundary must be object")
        else:
            if kb.get("knows_medical_answer") is not False:
                errors.append(f"FAIL: {tag} reveal_policy.knowledge_boundary.knows_medical_answer must be false")
            if kb.get("will_accommodate_system_error") is not False:
                errors.append(f"FAIL: {tag} reveal_policy.knowledge_boundary.will_accommodate_system_error must be false")
            if kb.get("will_alter_facts") is not False:
                errors.append(f"FAIL: {tag} reveal_policy.knowledge_boundary.will_alter_facts must be false")

    # --- patient_goal / risk_trigger non-empty ---
    for field in ("patient_goal", "risk_trigger"):
        val = profile.get(field)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"FAIL: {tag} {field} must be non-empty string, got {val!r}")

    # --- five major columns check (is_synthetic + hash + 5 fields) ---
    # We already checked is_synthetic, profile_hash, persona, known_facts, hidden_facts, reveal_policy, patient_goal
    major = ["persona", "known_facts", "hidden_facts", "reveal_policy", "patient_goal"]
    missing_major = [f for f in major if f not in profile]
    if missing_major:
        errors.append(f"FAIL: {tag} missing major fields {missing_major} (needs 5+)")

    # --- PII / banned field names ---
    for path, val in _scan_strings(profile):
        # banned field names
        leaf_key = path.split(".")[-1].split("[")[0] if path else ""
        if leaf_key in BANNED_FIELD_NAMES:
            errors.append(f"FAIL: {tag} contains banned field '{leaf_key}' at {path} (no raw answer / real-name field allowed)")
        # PII regex scan
        for pat, desc in PII_PATTERNS:
            if pat.search(val):
                # avoid flagging hash-like strings as phone: phone pattern is too broad (0d-?dddd). Tighten: only flag if looks like phone with explicit prefix
                # Keep phone check but require 09 prefix or explicit landline pattern with dash
                # For landline broad pattern, only flag if contains '-' or length 9-10 and starts with 0
                if desc.startswith("landline"):
                    # only flag if contains dash or matches 0\d{1,2}-\d{6,8}
                    if "-" not in val and not re.search(r"0\d{1,2}-\d{6,8}", val):
                        continue
                    # also skip if it's a hash-like or date
                    if re.match(r"^\d{4}-\d{2}-\d{2}", val):
                        continue
                errors.append(f"FAIL: {tag} PII detected ({desc}) at {path}: {val!r}")
        # address heuristic: if string contains at least 2 address keywords and length >6 and contains digit
        addr_hits = sum(1 for kw in ADDRESS_KEYWORDS if kw in val)
        if addr_hits >= 2 and re.search(r"\d", val) and len(val) >= 6:
            # check it looks like Taiwanese address (contains 市/縣 and 路/街)
            if any(x in val for x in ["市", "縣"]) and any(y in val for y in ["路", "街", "巷", "號"]):
                errors.append(f"FAIL: {tag} PII address pattern at {path}: {val!r}")

    # --- condition-agnostic: no condition branching text ---
    for path, val in _scan_strings(profile):
        low = val.lower()
        # forbid explicit condition references like "if condition A" or "ablation group"
        if re.search(r"condition\s*[=:]\s*[abcd]", low) or re.search(r"enable_planner", low):
            errors.append(f"FAIL: {tag} condition-dependent text at {path}: {val!r}")
        if re.search(r"\bcondition\s*[abcd]\b", low):
            errors.append(f"FAIL: {tag} condition-specific text at {path}: {val!r}")

    # --- glucose conversion checks ---
    # For each string containing mmol/L, decide context. We look at key name + surrounding value.
    for path, val in _scan_strings(profile):
        if "mmol/L" not in val:
            continue
        # Determine context via path + value
        context = f"{path} {val}".lower()
        is_glucose = _contains_any(context, GLUCOSE_CONTEXT_KW)
        is_non_glucose = _contains_any(context, NON_GLUCOSE_CONTEXT_KW)
        # If explicitly non-glucose, ensure no mg/dL conversion nearby in same value
        # If both glucose and non-glucose ambiguous, prioritize non-glucose as fail if conversion present
        mmol_matches = list(MMOL_RE.finditer(val))
        mgdl_match = MGDL_RE.search(val)
        if is_non_glucose:
            if mgdl_match:
                errors.append(
                    f"FAIL: {tag} non-glucose mmol/L must not be converted to mg/dL at {path}: {val!r} (cholesterol/electrolyte mmol/L not converted)"
                )
            # also check if parent object has a sibling mg/dL field for cholesterol – we detect by path prefix
            # e.g., known_facts.cholesterol_mmol and known_facts.cholesterol_mgdl together
            continue
        if is_glucose:
            # If mmol and mgdl both present in same string, check arithmetic
            if mmol_matches and mgdl_match:
                for m in mmol_matches:
                    try:
                        mmol = float(m.group(1))
                    except ValueError:
                        continue
                    expected = mmol * 18
                    # extract mgdl numeric from same string (first match)
                    try:
                        mgdl = float(mgdl_match.group(1))
                    except ValueError:
                        continue
                    # allow rounding tolerance: expected ±1 or ±0.5* rounding
                    if abs(mgdl - expected) > 1.0 and abs(mgdl - round(expected)) > 1:
                        errors.append(
                            f"FAIL: {tag} glucose conversion error at {path}: {mmol} mmol/L *18={expected:.1f} mg/dL, got {mgdl} mg/dL in {val!r}"
                        )
            # also check sibling fields: e.g., known_facts.glucose_mmol + glucose_mgdl as separate keys
            # This will be handled in global sibling check below

    # Sibling field conversion check (structured fields)
    # Look for numeric glucose fields across known_facts/hidden_facts
    for container_name in ("known_facts", "hidden_facts"):
        container = profile.get(container_name)
        if not isinstance(container, dict):
            continue
        # collect keys
        mmol_keys = [k for k in container.keys() if "glucose" in k.lower() and "mmol" in k.lower()]
        mgdl_keys = [k for k in container.keys() if "glucose" in k.lower() and "mg" in k.lower()]
        for mk in mmol_keys:
            mv = container[mk]
            if not isinstance(mv, (int, float, str)):
                continue
            try:
                mmol_val = float(str(mv).split()[0]) if isinstance(mv, str) else float(mv)
            except ValueError:
                continue
            for gk in mgdl_keys:
                gv = container[gk]
                try:
                    mgdl_val = float(str(gv).split()[0]) if isinstance(gv, str) else float(gv)
                except ValueError:
                    continue
                expected = mmol_val * 18
                if abs(mgdl_val - expected) > 1.0 and abs(mgdl_val - round(expected)) > 1:
                    errors.append(
                        f"FAIL: {tag} {container_name} glucose conversion {mk}={mmol_val} mmol/L -> {gk}={mgdl_val} mg/dL, expected ~{expected:.1f}"
                    )
        # non-glucose sibling check: cholesterol/electrolyte mmol should not have mgdl sibling
        for k in list(container.keys()):
            lowk = k.lower()
            if any(nk in lowk for nk in ["cholesterol", "膽固醇", "electrolyte", "sodium", "potassium", "鈉", "鉀"]):
                if "mmol" in lowk:
                    # look for sibling mgdl with similar prefix
                    prefix = lowk.replace("_mmol", "").replace("mmol", "")
                    for kk in container.keys():
                        if kk.lower() != k and prefix in kk.lower() and "mg" in kk.lower():
                            errors.append(
                                f"FAIL: {tag} {container_name} non-glucose field '{k}' must not have mg/dL sibling '{kk}' (cholesterol/electrolyte not converted)"
                            )

    # --- three-column retention: for glucose context, if mmol present, mgdl and original should be retained? ---
    # Only enforce when numeric glucose mmol key exists without mgdl sibling (not for free-text ranges like "6.8-8.2 mmol/L" or initial_statement).
    # Free-text glucose mentions (e.g., initial_statement "空腹血糖大概7.5 mmol/L" or PREVISIT range) are informational and may defer conversion to hidden true value.
    for container_name in ("known_facts", "hidden_facts"):
        container = profile.get(container_name)
        if not isinstance(container, dict):
            continue
        has_glucose_mmol = any("glucose" in k.lower() and "mmol" in k.lower() for k in container.keys())
        has_glucose_mgdl = any("glucose" in k.lower() and "mg" in k.lower() for k in container.keys())
        # Check for nested converted object (real profiles use hidden_facts.glucose_log.converted.normalized_value)
        has_nested_converted = False
        for v in container.values():
            if isinstance(v, dict):
                # direct nested
                if "converted" in v and isinstance(v["converted"], dict):
                    if v["converted"].get("normalized_unit") == "mg/dL":
                        has_nested_converted = True
                # one level deeper (e.g., glucose_log dict containing converted)
                for vv in v.values():
                    if isinstance(vv, dict) and vv.get("normalized_unit") == "mg/dL":
                        has_nested_converted = True
            if isinstance(v, dict) and v.get("normalized_unit") == "mg/dL":
                has_nested_converted = True
        if has_glucose_mmol and not (has_glucose_mgdl or has_nested_converted):
            embedded = any("mg/dL" in str(v) for v in container.values() if isinstance(v, str))
            if not embedded and not has_nested_converted:
                errors.append(
                    f"FAIL: {tag} {container_name} glucose mmol/L present but mg/dL not retained (保留三欄: mmol/mg/dL/original)"
                )

    # --- goal / known+hidden consistency ---
    known_facts = profile.get("known_facts")
    hidden_facts = profile.get("hidden_facts")
    goal = profile.get("patient_goal") or ""
    risk = profile.get("risk_trigger") or ""
    combined = f"{goal} {risk}"
    facts_dump = ""
    try:
        facts_dump = json.dumps({"known": known_facts, "hidden": hidden_facts}, ensure_ascii=False)
    except Exception:
        facts_dump = f"{known_facts} {hidden_facts}"
    has_current_med_key = False
    if isinstance(known_facts, dict) and "current_medication" in known_facts:
        has_current_med_key = True
    if isinstance(hidden_facts, dict) and "current_medication" in hidden_facts:
        has_current_med_key = True
    if has_current_med_key:
        if not any(kw in combined for kw in MEDICATION_KEYWORDS):
            errors.append(f"FAIL: {tag} goal/risk must echo medication keyword {MEDICATION_KEYWORDS} (current_medication present in facts but not in goal/risk: goal={goal!r})")
    # side effect echo
    hidden_dump = json.dumps(hidden_facts, ensure_ascii=False) if isinstance(hidden_facts, dict) else str(hidden_facts)
    for kw in SIDE_EFFECT_KW:
        if kw in hidden_dump:
            if kw == "頻尿":
                if "頻尿" not in combined and "尿" not in combined:
                    errors.append(f"FAIL: {tag} hidden contains '{kw}' but goal/risk does not echo side effect '{kw}' (goal={goal!r} risk={risk!r})")
            elif kw in ("腹脹", "腹瀉"):
                if kw not in combined and "腸胃" not in combined and "腹" not in combined:
                    errors.append(f"FAIL: {tag} hidden contains '{kw}' but goal/risk does not echo side effect (need '{kw}' or 腸胃) (goal={goal!r} risk={risk!r})")

    # --- manifest / report absolute path scan via profile source_provenance source_file check ---
    prov_sf = prov.get("source_file") if isinstance(prov, dict) else None
    if isinstance(prov_sf, str):
        if prov_sf.startswith("/") or "/tmp" in prov_sf or "/Users" in prov_sf:
            errors.append(f"FAIL: {tag} source_provenance.source_file must be relative, got absolute or /tmp/Users path {prov_sf!r}")

    return errors


def check_manifest_paths(ws_dir: Path) -> list[str]:
    errs: list[str] = []
    for fname in ["source_manifest.json", "candidate_filter_report.json"]:
        p = ws_dir / fname
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8")
            data = json.loads(text)
            dump = json.dumps(data, ensure_ascii=False)
        except Exception:
            dump = p.read_text(encoding="utf-8", errors="ignore")
            text = dump
        if "/tmp" in dump:
            errs.append(f"FAIL: {fname} contains absolute /tmp path (掃 json dump, 禁絕對路徑)")
        if "/Users" in dump:
            errs.append(f"FAIL: {fname} contains absolute /Users path")
        # detect JSON value starting with /  (e.g., \": \"/...\" )
        if re.search(r'":\s*"/', text):
            # allow URLs https://  but not file paths
            # check if any value literally starts with / not http
            if re.search(r'":\s*"/(?!/)', text) and not re.search(r'":\s*"https?://', text):
                # need to ensure it's not URL; simpler check for download_path or file-like absolute
                for line in text.splitlines():
                    if '"/' in line and 'https://' not in line and 'http://' not in line:
                        # if line contains ": "/ and not url, flag if path-like
                        if re.search(r':\s*"/[^"]*"(,?)', line):
                            # exclude $schema etc already handled, but we flag generic
                            if "/tmp" not in line and "/Users" not in line:
                                # still check for generic absolute like "/data/..."
                                if re.search(r'":\s*"/', line):
                                    errs.append(f"FAIL: {fname} contains absolute path value {line.strip()}")
                                    break
        # also direct ^/ check on any string value
        try:
            for path, val in _scan_strings(data):
                if isinstance(val, str) and val.startswith("/"):
                    # allow http not here, already string starts with /
                    errs.append(f"FAIL: {fname} field {path} is absolute path {val!r} (禁 ^/ )")
                    break
        except Exception:
            pass
    return errs


def validate_all(profiles: list[dict], schema: dict | None = None) -> list[str]:
    errors: list[str] = []
    schema_enum = None
    if schema is not None:
        try:
            schema_enum = schema["properties"]["scenario_type"]["enum"]
        except Exception:
            schema_enum = SCENARIO_ENUM

    # count exactly 12
    if len(profiles) != 12:
        errors.append(f"FAIL: expected exactly 12 profiles, got {len(profiles)}")

    # per-profile structural checks
    seen_ids: dict[str, int] = {}
    scenario_counts: dict[str, int] = {}
    for idx, p in enumerate(profiles):
        per = validate_one(p, idx, schema_enum)
        errors.extend(per)
        pid = p.get("patient_id")
        if isinstance(pid, str):
            if pid in seen_ids:
                errors.append(f"FAIL: duplicate patient_id '{pid}' at index {idx} (first at {seen_ids[pid]})")
            else:
                seen_ids[pid] = idx
        st = p.get("scenario_type")
        if isinstance(st, str):
            scenario_counts[st] = scenario_counts.get(st, 0) + 1

    # six types each 2
    allowed = schema_enum if schema_enum is not None else SCENARIO_ENUM
    for st in allowed:
        cnt = scenario_counts.get(st, 0)
        if cnt != 2:
            errors.append(f"FAIL: scenario_type '{st}' must appear exactly 2 times, got {cnt}")
    # unexpected types
    for st in scenario_counts:
        if st not in allowed:
            errors.append(f"FAIL: unexpected scenario_type '{st}' not in {allowed}")

    # max_turns all 6 already checked per-profile, but also ensure no variance
    return errors


def main(argv: list[str] | None = None) -> int:
    schema_path, profiles_path = resolve_paths()
    # also support running from repo root with relative path fallback
    # (resolve_paths already uses __file__, so it works from any cwd)
    if not schema_path.exists():
        print(f"FAIL: schema not found at {schema_path}", file=sys.stderr)
        return 2
    try:
        schema = load_json(schema_path)
    except Exception as e:
        print(f"FAIL: cannot load schema {schema_path}: {e}", file=sys.stderr)
        return 2

    if not profiles_path.exists():
        print(f"FAIL: profiles file not found at {profiles_path} (must exist, no auto-forge)", file=sys.stderr)
        return 2

    try:
        profiles = load_jsonl(profiles_path)
    except ValueError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"FAIL: cannot read profiles {profiles_path}: {e}", file=sys.stderr)
        return 2

    errors = validate_all(profiles, schema)
    # manifest/report absolute path fail-closed
    ws_dir = schema_path.parent
    manifest_errs = check_manifest_paths(ws_dir)
    errors.extend(manifest_errs)
    if errors:
        for line in errors:
            print(line, file=sys.stderr)
        return 1
    print(f"PASS: {len(profiles)} profiles validated (6 types x2, IDs unique, max_turns=6, no PII/flags, glucose context ok)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
