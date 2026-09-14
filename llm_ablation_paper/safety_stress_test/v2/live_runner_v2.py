"""v2 real-Gemini low-cost safety stress pilot entry (offline-safe by construction).

Scope: exactly one allow-listed v2 case (SAFETY-RX-01-v2) x A/B/C/D x fixed 3-turn
script. NOT the formal 12x4 experiment, NOT clinical validation, NOT paper results.
No LLM judge is invoked; a judge-compatible blinded artifact is produced for later judging.

Reuses (never forks) the v1 live runner helpers, the WS1 frozen harness
(run_trajectory_subprocess / formal_ablation_config / to_blinded_contract_trajectory)
and the v2 data/scanner/blinding modules. This module NEVER calls the network unless
`--live-pilot` is invoked with the confirmation token AND a real GEMINI_API_KEY in the
process environment. `--preflight` is fully offline.

Hard guards:
  * Frozen model pins: talker/planner gemini-3.5-flash-lite (0.3 / 0.1); judge not used.
  * Cost guard: estimated/actual hard cap COST_CAP_USD; on the live path missing usage is
    fail-closed (the mock/test client_factory path may record 0.0 and is test-only).
  * API key is read from the environment only and is never printed, persisted, or logged.
  * Resume is idempotent: usage ledger is keyed by condition and reconciled with the
    manifest; incomplete/empty runs are quarantined, never exported as judge-ready.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from llm_ablation_paper.safety_stress_test import live_runner as L1
from llm_ablation_paper.safety_stress_test import analysis as A1
from llm_ablation_paper.safety_stress_test.v2 import runner_v2 as RV2
from llm_ablation_paper.safety_stress_test.v2 import rule_based_scanner_v2 as S2
from llm_ablation_paper.safety_stress_test.v2 import validate_v2 as V2
from llm_ablation_paper.workstream_1_technical_lead.harness import (
    clear_session_cache,
    generate_random_condition_mapping,
    resolve_provider_credentials,
    run_trajectory_subprocess,
    to_blinded_contract_trajectory,
    validate_condition_mapping,
)
from llm_ablation_paper.workstream_1_technical_lead.harness.config import formal_runtime_spec
from llm_ablation_paper.workstream_5_judge_analysis.sanitizer import sanitize_turn_for_judge

V2_DIR = Path(__file__).resolve().parent
REPO_ROOT = V2_DIR.parents[2]

CONFIRM_LIVE_PILOT_V2 = "I_CONFIRM_SAFETY_STRESS_V2_LIVE_PILOT"
LIVE_TAG_NAME_V2 = "llm-ablation-safety-stress-v2-live-pilot-v1"
BASE_TAG_NAME = "llm-ablation-safety-live-judge-pilot-v1"
EXPECTED_BASE_SHA = "690eab3fc9f229d51dc52b66ab7bf0582bd416fc"
LIVE_CASE_ALLOWLIST = frozenset({"SAFETY-RX-01-v2"})
LIVE_MAX_TURNS = 3
EXECUTION_MODE = "safety_stress_v2_live_pilot"
DEFAULT_LIVE_ROOT = V2_DIR / "artifacts" / "live_pilot_v2"
PROVIDER_CONFIG = {"provider": "gemini"}
COST_CAP_USD = 0.25
USD_TWD = 32.0
FROZEN_TALKER_MODEL = "gemini-3.5-flash-lite"
FROZEN_TALKER_TEMPERATURE = 0.3
FROZEN_PLANNER_TEMPERATURE = 0.1
PRICING_SOURCE = "Google Gemini Developer API Pricing (2026-09-13), Standard tier"
TOKENS_SOURCE = "provider_reported"
PRICING_USD_PER_1M = {FROZEN_TALKER_MODEL: {"input": 0.30, "output": 2.50}}
ALLOWED_CHANGED_PREFIXES = (
    "llm_ablation_paper/safety_stress_test/v2/",
    "llm_ablation_paper/safety_stress_test/V2_PM_HANDOFF_RESULT.md",
    "llm_ablation_paper/safety_stress_test/V2_LIVE_PILOT_RESULT.md",
)
CONDITION_LEAK_RE = re.compile(r"\bcondition[\s_-]*[abcd]\b", re.IGNORECASE)
CONDITION_KEY_RE = re.compile(r"[\"']condition[\"']\s*:\s*[\"'][abcd][\"']", re.IGNORECASE)


class LiveV2Error(RuntimeError):
    pass


class LiveV2PreflightError(LiveV2Error):
    pass


class LiveV2ConfirmationError(LiveV2Error):
    pass


class CostGuardError(LiveV2Error):
    pass


def _git(args: List[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL).decode().strip()


def _rev(ref: str) -> str:
    try:
        return _git(["rev-list", "-n1", ref])
    except subprocess.CalledProcessError:
        return ""


def _tag_exists(ref: str) -> bool:
    try:
        _git(["rev-parse", "--verify", f"refs/tags/{ref}"])
        return True
    except subprocess.CalledProcessError:
        return False


def _tag_is_annotated(ref: str) -> bool:
    try:
        return _git(["cat-file", "-t", ref]) == "tag"
    except subprocess.CalledProcessError:
        return False


def git_probe_v2(tag_name: str = LIVE_TAG_NAME_V2) -> Dict[str, Any]:
    head = _git(["rev-parse", "HEAD"])
    dirty = bool(_git(["status", "--porcelain"]))
    live_tag_sha = _rev(tag_name)
    base_tag_sha = _rev(BASE_TAG_NAME)
    try:
        _git(["merge-base", "--is-ancestor", BASE_TAG_NAME, "HEAD"])
        base_is_ancestor = True
    except subprocess.CalledProcessError:
        base_is_ancestor = False
    try:
        changed = [p for p in _git(["diff", "--name-only", BASE_TAG_NAME, "HEAD"]).splitlines() if p]
    except subprocess.CalledProcessError:
        changed = ["<diff-vs-base-failed>"]
    return {
        "head": head,
        "dirty": dirty,
        "live_tag": tag_name,
        "live_tag_exists": _tag_exists(tag_name),
        "live_tag_annotated": _tag_is_annotated(tag_name),
        "live_tag_sha": live_tag_sha,
        "base_tag_sha": base_tag_sha,
        "base_is_ancestor": base_is_ancestor,
        "changed_vs_base": changed,
    }


def _assert_under_root(path: Path, root: Path) -> Path:
    resolved = Path(path).resolve()
    root_resolved = Path(root).resolve()
    if resolved != root_resolved and not str(resolved).startswith(str(root_resolved) + os.sep):
        raise LiveV2PreflightError(f"output path escapes live root: {resolved}")
    return resolved


def _mkdir_private(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def _atomic_write_text_v2(path: Path, text: str, mode: int = 0o600) -> None:
    """Atomic write with a unique O_EXCL|O_NOFOLLOW temp file (no predictable-name symlink race)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}-{hashlib.sha256(os.urandom(8)).hexdigest()[:8]}")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    os.chmod(path, mode)


