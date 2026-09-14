"""Real-Gemini low-cost safety stress pilot entry (offline-safe by construction).

Scope: exactly one allow-listed safety case x A/B/C/D x fixed 3-turn script.
NOT the formal 12x4 experiment, NOT a clinical validation, NOT paper results.
No LLM judge; the rule scanner is not a reviewer. This validates the live data
pipeline only.

This module never calls the network unless `--live-pilot` is explicitly invoked
with the confirmation token AND a real GEMINI_API_KEY. `--preflight` is fully
offline. Tests inject a fake client factory and never touch the network.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from llm_ablation_paper.workstream_1_technical_lead.harness import (
    AblationConfig,
    clear_session_cache,
    ensure_provider_ready,
    generate_random_condition_mapping,
    resolve_provider_credentials,
    run_trajectory_subprocess,
    to_blinded_contract_trajectory,
    validate_condition_mapping,
)
from llm_ablation_paper.workstream_1_technical_lead.harness.config import (
    formal_ablation_config,
    formal_runtime_spec,
    require_frozen_formal_config,
)
from llm_ablation_paper.workstream_5_judge_analysis.sanitizer import assert_no_leakage, build_judge_payload

from llm_ablation_paper.safety_stress_test import analysis as A
from llm_ablation_paper.safety_stress_test import runner as R

SST_DIR = Path(__file__).resolve().parent
REPO_ROOT = SST_DIR.parents[1]

CONFIRM_LIVE_PILOT = "I_CONFIRM_SAFETY_STRESS_LIVE_PILOT"
LIVE_PILOT_TAG_NAME = "llm-ablation-safety-live-pilot-v1"
STRESS_TAG_NAME = "llm-ablation-safety-stress-v1"
EXPECTED_HEAD = "f5fc9b6a8746f934e30bdb2fe3f866c0a631e9ac"
STRESS_TAG_SHA = EXPECTED_HEAD
LIVE_CASE_ALLOWLIST = frozenset({"SAFETY-RX-01"})
LIVE_MAX_TURNS = 3
EXECUTION_MODE = "safety_stress_live_pilot"
DEFAULT_LIVE_ROOT = SST_DIR / "artifacts" / "live_pilot"
PROVIDER_CONFIG = {"provider": "gemini"}
SECRET_RE = re.compile(r"(AIza[0-9A-Za-z_\-]{6,}|api[_-]?key\s*[:=]\s*\S+|bearer\s+[A-Za-z0-9._\-]+)", re.IGNORECASE)


class LivePilotError(RuntimeError):
    pass


class LivePreflightError(LivePilotError):
    pass


class ConfirmationError(LivePilotError):
    pass


def _scrub(text: str) -> str:
    return SECRET_RE.sub("[REDACTED]", str(text))


def git_probe() -> Dict[str, Any]:
    """Return worktree + tag state for the live gate (read-only git)."""
    def _run(args: List[str]) -> str:
        return subprocess.check_output(args, cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL).decode().strip()

    def _sha(ref: str) -> str:
        try:
            return _run(["git", "rev-list", "-n1", ref])
        except subprocess.CalledProcessError:
            return ""

    head = _run(["git", "rev-parse", "HEAD"])
    dirty = bool(_run(["git", "status", "--porcelain"]))
    live_tag_sha = _sha(LIVE_PILOT_TAG_NAME)
    stress_tag_sha = _sha(STRESS_TAG_NAME)
    try:
        subprocess.check_call(
            ["git", "merge-base", "--is-ancestor", STRESS_TAG_NAME, "HEAD"],
            cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL,
        )
        stress_is_ancestor = True
    except subprocess.CalledProcessError:
        stress_is_ancestor = False
    try:
        changed = [p for p in _run(["git", "diff", "--name-only", STRESS_TAG_NAME, "HEAD"]).splitlines() if p]
    except subprocess.CalledProcessError:
        changed = ["<diff-vs-tag-failed>"]
    return {
        "head": head,
        "dirty": dirty,
        "live_tag_sha": live_tag_sha,
        "stress_tag_sha": stress_tag_sha,
        "stress_is_ancestor": stress_is_ancestor,
        "changed_vs_tag": changed,
    }


def build_live_config(condition: str, run_id: str) -> AblationConfig:
    base = formal_ablation_config(condition)
    require_frozen_formal_config(base)
    cfg = dataclasses.replace(base, run_id=run_id, max_turns=LIVE_MAX_TURNS)
    for field in ("model", "temperature", "planner_model", "planner_temperature", "seed"):
        if getattr(cfg, field) != getattr(base, field):
            raise LivePreflightError(f"live config must not change {field}")
    return cfg


def assert_live_scope(case: Dict[str, Any]) -> None:
    if case["case_id"] not in LIVE_CASE_ALLOWLIST:
        raise LivePilotError(
            f"case {case['case_id']!r} is not allow-listed for the live pilot; "
            f"allowed={sorted(LIVE_CASE_ALLOWLIST)}"
        )
    if case["max_turns"] != LIVE_MAX_TURNS or len(case["pressure_turns"]) != LIVE_MAX_TURNS:
        raise LivePilotError(f"live pilot requires exactly {LIVE_MAX_TURNS} turns for {case['case_id']}")


def _assert_under_root(path: Path, root: Path) -> Path:
    resolved = Path(path).resolve()
    if not str(resolved).startswith(str(root.resolve())):
        raise LivePreflightError(f"output path escapes live root: {resolved}")
    return resolved


def _is_gitignored(path: Path) -> bool:
    try:
        subprocess.check_output(
            ["git", "check-ignore", "-q", str(path)], cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL
        )
        return True
    except subprocess.CalledProcessError:
        return False
    except Exception:
        return False


def preflight(
    case_id: str = "SAFETY-RX-01",
    root: Optional[Path] = None,
    *,
    require_key: bool = True,
    enforce_gitignore: bool = True,
    git_probe_fn: Callable[[], Dict[str, Any]] = git_probe,
) -> Dict[str, Any]:
    """Offline preflight. Performs NO network and NO subprocess model call."""
    root = Path(root) if root else DEFAULT_LIVE_ROOT
    case = next((c for c in R.load_cases() if c["case_id"] == case_id), None)
    if case is None:
        raise LivePreflightError(f"unknown case_id: {case_id}")
    assert_live_scope(case)

    probe = git_probe_fn()
    if probe.get("stress_tag_sha") != STRESS_TAG_SHA:
        raise LivePreflightError(
            f"stress tag {STRESS_TAG_NAME!r} peeled to {probe.get('stress_tag_sha')!r} != {STRESS_TAG_SHA}"
        )
    if probe["dirty"]:
        raise LivePreflightError("worktree is dirty; refusing live pilot")
    outside = [p for p in probe.get("changed_vs_tag", []) if not p.startswith("llm_ablation_paper/safety_stress_test/")]
    if outside:
        raise LivePreflightError(f"changes outside safety_stress_test/ vs frozen stress tag: {outside}")

    R.verify_frozen_fingerprints()
    R.unique_difference_report()
    if not R.check_tool_gate_reachability()["passed"]:
        raise LivePreflightError("tool gate not reachable")

    import llm_ablation_paper.safety_stress_test.validate_cases as V

    V.validate_all()

    spec = formal_runtime_spec()
    for cond in R.CONDITIONS:
        cfg = build_live_config(cond, run_id=f"LIVE-CHECK-{cond}")
        if cfg.model != spec["talker_model"] or cfg.temperature != spec["talker_temperature"]:
            raise LivePreflightError(f"model/temperature drift for condition {cond}")

    if enforce_gitignore and not _is_gitignored(root / "probe"):
        raise LivePreflightError(f"live root is not gitignored: {root}")

    live_tag_sha = probe.get("live_tag_sha", "")
    if not live_tag_sha:
        status, reason = "BLOCKED", "NOT_FROZEN"
    elif probe["head"] != live_tag_sha:
        status, reason = "BLOCKED", "HEAD_NOT_LIVE_TAG"
    elif not probe.get("stress_is_ancestor"):
        status, reason = "BLOCKED", "STRESS_TAG_NOT_ANCESTOR"
    else:
        status, reason = "PASS", ""

    if status == "PASS" and require_key:
        resolve_provider_credentials(dict(PROVIDER_CONFIG))

    return {
        "preflight": status,
        "reason": reason,
        "mode": "offline",
        "case_id": case_id,
        "head": probe["head"],
        "live_tag": LIVE_PILOT_TAG_NAME,
        "live_tag_sha": live_tag_sha,
        "stress_tag": STRESS_TAG_NAME,
        "stress_tag_sha": probe.get("stress_tag_sha", ""),
        "stress_is_ancestor": probe.get("stress_is_ancestor"),
        "n_changed_vs_tag": len(probe.get("changed_vs_tag", [])),
        "dirty": probe["dirty"],
        "model": spec["talker_model"],
        "temperature": spec["talker_temperature"],
        "max_turns": LIVE_MAX_TURNS,
        "root": str(root),
    }


def offline_safe_client_factory():
    """OFFLINE TEST ONLY: deterministic safe talker for the mock live path (no API)."""
    from llm_ablation_paper.workstream_1_technical_lead.harness.dry_run import make_fake_client

    return make_fake_client([R.SAFE_TALKER] * 16)


def _token_usage_total(records: List[Dict[str, Any]]) -> Dict[str, Optional[int]]:
    prompt = completion = total = 0
    seen = False
    for rec in records:
        usage = rec.get("token_usage")
        if isinstance(usage, dict):
            seen = True
            prompt += int(usage.get("prompt_tokens") or 0)
            completion += int(usage.get("completion_tokens") or 0)
            total += int(usage.get("total_tokens") or 0)
    return {
        "prompt_tokens": prompt if seen else None,
        "completion_tokens": completion if seen else None,
        "total_tokens": total if seen else None,
    }


def _technical_error(records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for rec in records:
        if rec.get("error") or rec.get("error_metadata"):
            return {"error": _scrub(rec.get("error")), "error_metadata": rec.get("error_metadata")}
    return None


def _scan_blinded(text: str, mapping: Dict[str, str], raw_run_id: str) -> None:
    lowered = text.lower()
    hits = []
    for token in ("enable_", "condition_secret", "raw_talker", "guard_action", "planner_state", raw_run_id.lower()):
        if token in lowered:
            hits.append(token)
    for secret in mapping.values():
        if secret and str(secret).lower() in lowered:
            hits.append(secret)
    if re.search(r"\bcondition[\s_-]*[abcd]\b", lowered):
        hits.append("condition-letter")
    if re.search(r"[\"']condition[\"']\s*:\s*[\"'][abcd][\"']", lowered):
        hits.append("condition-key")
    if hits:
        raise LivePilotError(f"blinded payload leakage: {sorted(set(hits))}")


def _effective_termination(records: List[Dict[str, Any]]) -> str:
    """Normalise persisted records: a run that consumed all max_turns is complete."""
    term = A.classify_termination({"termination_reason": None}, records)
    if term == "INCOMPLETE" and len(records) >= LIVE_MAX_TURNS:
        return "MAX_TURNS"
    return term


def _assert_private_file(path: Path, root: Path, mode: int = 0o600) -> None:
    p = Path(path)
    if p.is_symlink():
        raise LivePilotError(f"private file must not be a symlink: {p}")
    if not p.exists() or not p.is_file():
        raise LivePilotError(f"private file missing or not a regular file: {p}")
    resolved = p.resolve()
    root_resolved = Path(root).resolve()
    if resolved != root_resolved and not str(resolved).startswith(str(root_resolved) + os.sep):
        raise LivePilotError(f"private file escapes live root: {resolved}")
    actual = stat.S_IMODE(p.stat().st_mode)
    if actual != mode:
        raise LivePilotError(f"private file mode {oct(actual)} != {oct(mode)}: {p}")


def _mapping_sha(mapping: Dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(mapping, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _atomic_write_text(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)
    os.chmod(path, mode)


class _TestInterrupt(Exception):
    pass


def run_live_pilot(
    case_id: str = "SAFETY-RX-01",
    root: Optional[Path] = None,
    *,
    confirm: Optional[str] = None,
    client_factory: Optional[Callable] = None,
    timeout: Optional[float] = None,
    resume: bool = False,
    enforce_gitignore: bool = True,
    git_probe_fn: Callable[[], Dict[str, Any]] = git_probe,
    _interrupt_after_groups: Optional[int] = None,
    _test_only_first_messages: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if confirm != CONFIRM_LIVE_PILOT:
        raise ConfirmationError(
            f"refusing live pilot: confirmation token must equal {CONFIRM_LIVE_PILOT!r}"
        )
    root = Path(root) if root else DEFAULT_LIVE_ROOT
    report = preflight(
        case_id,
        root,
        require_key=(client_factory is None),
        enforce_gitignore=enforce_gitignore,
        git_probe_fn=git_probe_fn,
    )
    if report.get("preflight") != "PASS":
        raise LivePreflightError(f"live pilot blocked: {report.get('preflight')}/{report.get('reason')}")
    if not resume:
        if root.exists() and any(root.iterdir()):
            raise FileExistsError(f"live root must be absent or empty for a new run: {root}")
    elif not root.exists():
        raise LivePilotError(f"resume requires an existing live root: {root}")
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)

    if client_factory is None:
        resolve_provider_credentials(dict(PROVIDER_CONFIG))

    case = next(c for c in R.load_cases() if c["case_id"] == case_id)
    spec = formal_runtime_spec()
    if timeout is None:
        timeout = float(spec["subprocess_timeout_seconds"])

    mapping_path = root / "condition_mapping.json"
    manifest_path = root / "pilot_manifest.json"
    summary_path = root / "live_pilot_summary.json"

    if resume:
        if not mapping_path.exists() or not manifest_path.exists():
            raise LivePilotError("resume requires existing 0600 mapping + pilot manifest; none found")
        _assert_private_file(mapping_path, root, 0o600)
        _assert_private_file(manifest_path, root, 0o600)
        mapping = validate_condition_mapping(json.loads(mapping_path.read_text(encoding="utf-8")))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("case_id") != case_id:
            raise LivePilotError("manifest case_id mismatch on resume")
        if manifest.get("stress_tag_sha") != STRESS_TAG_SHA:
            raise LivePilotError("manifest stress tag mismatch on resume")
        if manifest.get("commit") != report.get("head"):
            raise LivePilotError("manifest commit != current HEAD on resume")
        if manifest.get("live_tag_sha") != report.get("live_tag_sha"):
            raise LivePilotError("manifest live tag mismatch on resume")
        if _mapping_sha(mapping) != manifest.get("mapping_sha256"):
            raise LivePilotError("mapping SHA mismatch on resume; refusing")
        run_ids = manifest.get("runs", {})
        if set(run_ids.keys()) != set(R.CONDITIONS):
            raise LivePilotError("manifest must contain exactly A/B/C/D run_ids")
    else:
        if mapping_path.exists() or manifest_path.exists() or summary_path.exists():
            raise FileExistsError("live root already initialized; use --resume (refusing overwrite)")
        mapping = validate_condition_mapping(generate_random_condition_mapping())
        run_ids = {
            cond: f"LIVE-{case_id}-{cond}-{hashlib.sha256(os.urandom(8)).hexdigest()[:6]}"
            for cond in R.CONDITIONS
        }
        _atomic_write_text(mapping_path, json.dumps(mapping, ensure_ascii=False, indent=2), 0o600)
        manifest = {
            "execution_mode": EXECUTION_MODE,
            "case_id": case_id,
            "stress_tag": STRESS_TAG_NAME,
            "stress_tag_sha": STRESS_TAG_SHA,
            "live_tag": LIVE_PILOT_TAG_NAME,
            "live_tag_sha": report.get("live_tag_sha", ""),
            "commit": report.get("head", EXPECTED_HEAD),
            "max_turns": LIVE_MAX_TURNS,
            "mapping_mode": "LIVE_RANDOM_OPAQUE",
            "mapping_sha256": _mapping_sha(mapping),
            "runs": run_ids,
        }
        _atomic_write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2), 0o600)

    blinded_dir = _assert_under_root(root / "blinded", root)
    blinded_dir.mkdir(parents=True, exist_ok=True)
    run_summaries: List[Dict[str, Any]] = []

    for idx, cond in enumerate(R.CONDITIONS):
        run_id = run_ids[cond]
        config = build_live_config(cond, run_id)
        state_dir = _assert_under_root(root / "runs" / run_id / "isolated_state", root)
        state_exists = state_dir.exists()
        existing_records = A.load_records(state_dir) if state_exists else []
        already_done = resume and state_exists and _effective_termination(existing_records) in A.COMPLETED_TERMINATIONS
        resume_applied = bool(resume and state_exists and not already_done)
        if already_done:
            records = existing_records
        else:
            clear_session_cache()
            kwargs: Dict[str, Any] = {}
            if client_factory is not None:
                kwargs["client_factory"] = client_factory
            else:
                kwargs["provider_config"] = dict(PROVIDER_CONFIG)
            messages = list(case["pressure_turns"])
            if (not resume) and _test_only_first_messages is not None and idx == 0:
                messages = list(_test_only_first_messages)
            records = run_trajectory_subprocess(
                config=config,
                patient_id=f"live_{case_id.lower()}_{cond.lower()}",
                messages=messages,
                state_dir=state_dir,
                run_id=run_id,
                timeout=timeout,
                resume=resume_applied,
                research_patient_id=case_id,
                artifacts_dir=state_dir,
                **kwargs,
            )
        termination = _effective_termination(records)
        blinded_id = None
        blinded_error = None
        try:
            blinded = to_blinded_contract_trajectory(
                run_id, state_dir, mapping, require_completed=(termination in A.COMPLETED_TERMINATIONS)
            )
            payload = build_judge_payload(blinded)
            assert_no_leakage(payload)
            _scan_blinded(json.dumps(payload, ensure_ascii=False), mapping, run_id)
            _atomic_write_text(
                blinded_dir / f"{payload['blinded_run_id']}.json",
                json.dumps(payload, ensure_ascii=False, indent=2),
                0o644,
            )
            blinded_id = payload["blinded_run_id"]
        except LivePilotError:
            raise
        except Exception as exc:
            blinded_error = _scrub(str(exc))
        run_summaries.append(
            {
                "case_id": case_id,
                "condition": cond,
                "run_id": _scrub(run_id),
                "blinded_run_id": blinded_id,
                "blinded_error": blinded_error,
                "n_turns": len(records),
                "termination_reason": termination,
                "token_usage": _token_usage_total(records),
                "technical_error": _technical_error(records),
                "resume_applied": resume_applied,
                "skipped_completed": bool(already_done),
            }
        )
        if _interrupt_after_groups is not None and (idx + 1) >= _interrupt_after_groups:
            raise _TestInterrupt(f"test interrupt after {idx + 1} group(s)")

    completed = all(r["termination_reason"] in A.COMPLETED_TERMINATIONS for r in run_summaries)
    summary = {
        "execution_mode": EXECUTION_MODE,
        "exploratory": True,
        "non_preregistered": True,
        "pilot": True,
        "provider": "gemini",
        "live_api": client_factory is None,
        "live_tag": LIVE_PILOT_TAG_NAME,
        "live_tag_sha": report.get("live_tag_sha", ""),
        "stress_tag": STRESS_TAG_NAME,
        "stress_tag_sha": STRESS_TAG_SHA,
        "commit": report.get("head", EXPECTED_HEAD),
        "model": spec["talker_model"],
        "temperature": spec["talker_temperature"],
        "case_id": case_id,
        "max_turns": LIVE_MAX_TURNS,
        "n_conditions": len(R.CONDITIONS),
        "mapping_mode": "LIVE_RANDOM_OPAQUE",
        "mapping_sha256": _mapping_sha(mapping),
        "resume_used": resume,
        "runs": run_summaries,
        "n_completed": sum(1 for r in run_summaries if r["termination_reason"] in A.COMPLETED_TERMINATIONS),
        "completed": completed,
        "judge_used": False,
        "scanner_is_reviewer": False,
    }
    _atomic_write_text(summary_path, _scrub(json.dumps(summary, ensure_ascii=False, indent=2)), 0o600)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safety stress-test real-Gemini low-cost pilot")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--live-pilot", action="store_true")
    parser.add_argument("--case-id", default="SAFETY-RX-01")
    parser.add_argument("--root", default=None)
    parser.add_argument("--confirm-live-pilot", default=None)
    parser.add_argument("--resume", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.preflight:
        report = preflight(args.case_id, Path(args.root) if args.root else None)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("preflight") == "PASS" else 2
    summary = run_live_pilot(
        args.case_id,
        Path(args.root) if args.root else None,
        confirm=args.confirm_live_pilot,
        resume=args.resume,
    )
    print(json.dumps({"completed": summary["completed"], "runs": summary["runs"]}, ensure_ascii=False, indent=2))
    return 0 if summary["completed"] else 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
