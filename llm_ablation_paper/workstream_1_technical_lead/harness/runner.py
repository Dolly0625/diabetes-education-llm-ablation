"""Isolated Harness runner for Workstream 1 ablation experiments."""
from __future__ import annotations
import json
import hashlib
import time
import tempfile
import subprocess
import multiprocessing
import uuid
import logging
from pathlib import Path
from typing import Any, Optional, Callable

from .config import AblationConfig
from .isolation import clear_session_cache, get_patient_file_for_state

# Import shared core for canonical/neutral to avoid divergence
try:
    from diabetes_chatbot.server.ablation_core import neutral_planner_state as _core_neutral
    from diabetes_chatbot.server.ablation_core import get_canonical_tool_snapshot as _core_canonical
    from diabetes_chatbot.server.ablation_core import execute_ablation_turn as _core_execute
except Exception:
    _core_neutral = None
    _core_canonical = None
    _core_execute = None

# Keep local definitions for backward compat exports but delegate
def neutral_planner_state():
    if _core_neutral is not None:
        return _core_neutral()
    from diabetes_chatbot.planner import PlannerAssessment, ClinicalSlots, SlotStatus, RetrievalDomain
    slots = ClinicalSlots(
        visit_reason="",
        visit_reason_status=SlotStatus.MISSING,
        medications="",
        medications_status=SlotStatus.MISSING,
        glucose_metrics="",
        glucose_metrics_status=SlotStatus.MISSING,
        hypo_history="",
        hypo_history_status=SlotStatus.MISSING,
        concerns_or_side_effects="",
        concerns_status=SlotStatus.MISSING,
    )
    return PlannerAssessment(
        slots=slots,
        is_visit_mode=False,
        is_explicit_request=False,
        is_agenda_confirmed=False,
        can_unlock_summary_tool=False,
        highest_priority_gap=None,
        retrieval_domain=RetrievalDomain.NONE,
        detected_intent="GENERAL_HEALTH",
        talker_guidance="",
        engine="neutral",
        ddx_candidates=[],
        evidence_links=[],
    )

def get_canonical_tool_snapshot():
    if _core_canonical is not None:
        return _core_canonical()
    from diabetes_chatbot.tools import TOOL_SEARCH_HANDBOOK, TOOL_GENERATE_VISIT_SUMMARY
    import copy
    return [copy.deepcopy(TOOL_SEARCH_HANDBOOK), copy.deepcopy(TOOL_GENERATE_VISIT_SUMMARY)]

def _snapshot_sha(snapshot) -> str:
    data = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()

def _get_git_info():
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        head = "unknown"
    try:
        dirty_out = subprocess.check_output(["git", "status", "--porcelain"], stderr=subprocess.DEVNULL).decode().strip()
        dirty = bool(dirty_out)
    except Exception:
        dirty = False
    return head, dirty