def _assert_private_regular(path: Path, root: Path, mode: int = 0o600) -> None:
    p = Path(path)
    if p.is_symlink():
        raise LiveV2Error(f"private file must not be a symlink: {p}")
    if not p.exists() or not p.is_file():
        raise LiveV2Error(f"private file missing or not a regular file: {p}")
    resolved = p.resolve()
    root_resolved = Path(root).resolve()
    if resolved != root_resolved and not str(resolved).startswith(str(root_resolved) + os.sep):
        raise LiveV2Error(f"private file escapes live root: {resolved}")
    actual = stat.S_IMODE(p.stat().st_mode)
    if actual != mode:
        raise LiveV2Error(f"private file mode {oct(actual)} != {oct(mode)}: {p}")


def assert_live_scope_v2(case: Dict[str, Any]) -> None:
    if case["case_id"] not in LIVE_CASE_ALLOWLIST:
        raise LiveV2Error(f"case {case['case_id']!r} not allow-listed; allowed={sorted(LIVE_CASE_ALLOWLIST)}")
    if case.get("set") != "main_safety":
        raise LiveV2Error(f"live pilot case must be main_safety, got {case.get('set')!r}")
    if case["max_turns"] != LIVE_MAX_TURNS or len(case["pressure_turns"]) != LIVE_MAX_TURNS:
        raise LiveV2Error(f"live pilot requires exactly {LIVE_MAX_TURNS} turns for {case['case_id']}")


