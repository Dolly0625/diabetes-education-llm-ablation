"""Live Gemini judge pilot for the safety stress test (offline-safe by construction).

Evaluates the SAME live-pilot blinded A/B/C/D block (4 trajectories). Exploratory,
non-preregistered; NOT clinical validation and NOT part of the formal 12x4.
The keyword scanner is not a reviewer.

No network unless `--live-judge` is invoked with the confirmation token AND a real
GEMINI_API_KEY. `--preflight` is fully offline. Tests inject an evaluator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from llm_ablation_paper.workstream_5_judge_analysis.judge_runner import (
    CANONICAL_GEMINI_HOST,
    CANONICAL_JUDGE_MODEL,
    CANONICAL_JUDGE_TEMPERATURE,
    CANONICAL_RETRY_BACKOFFS,
    determine_consensus_failure_types,
    format_conversation_for_judge,
    is_transient_error,
    sanitize_error_message,
    validate_judge_evaluation_invariants,
    verify_canaries,
)
from llm_ablation_paper.workstream_5_judge_analysis.sanitizer import assert_no_leakage, build_judge_payload

from llm_ablation_paper.safety_stress_test import analysis as A
from llm_ablation_paper.safety_stress_test import live_runner as L
from llm_ablation_paper.safety_stress_test import runner as R

SST_DIR = Path(__file__).resolve().parent
REPO_ROOT = SST_DIR.parents[1]
CANARY_PATH = REPO_ROOT / "llm_ablation_paper" / "workstream_5_judge_analysis" / "canary_trajectories.jsonl"
JUDGE_PROMPT_PATH = REPO_ROOT / "llm_ablation_paper" / "workstream_5_judge_analysis" / "judge_prompt.md"

CONFIRM_LIVE_JUDGE = "I_CONFIRM_SAFETY_STRESS_LIVE_JUDGE"
JUDGE_TAG_NAME = "llm-ablation-safety-live-judge-pilot-v1"
LIVE_PILOT_TAG_NAME = L.LIVE_PILOT_TAG_NAME
EXPECTED_LIVE_SHA = "b63f9997f00cdc5569950d5f5c88e7f0309b7b3e"
STRESS_TAG_SHA = "f5fc9b6a8746f934e30bdb2fe3f866c0a631e9ac"
JUDGE_MODEL = CANONICAL_JUDGE_MODEL
JUDGE_TEMPERATURE = CANONICAL_JUDGE_TEMPERATURE
DEFAULT_STATE_DIR = SST_DIR / "artifacts" / "live_judge_pilot"
SECRET_RE = re.compile(r"(AIza[0-9A-Za-z_\-]{6,}|api[_-]?key\s*[:=]\s*\S+|bearer\s+[A-Za-z0-9._\-]+)", re.IGNORECASE)
SCORE_KEYS = ("safety", "tool_use", "state_consistency", "dialogue_planning", "helpfulness")
TURN_KEYS = {"turn", "patient_text", "tools_exposed", "tools_called", "final_output"}


class JudgePilotError(RuntimeError):
    pass


class JudgePreflightError(JudgePilotError):
    pass


class JudgeConfirmationError(JudgePilotError):
    pass


def _scrub(text: str) -> str:
    return SECRET_RE.sub("[REDACTED]", str(text))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping_sha(mapping: Dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(mapping, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def git_probe() -> Dict[str, Any]:
    def _run(args: List[str]) -> str:
        return subprocess.check_output(args, cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL).decode().strip()

    def _sha(ref: str) -> str:
        try:
            return _run(["git", "rev-list", "-n1", ref])
        except subprocess.CalledProcessError:
            return ""

    def _type(ref: str) -> str:
        try:
            return _run(["git", "cat-file", "-t", ref])
        except subprocess.CalledProcessError:
            return ""

    head = _run(["git", "rev-parse", "HEAD"])
    dirty = bool(_run(["git", "status", "--porcelain"]))
    judge_tag_sha = _sha(JUDGE_TAG_NAME)
    judge_tag_type = _type(JUDGE_TAG_NAME)
    live_pilot_tag_sha = _sha(LIVE_PILOT_TAG_NAME)
    try:
        subprocess.check_call(["git", "merge-base", "--is-ancestor", LIVE_PILOT_TAG_NAME, "HEAD"],
                              cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL)
        live_is_ancestor = True
    except subprocess.CalledProcessError:
        live_is_ancestor = False
    try:
        changed = [p for p in _run(["git", "diff", "--name-only", LIVE_PILOT_TAG_NAME, "HEAD"]).splitlines() if p]
    except subprocess.CalledProcessError:
        changed = ["<diff-vs-tag-failed>"]
    return {
        "head": head,
        "dirty": dirty,
        "judge_tag_sha": judge_tag_sha,
        "judge_tag_type": judge_tag_type,
        "live_pilot_tag_sha": live_pilot_tag_sha,
        "live_is_ancestor": live_is_ancestor,
        "changed_vs_tag": changed,
    }


def _assert_endpoint(endpoint: str) -> str:
    import urllib.parse

    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme != "https":
        raise JudgePreflightError("judge endpoint violates scheme policy (https required)")
    if parsed.username or parsed.password:
        raise JudgePreflightError("judge endpoint violates policy (userinfo not allowed)")
    if parsed.query:
        raise JudgePreflightError("judge endpoint violates policy (query not allowed)")
    if parsed.fragment:
        raise JudgePreflightError("judge endpoint violates policy (fragment not allowed)")
    host = (parsed.hostname or "").lower()
    if host != CANONICAL_GEMINI_HOST and not host.endswith("." + CANONICAL_GEMINI_HOST):
        raise JudgePreflightError("judge endpoint violates policy (host not allowed)")
    return host


def _assert_no_secret(obj: Any) -> None:
    dumped = json.dumps(obj, ensure_ascii=False)
    if SECRET_RE.search(dumped):
        raise JudgePilotError("secret-like content detected in judge output; refusing to persist (fail-closed)")


def assert_judge_provider_ready() -> str:
    key = (os.environ.get("GEMINI_API_KEY", "") or "").strip()
    if not key:
        raise JudgePreflightError("GEMINI_API_KEY is not set; live judge blocked (fail-closed)")
    endpoint = (os.environ.get("GEMINI_BASE_URL", "") or "https://generativelanguage.googleapis.com/v1beta/openai/").strip()
    return _assert_endpoint(endpoint)


class GeminiJudgeEvaluator:
    """Gemini judge call appending provider usage to an append-only ledger per call.

    Usage is recorded immediately after a provider response is received (before any
    schema validation), so charged-but-invalid calls and retries are never lost.
    """

    def __init__(self) -> None:
        self.usage_ledger: List[Dict[str, Any]] = []

    def _record_usage(self, judge_run_id: str, usage: Any) -> None:
        pt = getattr(usage, "prompt_tokens", None)
        ct = getattr(usage, "completion_tokens", None)
        tt = getattr(usage, "total_tokens", None)
        self.usage_ledger.append({
            "judge_run_id": judge_run_id,
            "prompt_tokens": pt if isinstance(pt, int) else None,
            "completion_tokens": ct if isinstance(ct, int) else None,
            "total_tokens": tt if isinstance(tt, int) else None,
        })

    def __call__(self, sanitized_payload: Dict[str, Any], judge_run_id: str) -> Tuple[str, Dict[str, Any]]:
        key = (os.environ.get("GEMINI_API_KEY", "") or "").strip()
        if not key:
            raise JudgePreflightError("GEMINI_API_KEY is not set; live judge blocked (fail-closed)")
        endpoint = (os.environ.get("GEMINI_BASE_URL", "") or "https://generativelanguage.googleapis.com/v1beta/openai/").strip()
        _assert_endpoint(endpoint)

        from openai import OpenAI

        client = OpenAI(api_key=key, base_url=endpoint)
        system_instruction = JUDGE_PROMPT_PATH.read_text(encoding="utf-8") if JUDGE_PROMPT_PATH.exists() else "You are an LLM Judge."
        response = client.chat.completions.create(
            model=JUDGE_MODEL,
            temperature=JUDGE_TEMPERATURE,
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": format_conversation_for_judge(sanitized_payload)},
            ],
            response_format={"type": "json_object"},
        )
        self._record_usage(judge_run_id, getattr(response, "usage", None))
        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        parsed["judge_run_id"] = judge_run_id
        parsed["blinded_run_id"] = sanitized_payload.get("blinded_run_id")
        return raw, parsed


def _drain_usage(evaluator: Any, cursor: int) -> Tuple[List[Dict[str, Any]], int]:
    ledger = getattr(evaluator, "usage_ledger", None)
    if not isinstance(ledger, list):
        return [], cursor
    new = list(ledger[cursor:])
    return new, len(ledger)


def _record_usage_calls(ckpt: Dict[str, Any], entries: List[Dict[str, Any]], stage: str, phase: Optional[str],
                        blinded_id: Optional[str]) -> None:
    calls = ckpt.setdefault("usage_ledger", [])
    for entry in entries:
        rec = {
            "call_index": len(calls),
            "stage": stage,
            "phase": phase,
            "blinded_run_id": blinded_id,
            "judge_run_id": entry.get("judge_run_id"),
            "prompt_tokens": entry.get("prompt_tokens"),
            "completion_tokens": entry.get("completion_tokens"),
            "total_tokens": entry.get("total_tokens"),
        }
        calls.append(rec)


def _execute_with_usage(evaluator, sanitized_payload, judge_run_id, backoffs, stage, phase, blinded_id, ckpt, cursor_box):
    expected = str(sanitized_payload.get("blinded_run_id"))
    history: List[Dict[str, Any]] = []
    last: Optional[Exception] = None
    max_attempts = len(backoffs) + 1
    for attempt in range(max_attempts):
        try:
            raw, parsed = evaluator(sanitized_payload, judge_run_id)
        except Exception as exc:  # charged call may still be recorded by the evaluator
            entries, cursor_box["v"] = _drain_usage(evaluator, cursor_box["v"])
            _record_usage_calls(ckpt, entries, stage, phase, blinded_id)
            last = exc
            transient = is_transient_error(exc)
            history.append({
                "attempt": attempt + 1,
                "error_type": type(exc).__name__,
                "sanitized_message": sanitize_error_message(str(exc)),
                "is_transient": transient,
            })
            if not transient:
                raise JudgePilotError(f"non-transient judge failure: {sanitize_error_message(str(exc))}") from exc
            if attempt < len(backoffs):
                import time

                time.sleep(backoffs[attempt])
            continue
        entries, cursor_box["v"] = _drain_usage(evaluator, cursor_box["v"])
        _record_usage_calls(ckpt, entries, stage, phase, blinded_id)
        try:
            validate_judge_evaluation_invariants(parsed, sanitized_payload, judge_run_id, expected)
            return raw, parsed, history
        except Exception as exc:
            last = exc
            transient = is_transient_error(exc)
            history.append({
                "attempt": attempt + 1,
                "error_type": type(exc).__name__,
                "sanitized_message": sanitize_error_message(str(exc)),
                "is_transient": transient,
            })
            if not transient:
                raise JudgePilotError(f"non-transient judge failure: {sanitize_error_message(str(exc))}") from exc
            if attempt < len(backoffs):
                import time

                time.sleep(backoffs[attempt])
    raise JudgePilotError(f"judge failed after {max_attempts} attempts: {sanitize_error_message(str(last))}")


def _assert_state_dir_private(state_dir: Path) -> None:
    p = Path(state_dir)
    if p.is_symlink():
        raise JudgePilotError(f"state dir must not be a symlink: {p}")
    if not p.exists() or not p.is_dir():
        raise JudgePilotError(f"state dir missing or not a directory: {p}")
    mode = p.stat().st_mode
    if not os.path.isdir(p) or os.path.islink(p):
        raise JudgePilotError(f"state dir must be a real directory: {p}")
    actual = mode & 0o777
    if actual != 0o700:
        raise JudgePilotError(f"state dir mode {oct(actual)} != 0o700: {p}")


def _assert_private_file(path: Path, root: Path, mode: int = 0o600) -> None:
    try:
        L._assert_private_file(path, root, mode)
    except L.LivePilotError as exc:
        raise JudgePilotError(str(exc)) from exc


def load_source_block(block_root: Path) -> Dict[str, Any]:
    block_root = Path(block_root)
    summary_path = block_root / "live_pilot_summary.json"
    manifest_path = block_root / "pilot_manifest.json"
    mapping_path = block_root / "condition_mapping.json"
    for p in (summary_path, manifest_path):
        _assert_private_file(p, block_root, 0o600)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    _assert_private_file(mapping_path, block_root, 0o600)
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    if set(mapping.keys()) != {"A", "B", "C", "D"}:
        raise JudgePreflightError("source mapping must contain exactly A/B/C/D")
    if len(set(mapping.values())) != 4:
        raise JudgePreflightError("source mapping values must be unique")
    for value in mapping.values():
        if not isinstance(value, str) or not re.match(r"^COND-[0-9A-F]{8}$", value):
            raise JudgePreflightError(f"source mapping value format invalid: {value!r}")
    mapping_sha = _mapping_sha(mapping)
    if mapping_sha != summary.get("mapping_sha256") or mapping_sha != manifest.get("mapping_sha256"):
        raise JudgePreflightError("source mapping SHA mismatch vs summary/manifest")

    if summary.get("completed") is not True:
        raise JudgePreflightError("source live pilot is not completed")
    if summary.get("live_tag_sha") != EXPECTED_LIVE_SHA or summary.get("commit") != EXPECTED_LIVE_SHA:
        raise JudgePreflightError("source live tag/commit mismatch")
    if summary.get("stress_tag_sha") != STRESS_TAG_SHA:
        raise JudgePreflightError("source stress tag mismatch")

    runs = summary.get("runs", [])
    conditions = sorted(r.get("condition") for r in runs)
    if conditions != ["A", "B", "C", "D"]:
        raise JudgePreflightError(f"source block must contain exactly A/B/C/D once, got {conditions}")

    raw_run_ids = [str(r.get("run_id", "")) for r in runs]
    if len(set(raw_run_ids)) != 4 or any(not x for x in raw_run_ids):
        raise JudgePreflightError("source run_ids must be four unique non-empty values")

    blinded_dir = block_root / "blinded"
    payloads: Dict[str, Dict[str, Any]] = {}
    file_hashes: Dict[str, str] = {}
    patient_ids = set()
    for run in runs:
        if run.get("blinded_error"):
            raise JudgePreflightError(f"blinded export error present for {run.get('condition')}")
        if run.get("termination_reason") not in A.COMPLETED_TERMINATIONS:
            raise JudgePreflightError(f"run not completed: {run.get('condition')}")
        bid = run.get("blinded_run_id")
        if not bid:
            raise JudgePreflightError("missing blinded_run_id in summary")
        path = blinded_dir / f"{bid}.json"
        _assert_source_regular(path)
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
        assert_no_leakage(payload)
        if set(payload.keys()) != {"blinded_run_id", "patient_id", "turns"}:
            raise JudgePreflightError(f"payload top-level keys must be exactly the blinded contract: {sorted(payload.keys())}")
        if not payload.get("patient_id"):
            raise JudgePreflightError(f"empty patient_id in {bid}")
        if payload.get("blinded_run_id") != bid:
            raise JudgePreflightError(f"blinded_run_id mismatch in {bid}")
        if not re.match(r"^BLIND-[0-9a-f]{8}$", str(bid)):
            raise JudgePreflightError(f"non-opaque blinded id: {bid}")
        turns = payload.get("turns", [])
        if len(turns) != L.LIVE_MAX_TURNS:
            raise JudgePreflightError(f"expected {L.LIVE_MAX_TURNS} turns in {bid}, got {len(turns)}")
        for idx, t in enumerate(turns, start=1):
            if set(t.keys()) != TURN_KEYS:
                raise JudgePreflightError(f"turn keys must be exactly {sorted(TURN_KEYS)} in {bid}")
            if t.get("turn") != idx:
                raise JudgePreflightError(f"turn numbering must be 1..{L.LIVE_MAX_TURNS} in {bid}")
            if not isinstance(t.get("patient_text"), str) or not isinstance(t.get("final_output"), str):
                raise JudgePreflightError(f"non-string text in {bid} turn {idx}")
        patient_ids.add(payload.get("patient_id"))
        payloads[bid] = payload
        file_hashes[bid] = _sha256_file(path)
    if len(payloads) != 4:
        raise JudgePreflightError("blinded ids must be unique across the four runs")
    if len(patient_ids) != 1:
        raise JudgePreflightError("all blinded payloads must share one patient_id")

    for bid, payload in payloads.items():
        _scan_payload(json.dumps(payload, ensure_ascii=False), raw_run_ids)

    block_sha = hashlib.sha256(
        json.dumps({k: file_hashes[k] for k in sorted(file_hashes)}, sort_keys=True).encode()
    ).hexdigest()
    return {
        "summary": summary,
        "manifest": manifest,
        "payloads": payloads,
        "file_hashes": file_hashes,
        "raw_run_ids": raw_run_ids,
        "block_sha256": block_sha,
        "mapping_sha256": mapping_sha,
        "condition_of": {r["blinded_run_id"]: r["condition"] for r in runs},
    }


def _assert_source_regular(path: Path) -> None:
    if path.is_symlink():
        raise JudgePreflightError(f"source file must not be a symlink: {path}")
    if not path.exists() or not path.is_file():
        raise JudgePreflightError(f"source file missing or not regular: {path}")


def _scan_payload(text: str, raw_run_ids: List[str]) -> None:
    lowered = text.lower()
    hits = []
    for token in ("enable_", "condition_secret", "raw_talker", "guard_action", "planner_state", "cond-"):
        if token in lowered:
            hits.append(token)
    for rid in raw_run_ids:
        if rid and rid.lower() in lowered:
            hits.append(rid)
    if re.search(r"[\"']condition[\"']\s*:\s*[\"'][abcd][\"']", lowered):
        hits.append("condition-key")
    if hits:
        raise JudgePreflightError(f"payload leakage: {sorted(set(hits))}")


def preflight(
    block_root: Path,
    state_dir: Optional[Path] = None,
    *,
    require_key: bool = True,
    enforce_gitignore: bool = True,
    git_probe_fn: Callable[[], Dict[str, Any]] = git_probe,
) -> Dict[str, Any]:
    block_root = Path(block_root)
    state_dir = Path(state_dir) if state_dir else DEFAULT_STATE_DIR

    probe = git_probe_fn()
    if probe.get("live_pilot_tag_sha") != EXPECTED_LIVE_SHA:
        raise JudgePreflightError("live pilot tag did not peel to the expected SHA")
    if probe["dirty"]:
        raise JudgePreflightError("worktree is dirty; refusing live judge")
    outside = [p for p in probe.get("changed_vs_tag", []) if not p.startswith("llm_ablation_paper/safety_stress_test/")]
    if outside:
        raise JudgePreflightError(f"changes outside safety_stress_test/: {outside}")

    R.verify_frozen_fingerprints()
    R.unique_difference_report()
    block = load_source_block(block_root)
    if enforce_gitignore and not L._is_gitignored(state_dir / "probe"):
        raise JudgePreflightError(f"judge state dir is not gitignored: {state_dir}")

    judge_tag_sha = probe.get("judge_tag_sha", "")
    judge_tag_type = probe.get("judge_tag_type", "")
    if not judge_tag_sha:
        status, reason = "BLOCKED", "NOT_FROZEN"
    elif judge_tag_type != "tag":
        status, reason = "BLOCKED", "JUDGE_TAG_NOT_ANNOTATED"
    elif probe["head"] != judge_tag_sha:
        status, reason = "BLOCKED", "HEAD_NOT_JUDGE_TAG"
    elif not probe.get("live_is_ancestor"):
        status, reason = "BLOCKED", "LIVE_PILOT_TAG_NOT_ANCESTOR"
    else:
        status, reason = "PASS", ""
    if status == "PASS" and require_key:
        assert_judge_provider_ready()

    return {
        "preflight": status,
        "reason": reason,
        "mode": "offline",
        "block_root": str(block_root),
        "head": probe["head"],
        "judge_tag": JUDGE_TAG_NAME,
        "judge_tag_sha": judge_tag_sha,
        "live_pilot_tag_sha": probe.get("live_pilot_tag_sha"),
        "judge_model": JUDGE_MODEL,
        "judge_temperature": JUDGE_TEMPERATURE,
        "block_sha256": block["block_sha256"],
        "n_blinded": len(block["payloads"]),
    }


def _load_or_init_checkpoint(state_dir: Path, block: Dict[str, Any], resume: bool) -> Dict[str, Any]:
    ckpt_path = state_dir / "judge_checkpoint.json"
    if resume:
        _assert_state_dir_private(state_dir)
        _assert_private_file(ckpt_path, state_dir, 0o600)
        raw_dir = state_dir / "raw"
        if raw_dir.exists():
            for f in raw_dir.iterdir():
                _assert_private_file(f, state_dir, 0o600)
        ckpt = json.loads(ckpt_path.read_text(encoding="utf-8"))
        if ckpt.get("block_sha256") != block["block_sha256"]:
            raise JudgePilotError("checkpoint block hash mismatch on resume; refusing")
        if ckpt.get("mapping_sha256") != block["mapping_sha256"]:
            raise JudgePilotError("checkpoint mapping SHA mismatch on resume; refusing")
        if ckpt.get("file_hashes") != block["file_hashes"]:
            raise JudgePilotError("checkpoint file hashes mismatch on resume; refusing")
        return ckpt
    if state_dir.exists():
        if state_dir.is_symlink():
            raise JudgePilotError(f"state dir must not be a symlink: {state_dir}")
        if any(state_dir.iterdir()):
            raise FileExistsError(f"judge state dir must be absent or empty for a new run: {state_dir}")
    state_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(state_dir, 0o700)
    return {
        "schema": "sst-live-judge-v1",
        "anchored": True,
        "block_sha256": block["block_sha256"],
        "mapping_sha256": block["mapping_sha256"],
        "file_hashes": dict(block["file_hashes"]),
        "trajectories": {},
        "usage_ledger": [],
    }


def _save_checkpoint(state_dir: Path, ckpt: Dict[str, Any]) -> None:
    L._atomic_write_text(state_dir / "judge_checkpoint.json", json.dumps(ckpt, ensure_ascii=False, indent=2), 0o600)


def _judge_phase(state_dir, ckpt, blinded_id, phase, judge_run_id, payload, evaluator, backoffs, raw_ids, cursor_box) -> Dict[str, Any]:
    rec = ckpt["trajectories"].setdefault(blinded_id, {})
    if phase in rec:
        return rec[phase]
    try:
        raw, parsed, retry = _execute_with_usage(
            evaluator, payload, judge_run_id, backoffs, "trajectory", phase, blinded_id, ckpt, cursor_box
        )
    finally:
        _save_checkpoint(state_dir, ckpt)
    _assert_no_secret({"raw": raw, "parsed": parsed, "retry": retry})
    rec[phase] = {"raw": _scrub(raw), "parsed": parsed, "retry": retry}
    _scan_payload(json.dumps(rec[phase], ensure_ascii=False), raw_ids)
    L._atomic_write_text(state_dir / "raw" / f"{blinded_id}-{phase}.json",
                         json.dumps(rec[phase], ensure_ascii=False, indent=2), 0o600)
    _save_checkpoint(state_dir, ckpt)
    return rec[phase]


def _judge_trajectory(state_dir, ckpt, blinded_id, payload, evaluator, backoffs, raw_ids, cursor_box) -> Dict[str, Any]:
    r1 = _judge_phase(state_dir, ckpt, blinded_id, "r1", f"JUDGE-R1-{blinded_id}", payload, evaluator, backoffs, raw_ids, cursor_box)
    r2 = _judge_phase(state_dir, ckpt, blinded_id, "r2", f"JUDGE-R2-{blinded_id}", payload, evaluator, backoffs, raw_ids, cursor_box)
    evals = [r1["parsed"], r2["parsed"]]
    cf1 = bool(r1["parsed"]["critical_failure"])
    cf2 = bool(r2["parsed"]["critical_failure"])
    if cf1 != cf2:
        r3 = _judge_phase(state_dir, ckpt, blinded_id, "r3", f"JUDGE-R3-TIEBREAK-{blinded_id}", payload, evaluator, backoffs, raw_ids, cursor_box)
        evals.append(r3["parsed"])
        final_cf = (int(cf1) + int(cf2) + int(bool(r3["parsed"]["critical_failure"]))) >= 2
    else:
        final_cf = cf1
    ftypes = determine_consensus_failure_types(final_cf, evals)
    scores = {k: sum(e["scores"][k] for e in evals) / len(evals) for k in SCORE_KEYS}
    total_tokens = 0
    seen_tokens = False
    for call in ckpt.get("usage_ledger", []):
        if call.get("blinded_run_id") == blinded_id and isinstance(call.get("total_tokens"), int):
            total_tokens += call["total_tokens"]
            seen_tokens = True
    return {
        "blinded_run_id": blinded_id,
        "critical_failure": bool(final_cf),
        "failure_types": ftypes,
        "scores": scores,
        "n_judge_runs": len(evals),
        "phases": [p for p in ("r1", "r2", "r3") if p in ckpt["trajectories"].get(blinded_id, {})],
        "total_tokens": total_tokens if seen_tokens else None,
    }


def render_judge_result_md(block: Dict[str, Any], judged: List[Dict[str, Any]], out_path: Path) -> None:
    lines = []
    lines.append("# Live Judge Pilot RESULT（探索性、非預先註冊）\n")
    lines.append(f"> 對 `{block['summary'].get('case_id')}` 之同一病患 A/B/C/D 四份 blinded 軌跡進行**同模型兩次隔離重複裁決（repeated evaluations）**（非兩位獨立評審、非人類評審一致性）。")
    lines.append("> 單病例、探索性 pilot，**不是**論文效果結論，**不是**臨床驗證；關鍵字 scanner 不是 ground truth。\n")
    lines.append(f"- source live tag: `{LIVE_PILOT_TAG_NAME}` @ `{EXPECTED_LIVE_SHA}`")
    lines.append(f"- judge model: `{JUDGE_MODEL}` temperature `{JUDGE_TEMPERATURE}`")
    lines.append(f"- source block sha256（首次錨定，非事前凍結）: `{block['block_sha256']}`")
    lines.append("")
    lines.append("| condition | blinded_run_id | critical_failure | failure_types | n_runs |")
    lines.append("|---|---|---|---|---|")
    cond_of = block["condition_of"]
    for row in judged:
        lines.append(f"| {cond_of.get(row['blinded_run_id'],'?')} | {row['blinded_run_id']} | "
                     f"{row['critical_failure']} | {row['failure_types']} | {row['n_judge_runs']} |")
    lines.append("")
    lines.append("## 邊界\n")
    lines.append("- 事後探索性、非預先註冊；單病例；association not causation。")
    lines.append("- `zero observed` 不代表零風險；Judge 非醫師；不可作臨床或論文效果主張。")
    lines.append("- 不得將本 pilot 結果混入正式 12×4；不得改寫 frozen v1 主指標。")
    L._atomic_write_text(out_path, "\n".join(lines) + "\n", 0o600)


def run_judge_pilot(
    block_root: Path,
    state_dir: Optional[Path] = None,
    *,
    confirm: Optional[str] = None,
    evaluator: Optional[Any] = None,
    resume: bool = False,
    enforce_gitignore: bool = True,
    git_probe_fn: Callable[[], Dict[str, Any]] = git_probe,
    backoffs: Optional[List[float]] = None,
) -> Dict[str, Any]:
    if confirm != CONFIRM_LIVE_JUDGE:
        raise JudgeConfirmationError(f"refusing live judge: confirmation token must equal {CONFIRM_LIVE_JUDGE!r}")
    block_root = Path(block_root)
    state_dir = Path(state_dir) if state_dir else DEFAULT_STATE_DIR
    apply_evaluator = evaluator if evaluator is not None else GeminiJudgeEvaluator()
    report = preflight(block_root, state_dir, require_key=(evaluator is None),
                       enforce_gitignore=enforce_gitignore, git_probe_fn=git_probe_fn)
    if report.get("preflight") != "PASS":
        raise JudgePreflightError(f"live judge blocked: {report.get('preflight')}/{report.get('reason')}")

    block = load_source_block(block_root)
    ckpt = _load_or_init_checkpoint(state_dir, block, resume)
    if not resume:
        ckpt.setdefault("canary_passed", False)
        _save_checkpoint(state_dir, ckpt)
    cursor_box = {"v": 0}
    if not ckpt.get("canary_passed"):
        try:
            verify_canaries(CANARY_PATH, apply_evaluator)
        except Exception as exc:
            entries, cursor_box["v"] = _drain_usage(apply_evaluator, cursor_box["v"])
            _record_usage_calls(ckpt, entries, "canary", None, None)
            ckpt["canary_passed"] = False
            ckpt["canary_error"] = {"type": type(exc).__name__, "message": sanitize_error_message(str(exc))}
            _save_checkpoint(state_dir, ckpt)
            raise
        entries, cursor_box["v"] = _drain_usage(apply_evaluator, cursor_box["v"])
        _record_usage_calls(ckpt, entries, "canary", None, None)
        ckpt["canary_passed"] = True
        ckpt.pop("canary_error", None)
        _save_checkpoint(state_dir, ckpt)
    raw_ids = list(block["raw_run_ids"])
    backoffs = backoffs if backoffs is not None else list(CANONICAL_RETRY_BACKOFFS)
    judged = [_judge_trajectory(state_dir, ckpt, bid, block["payloads"][bid], apply_evaluator, backoffs, raw_ids, cursor_box)
              for bid in sorted(block["payloads"])]

    ledger = ckpt.get("usage_ledger", [])
    canary_tokens = sum(c["total_tokens"] for c in ledger if c.get("stage") == "canary" and isinstance(c.get("total_tokens"), int))
    trajectory_tokens = sum(c["total_tokens"] for c in ledger if c.get("stage") == "trajectory" and isinstance(c.get("total_tokens"), int))
    total_tokens = canary_tokens + trajectory_tokens
    summary = {
        "execution_mode": "safety_stress_live_judge",
        "exploratory": True,
        "non_preregistered": True,
        "judge_model": JUDGE_MODEL,
        "judge_temperature": JUDGE_TEMPERATURE,
        "evaluator_model_runs_same_model": True,
        "evaluation_semantics": "repeated evaluations (same model, isolated calls); NOT independent human raters",
        "source_live_tag": LIVE_PILOT_TAG_NAME,
        "source_live_sha": EXPECTED_LIVE_SHA,
        "block_sha256": block["block_sha256"],
        "mapping_sha256": block["mapping_sha256"],
        "n_judged": len(judged),
        "canary_tokens": canary_tokens or None,
        "trajectory_tokens": trajectory_tokens or None,
        "total_tokens": total_tokens or None,
        "usage_calls": len(ledger),
        "judged": judged,
        "scanner_is_ground_truth": False,
    }
    L._atomic_write_text(state_dir / "judge_summary.json", _scrub(json.dumps(summary, ensure_ascii=False, indent=2)), 0o600)
    L._atomic_write_text(state_dir / "judged.json", json.dumps(judged, ensure_ascii=False, indent=2), 0o600)
    render_judge_result_md(block, judged, state_dir / "JUDGE_RESULT.md")
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safety stress-test live judge pilot")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--live-judge", action="store_true")
    parser.add_argument("--block-root", required=True)
    parser.add_argument("--state-dir", default=None)
    parser.add_argument("--confirm-live-judge", default=None)
    parser.add_argument("--resume", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    state_dir = Path(args.state_dir) if args.state_dir else None
    if args.preflight:
        report = preflight(Path(args.block_root), state_dir)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("preflight") == "PASS" else 2
    summary = run_judge_pilot(Path(args.block_root), state_dir,
                              confirm=args.confirm_live_judge, resume=args.resume)
    print(json.dumps({"n_judged": summary["n_judged"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
