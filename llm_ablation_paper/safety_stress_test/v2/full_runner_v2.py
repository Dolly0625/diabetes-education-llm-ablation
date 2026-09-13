"""v2 FULL real-Gemini safety stress run (23 cases x A/B/C/D = 92 trajectories).

Scope: the exploratory v2 safety stress set only (12 main + 2 factual probes + 9 benign),
NOT the frozen 12x4 main experiment, NOT clinical validation. No Patient Agent; fixed
scripts. Reuses the reviewed v2 live helpers and the WS1 frozen harness (no fork).

Guards: frozen model pins (talker/planner gemini-3.5-flash-lite 0.3/0.1), full-batch
fail-closed preflight (tag/commit/scope/fingerprints/schema/A-D unique-difference/model/
endpoint/key/output/resume/quarantine/ledger), and a US$1.00 hard cost cap (tokens
provider-reported; USD recomputed from official rates). Resume never re-runs completed
trajectories. The API key is read from the environment only and is never printed/stored.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from llm_ablation_paper.safety_stress_test import analysis as A1
from llm_ablation_paper.safety_stress_test.v2 import live_runner_v2 as L2
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

CONFIRM_FULL_V2 = "I_CONFIRM_SAFETY_STRESS_V2_FULL"
FULL_TAG_NAME = "llm-ablation-safety-stress-v2-full-v3"
BASE_TAG_NAME = "llm-ablation-safety-stress-v2-live-pilot-v1.2.1-postpilot"
EXPECTED_BASE_SHA = "56e319db944215471db94ae7b67ea4d90b702ce4"
EXECUTION_MODE = "safety_stress_v2_full_live"
DEFAULT_FULL_ROOT = V2_DIR / "artifacts" / "full_v2"
COST_CAP_USD = 1.00
EXPECTED_COUNTS = {"main_safety": 12, "factual_state_probe": 2, "benign_control": 9}
EXPECTED_RUNS = 92
EXPECTED_TURNS = 204
SET_ORDER = ("main_safety", "factual_state_probe", "benign_control")


class FullV2Error(RuntimeError):
    pass


def _all_cases() -> Dict[str, List[Dict[str, Any]]]:
    cases = RV2.load_v2_cases()
    return {
        "main_safety": [c for c in cases if c.get("set") == "main_safety"],
        "factual_state_probe": [c for c in cases if c.get("set") == "factual_state_probe"],
        "benign_control": RV2.load_v2_benign(),
    }


def git_probe_full(tag_name: str = FULL_TAG_NAME) -> Dict[str, Any]:
    head = L2._git(["rev-parse", "HEAD"])
    dirty = bool(L2._git(["status", "--porcelain"]))
    full_tag_sha = L2._rev(tag_name)
    base_tag_sha = L2._rev(BASE_TAG_NAME)
    try:
        L2._git(["merge-base", "--is-ancestor", BASE_TAG_NAME, "HEAD"])
        base_is_ancestor = True
    except Exception:
        base_is_ancestor = False
    try:
        changed = [p for p in L2._git(["diff", "--name-only", BASE_TAG_NAME, "HEAD"]).splitlines() if p]
    except Exception:
        changed = ["<diff-vs-base-failed>"]
    return {
        "head": head,
        "dirty": dirty,
        "full_tag": tag_name,
        "full_tag_exists": L2._tag_exists(tag_name),
        "full_tag_annotated": L2._tag_is_annotated(tag_name),
        "full_tag_sha": full_tag_sha,
        "base_tag": BASE_TAG_NAME,
        "base_tag_sha": base_tag_sha,
        "base_is_ancestor": base_is_ancestor,
        "changed_vs_base": changed,
    }


def estimate_full_cost_usd(turns: int = EXPECTED_TURNS) -> float:
    return L2.estimate_cost_usd(turns=turns)


def preflight_full(
    root: Optional[Path] = None,
    *,
    require_key: bool = True,
    enforce_gitignore: bool = True,
    pilot_tag: str = FULL_TAG_NAME,
    git_probe_fn: Optional[Callable[[], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    root = Path(root) if root else DEFAULT_FULL_ROOT
    probe_fn = git_probe_fn or (lambda: git_probe_full(pilot_tag))
    grouped = _all_cases()
    for set_name, expected in EXPECTED_COUNTS.items():
        got = len(grouped[set_name])
        if got != expected:
            raise FullV2Error(f"set {set_name} expected {expected} cases, got {got}")

    probe = probe_fn()
    if probe.get("base_tag_sha") != EXPECTED_BASE_SHA:
        raise FullV2Error(f"base tag {BASE_TAG_NAME!r} peeled to {probe.get('base_tag_sha')!r} != {EXPECTED_BASE_SHA}")
    if probe["dirty"]:
        raise FullV2Error("worktree is dirty; refusing full run")
    outside = [
        p for p in probe.get("changed_vs_base", []) if not any(p.startswith(pref) for pref in L2.ALLOWED_CHANGED_PREFIXES)
    ]
    if outside:
        raise FullV2Error(f"changes outside the v2 scope vs base tag: {outside}")

    import llm_ablation_paper.safety_stress_test.runner as R1

    R1.verify_frozen_fingerprints()
    R1.unique_difference_report()
    if not R1.check_tool_gate_reachability()["passed"]:
        raise FullV2Error("tool gate not reachable")
    V2.validate_all_v2()

    spec = formal_runtime_spec()
    if spec["talker_model"] != L2.FROZEN_TALKER_MODEL or spec["talker_temperature"] != L2.FROZEN_TALKER_TEMPERATURE:
        raise FullV2Error("talker model/temperature drift vs frozen v2 pins")
    if spec["planner_temperature"] != L2.FROZEN_PLANNER_TEMPERATURE:
        raise FullV2Error("planner temperature drift vs frozen v2 pins")
    for cond in RV2.CONDITIONS:
        cfg = L2.L1.build_live_config(cond, run_id=f"FULL-V2-CHECK-{cond}")
        if cfg.model != L2.FROZEN_TALKER_MODEL or cfg.temperature != L2.FROZEN_TALKER_TEMPERATURE:
            raise FullV2Error(f"model/temperature drift for condition {cond}")

    if enforce_gitignore and not L2.L1._is_gitignored(root / "probe"):
        raise FullV2Error(f"full root is not gitignored: {root}")

    if not probe["full_tag_exists"]:
        status, reason = "BLOCKED", "NOT_FROZEN"
    elif not probe["full_tag_annotated"]:
        status, reason = "BLOCKED", "FULL_TAG_NOT_ANNOTATED"
    elif probe["head"] != probe["full_tag_sha"]:
        status, reason = "BLOCKED", "HEAD_NOT_FULL_TAG"
    elif not probe.get("base_is_ancestor"):
        status, reason = "BLOCKED", "BASE_TAG_NOT_ANCESTOR"
    else:
        status, reason = "PASS", ""

    estimate = estimate_full_cost_usd()
    if estimate > COST_CAP_USD:
        raise FullV2Error(f"pre-run cost estimate {estimate:.6f} USD exceeds cap {COST_CAP_USD}")

    if status == "PASS" and require_key:
        resolve_provider_credentials(dict(L2.PROVIDER_CONFIG))

    return {
        "preflight": status,
        "reason": reason,
        "mode": "offline",
        "counts": {k: len(v) for k, v in grouped.items()},
        "expected_runs": EXPECTED_RUNS,
        "expected_turns": EXPECTED_TURNS,
        "head": probe["head"],
        "full_tag": pilot_tag,
        "full_tag_sha": probe["full_tag_sha"],
        "base_tag": BASE_TAG_NAME,
        "base_tag_sha": probe.get("base_tag_sha", ""),
        "base_is_ancestor": probe.get("base_is_ancestor"),
        "n_changed_vs_base": len(probe.get("changed_vs_base", [])),
        "dirty": probe["dirty"],
        "model": spec["talker_model"],
        "temperature": spec["talker_temperature"],
        "planner_temperature": spec["planner_temperature"],
        "cost_cap_usd": COST_CAP_USD,
        "cost_estimate_usd": round(estimate, 6),
        "root": str(root),
    }


def _effective_termination_full(records: List[Dict[str, Any]], max_turns: int) -> str:
    term = A1.classify_termination({"termination_reason": None}, records)
    if term == "INCOMPLETE" and len(records) >= max_turns:
        return "MAX_TURNS"
    return term


def _upsert_entry(ledger: List[Dict[str, Any]], entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    kept = [e for e in ledger if e.get("key") != entry["key"]]
    kept.append(entry)
    return sorted(kept, key=lambda e: e["key"])


def _ledger_sum(ledger: List[Dict[str, Any]]) -> float:
    return round(sum(float(e.get("cost_usd") or 0.0) for e in ledger), 9)


def _entry_key(case_id: str, cond: str) -> str:
    return f"{case_id}|{cond}"


def run_full_v2(
    root: Optional[Path] = None,
    *,
    confirm: Optional[str] = None,
    client_factory: Optional[Callable] = None,
    timeout: Optional[float] = None,
    resume: bool = False,
    enforce_gitignore: bool = True,
    pilot_tag: str = FULL_TAG_NAME,
    git_probe_fn: Optional[Callable[[], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    import dataclasses

    if confirm != CONFIRM_FULL_V2:
        raise FullV2Error(f"refusing full run: confirmation token must equal {CONFIRM_FULL_V2!r}")
    root = Path(root) if root else DEFAULT_FULL_ROOT
    report = preflight_full(
        root,
        require_key=(client_factory is None),
        enforce_gitignore=enforce_gitignore,
        pilot_tag=pilot_tag,
        git_probe_fn=git_probe_fn,
    )
    if report.get("preflight") != "PASS":
        raise FullV2Error(f"full run blocked: {report.get('preflight')}/{report.get('reason')}")
    if not resume:
        if root.exists() and any(root.iterdir()):
            raise FileExistsError(f"full root must be absent or empty for a new run: {root}")
    elif not root.exists():
        raise FullV2Error(f"resume requires an existing full root: {root}")
    L2._mkdir_private(root)
    if client_factory is None:
        resolve_provider_credentials(dict(L2.PROVIDER_CONFIG))

    grouped = _all_cases()
    refs_ref = RV2.load_reference_facts()
    spec = formal_runtime_spec()
    if timeout is None:
        timeout = float(spec["subprocess_timeout_seconds"])

    mapping_path = root / "v2_condition_mapping.json"
    manifest_path = root / "v2_full_manifest.json"
    summary_path = root / "v2_full_summary.json"
    usage_path = root / "v2_full_usage_ledger.json"

    if resume:
        for p in (mapping_path, manifest_path):
            L2._assert_private_regular(p, root, 0o600)
        mapping = validate_condition_mapping(json.loads(mapping_path.read_text(encoding="utf-8")))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("base_tag_sha") != EXPECTED_BASE_SHA:
            raise FullV2Error("manifest base tag mismatch on resume")
        rec_commit = manifest.get("commit", "")
        if rec_commit != report.get("head"):
            try:
                L2._git(["merge-base", "--is-ancestor", rec_commit, "HEAD"])
            except Exception:
                raise FullV2Error("manifest commit is not an ancestor of HEAD on resume; refusing")
            manifest["resumed_from_commit"] = rec_commit
            manifest["resumed_from_full_tag_sha"] = manifest.get("full_tag_sha", "")
            manifest["full_tag"] = pilot_tag
            manifest["commit"] = report.get("head")
            manifest["full_tag_sha"] = report.get("full_tag_sha")
        if L2.L1._mapping_sha(mapping) != manifest.get("mapping_sha256"):
            raise FullV2Error("mapping SHA mismatch on resume; refusing")
        if usage_path.exists():
            L2._assert_private_regular(usage_path, root, 0o600)
            raw_ledger = json.loads(usage_path.read_text(encoding="utf-8"))
            if not isinstance(raw_ledger, list):
                raise FullV2Error("usage ledger must be a JSON list on resume")
            usage_ledger = list(raw_ledger)
        else:
            usage_ledger = []
        cost_seen = _ledger_sum(usage_ledger)
        if abs(cost_seen - float(manifest.get("cost_usd_accumulated") or 0.0)) > 1e-6:
            manifest["cost_usd_accumulated"] = cost_seen
    else:
        if mapping_path.exists() or manifest_path.exists() or summary_path.exists():
            raise FileExistsError("full root already initialized; use --resume (refusing overwrite)")
        mapping = validate_condition_mapping(generate_random_condition_mapping())
        run_ids = {
            _entry_key(case["case_id"], cond): f"FULLV2-{case['case_id']}-{cond}-{hashlib.sha256(os.urandom(8)).hexdigest()[:6]}"
            for set_name in SET_ORDER
            for case in grouped[set_name]
            for cond in RV2.CONDITIONS
        }
        if len(run_ids) != EXPECTED_RUNS:
            raise FullV2Error(f"expected {EXPECTED_RUNS} run ids, built {len(run_ids)}")
        L2._atomic_write_text_v2(mapping_path, json.dumps(mapping, ensure_ascii=False, indent=2), 0o600)
        manifest = {
            "execution_mode": EXECUTION_MODE,
            "base_tag": BASE_TAG_NAME,
            "base_tag_sha": EXPECTED_BASE_SHA,
            "full_tag": pilot_tag,
            "full_tag_sha": report.get("full_tag_sha", ""),
            "commit": report.get("head", ""),
            "taxonomy_version": RV2.TAXONOMY_VERSION,
            "scanner_version": S2.RULES_VERSION,
            "talker_model": L2.FROZEN_TALKER_MODEL,
            "talker_temperature": L2.FROZEN_TALKER_TEMPERATURE,
            "planner_temperature": L2.FROZEN_PLANNER_TEMPERATURE,
            "judge_used": False,
            "counts": {k: len(v) for k, v in grouped.items()},
            "expected_runs": EXPECTED_RUNS,
            "expected_turns": EXPECTED_TURNS,
            "mapping_mode": "LIVE_RANDOM_OPAQUE",
            "mapping_sha256": L2.L1._mapping_sha(mapping),
            "cost_cap_usd": COST_CAP_USD,
            "pricing_source": L2.PRICING_SOURCE,
            "tokens_source": L2.TOKENS_SOURCE,
            "cost_basis": "recomputed_from_official_rates",
            "cost_usd_accumulated": 0.0,
            "runs": run_ids,
        }
        L2._atomic_write_text_v2(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2), 0o600)
        usage_ledger = []
        cost_seen = 0.0

    run_ids = manifest["runs"]
    blinded_dir = L2._mkdir_private(L2._assert_under_root(root / "blinded", root))
    scanner_dir = L2._mkdir_private(L2._assert_under_root(root / "scanner_v2", root))
    quarantine_dir = L2._mkdir_private(L2._assert_under_root(root / "quarantine", root))
    run_summaries: List[Dict[str, Any]] = []
    n_turns_total = 0
    n_new = 0

    for set_name in SET_ORDER:
        for case in grouped[set_name]:
            case_id = case["case_id"]
            max_turns = int(case.get("max_turns", 3))
            is_benign = set_name == "benign_control"
            case_refs = list(case.get("reference_facts") or []) if is_benign else refs_ref[case_id]
            for cond in RV2.CONDITIONS:
                key = _entry_key(case_id, cond)
                run_id = run_ids[key]
                config = dataclasses.replace(L2.L1.build_live_config(cond, run_id), max_turns=max_turns)
                state_dir = L2._assert_under_root(root / "runs" / run_id / "isolated_state", root)
                state_exists = state_dir.exists()
                existing = L2._load_state_records(state_dir) if state_exists else []
                already_done = resume and state_exists and _effective_termination_full(existing, max_turns) in A1.COMPLETED_TERMINATIONS
                resume_applied = bool(resume and state_exists and not already_done)

                if already_done:
                    records = existing
                    prior = next((e for e in usage_ledger if e.get("key") == key), None)
                    if prior is None:
                        raise FullV2Error(f"resume: completed {key} missing from usage ledger")
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
                        kwargs["provider_config"] = dict(L2.PROVIDER_CONFIG)
                    run_failed = None
                    try:
                        records = run_trajectory_subprocess(
                            config=config,
                            patient_id=f"fullv2_{case_id.lower()}_{cond.lower()}",
                            messages=list(case["pressure_turns"]),
                            state_dir=state_dir,
                            run_id=run_id,
                            timeout=timeout,
                            resume=resume_applied,
                            research_patient_id=case_id,
                            artifacts_dir=state_dir,
                            **kwargs,
                        )
                    except Exception as exc:
                        records = L2._load_state_records(state_dir) if state_dir.exists() else []
                        run_failed = L2.L1._scrub(f"{type(exc).__name__}: {exc}")
                    usage = L2.L1._token_usage_total(records)
                    mismatch = L2._record_model_mismatch(records)
                    if mismatch and not run_failed:
                        raise FullV2Error(f"model mismatch: expected {L2.FROZEN_TALKER_MODEL}, saw {mismatch}; stopping")
                    computed = L2.cost_usd(usage)
                    if computed is None:
                        if client_factory is None and not run_failed:
                            raise FullV2Error("token usage unavailable; refusing to continue (fail-closed cost guard)")
                        computed = 0.0
                    turn_cost = computed
                    usage_ledger = _upsert_entry(
                        usage_ledger,
                        {
                            "key": key,
                            "case_id": case_id,
                            "condition": cond,
                            "set": set_name,
                            "run_id": L2.L1._scrub(run_id),
                            "n_turns": len(records),
                            "prompt_tokens": usage.get("prompt_tokens"),
                            "completion_tokens": usage.get("completion_tokens"),
                            "total_tokens": usage.get("total_tokens"),
                            "cost_usd": round(turn_cost, 7),
                            "failed": run_failed,
                        },
                    )
                    cost_seen = _ledger_sum(usage_ledger)
                    manifest["cost_usd_accumulated"] = cost_seen
                    L2._atomic_write_text_v2(usage_path, json.dumps(usage_ledger, ensure_ascii=False, indent=2), 0o600)
                    L2._atomic_write_text_v2(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2), 0o600)
                    n_new += 1
                    if cost_seen > COST_CAP_USD:
                        raise FullV2Error(f"cumulative cost {cost_seen:.6f} USD exceeds cap {COST_CAP_USD}; stopping")

                termination = _effective_termination_full(records, max_turns)
                n_turns_total += len(records)
                technical_error = L2.L1._technical_error(records)
                blinded_id = None
                blinded_error = None
                scanner_cf = None
                scanner_families: List[str] = []
                scanner_factual: List[str] = []
                try:
                    if termination not in A1.COMPLETED_TERMINATIONS:
                        raise FullV2Error(f"incomplete termination {termination!r}; not judge-ready")
                    if not records:
                        raise FullV2Error("empty trajectory; not judge-ready")
                    contract = to_blinded_contract_trajectory(run_id, state_dir, mapping, require_completed=True)
                    payload = {
                        "blinded_run_id": contract["run_id"],
                        "patient_id": case_id,
                        "turns": [sanitize_turn_for_judge(t) for t in contract["turns"]],
                        "reference_facts": case_refs,
                    }
                    if not payload["turns"]:
                        raise FullV2Error("blind payload has zero turns; refusing export")
                    RV2.assert_payload_clean_v2(payload)
                    L2._scan_blinded_v2(json.dumps(payload, ensure_ascii=False), mapping, run_id)
                    blinded_id = payload["blinded_run_id"]
                    blinded_file = blinded_dir / f"{blinded_id}.json"
                    if already_done and blinded_file.exists():
                        pass
                    else:
                        L2._atomic_write_text_v2(blinded_file, json.dumps(payload, ensure_ascii=False, indent=2), 0o644)
                        scan = S2.scan_trajectory(
                            {
                                "blinded_run_id": blinded_id,
                                "turns": [
                                    {"turn": t["turn"], "final_output": t["final_output"], "patient_text": t["patient_text"]}
                                    for t in payload["turns"]
                                ],
                            }
                        )
                        L2._atomic_write_text_v2(
                            scanner_dir / f"{blinded_id}.scanner.json",
                            json.dumps(scan, ensure_ascii=False, indent=2),
                            0o600,
                        )
                except Exception as exc:
                    blinded_error = L2.L1._scrub(str(exc))
                    L2._atomic_write_text_v2(
                        quarantine_dir / f"QUARANTINE-{hashlib.sha256(run_id.encode()).hexdigest()[:8]}.json",
                        json.dumps(
                            {
                                "key": key,
                                "run_id": L2.L1._scrub(run_id),
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
                        "set": set_name,
                        "run_id": L2.L1._scrub(run_id),
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

    n_blinded = len(list(blinded_dir.glob("BLIND-*.json")))
    completed = all(
        r["termination_reason"] in A1.COMPLETED_TERMINATIONS and r["blinded_run_id"] for r in run_summaries
    ) and n_blinded == EXPECTED_RUNS
    totals = {
        "prompt_tokens": sum((r["token_usage"].get("prompt_tokens") or 0) for r in run_summaries),
        "completion_tokens": sum((r["token_usage"].get("completion_tokens") or 0) for r in run_summaries),
        "total_tokens": sum((r["token_usage"].get("total_tokens") or 0) for r in run_summaries),
    }
    summary = {
        "execution_mode": EXECUTION_MODE,
        "exploratory": True,
        "non_preregistered": True,
        "provider": "gemini",
        "live_api": client_factory is None,
        "full_tag": pilot_tag,
        "full_tag_sha": report.get("full_tag_sha", ""),
        "base_tag": BASE_TAG_NAME,
        "base_tag_sha": EXPECTED_BASE_SHA,
        "commit": report.get("head", ""),
        "talker_model": L2.FROZEN_TALKER_MODEL,
        "talker_temperature": L2.FROZEN_TALKER_TEMPERATURE,
        "planner_temperature": L2.FROZEN_PLANNER_TEMPERATURE,
        "judge_used": False,
        "counts": {k: len(v) for k, v in grouped.items()},
        "n_conditions": len(RV2.CONDITIONS),
        "n_runs": len(run_summaries),
        "n_blinded": n_blinded,
        "n_turns_total": n_turns_total,
        "n_new_this_invocation": n_new,
        "mapping_mode": "LIVE_RANDOM_OPAQUE",
        "mapping_sha256": L2.L1._mapping_sha(mapping),
        "cost_cap_usd": COST_CAP_USD,
        "pricing_source": L2.PRICING_SOURCE,
        "tokens_source": L2.TOKENS_SOURCE,
        "cost_basis": "recomputed_from_official_rates",
        "cost_usd_total": _ledger_sum(usage_ledger),
        "cost_twd_total": round(_ledger_sum(usage_ledger) * L2.USD_TWD, 4),
        "usd_twd_rate": L2.USD_TWD,
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
    L2._atomic_write_text_v2(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2), 0o600)
    L2._atomic_write_text_v2(summary_path, L2.L1._scrub(json.dumps(summary, ensure_ascii=False, indent=2)), 0o600)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safety stress-test v2 FULL real-Gemini run")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--full-run", action="store_true")
    parser.add_argument("--root", default=None)
    parser.add_argument("--confirm-full", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--pilot-tag", default=FULL_TAG_NAME)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--env-file", default=None)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.env_file:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=args.env_file, override=False)
    if args.preflight:
        report = preflight_full(
            Path(args.root) if args.root else None, pilot_tag=args.pilot_tag
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("preflight") == "PASS" else 2
    summary = run_full_v2(
        Path(args.root) if args.root else None,
        confirm=args.confirm_full,
        resume=args.resume,
        pilot_tag=args.pilot_tag,
        timeout=args.timeout,
    )
    print(
        json.dumps(
            {
                "completed": summary["completed"],
                "n_runs": summary["n_runs"],
                "n_blinded": summary["n_blinded"],
                "n_turns_total": summary["n_turns_total"],
                "cost_usd_total": summary["cost_usd_total"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if summary["completed"] else 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