def estimate_cost_usd(turns: int = 12, prompt_tokens_per_turn: int = 1200, completion_tokens_per_turn: int = 400) -> float:
    price = PRICING_USD_PER_1M[FROZEN_TALKER_MODEL]
    return (turns * prompt_tokens_per_turn / 1e6) * price["input"] + (
        turns * completion_tokens_per_turn / 1e6
    ) * price["output"]


def cost_usd(tokens: Dict[str, Any]) -> Optional[float]:
    prompt = tokens.get("prompt_tokens")
    completion = tokens.get("completion_tokens")
    if prompt is None and completion is None:
        return None
    price = PRICING_USD_PER_1M[FROZEN_TALKER_MODEL]
    return ((prompt or 0) / 1e6) * price["input"] + ((completion or 0) / 1e6) * price["output"]


def _record_model_mismatch(records: List[Dict[str, Any]]) -> Optional[str]:
    for rec in records:
        for key, value in rec.items():
            if key == "model" or key.endswith("_model"):
                if value and str(value) != FROZEN_TALKER_MODEL:
                    return f"{key}={value}"
    return None


def _effective_termination_v2(records: List[Dict[str, Any]]) -> str:
    term = A1.classify_termination({"termination_reason": None}, records)
    if term == "INCOMPLETE" and len(records) >= LIVE_MAX_TURNS:
        return "MAX_TURNS"
    return term


def _load_state_records(state_dir: Path) -> List[Dict[str, Any]]:
    return A1.load_records(state_dir) if state_dir.exists() else []


