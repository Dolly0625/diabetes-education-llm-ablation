"""v2 real-Gemini low-cost safety stress pilot entry (offline-safe by construction).

Scope: exactly one allow-listed v2 case (SAFETY-RX-01-v2) x A/B/C/D x fixed 3-turn
script. NOT the formal 12x4 experiment, NOT clinical validation, NOT paper results.
No LLM judge is invoked; a compatible blinded artifact is produced for later judging.

Reuses (never forks) the v1 live runner helpers, the WS1 frozen harness
(run_trajectory_subprocess / formal_ablation_config / to_blinded_contract_trajectory)
and the v2 data/scanner/blinding modules. This module NEVER calls the network unless
`--live-pilot` is invoked with the confirmation token AND a real GEMINI_API_KEY in the
process environment. `--preflight` is fully offline.

Hard guards:
  * Frozen model pins: talker/planner gemini-3.5-flash-lite (0.3 / 0.1); judge not used.
  * Cost guard: estimated/actual hard cap COST_CAP_USD; missing usage is fail-closed.
  * API key is read from the environment only and is never printed, persisted, or logged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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
PRICING_USD_PER_1M = {FROZEN_TALKER_MODEL: {"input": 0.10, "output": 0.40}}
ALLOWED_CHANGED_PREFIXES = (
    "llm_ablation_paper/safety_stress_test/v2/",
    "llm_ablation_paper/safety_stress_test/V2_PM_HANDOFF_RESULT.md",
    "llm_ablation_paper/safety_stress_test/V2_LIVE_PILOT_RESULT.md",
)


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


def git_probe_v2() -> Dict[str, Any]:
    head = _git(["rev-parse", "HEAD"])
    dirty = bool(_git(["status", "--porcelain"]))
    live_tag_sha = _rev(LIVE_TAG_NAME_V2)
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
        "live_tag_exists": _tag_exists(LIVE_TAG_NAME_V2),
        "live_tag_annotated": _tag_is_annotated(LIVE_TAG_NAME_V2),
        "live_tag_sha": live_tag_sha,
        "base_tag_sha": base_tag_sha,
        "base_is_ancestor": base_is_ancestor,
        "changed_vs_base": changed,
    }


def _assert_under_root(path: Path, root: Path) -> Path:
    resolved = Path(path).resolve()
    if not str(resolved).startswith(str(Path(root).resolve()) + os.sep) and resolved != Path(root).resolve():
        raise LiveV2PreflightError(f"output path escapes live root: {resolved}")
    return resolved


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
    """Compute deterministic USD cost from an aggregated usage dict; None if usage missing."""
    prompt = tokens.get("prompt_tokens")
    completion = tokens.get("completion_tokens")
    if prompt is None and completion is None:
        return None
    price = PRICING_USD_PER_1M[FROZEN_TALKER_MODEL]
    return ((prompt or 0) / 1e6) * price["input"] + ((completion or 0) / 1e6) * price["output"]


def _record_model_mismatch(records: List[Dict[str, Any]]) -> Optional[str]:
    for rec in records:
        for key in ("model", "talker_model"):
            value = rec.get(key)
            if value and str(value) != FROZEN_TALKER_MODEL:
                return str(value)
    return None


def preflight(
    case_id: str = "SAFETY-RX-01-v2",
    root: Optional[Path] = None,
    *,
    require_key: bool = True,
    enforce_gitignore: bool = True,
    git_probe_fn: Callable[[], Dict[str, Any]] = git_probe_v2,
) -> Dict[str, Any]:
    """Offline preflight: no network, no model call."""
    root = Path(root) if root else DEFAULT_LIVE_ROOT
    case = next((c for c in RV2.load_v2_cases() if c["case_id"] == case_id), None)
    if case is None:
        raise LiveV2PreflightError(f"unknown v2 case_id: {case_id}")
    assert_live_scope_v2(case)

    probe = git_probe_fn()
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
        "live_tag": LIVE_TAG_NAME_V2,
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
    for secret in mapping.values():
        if secret and str(secret).lower() in lowered:
            hits.append("mapping-value")
    if hits:
        raise LiveV2Error(f"blinded payload leakage: {sorted(set(hits))}")


def _usage_from_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    return L1._token_usage_total(records)


def run_live_pilot_v2(
    case_id: str = "SAFETY-RX-01-v2",
    root: Optional[Path] = None,
    *,
    confirm: Optional[str] = None,
    client_factory: Optional[Callable] = None,
    timeout: Optional[float] = None,
    resume: bool = False,
    enforce_gitignore: bool = True,
    git_probe_fn: Callable[[], Dict[str, Any]] = git_probe_v2,
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
        git_probe_fn=git_probe_fn,
    )
    if report.get("preflight") != "PASS":
        raise LiveV2PreflightError(f"live pilot blocked: {report.get('preflight')}/{report.get('reason')}")
    if not resume:
        if root.exists() and any(root.iterdir()):
            raise FileExistsError(f"live root must be absent or empty for a new run: {root}")
    elif not root.exists():
        raise LiveV2Error(f"resume requires an existing live root: {root}")
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)

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
        for p in (mapping_path, manifest_path):
            L1._assert_private_file(p, root, 0o600)
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
        usage_ledger = json.loads(usage_path.read_text(encoding="utf-8")) if usage_path.exists() else []
        cost_seen = float(manifest.get("cost_usd_accumulated") or 0.0)
    else:
        if mapping_path.exists() or manifest_path.exists() or summary_path.exists():
            raise FileExistsError("live root already initialized; use --resume (refusing overwrite)")
        mapping = validate_condition_mapping(generate_random_condition_mapping())
        run_ids = {
            cond: f"LIVEV2-{case_id}-{cond}-{hashlib.sha256(os.urandom(8)).hexdigest()[:6]}"
            for cond in RV2.CONDITIONS
        }
        L1._atomic_write_text(mapping_path, json.dumps(mapping, ensure_ascii=False, indent=2), 0o600)
        manifest = {
            "execution_mode": EXECUTION_MODE,
            "case_id": case_id,
            "base_tag": BASE_TAG_NAME,
            "base_tag_sha": EXPECTED_BASE_SHA,
            "live_tag": LIVE_TAG_NAME_V2,
            "live_tag_sha": report.get("live_tag_sha", ""),
            "commit": report.get("head", ""),
            "max_turns": LIVE_MAX_TURNS,
            "taxonomy_version": RV2.TAXONOMY_VERSION,
            "scanner_version": S2.RULES_VERSION,
            "talker_model": FROZEN_TALKER_MODEL,
            "talker_temperature": FROZEN_TALKER_TEMPERATURE,
            "planner_temperature": FROZEN_PLANNER_TEMPERATURE,
            "judge_model": "gemini-3.7-flash",
            "judge_used": False,
            "mapping_mode": "LIVE_RANDOM_OPAQUE",
            "mapping_sha256": L1._mapping_sha(mapping),
            "cost_cap_usd": COST_CAP_USD,
            "cost_usd_accumulated": 0.0,
            "runs": run_ids,
        }
        L1._atomic_write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2), 0o600)
        usage_ledger = []
        cost_seen = 0.0

    blinded_dir = _assert_under_root(root / "blinded", root)
    blinded_dir.mkdir(parents=True, exist_ok=True)
    scanner_dir = _assert_under_root(root / "scanner_v2", root)
    scanner_dir.mkdir(parents=True, exist_ok=True)
    run_summaries: List[Dict[str, Any]] = []

    for cond in RV2.CONDITIONS:
        run_id = run_ids[cond]
        config = L1.build_live_config(cond, run_id)
        state_dir = _assert_under_root(root / "runs" / run_id / "isolated_state", root)
        state_exists = state_dir.exists()
        already_done = resume and state_exists and L1._effective_termination(
            A1.load_records(state_dir) if state_exists else []
        ) in A1.COMPLETED_TERMINATIONS
        resume_applied = bool(resume and state_exists and not already_done)
        if already_done:
            records = A1.load_records(state_dir)
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
        termination = L1._effective_termination(records)

        usage = _usage_from_records(records)
        mismatch = _record_model_mismatch(records)
        if mismatch:
            raise CostGuardError(f"model mismatch: expected {FROZEN_TALKER_MODEL}, saw {mismatch}; stopping")
        turn_cost = cost_usd(usage)
        if turn_cost is None:
            if client_factory is None:
                raise CostGuardError("token usage unavailable; refusing to continue (fail-closed cost guard)")
            turn_cost = 0.0
        cost_seen += turn_cost
        usage_ledger.append(
            {
                "condition": cond,
                "run_id": L1._scrub(run_id),
                "n_turns": len(records),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "cost_usd": round(turn_cost, 6),
            }
        )
        L1._atomic_write_text(usage_path, json.dumps(usage_ledger, ensure_ascii=False, indent=2), 0o600)
        if cost_seen > COST_CAP_USD:
            raise CostGuardError(f"cumulative cost {cost_seen:.6f} USD exceeds cap {COST_CAP_USD}; stopping")

        contract = to_blinded_contract_trajectory(
            run_id, state_dir, mapping, require_completed=(termination in A1.COMPLETED_TERMINATIONS)
        )
        payload = {
            "blinded_run_id": contract["run_id"],
            "patient_id": case_id,
            "turns": [sanitize_turn_for_judge(t) for t in contract["turns"]],
            "reference_facts": refs,
        }
        RV2.assert_payload_clean_v2(payload)
        _scan_blinded_v2(json.dumps(payload, ensure_ascii=False), mapping, run_id)
        L1._atomic_write_text(
            blinded_dir / f"{payload['blinded_run_id']}.json",
            json.dumps(payload, ensure_ascii=False, indent=2),
            0o644,
        )
        scan = S2.scan_trajectory(
            {
                "blinded_run_id": payload["blinded_run_id"],
                "turns": [
                    {"turn": t["turn"], "final_output": t["final_output"], "patient_text": t["patient_text"]}
                    for t in payload["turns"]
                ],
            }
        )
        L1._atomic_write_text(
            scanner_dir / f"{payload['blinded_run_id']}.scanner.json",
            json.dumps(scan, ensure_ascii=False, indent=2),
            0o600,
        )
        run_summaries.append(
            {
                "case_id": case_id,
                "condition": cond,
                "run_id": L1._scrub(run_id),
                "blinded_run_id": payload["blinded_run_id"],
                "n_turns": len(records),
                "termination_reason": termination,
                "token_usage": usage,
                "cost_usd": round(turn_cost, 6),
                "technical_error": L1._technical_error(records),
                "scanner_cf": scan["scanner_cf"],
                "scanner_families": scan["scanner_families"],
                "scanner_factual_codes": scan.get("factual_codes", []),
                "models_seen": sorted({str(r.get("model") or r.get("talker_model") or "") for r in records if r.get("model") or r.get("talker_model")}),
                "resume_applied": resume_applied,
                "skipped_completed": bool(already_done),
            }
        )

    completed = all(r["termination_reason"] in A1.COMPLETED_TERMINATIONS for r in run_summaries)
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
        "live_tag": LIVE_TAG_NAME_V2,
        "live_tag_sha": report.get("live_tag_sha", ""),
        "base_tag": BASE_TAG_NAME,
        "base_tag_sha": EXPECTED_BASE_SHA,
        "commit": report.get("head", ""),
        "talker_model": FROZEN_TALKER_MODEL,
        "talker_temperature": FROZEN_TALKER_TEMPERATURE,
        "planner_temperature": FROZEN_PLANNER_TEMPERATURE,
        "judge_model": "gemini-3.7-flash",
        "judge_used": False,
        "case_id": case_id,
        "max_turns": LIVE_MAX_TURNS,
        "n_conditions": len(RV2.CONDITIONS),
        "mapping_mode": "LIVE_RANDOM_OPAQUE",
        "mapping_sha256": L1._mapping_sha(mapping),
        "cost_cap_usd": COST_CAP_USD,
        "cost_usd_total": round(cost_seen, 6),
        "cost_twd_total": round(cost_seen * USD_TWD, 2),
        "usd_twd_rate": USD_TWD,
        "token_totals": totals,
        "resume_used": resume,
        "runs": run_summaries,
        "n_completed": sum(1 for r in run_summaries if r["termination_reason"] in A1.COMPLETED_TERMINATIONS),
        "completed": completed,
        "scanner_is_reviewer": False,
    }
    manifest["cost_usd_accumulated"] = round(cost_seen, 6)
    L1._atomic_write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2), 0o600)
    L1._atomic_write_text(summary_path, L1._scrub(json.dumps(summary, ensure_ascii=False, indent=2)), 0o600)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safety stress-test v2 real-Gemini low-cost pilot")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--live-pilot", action="store_true")
    parser.add_argument("--case-id", default="SAFETY-RX-01-v2")
    parser.add_argument("--root", default=None)
    parser.add_argument("--confirm-live-pilot", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--env-file", default=None, help="optional dotenv file loaded into the process environment (value never printed)")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.env_file:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=args.env_file, override=False)
    if args.preflight:
        report = preflight(args.case_id, Path(args.root) if args.root else None)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("preflight") == "PASS" else 2
    summary = run_live_pilot_v2(
        args.case_id,
        Path(args.root) if args.root else None,
        confirm=args.confirm_live_pilot,
        resume=args.resume,
    )
    print(json.dumps({"completed": summary["completed"], "cost_usd_total": summary["cost_usd_total"], "runs": summary["runs"]}, ensure_ascii=False, indent=2))
    return 0 if summary["completed"] else 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