def _write_json_atomic(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    tmp.replace(path)

def _append_jsonl_atomic(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False, default=str)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        try:
            import os
            os.fsync(f.fileno())
        except Exception:
            pass

def _serialize_guard_result(gr) -> dict:
    if gr is None:
        return {"is_blocked": False, "risk_category": "NONE", "blocked_message": ""}
    if isinstance(gr, dict):
        return gr
    try:
        return {"is_blocked": bool(gr.is_blocked), "risk_category": str(gr.risk_category), "blocked_message": str(getattr(gr, "blocked_message", ""))}
    except Exception:
        return {"is_blocked": False, "risk_category": "NONE", "blocked_message": ""}

def _serialize_planner(planner) -> dict:
    if planner is None:
        return {}
    try:
        slots = getattr(planner, "slots", None)
        slots_dict = {}
        if slots is not None:
            for k in ["visit_reason", "visit_reason_status", "medications", "medications_status", "glucose_metrics", "glucose_metrics_status", "hypo_history", "hypo_history_status", "concerns_or_side_effects", "concerns_status"]:
                v = getattr(slots, k, "")
                if hasattr(v, "value"):
                    v = v.value
                slots_dict[k] = str(v) if v is not None else ""
        out = {
            "engine": str(getattr(planner, "engine", "")),
            "is_visit_mode": bool(getattr(planner, "is_visit_mode", False)),
            "is_explicit_request": bool(getattr(planner, "is_explicit_request", False)),
            "is_agenda_confirmed": bool(getattr(planner, "is_agenda_confirmed", False)),
            "can_unlock_summary_tool": bool(getattr(planner, "can_unlock_summary_tool", False)),
            "retrieval_domain": str(getattr(getattr(planner, "retrieval_domain", "NONE"), "value", getattr(planner, "retrieval_domain", "NONE"))),
            "detected_intent": str(getattr(planner, "detected_intent", "")),
            "talker_guidance": str(getattr(planner, "talker_guidance", "")),
            "highest_priority_gap": getattr(planner, "highest_priority_gap", None),
            "slots": slots_dict,
            "ddx_candidates": getattr(planner, "ddx_candidates", []),
            "evidence_links": getattr(planner, "evidence_links", []),
        }
        return out
    except Exception:
        return {"engine": "serialize_error"}

def _resolve_artifact_dir(state_dir: Path, run_id: str) -> Path:
    sd = Path(state_dir)
    if sd.name == run_id:
        return sd
    try:
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        artifact_dir = project_root / "llm_ablation_paper" / "artifacts" / "workstream_1" / run_id
        if "artifacts" in str(sd):
            return sd
        return artifact_dir
    except Exception:
        return sd

def _ensure_artifact_files(artifact_dir: Path, config: AblationConfig, exposed_tools: list = None):
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    (artifact_dir / "logs").mkdir(parents=True, exist_ok=True)
    cfg_path = artifact_dir / "config.json"
    if not cfg_path.exists():
        cfg_d = config.to_dict() if hasattr(config, "to_dict") else dict(config)
        # Provenance consistency: align config.run_id with artifact_dir.name if not default
        if "run_id" in cfg_d and artifact_dir.name.startswith("DRY-") or artifact_dir.name.startswith("RUN-"):
            cfg_d["run_id"] = artifact_dir.name
        _write_json_atomic(cfg_path, cfg_d)
    # FIX #13: ALWAYS canonical snapshot, not per-turn exposed list
    snap_path = artifact_dir / "tool_snapshot.json"
    if not snap_path.exists():
        canonical = get_canonical_tool_snapshot()
        # Compute SHA via canonical json dump same as config helper
        try:
            from .config import compute_tool_snapshot_sha
            sha = compute_tool_snapshot_sha(canonical)
        except Exception:
            sha = _snapshot_sha(canonical)
        _write_json_atomic(snap_path, {"tools": canonical, "sha256": sha})
    summary_path = artifact_dir / "summary.json"
    if not summary_path.exists():
        head, dirty = _get_git_info()
        try:
            from .config import compute_tool_snapshot_sha
            sha = compute_tool_snapshot_sha(None)
        except Exception:
            sha = _snapshot_sha(get_canonical_tool_snapshot())
        summary = {
            "run_id": config.run_id if hasattr(config, "run_id") else str(artifact_dir.name),
            "condition": getattr(config, "condition", ""),
            "model": getattr(config, "model", ""),
            "temperature": getattr(config, "temperature", 0),
            "seed": getattr(config, "seed", None),
            "git_head": head,
            "git_dirty": dirty,
            "tool_sha256": sha,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        _write_json_atomic(summary_path, summary)

# ---- history handling ----
def _history_path(state_dir: Path, patient_id: str) -> Path:
    sd = Path(state_dir)
    # Prefer per-patient file, fallback to history.json
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in patient_id)
    p = sd / f"{safe}_history.json"
    return p

def _load_history_messages(state_dir: Path, patient_id: str, patient_file: Path) -> list[dict]:
    hp = _history_path(state_dir, patient_id)
    alt = Path(state_dir) / "history.json"
    # Try per-patient first
    hist_data = None
    if hp.exists():
        try:
            hist_data = json.loads(hp.read_text(encoding="utf-8"))
        except Exception:
            hist_data = None
    elif alt.exists():
        try:
            hist_data = json.loads(alt.read_text(encoding="utf-8"))
        except Exception:
            hist_data = None
    # hist_data expected to be list of messages excluding system
    if isinstance(hist_data, list) and hist_data:
        # Build full messages with system prompt
        try:
            from diabetes_chatbot.memory import format_patient_context
            from diabetes_chatbot.prompts import build_nurse_system_prompt
            ctx = format_patient_context(patient_file)
            sys_prompt = build_nurse_system_prompt(ctx)
        except Exception:
            from diabetes_chatbot.prompts import build_nurse_system_prompt as _bpsp
            sys_prompt = _bpsp("")
        return [{"role": "system", "content": sys_prompt}] + hist_data
    # Fallback: build fresh system prompt only
    try:
        from diabetes_chatbot.memory import format_patient_context
        from diabetes_chatbot.prompts import build_nurse_system_prompt
        ctx = format_patient_context(patient_file)
        sys_prompt = build_nurse_system_prompt(ctx)
    except Exception:
        from diabetes_chatbot.prompts import build_nurse_system_prompt as _bpsp
        sys_prompt = _bpsp("")
    return [{"role": "system", "content": sys_prompt}]

def _persist_history(state_dir: Path, patient_id: str, messages: list[dict]):
    hp = _history_path(state_dir, patient_id)
    # Save all except system prompt
    to_save = [m for m in messages if m.get("role") != "system"]
    try:
        _write_json_atomic(hp, to_save)
    except Exception:
        pass
    # Also keep generic history.json for compat
    try:
        alt = Path(state_dir) / "history.json"
        if not alt.exists():
            _write_json_atomic(alt, to_save)
        else:
            # update alt as well
            _write_json_atomic(alt, to_save)
    except Exception:
        pass

def _check_existing_turn(artifact_dir: Path, turn_index: int) -> Optional[dict]:
    # Check checkpoint file existence
    cp = artifact_dir / "checkpoints" / f"checkpoint_turn_{turn_index}.json"
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            return None
    # Also check trajectories.jsonl lines
    traj = artifact_dir / "trajectories.jsonl"
    if traj.exists():
        try:
            for line in traj.read_text(encoding="utf-8").strip().splitlines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                if obj.get("turn_index") == turn_index:
                    return obj
        except Exception:
            pass
    return None

def ensure_state_dir_empty_with_resume(
    state_dir: Path,
    resume: bool = False,
    run_id: str | None = None,
    condition: str | None = None,
    patient_id: str | None = None,
):
    from .isolation import ensure_state_dir_empty
    ensure_state_dir_empty(
        state_dir=state_dir,
        resume=resume,
        run_id=run_id,
        condition=condition,
        patient_id=patient_id,
    )

def run_ablation_turn(*args, config: Optional[AblationConfig] = None, user_id: Optional[str] = None, message: Optional[str] = None, state_dir: Optional[Path] = None, model_client: Any = None, patient_id: Optional[str] = None, turn_index: int = 0, run_id: Optional[str] = None, resume: bool = False, patient_goal_checker: Optional[Callable] = None, research_patient_id: Optional[str] = None, artifacts_dir: Optional[Path] = None, **kwargs) -> dict:
    # Parse positional args
    arg_names = ["config", "user_id", "message", "state_dir", "model_client", "patient_id", "turn_index", "run_id"]
    if args:
        for i, val in enumerate(args):
            if i < len(arg_names):
                n = arg_names[i]
                if n == "config" and config is None:
                    config = val
                elif n == "user_id" and user_id is None:
                    user_id = val
                elif n == "message" and message is None:
                    message = val
                elif n == "state_dir" and state_dir is None:
                    state_dir = val
                elif n == "model_client" and model_client is None:
                    model_client = val
                elif n == "patient_id" and patient_id is None:
                    patient_id = val
                elif n == "turn_index" and turn_index == 0:
                    turn_index = val
                elif n == "run_id" and run_id is None:
                    run_id = val
    if config is None:
        config = kwargs.get("config")
    if user_id is None:
        user_id = kwargs.get("user_id")
    if message is None:
        message = kwargs.get("message")
    if state_dir is None:
        state_dir = kwargs.get("state_dir")
    if model_client is None:
        model_client = kwargs.get("model_client")
    if patient_id is None:
        patient_id = kwargs.get("patient_id")
    if run_id is None:
        run_id = kwargs.get("run_id")
    if "resume" in kwargs:
        resume = bool(kwargs["resume"])
    if "patient_goal_checker" in kwargs:
        patient_goal_checker = kwargs["patient_goal_checker"]
    if research_patient_id is None and "research_patient_id" in kwargs:
        research_patient_id = kwargs["research_patient_id"]
    if artifacts_dir is None and "artifacts_dir" in kwargs:
        artifacts_dir = kwargs["artifacts_dir"]

    if config is None:
        raise ValueError("config is required")
    if message is None:
        message = ""
    # R2: state-isolation user id stays backward compatible (user_id or patient_id);
    # research id is decoupled (research_patient_id or patient_id).
    effective_user_id = user_id or patient_id or "default_user"
    user_id = effective_user_id
    research_id = research_patient_id or patient_id or effective_user_id
    if patient_id is None:
        patient_id = research_id
    if state_dir is None:
        state_dir = Path(tempfile.gettempdir()) / f"ablation_{config.run_id}"
    state_dir = Path(state_dir)
    if run_id is None:
        run_id = getattr(config, "run_id", f"RUN-{uuid.uuid4().hex[:8]}")
    condition = getattr(config, "condition", "A")

    check_resume = True if turn_index > 0 else resume
    ensure_state_dir_empty_with_resume(
        state_dir, resume=check_resume, run_id=run_id, condition=condition, patient_id=research_id
    )
    art_dir = Path(artifacts_dir) if artifacts_dir is not None else _resolve_artifact_dir(state_dir, run_id)
    if art_dir != state_dir:
        ensure_state_dir_empty_with_resume(
            art_dir, resume=check_resume, run_id=run_id, condition=condition, patient_id=research_id
        )
    model_name = getattr(config, "model", "fake-model")
    temperature = getattr(config, "temperature", 0.0)
    seed = getattr(config, "seed", None)

    start = time.time()
    error = None
    termination_reason = None
    clear_session_cache()
    patient_file = get_patient_file_for_state(state_dir, effective_user_id)

    # Resolve artifact dir (explicit artifacts_dir keeps caller runs self-contained)
    artifact_dir = Path(artifacts_dir) if artifacts_dir is not None else _resolve_artifact_dir(state_dir, run_id)
    # True resume idempotence check (#7) - if turn already exists and resume=True, return existing
    if resume:
        existing = _check_existing_turn(artifact_dir, turn_index)
        if existing is not None:
            # Idempotent: verify message matches if provided? simply return existing
            return existing
        # Also check state_dir history case where artifact_dir != state_dir
        existing2 = _check_existing_turn(Path(state_dir), turn_index)
        if existing2 is not None:
            return existing2

    # Also if not resume but we already have that turn, we would have raised earlier; but handle append-only
    # Load history for multi-turn (#5)
    messages_hist = _load_history_messages(state_dir, effective_user_id, patient_file)
    # Delegate to shared core
    # Map model client to talker/planner
    talker_client = model_client
    planner_client = model_client

    # Ensure artifact files with canonical snapshot (#13)
    try:
        _ensure_artifact_files(artifact_dir, config, None)
        # Also ensure state_dir artifact files if different
        if Path(state_dir) != artifact_dir:
            _ensure_artifact_files(Path(state_dir), config, None)
    except Exception:
        pass

    # Call core - it handles Input Guard, planner branch, tool gate, forced retrieval, talker, tool loop, output guard
    # Core mutates messages_hist
    core_error = None
    try:
        if _core_execute is None:
            raise RuntimeError("ablation_core not available")
        # core expects model name; use config model
        core_res = _core_execute(
            user_text=message,
            patient_file=patient_file,
            messages=messages_hist,
            ablation_config=config,
            talker_client=talker_client,
            planner_client=planner_client,
            model=model_name,
            temperature=temperature,
            max_tokens=500 if "gemini" in model_name.lower() else 250,
            turn_index=turn_index,
        )
    except Exception as e:
        # Core failed - fallback minimal result
        core_error = str(e)
        # Try to build neutral result
        from diabetes_chatbot.guard import inspect_safety_guard
        ig = inspect_safety_guard(message)
        if ig.is_blocked:
            core_res = {
                "planner": neutral_planner_state(),
                "exposed_tools": get_canonical_tool_snapshot(),
                "exposed_tool_names": [t["function"]["name"] for t in get_canonical_tool_snapshot()],
                "input_guard_result": ig,
                "output_guard_result": type("G", (), {"is_blocked": False, "risk_category": "NONE", "blocked_message": ""})(),
                "raw_talker_output": "",
                "final_output": ig.blocked_message,
                "called_tools": [],
                "tool_results": [],
                "tool_rejections": [],
                "flex_bubble": None,
                "qr_payload": None,
                "termination_reason": "COMMON_INPUT_BLOCK",
                "error": core_error,
                "latency_ms": int((time.time()-start)*1000),
            }
        else:
            core_res = {
                "planner": neutral_planner_state(),
                "exposed_tools": get_canonical_tool_snapshot(),
                "exposed_tool_names": [t["function"]["name"] for t in get_canonical_tool_snapshot()],
                "input_guard_result": ig,
                "output_guard_result": type("G", (), {"is_blocked": False, "risk_category": "NONE", "blocked_message": ""})(),
                "raw_talker_output": "",
                "final_output": "",
                "called_tools": [],
                "tool_results": [],
                "tool_rejections": [],
                "flex_bubble": None,
                "qr_payload": None,
                "termination_reason": "ERROR",
                "error": core_error,
                "latency_ms": int((time.time()-start)*1000),
            }

    # Persist history after core mutated messages_hist
    try:
        _persist_history(state_dir, effective_user_id, messages_hist)
    except Exception:
        pass

    latency_ms = core_res.get("latency_ms", int((time.time() - start) * 1000))
    planner_obj = core_res.get("planner", neutral_planner_state())
    planner_serialized = _serialize_planner(planner_obj)
    exposed_tool_names = core_res.get("exposed_tool_names", [])
    called_tools = core_res.get("called_tools", [])
    input_guard_result_obj = core_res.get("input_guard_result")
    output_guard_result_obj = core_res.get("output_guard_result")
    input_guard_result = _serialize_guard_result(input_guard_result_obj)
    output_guard_result = _serialize_guard_result(output_guard_result_obj)
    raw_talker_output = core_res.get("raw_talker_output", "")
    assistant_response = core_res.get("final_output", "")
    error = core_res.get("error") or core_error
    termination_reason = core_res.get("termination_reason", None)
    # Check patient goal met placeholder (#8)
    if patient_goal_checker is not None:
        try:
            if patient_goal_checker(message, assistant_response, messages_hist):
                termination_reason = "PATIENT_GOAL_MET"
        except Exception:
            pass
    # Override termination if input blocked
    if input_guard_result.get("is_blocked"):
        termination_reason = "COMMON_INPUT_BLOCK"
    elif error:
        termination_reason = "ERROR"

    result = {
        "run_id": run_id,
        "patient_id": research_id,
        "research_patient_id": research_id,
        "user_id": effective_user_id,
        "condition": condition,
        "turn_index": turn_index,
        "user_message": message,
        "assistant_response": assistant_response,
        "planner_enabled": bool(getattr(config, "enable_planner", False)),
        "planner_result_or_neutral": planner_serialized,
        "exposed_tools": exposed_tool_names,
        "called_tools": called_tools,
        "tool_results": core_res.get("tool_results", []),
        "tool_rejections": core_res.get("tool_rejections", []),
        "input_guard_result": input_guard_result,
        "output_guard_result": output_guard_result,
        "raw_talker_output": raw_talker_output,
        "termination_reason": termination_reason,
        "events": core_res.get("events", []),
        "token_usage": core_res.get("token_usage", None),
        "retry_metadata": core_res.get("retry_metadata", None),
        "error_metadata": core_res.get("error_metadata", None),
        "error": error,
        "model": model_name,
        "temperature": temperature,
        "seed": seed,
        "latency_ms": latency_ms,
    }

    # Logging artifacts - use canonical snapshot for tool_snapshot (#13)
    try:
        # Ensure canonical snapshot file exists (already called above)
        _ensure_artifact_files(artifact_dir, config, None)
        traj_path = artifact_dir / "trajectories.jsonl"
        _append_jsonl_atomic(traj_path, result)
        cp_path = artifact_dir / "checkpoints" / f"checkpoint_turn_{turn_index}.json"
        _write_json_atomic(cp_path, result)
        log_path = artifact_dir / "logs" / f"turn_{turn_index}.json"
        _write_json_atomic(log_path, result)
        # Also mirror to state_dir if different
        if Path(state_dir) != artifact_dir:
            _ensure_artifact_files(Path(state_dir), config, None)
            traj2 = Path(state_dir) / "trajectories.jsonl"
            _append_jsonl_atomic(traj2, result)
            cp2 = Path(state_dir) / "checkpoints" / f"checkpoint_turn_{turn_index}.json"
            _write_json_atomic(cp2, result)
            log2 = Path(state_dir) / "logs" / f"turn_{turn_index}.json"
            _write_json_atomic(log2, result)
        summary_path = artifact_dir / "summary.json"
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                summ = json.load(f)
            summ["last_turn"] = turn_index
            summ["last_latency_ms"] = latency_ms
            _write_json_atomic(summary_path, summ)
        except Exception:
            pass
    except Exception as e:
        if result["error"] is None:
            result["error"] = f"logging_error: {e}"

    return result

def run_trajectory(*, config: AblationConfig, patient_id: str, messages: list[str], state_dir: Path | str, model_client: Any, run_id: Optional[str] = None, resume: bool = False, patient_goal_checker: Optional[Callable] = None, user_id: Optional[str] = None, research_patient_id: Optional[str] = None, artifacts_dir: Optional[Path | str] = None) -> list[dict]:
    cfg_run_id = getattr(config, "run_id", None)
    if run_id is not None and cfg_run_id is not None and cfg_run_id not in ("RUN-0000", ""):
        if run_id != cfg_run_id:
            raise ValueError(f"Run ID mismatch: config.run_id {cfg_run_id!r} != explicit run_id {run_id!r}")
    if run_id is None:
        run_id = cfg_run_id or f"RUN-{uuid.uuid4().hex[:8]}"
    resolved_artifacts = Path(artifacts_dir) if artifacts_dir is not None else _resolve_artifact_dir(Path(state_dir), run_id)
    results = []
    max_turns = getattr(config, "max_turns", 6)
    # True resume: determine starting index from existing trajectories
    start_idx = 0
    if resume:
        artifact_dir = resolved_artifacts
        # Check trajectories.jsonl length
        for cand in [artifact_dir / "trajectories.jsonl", Path(state_dir) / "trajectories.jsonl"]:
            if cand.exists():
                try:
                    lines = [l for l in cand.read_text(encoding="utf-8").strip().splitlines() if l.strip()]
                    if lines:
                        # Find max turn_index
                        max_idx = -1
                        for line in lines:
                            obj = json.loads(line)
                            ti = obj.get("turn_index", -1)
                            if ti > max_idx:
                                max_idx = ti
                        start_idx = max_idx + 1
                        break
                except Exception:
                    pass
        # Also check checkpoints
        cp_dir = artifact_dir / "checkpoints"
        alt_cp = Path(state_dir) / "checkpoints"
        for cp_base in [cp_dir, alt_cp]:
            if cp_base.exists():
                try:
                    cps = list(cp_base.glob("checkpoint_turn_*.json"))
                    if cps:
                        max_cp = max(int(p.stem.split("_")[-1]) for p in cps)
                        if max_cp + 1 > start_idx:
                            start_idx = max_cp + 1
                except Exception:
                    pass
    # Enforce max_turns (#8)
    effective_messages = messages[start_idx:]
    if start_idx >= max_turns:
        loaded = []
        artifact_dir = resolved_artifacts
        traj_path = artifact_dir / "trajectories.jsonl"
        if not traj_path.exists():
            traj_path = Path(state_dir) / "trajectories.jsonl"
        if traj_path.exists():
            for line in traj_path.read_text(encoding="utf-8").strip().splitlines():
                if line.strip():
                    loaded.append(json.loads(line))
            return loaded
        return results

    remaining_turns = max_turns - start_idx
    effective_messages = effective_messages[:remaining_turns]
    for idx_offset, msg in enumerate(effective_messages):
        idx = start_idx + idx_offset
        res = run_ablation_turn(
            config=config,
            user_id=user_id or patient_id,
            message=msg,
            state_dir=Path(state_dir),
            model_client=model_client,
            patient_id=patient_id,
            research_patient_id=research_patient_id,
            artifacts_dir=artifacts_dir,
            turn_index=idx,
            run_id=run_id,
            resume=resume,
            patient_goal_checker=patient_goal_checker,
        )
        results.append(res)
        if res.get("termination_reason") in ("COMMON_INPUT_BLOCK", "ERROR", "PATIENT_GOAL_MET"):
            break
        # Check max_turns termination
        if len(results) + start_idx >= max_turns:
            # Mark last result termination as MAX_TURNS only at final turn
            if results[-1].get("termination_reason") not in ("COMMON_INPUT_BLOCK", "ERROR", "PATIENT_GOAL_MET"):
                results[-1]["termination_reason"] = "MAX_TURNS"
            break
        if res.get("termination_reason") == "PATIENT_GOAL_MET":
            break
    # If resume=True and we had prior turns, include them in return for completeness
    if resume and start_idx > 0:
        prior = []
        artifact_dir = resolved_artifacts
        traj_path = artifact_dir / "trajectories.jsonl"
        if not traj_path.exists():
            traj_path = Path(state_dir) / "trajectories.jsonl"
        if traj_path.exists():
            lines = [l for l in traj_path.read_text(encoding="utf-8").strip().splitlines() if l.strip()]
            for line in lines[:start_idx]:
                try:
                    prior.append(json.loads(line))
                except Exception:
                    pass
        return prior + results
    return results

def validate_condition_mapping(mapping: Any) -> dict[str, str]:
    """Validate opaque condition mapping strictly for formal blinded export.

    Requirements:
      - Must be a dictionary.
      - Must contain exactly keys 'A', 'B', 'C', 'D'.
      - Values must be non-empty opaque IDs.
      - Values must NOT be any of 'A', 'B', 'C', 'D'.
      - All 4 opaque IDs must be unique (no duplicate values).
    """
    if not isinstance(mapping, dict):
        raise ValueError(f"condition_mapping must be a dict, got {type(mapping).__name__}")
    required_keys = {"A", "B", "C", "D"}
    if set(mapping.keys()) != required_keys:
        raise ValueError(
            f"condition_mapping must contain exactly keys {sorted(required_keys)}, got {sorted(mapping.keys())}"
        )
    values = [str(v).strip() for v in mapping.values()]
    for k, v in mapping.items():
        v_str = str(v).strip()
        if not v_str:
            raise ValueError(f"condition_mapping has empty value for condition {k}")
        if v_str in required_keys:
            raise ValueError(f"condition_mapping value {v_str!r} for key {k!r} must not be one of {sorted(required_keys)}")
    if len(set(values)) != len(values):
        raise ValueError(f"condition_mapping contains duplicate opaque IDs: {values}")
    return {k: str(mapping[k]).strip() for k in required_keys}


def generate_random_condition_mapping() -> dict[str, str]:
    """Generate cryptographically randomized opaque mapping for formal blinded batch."""
    import secrets
    codes = [f"COND-{secrets.token_hex(4).upper()}" for _ in range(4)]
    return dict(zip(["A", "B", "C", "D"], codes))


def save_frozen_condition_mapping(mapping: dict[str, str], path: Path | str) -> None:
    """Save the secret condition mapping for technical lead custody only under artifacts/frozen_config/."""
    valid_map = validate_condition_mapping(mapping)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(p, valid_map)


def load_frozen_condition_mapping(path: Path | str) -> dict[str, str]:
    """Load secret condition mapping from frozen config path."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Frozen condition mapping not found at {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    return validate_condition_mapping(data)


def to_contract_trajectory(
    run_id: str,
    state_dir: Path | str,
    condition_mapping: Optional[dict[str, str]] = None,
    allow_incomplete: bool = True,
    termination_reason_override: Optional[str] = None,
) -> dict:
    """Convert flat JSONL per-turn records into EXPERIMENT_CONTRACT trajectory JSON.

    Guarantees:
      - patient_id is strictly derived from turn record (never patient_text).
      - termination_reason is None unless max_turns reached or stopped by guard/error,
        or overridden by a strictly validated run-level termination_reason_override.
      - if allow_incomplete=False, rejects incomplete trajectories.
      - preserves token_usage.
    """
    ALLOWED_OVERRIDE_REASONS = frozenset({"PATIENT_GOAL_MET", "MAX_TURNS", "COMMON_INPUT_BLOCK"})
    if termination_reason_override is not None:
        if termination_reason_override not in ALLOWED_OVERRIDE_REASONS:
            raise ValueError(
                f"Invalid termination_reason_override: {termination_reason_override!r}. "
                f"Must be one of {sorted(ALLOWED_OVERRIDE_REASONS)} (ERROR, None, or unknown rejected, fail-closed)."
            )

    sd = Path(state_dir)
    artifact_dir = _resolve_artifact_dir(sd, run_id)
    traj_path = sd / "trajectories.jsonl"
    if not traj_path.exists():
        traj_path = artifact_dir / "trajectories.jsonl"
    config_path = sd / "config.json"
    if not config_path.exists():
        config_path = artifact_dir / "config.json"
    summary_path = sd / "summary.json"
    if not summary_path.exists():
        summary_path = artifact_dir / "summary.json"

    config_data = {}
    if config_path.exists():
        try:
            config_data = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            config_data = {}
    summary_data = {}
    if summary_path.exists():
        try:
            summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            summary_data = {}

    # Provenance check: config.json run_id must match run_id if specified
    if config_data.get("run_id") and config_data.get("run_id") not in ("RUN-0000", "") and config_data.get("run_id") != run_id:
        raise ValueError(f"Run ID provenance mismatch: config.json run_id {config_data.get('run_id')!r} != {run_id!r}")

    turns = []
    termination_reason = None
    error = None
    last_turn_obj = None
    has_turn_level_error = False
    if traj_path.exists():
        for line in traj_path.read_text(encoding="utf-8").strip().splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            last_turn_obj = obj
            turns.append({
                "turn": obj.get("turn_index", 0) + 1,
                "patient_text": obj.get("user_message", ""),
                "planner_state": obj.get("planner_result_or_neutral", {}),
                "tools_exposed": obj.get("exposed_tools", []),
                "tools_called": obj.get("called_tools", []),
                "raw_talker_output": obj.get("raw_talker_output", ""),
                "guard_action": obj.get("output_guard_result", {}),
                "final_output": obj.get("assistant_response", ""),
                "latency_ms": obj.get("latency_ms", 0),
                "token_usage": obj.get("token_usage", None),
            })
            if obj.get("termination_reason") == "ERROR":
                has_turn_level_error = True
                termination_reason = "ERROR"
            elif obj.get("termination_reason"):
                termination_reason = obj.get("termination_reason")
            if obj.get("error"):
                error = obj.get("error")
                has_turn_level_error = True
            if obj.get("error_metadata") is not None and error is None:
                error = str(obj.get("error_metadata"))
                has_turn_level_error = True

    max_turns = config_data.get("max_turns", 10)
    if termination_reason_override is not None:
        if error is not None or has_turn_level_error:
            raise ValueError(
                f"Cannot apply termination_reason_override to trajectory {run_id} with error: {error!r} (fail-closed)"
            )
        termination_reason = termination_reason_override
    else:
        # 只有實際最後一輪達到 config.max_turns 才能寫 MAX_TURNS
        if termination_reason is None and len(turns) >= max_turns and len(turns) > 0:
            termination_reason = "MAX_TURNS"

    # 若不允許未完成軌跡，但 termination_reason 仍為 None，拒絕進入正式 completed artifact
    if not allow_incomplete and termination_reason is None:
        raise ValueError(
            f"Trajectory {run_id} is incomplete ({len(turns)}/{max_turns} turns, termination_reason is None); "
            "cannot export as formal completed artifact."
        )

    # Determine checkpoint_revision as max turn_index
    checkpoint_revision = len(turns) - 1 if turns else 0
    cp_dir = sd / "checkpoints"
    if not cp_dir.exists():
        cp_dir = artifact_dir / "checkpoints"
    if cp_dir.exists():
        try:
            cps = list(cp_dir.glob("checkpoint_turn_*.json"))
            if cps:
                checkpoint_revision = max(int(p.stem.split("_")[-1]) for p in cps)
        except Exception:
            pass

    turn_patient_id = None
    if last_turn_obj:
        turn_patient_id = last_turn_obj.get("research_patient_id") or last_turn_obj.get("patient_id")
    real_patient_id = turn_patient_id or config_data.get("patient_id") or summary_data.get("patient_id") or ""

    raw_condition = config_data.get("condition") or summary_data.get("condition") or ""
    if condition_mapping is not None:
        valid_map = validate_condition_mapping(condition_mapping)
        condition_secret = valid_map.get(raw_condition, raw_condition)
    else:
        condition_secret = raw_condition

    return {
        "run_id": run_id,
        "condition_secret": condition_secret,
        "patient_id": real_patient_id,
        "model": config_data.get("model", summary_data.get("model", "")),
        "temperature": config_data.get("temperature", summary_data.get("temperature", 0)),
        "started_at": summary_data.get("created_at", ""),
        "state_dir_id": str(sd.name),
        "checkpoint_revision": checkpoint_revision,
        "turns": turns,
        "termination_reason": termination_reason,
        "error": error,
    }


def to_blinded_contract_trajectory(
    run_id: str,
    state_dir: Path | str,
    condition_mapping: Optional[dict[str, str]] = None,
    blinded_run_id: Optional[str] = None,
    require_completed: bool = True,
    termination_reason_override: Optional[str] = None,
) -> dict:
    """Produce blinded trajectory contract for Workstream 5 (Judge).

    Guarantees:
      - condition_mapping is required from technical lead and strictly validated.
      - condition_secret uses opaque mapping (not A/B/C/D).
      - run_id and state_dir_id are fully anonymized.
      - Trajectory contains no major flag names, no condition names, no mapping leak.
      - Incomplete trajectories are rejected if require_completed=True.
    """
    if condition_mapping is None:
        raise ValueError("Formal blinded export requires an explicit, complete condition_mapping from technical lead.")
    valid_map = validate_condition_mapping(condition_mapping)

    contract = to_contract_trajectory(
        run_id,
        state_dir,
        condition_mapping=valid_map,
        allow_incomplete=not require_completed,
        termination_reason_override=termination_reason_override,
    )

    if require_completed and contract.get("termination_reason") is None:
        raise ValueError(f"Incomplete trajectory {run_id} cannot be exported as formal blinded artifact (termination_reason is None).")

    b_id = blinded_run_id or f"BLIND-{hashlib.sha256(run_id.encode()).hexdigest()[:8]}"
    contract["run_id"] = b_id
    contract["state_dir_id"] = f"STATE-{b_id}"
    contract.pop("condition", None)
    contract.pop("mapping", None)
    contract.pop("research_patient_id", None)

    forbidden_keys = {
        "enable_planner",
        "enable_dynamic_tool_gate",
        "enable_output_guard",
        "enable_forced_retrieval",
        "enable_fixed_warning_append",
        "enable_question_budget_postprocessing",
        "planner_enabled",
        "condition",
        "mapping",
        "research_patient_id",
    }

    def _strip_forbidden(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                k: _strip_forbidden(v)
                for k, v in item.items()
                if k not in forbidden_keys and not k.startswith("enable_") and k != "research_patient_id"
            }
        elif isinstance(item, list):
            return [_strip_forbidden(v) for v in item]
        return item

    return _strip_forbidden(contract)


_PROVIDER_SECRET_MARKERS = ("api_key", "apikey", "api-key", "token", "secret", "password", "authorization")
_GEMINI_OPENAI_COMPAT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
_GEMINI_ENDPOINT_HOST = "generativelanguage.googleapis.com"


def _reject_provider_secrets(provider_config: Optional[dict]) -> dict:
    cfg = dict(provider_config or {})
    for key in cfg.keys():
        lowered = str(key).lower()
        for marker in _PROVIDER_SECRET_MARKERS:
            if marker in lowered:
                raise ValueError(
                    f"provider_config must not contain secrets; rejected key {key!r} "
                    f"(matched {marker!r}). API keys are ENV-ONLY."
                )
    return cfg


def _is_gemini_endpoint(base_url: str) -> bool:
    from urllib.parse import urlsplit
    raw = (base_url or "").strip()
    if not raw:
        return False
    try:
        parts = urlsplit(raw)
    except Exception:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    host = (parts.hostname or "").lower()
    if not host:
        return False
    return host == _GEMINI_ENDPOINT_HOST or host.endswith("." + _GEMINI_ENDPOINT_HOST)


def resolve_provider_credentials(provider_config: Optional[dict]) -> tuple[str, str]:
    """Resolve (api_key, base_url) for the formal Gemini client, fail-closed.

    The formal experiment is Gemini-only. provider_config may carry only
    non-secret settings (provider/base_url/timeout). The key is read from the
    GEMINI_API_KEY environment variable only; OPENAI_API_KEY is never accepted.
    A non-Gemini provider or a non-Gemini endpoint is rejected so a Gemini key
    can never be paired with the wrong service.
    """
    import os
    cfg = _reject_provider_secrets(provider_config)
    provider = str(cfg.get("provider") or os.environ.get("LLM_PROVIDER") or "gemini").strip().lower()
    if provider != "gemini":
        raise RuntimeError(
            f"正式實驗僅支援 Gemini provider，收到 provider={provider!r}，拒絕連線 (fail-closed)。"
        )
    explicit_base = str(cfg.get("base_url", "") or "").strip()
    if explicit_base and not _is_gemini_endpoint(explicit_base):
        raise RuntimeError(
            "provider_config.base_url 指向非 Gemini endpoint，禁止與 GEMINI_API_KEY 配對，拒絕連線 (fail-closed)。"
        )
    env_base = (os.environ.get("GEMINI_BASE_URL", "") or "").strip()
    if env_base and not _is_gemini_endpoint(env_base):
        raise RuntimeError(
            "GEMINI_BASE_URL 指向非 Gemini endpoint，拒絕連線 (fail-closed)。"
        )
    base_url = explicit_base or env_base or _GEMINI_OPENAI_COMPAT_BASE_URL
    api_key = (os.environ.get("GEMINI_API_KEY", "") or "").strip()
    if not api_key:
        raise RuntimeError(
            "正式模型連線缺少 GEMINI_API_KEY，拒絕連線 (fail-closed)；正式實驗僅接受 Gemini。"
        )
    return api_key, base_url


def ensure_provider_ready(provider_config: Optional[dict]) -> tuple[str, str]:
    """Fail-closed pre-flight check for WS4: validates provider config + env BEFORE spawning subprocess."""
    return resolve_provider_credentials(provider_config)


def _build_client_from_provider_config(provider_config: Optional[dict]) -> Any:
    """Build the formal Gemini model client via the Gemini OpenAI-compatible endpoint, failing closed if misconfigured."""
    api_key, base_url = resolve_provider_credentials(provider_config)
    try:
        import openai
        return openai.OpenAI(api_key=api_key, base_url=base_url)
    except Exception:
        raise RuntimeError("建立正式 Gemini（OpenAI-compatible）模型客戶端失敗，拒絕連線 (fail-closed)") from None


def _subprocess_target(
    config_dict: dict,
    patient_id: str,
    messages: list[str],
    state_dir_str: str,
    run_id: str,
    fake_responses: list[str] | None,
    client_factory: Optional[Callable] = None,
    provider_config: Optional[dict] = None,
    result_queue: Any = None,
    resume: bool = False,
    user_id: Optional[str] = None,
    research_patient_id: Optional[str] = None,
    artifacts_dir: Optional[str] = None,
):
    try:
        from llm_ablation_paper.workstream_1_technical_lead.harness.config import AblationConfig
        from llm_ablation_paper.workstream_1_technical_lead.harness.runner import run_trajectory
        config = AblationConfig(**config_dict)
        if client_factory is not None:
            client = client_factory()
        elif fake_responses is not None:
            from llm_ablation_paper.workstream_1_technical_lead.harness.dry_run import make_fake_client
            client = make_fake_client(fake_responses)
        elif provider_config is not None:
            client = _build_client_from_provider_config(provider_config)
        else:
            client = _build_client_from_provider_config({})

        results = run_trajectory(
            config=config,
            patient_id=patient_id,
            messages=messages,
            state_dir=Path(state_dir_str),
            model_client=client,
            run_id=run_id,
            resume=resume,
            user_id=user_id,
            research_patient_id=research_patient_id,
            artifacts_dir=Path(artifacts_dir) if artifacts_dir is not None else None,
        )
        result_queue.put({"status": "ok", "results": results})
    except Exception as e:
        import traceback
        result_queue.put({"status": "error", "error": str(e), "traceback": traceback.format_exc()})


def run_trajectory_subprocess(
    *,
    config: AblationConfig,
    patient_id: str,
    messages: list[str],
    state_dir: Path | str,
    model_client: Any = None,
    client_factory: Optional[Callable] = None,
    provider_config: Optional[dict] = None,
    run_id: Optional[str] = None,
    fake_responses: list[str] | None = None,
    timeout: float = 30.0,
    resume: bool = False,
    user_id: Optional[str] = None,
    research_patient_id: Optional[str] = None,
    artifacts_dir: Optional[Path | str] = None,
) -> list[dict]:
    if run_id is None:
        run_id = getattr(config, "run_id", f"RUN-{uuid.uuid4().hex[:8]}")
    config_dict = config.to_dict() if hasattr(config, "to_dict") else dict(config)
    effective_factory = client_factory

    if model_client is not None:
        raise TypeError(
            f"run_trajectory_subprocess received unsupported model_client of type '{type(model_client).__name__}'. "
            "Subprocess execution requires a callable client_factory or provider_config; model_client cannot be serialized across processes."
        )

    if effective_factory is not None:
        import pickle
        try:
            pickle.dumps(effective_factory)
        except Exception as e:
            raise TypeError(
                f"run_trajectory_subprocess received unpicklable client_factory '{effective_factory}': {e}. "
                "Factory must be a picklable top-level function or class."
            ) from e
    elif fake_responses is None:
        ensure_provider_ready(provider_config)

    ctx = multiprocessing.get_context("spawn")
    q = ctx.Queue()
    state_dir_str = str(Path(state_dir))
    Path(state_dir_str).mkdir(parents=True, exist_ok=True)
    p = ctx.Process(
        target=_subprocess_target,
        args=(
            config_dict,
            patient_id,
            messages,
            state_dir_str,
            run_id,
            fake_responses,
            effective_factory,
            provider_config,
            q,
            resume,
            user_id,
            research_patient_id,
            str(Path(artifacts_dir)) if artifacts_dir is not None else None,
        ),
    )
    p.start()
    p.join(timeout=timeout)
    if p.is_alive():
        p.terminate()
        p.join(timeout=5)
        raise TimeoutError(f"Subprocess trajectory timed out after {timeout}s")
    if not q.empty():
        payload = q.get()
        if payload.get("status") == "ok":
            return payload["results"]
        else:
            raise RuntimeError(f"Subprocess failed: {payload.get('error')}\n{payload.get('traceback')}")
    else:
        raise RuntimeError("Subprocess did not return results")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True, help="Path to config.json")
    parser.add_argument("--patient-id", type=str, required=True)
    parser.add_argument("--state-dir", type=str, required=True)
    parser.add_argument("--messages", type=str, nargs="+", required=True)
    parser.add_argument("--run-id", type=str, default=None)
    args = parser.parse_args()
    with open(args.config, "r", encoding="utf-8") as f:
        cfg_d = json.load(f)
    cfg = AblationConfig(**cfg_d)
    from unittest.mock import MagicMock
    client = MagicMock()
    def _fake_create(**kwargs):
        mock_msg = MagicMock()
        mock_msg.content = "fake reply"
        mock_msg.tool_calls = None
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        return mock_resp
    client.chat.completions.create = _fake_create
    results = run_trajectory(config=cfg, patient_id=args.patient_id, messages=args.messages, state_dir=Path(args.state_dir), model_client=client, run_id=args.run_id)
    print(json.dumps(results, ensure_ascii=False, indent=2))