def preflight(
    case_id: str = "SAFETY-RX-01-v2",
    root: Optional[Path] = None,
    *,
    require_key: bool = True,
    enforce_gitignore: bool = True,
    pilot_tag: str = LIVE_TAG_NAME_V2,
    git_probe_fn: Optional[Callable[[], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Offline preflight: no network, no model call."""
    root = Path(root) if root else DEFAULT_LIVE_ROOT
    probe_fn = git_probe_fn or (lambda: git_probe_v2(pilot_tag))
    case = next((c for c in RV2.load_v2_cases() if c["case_id"] == case_id), None)
    if case is None:
        raise LiveV2PreflightError(f"unknown v2 case_id: {case_id}")
    assert_live_scope_v2(case)

    probe = probe_fn()
    if probe.get("base_tag_sha") != EXPECTED_BASE_SHA:
        raise LiveV2PreflightError(
            f"base tag {BASE_TAG_NAME!r} peeled to {probe.get('base_tag_sha')!r} != {EXPECTED_BASE_SHA}"
        )
    if probe["dirty"]:
        raise LiveV2PreflightError("worktree is dirty; refusing live pilot")
    outside = [
        p for p in probe.get("changed_vs_base", []) if not any(p.startswith(pref) for pref in ALLOWED_CHANGED_PREFIXES)
    ]
    if outside:
        raise LiveV2PreflightError(f"changes outside the v2 scope vs base tag: {outside}")

    import llm_ablation_paper.safety_stress_test.runner as R1

    R1.verify_frozen_fingerprints()
    R1.unique_difference_report()
    if not R1.check_tool_gate_reachability()["passed"]:
        raise LiveV2PreflightError("tool gate not reachable")

    V2.validate_all_v2()

    spec = formal_runtime_spec()
    if spec["talker_model"] != FROZEN_TALKER_MODEL or spec["talker_temperature"] != FROZEN_TALKER_TEMPERATURE:
        raise LiveV2PreflightError("talker model/temperature drift vs frozen v2 pins")
    if spec["planner_temperature"] != FROZEN_PLANNER_TEMPERATURE:
        raise LiveV2PreflightError("planner temperature drift vs frozen v2 pins")
    for cond in RV2.CONDITIONS:
        cfg = L1.build_live_config(cond, run_id=f"LIVE-V2-CHECK-{cond}")
        if cfg.model != FROZEN_TALKER_MODEL or cfg.temperature != FROZEN_TALKER_TEMPERATURE:
            raise LiveV2PreflightError(f"model/temperature drift for condition {cond}")

    if enforce_gitignore and not L1._is_gitignored(root / "probe"):
        raise LiveV2PreflightError(f"live root is not gitignored: {root}")

    if not probe["live_tag_exists"]:
        status, reason = "BLOCKED", "NOT_FROZEN"
    elif not probe["live_tag_annotated"]:
        status, reason = "BLOCKED", "LIVE_TAG_NOT_ANNOTATED"
    elif probe["head"] != probe["live_tag_sha"]:
        status, reason = "BLOCKED", "HEAD_NOT_LIVE_TAG"
    elif not probe.get("base_is_ancestor"):
        status, reason = "BLOCKED", "BASE_TAG_NOT_ANCESTOR"
    else:
        status, reason = "PASS", ""

    estimate = estimate_cost_usd()
    if estimate > COST_CAP_USD:
        raise CostGuardError(f"pre-run cost estimate {estimate:.6f} USD exceeds cap {COST_CAP_USD}")

    if status == "PASS" and require_key:
        resolve_provider_credentials(dict(PROVIDER_CONFIG))

    return {
        "preflight": status,
        "reason": reason,
        "mode": "offline",
        "case_id": case_id,
        "head": probe["head"],
        "live_tag": pilot_tag,
        "live_tag_sha": probe["live_tag_sha"],
        "base_tag": BASE_TAG_NAME,
        "base_tag_sha": probe.get("base_tag_sha", ""),
        "base_is_ancestor": probe.get("base_is_ancestor"),
        "n_changed_vs_base": len(probe.get("changed_vs_base", [])),
        "dirty": probe["dirty"],
        "model": spec["talker_model"],
        "temperature": spec["talker_temperature"],
        "planner_temperature": spec["planner_temperature"],
        "max_turns": LIVE_MAX_TURNS,
        "cost_cap_usd": COST_CAP_USD,
        "cost_estimate_usd": round(estimate, 6),
        "root": str(root),
    }


def _scan_blinded_v2(text: str, mapping: Dict[str, str], raw_run_id: str) -> None:
    lowered = text.lower()
    hits = []
    for token in ("enable_", "condition_secret", "raw_talker", "guard_action", "planner_state", raw_run_id.lower()):
        if token in lowered:
            hits.append(token)
    if CONDITION_LEAK_RE.search(lowered) or CONDITION_KEY_RE.search(text):
        hits.append("condition-letter")
    for secret in mapping.values():
        if secret and str(secret).lower() in lowered:
            hits.append("mapping-value")
    if hits:
        raise LiveV2Error(f"blinded payload leakage: {sorted(set(hits))}")


def _upsert_ledger(ledger: List[Dict[str, Any]], entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    kept = [e for e in ledger if e.get("condition") != entry["condition"]]
    kept.append(entry)
    return sorted(kept, key=lambda e: list(RV2.CONDITIONS).index(e["condition"]))


def _ledger_sum(ledger: List[Dict[str, Any]]) -> float:
    return round(sum(float(e.get("cost_usd") or 0.0) for e in ledger), 9)


def run_live_pilot_v2(
    case_id: str = "SAFETY-RX-01-v2",
    root: Optional[Path] = None,
    *,
    confirm: Optional[str] = None,
    client_factory: Optional[Callable] = None,
    timeout: Optional[float] = None,
    resume: bool = False,
    enforce_gitignore: bool = True,
    pilot_tag: str = LIVE_TAG_NAME_V2,
    git_probe_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    _test_only_first_messages: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if confirm != CONFIRM_LIVE_PILOT_V2:
        raise LiveV2ConfirmationError(f"refusing live pilot: confirmation token must equal {CONFIRM_LIVE_PILOT_V2!r}")
    root = Path(root) if root else DEFAULT_LIVE_ROOT
    report = preflight(
        case_id,
        root,
        require_key=(client_factory is None),
        enforce_gitignore=enforce_gitignore,
        pilot_tag=pilot_tag,
        git_probe_fn=git_probe_fn,
    )
    if report.get("preflight") != "PASS":
        raise LiveV2PreflightError(f"live pilot blocked: {report.get('preflight')}/{report.get('reason')}")
    if not resume:
        if root.exists() and any(root.iterdir()):
            raise FileExistsError(f"live root must be absent or empty for a new run: {root}")
    elif not root.exists():
        raise LiveV2Error(f"resume requires an existing live root: {root}")
    _mkdir_private(root)

    if client_factory is None:
        resolve_provider_credentials(dict(PROVIDER_CONFIG))

    case = next(c for c in RV2.load_v2_cases() if c["case_id"] == case_id)
    refs = RV2.load_reference_facts()[case_id]
    spec = formal_runtime_spec()
    if timeout is None:
        timeout = float(spec["subprocess_timeout_seconds"])

    mapping_path = root / "v2_condition_mapping.json"
    manifest_path = root / "v2_live_pilot_manifest.json"
    summary_path = root / "v2_live_pilot_summary.json"
    usage_path = root / "v2_usage_ledger.json"

    if resume:
        _assert_private_regular(mapping_path, root, 0o600)
        _assert_private_regular(manifest_path, root, 0o600)
        mapping = validate_condition_mapping(json.loads(mapping_path.read_text(encoding="utf-8")))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("case_id") != case_id:
            raise LiveV2Error("manifest case_id mismatch on resume")
        if manifest.get("base_tag_sha") != EXPECTED_BASE_SHA:
            raise LiveV2Error("manifest base tag mismatch on resume")
        if manifest.get("commit") != report.get("head"):
            raise LiveV2Error("manifest commit != current HEAD on resume")
        if manifest.get("live_tag_sha") != report.get("live_tag_sha"):
            raise LiveV2Error("manifest live tag mismatch on resume")
        if L1._mapping_sha(mapping) != manifest.get("mapping_sha256"):
            raise LiveV2Error("mapping SHA mismatch on resume; refusing")
        run_ids = manifest.get("runs", {})
        if set(run_ids.keys()) != set(RV2.CONDITIONS):
            raise LiveV2Error("manifest must contain exactly A/B/C/D run_ids")
        if usage_path.exists():
            _assert_private_regular(usage_path, root, 0o600)
            raw_ledger = json.loads(usage_path.read_text(encoding="utf-8"))
            if not isinstance(raw_ledger, list):
                raise LiveV2Error("usage ledger must be a JSON list on resume")
            unknown = [e.get("condition") for e in raw_ledger if e.get("condition") not in RV2.CONDITIONS]
            if unknown or len({e.get("condition") for e in raw_ledger}) != len(raw_ledger):
                raise LiveV2Error(f"usage ledger has invalid/duplicate conditions: {unknown}")
            usage_ledger = list(raw_ledger)
        else:
            usage_ledger = []
        cost_seen = _ledger_sum(usage_ledger)
        if abs(cost_seen - float(manifest.get("cost_usd_accumulated") or 0.0)) > 1e-6:
            raise LiveV2Error(
                f"resume cost mismatch: ledger {cost_seen} != manifest {manifest.get('cost_usd_accumulated')}"
            )
    else:
        if mapping_path.exists() or manifest_path.exists() or summary_path.exists():
            raise FileExistsError("live root already initialized; use --resume (refusing overwrite)")
        mapping = validate_condition_mapping(generate_random_condition_mapping())
        run_ids = {
            cond: f"LIVEV2-{case_id}-{cond}-{hashlib.sha256(os.urandom(8)).hexdigest()[:6]}"
            for cond in RV2.CONDITIONS
        }
        _atomic_write_text_v2(mapping_path, json.dumps(mapping, ensure_ascii=False, indent=2), 0o600)
        manifest = {
            "execution_mode": EXECUTION_MODE,
            "case_id": case_id,
            "base_tag": BASE_TAG_NAME,
            "base_tag_sha": EXPECTED_BASE_SHA,
            "live_tag": report.get("live_tag", pilot_tag),
            "live_tag_sha": report.get("live_tag_sha", ""),
            "commit": report.get("head", ""),
            "max_turns": LIVE_MAX_TURNS,
            "taxonomy_version": RV2.TAXONOMY_VERSION,
            "scanner_version": S2.RULES_VERSION,
            "talker_model": FROZEN_TALKER_MODEL,
            "talker_temperature": FROZEN_TALKER_TEMPERATURE,
            "planner_temperature": FROZEN_PLANNER_TEMPERATURE,
            "judge_used": False,
            "mapping_mode": "LIVE_RANDOM_OPAQUE",
            "mapping_sha256": L1._mapping_sha(mapping),
            "cost_cap_usd": COST_CAP_USD,
            "cost_usd_accumulated": 0.0,
            "pricing_source": PRICING_SOURCE,
            "tokens_source": TOKENS_SOURCE,
            "cost_basis": "recomputed_from_official_rates",
            "runs": run_ids,
        }
        _atomic_write_text_v2(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2), 0o600)
        usage_ledger = []
        cost_seen = 0.0

    blinded_dir = _mkdir_private(_assert_under_root(root / "blinded", root))
    scanner_dir = _mkdir_private(_assert_under_root(root / "scanner_v2", root))
    quarantine_dir = _mkdir_private(_assert_under_root(root / "quarantine", root))
    run_summaries: List[Dict[str, Any]] = []

    for cond in RV2.CONDITIONS:
        run_id = run_ids[cond]
        config = L1.build_live_config(cond, run_id)
        state_dir = _assert_under_root(root / "runs" / run_id / "isolated_state", root)
        state_exists = state_dir.exists()
        existing = _load_state_records(state_dir) if state_exists else []
        already_done = resume and state_exists and _effective_termination_v2(existing) in A1.COMPLETED_TERMINATIONS
        resume_applied = bool(resume and state_exists and not already_done)

        if already_done:
            records = existing
            prior = next((e for e in usage_ledger if e.get("condition") == cond), None)
            if prior is None:
                raise LiveV2Error(f"resume: completed condition {cond} missing from usage ledger")
            usage = {
                "prompt_tokens": prior.get("prompt_tokens"),
                "completion_tokens": prior.get("completion_tokens"),
                "total_tokens": prior.get("total_tokens"),
            }
            turn_cost = float(prior.get("cost_usd") or 0.0)
        else:
            clear_session_cache()
            kwargs: Dict[str, Any] = {}
            if client_factory is not None:
                kwargs["client_factory"] = client_factory
            else:
                kwargs["provider_config"] = dict(PROVIDER_CONFIG)
            messages = list(case["pressure_turns"])
            if (not resume) and _test_only_first_messages is not None and cond == "A":
                messages = list(_test_only_first_messages)
            records = run_trajectory_subprocess(
                config=config,
                patient_id=f"livev2_{case_id.lower()}_{cond.lower()}",
                messages=messages,
                state_dir=state_dir,
                run_id=run_id,
                timeout=timeout,
                resume=resume_applied,
                research_patient_id=case_id,
                artifacts_dir=state_dir,
                **kwargs,
            )
            usage = L1._token_usage_total(records)
            mismatch = _record_model_mismatch(records)
            if mismatch:
                raise CostGuardError(f"model mismatch: expected {FROZEN_TALKER_MODEL}, saw {mismatch}; stopping")
            computed = cost_usd(usage)
            if computed is None:
                if client_factory is None:
                    raise CostGuardError("token usage unavailable; refusing to continue (fail-closed cost guard)")
                computed = 0.0
            turn_cost = computed
            usage_ledger = _upsert_ledger(
                usage_ledger,
                {
                    "condition": cond,
                    "run_id": L1._scrub(run_id),
                    "n_turns": len(records),
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                    "cost_usd": round(turn_cost, 7),
                },
            )
            cost_seen = _ledger_sum(usage_ledger)
            manifest["cost_usd_accumulated"] = cost_seen
            _atomic_write_text_v2(usage_path, json.dumps(usage_ledger, ensure_ascii=False, indent=2), 0o600)
            _atomic_write_text_v2(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2), 0o600)
            if cost_seen > COST_CAP_USD:
                raise CostGuardError(f"cumulative cost {cost_seen:.6f} USD exceeds cap {COST_CAP_USD}; stopping")

        termination = _effective_termination_v2(records)
        technical_error = L1._technical_error(records)
        blinded_id = None
        blinded_error = None
        scanner_cf = None
        scanner_families: List[str] = []
        scanner_factual: List[str] = []

        try:
            if termination not in A1.COMPLETED_TERMINATIONS:
                raise LiveV2Error(f"incomplete termination {termination!r}; not judge-ready")
            if not records:
                raise LiveV2Error("empty trajectory; not judge-ready")
            contract = to_blinded_contract_trajectory(run_id, state_dir, mapping, require_completed=True)
            payload = {
                "blinded_run_id": contract["run_id"],
                "patient_id": case_id,
                "turns": [sanitize_turn_for_judge(t) for t in contract["turns"]],
                "reference_facts": refs,
            }
            if not payload["turns"]:
                raise LiveV2Error("blind payload has zero turns; refusing export")
            RV2.assert_payload_clean_v2(payload)
            _scan_blinded_v2(json.dumps(payload, ensure_ascii=False), mapping, run_id)
            blinded_id = payload["blinded_run_id"]
            blinded_file = blinded_dir / f"{blinded_id}.json"
            if already_done and blinded_file.exists():
                pass
            else:
                _atomic_write_text_v2(blinded_file, json.dumps(payload, ensure_ascii=False, indent=2), 0o644)
                scan = S2.scan_trajectory(
                    {
                        "blinded_run_id": blinded_id,
                        "turns": [
                            {"turn": t["turn"], "final_output": t["final_output"], "patient_text": t["patient_text"]}
                            for t in payload["turns"]
                        ],
                    }
                )
                _atomic_write_text_v2(
                    scanner_dir / f"{blinded_id}.scanner.json",
                    json.dumps(scan, ensure_ascii=False, indent=2),
                    0o600,
                )
        except Exception as exc:
            if isinstance(exc, (CostGuardError, LiveV2ConfirmationError)):
                raise
            blinded_error = L1._scrub(str(exc))
            _atomic_write_text_v2(
                quarantine_dir / f"QUARANTINE-{L1._scrub(run_id)}.json",
                json.dumps(
                    {
                        "run_id": L1._scrub(run_id),
                        "termination_reason": termination,
                        "n_turns": len(records),
                        "technical_error": technical_error,
                        "reason": blinded_error,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                0o600,
            )

        if blinded_id is not None:
            scan_path = scanner_dir / f"{blinded_id}.scanner.json"
            if scan_path.exists():
                sc = json.loads(scan_path.read_text(encoding="utf-8"))
                scanner_cf = sc.get("scanner_cf")
                scanner_families = sc.get("scanner_families", [])
                scanner_factual = sc.get("factual_codes", [])

        run_summaries.append(
            {
                "case_id": case_id,
                "condition": cond,
                "run_id": L1._scrub(run_id),
                "blinded_run_id": blinded_id,
                "blinded_error": blinded_error,
                "n_turns": len(records),
                "termination_reason": termination,
                "token_usage": usage,
                "cost_usd": round(turn_cost, 7),
                "technical_error": technical_error,
                "scanner_cf": scanner_cf,
                "scanner_families": scanner_families,
                "scanner_factual_codes": scanner_factual,
                "models_seen": sorted(
                    {str(r.get(k)) for r in records for k in r if (k == "model" or k.endswith("_model")) and r.get(k)}
                ),
                "resume_applied": resume_applied,
                "skipped_completed": bool(already_done),
            }
        )

    completed = all(
        r["termination_reason"] in A1.COMPLETED_TERMINATIONS and r["blinded_run_id"] for r in run_summaries
    )
    totals = {
        "prompt_tokens": sum((r["token_usage"].get("prompt_tokens") or 0) for r in run_summaries),
        "completion_tokens": sum((r["token_usage"].get("completion_tokens") or 0) for r in run_summaries),
        "total_tokens": sum((r["token_usage"].get("total_tokens") or 0) for r in run_summaries),
    }
    summary = {
        "execution_mode": EXECUTION_MODE,
        "exploratory": True,
        "non_preregistered": True,
        "pilot": True,
        "provider": "gemini",
        "live_api": client_factory is None,
        "live_tag": report.get("live_tag", pilot_tag),
        "live_tag_sha": report.get("live_tag_sha", ""),
        "base_tag": BASE_TAG_NAME,
        "base_tag_sha": EXPECTED_BASE_SHA,
        "commit": report.get("head", ""),
        "talker_model": FROZEN_TALKER_MODEL,
        "talker_temperature": FROZEN_TALKER_TEMPERATURE,
        "planner_temperature": FROZEN_PLANNER_TEMPERATURE,
        "judge_used": False,
        "case_id": case_id,
        "max_turns": LIVE_MAX_TURNS,
        "n_conditions": len(RV2.CONDITIONS),
        "mapping_mode": "LIVE_RANDOM_OPAQUE",
        "mapping_sha256": L1._mapping_sha(mapping),
        "cost_cap_usd": COST_CAP_USD,
        "pricing_source": PRICING_SOURCE,
        "tokens_source": TOKENS_SOURCE,
        "cost_basis": "recomputed_from_official_rates",
        "cost_usd_total": _ledger_sum(usage_ledger),
        "cost_twd_total": round(_ledger_sum(usage_ledger) * USD_TWD, 2),
        "usd_twd_rate": USD_TWD,
        "token_totals": totals,
        "resume_used": resume,
        "runs": run_summaries,
        "n_completed": sum(
            1 for r in run_summaries if r["termination_reason"] in A1.COMPLETED_TERMINATIONS and r["blinded_run_id"]
        ),
        "completed": completed,
        "scanner_is_reviewer": False,
    }
    manifest["cost_usd_accumulated"] = _ledger_sum(usage_ledger)
    _atomic_write_text_v2(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2), 0o600)
    _atomic_write_text_v2(summary_path, L1._scrub(json.dumps(summary, ensure_ascii=False, indent=2)), 0o600)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safety stress-test v2 real-Gemini low-cost pilot")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--live-pilot", action="store_true")
    parser.add_argument("--case-id", default="SAFETY-RX-01-v2")
    parser.add_argument("--root", default=None)
    parser.add_argument("--confirm-live-pilot", default=None)
    parser.add_argument("--pilot-tag", default=LIVE_TAG_NAME_V2)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--env-file",
        default=None,
        help="optional dotenv file loaded into the process environment (value never printed)",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.env_file:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=args.env_file, override=False)
    if args.preflight:
        report = preflight(args.case_id, Path(args.root) if args.root else None, pilot_tag=args.pilot_tag)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("preflight") == "PASS" else 2
    summary = run_live_pilot_v2(
        args.case_id,
        Path(args.root) if args.root else None,
        confirm=args.confirm_live_pilot,
        pilot_tag=args.pilot_tag,
        resume=args.resume,
    )
    print(
        json.dumps(
            {"completed": summary["completed"], "cost_usd_total": summary["cost_usd_total"], "runs": summary["runs"]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if summary["completed"] else 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
