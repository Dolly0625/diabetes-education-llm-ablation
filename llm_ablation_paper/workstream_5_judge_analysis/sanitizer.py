"""Judge input sanitizer and payload builder for Workstream 5.

Guarantees physical removal of:
  - condition, condition_secret
  - state_dir_id, checkpoint_revision
  - config/toggles (enable_planner, enable_dynamic_tool_gate, enable_output_guard, etc.)
  - planner_state, raw_talker_output, guard_action
  - latency_ms, token_usage

Preserves:
  - run_id (anonymized, e.g. BLIND-xxxx or CANARY-xxxx)
  - patient_id
  - turns: turn, patient_text, tools_exposed, tools_called, final_output
"""

import json
import re
from typing import Any, Dict, List, Set


class SanitizationLeakError(Exception):
    """Raised when forbidden architectural flags or secrets leak into Judge payload."""
    pass


class BlindedContractViolationError(Exception):
    """Raised when an unblinded, raw, or leaky trajectory is supplied to the batch runner."""
    pass


FORBIDDEN_LEAK_SUBSTRINGS: Set[str] = {
    "condition_secret",
    "state_dir_id",
    "planner_state",
    "raw_talker_output",
    "guard_action",
    "checkpoint_revision",
    "enable_planner",
    "enable_dynamic_tool_gate",
    "enable_output_guard",
    "enable_forced_retrieval",
    "enable_fixed_warning_append",
    "enable_question_budget_postprocessing",
    "planner_enabled",
}

FORBIDDEN_FLAG_KEYS: Set[str] = {
    "enable_planner",
    "enable_dynamic_tool_gate",
    "enable_output_guard",
    "enable_forced_retrieval",
    "enable_fixed_warning_append",
    "enable_question_budget_postprocessing",
    "planner_enabled",
}


def validate_blinded_input_trajectory(
    trajectory: Dict[str, Any],
    require_completed: bool = True,
) -> None:
    """Validate that input trajectory meets blinded contract requirements.

    Rejects:
      - Raw unblinded run_id (e.g. RUN-*)
      - Explicit condition names in metadata (e.g. condition: "A", "Condition A")
      - Major architectural flags (enable_*)
      - Incomplete trajectories if require_completed is True
    Ensures:
      - Does NOT falsely flag legitimate patient/clinical mentions of letters (e.g., Vitamin C, HbA1c).
    """
    if not isinstance(trajectory, dict):
        raise BlindedContractViolationError("Trajectory must be a dictionary.")

    run_id = str(trajectory.get("run_id") or trajectory.get("blinded_run_id") or "")
    if not run_id:
        raise BlindedContractViolationError("Trajectory is missing run_id / blinded_run_id.")

    # Must start with BLIND- or CANARY-
    if run_id.startswith("RUN-"):
        raise BlindedContractViolationError(
            f"Raw unblinded run ID detected: {run_id!r}. Only BLIND-* or CANARY-* trajectories are accepted."
        )

    # Check termination reason
    if require_completed:
        term_reason = trajectory.get("termination_reason")
        if not term_reason:
            raise BlindedContractViolationError(
                f"Trajectory {run_id} is incomplete (missing termination_reason)."
            )

    # Check forbidden keys at top level
    for key in FORBIDDEN_FLAG_KEYS:
        if key in trajectory:
            raise BlindedContractViolationError(
                f"Trajectory {run_id} contains forbidden flag key {key!r}."
            )

    # Check condition leakage in metadata
    raw_cond = trajectory.get("condition")
    if raw_cond is not None and str(raw_cond).strip().upper() in ("A", "B", "C", "D"):
        raise BlindedContractViolationError(
            f"Trajectory {run_id} contains explicit unblinded condition: {raw_cond!r}."
        )

    # Check metadata strings for condition leakage (excluding dialogue text)
    metadata_to_check = {
        "run_id": run_id,
        "patient_id": str(trajectory.get("patient_id", "")),
        "state_dir_id": str(trajectory.get("state_dir_id", "")),
    }
    for meta_key, meta_val in metadata_to_check.items():
        if re.search(r"\bcondition[_\s-]*[a-d]\b", meta_val, re.IGNORECASE):
            raise BlindedContractViolationError(
                f"Metadata {meta_key}={meta_val!r} contains condition leakage marker."
            )


def sanitize_turn_for_judge(turn_data: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize a single dialogue turn for Judge payload."""
    turn_num = turn_data.get("turn", 1)
    patient_text = turn_data.get("patient_text", "")
    final_output = turn_data.get("final_output", "")

    # Preserve tools_exposed and tools_called for Tool Use dimension evaluation
    tools_exposed = turn_data.get("tools_exposed", [])
    if isinstance(tools_exposed, list):
        clean_exposed = [str(t) for t in tools_exposed]
    else:
        clean_exposed = []

    tools_called = turn_data.get("tools_called", [])
    clean_called = []
    if isinstance(tools_called, list):
        for tc in tools_called:
            if isinstance(tc, dict):
                clean_called.append({
                    "name": str(tc.get("name", "")),
                    "arguments": tc.get("arguments", {}),
                })
            else:
                clean_called.append({"name": str(tc), "arguments": {}})

    return {
        "turn": turn_num,
        "patient_text": str(patient_text),
        "tools_exposed": clean_exposed,
        "tools_called": clean_called,
        "final_output": str(final_output),
    }


def build_judge_payload(contract_trajectory: Dict[str, Any]) -> Dict[str, Any]:
    """Transform a blinded contract trajectory into a sanitized Judge payload.

    Physically strips all internal artifacts, toggles, condition_secret, planner and guard logs.
    """
    blinded_run_id = contract_trajectory.get("run_id") or contract_trajectory.get("blinded_run_id", "")
    patient_id = contract_trajectory.get("patient_id", "")

    raw_turns = contract_trajectory.get("turns", [])
    sanitized_turns: List[Dict[str, Any]] = []
    for t in raw_turns:
        sanitized_turns.append(sanitize_turn_for_judge(t))

    payload = {
        "blinded_run_id": str(blinded_run_id),
        "patient_id": str(patient_id),
        "turns": sanitized_turns,
    }

    assert_no_leakage(payload)
    return payload


def assert_no_leakage(payload: Dict[str, Any]) -> None:
    """Verify that payload contains zero forbidden architectural or secret keys."""
    dumped = json.dumps(payload, ensure_ascii=False)
    dumped_lower = dumped.lower()

    for forbidden in FORBIDDEN_LEAK_SUBSTRINGS:
        if forbidden.lower() in dumped_lower:
            raise SanitizationLeakError(
                f"Forbidden leak detected in Judge payload: {forbidden!r}"
            )

    # Check top-level keys
    allowed_top_keys = {"blinded_run_id", "patient_id", "turns"}
    extra_keys = set(payload.keys()) - allowed_top_keys
    if extra_keys:
        raise SanitizationLeakError(
            f"Extra unauthorized top-level keys in Judge payload: {extra_keys}"
        )

    # Check turn keys
    allowed_turn_keys = {"turn", "patient_text", "tools_exposed", "tools_called", "final_output"}
    for idx, t in enumerate(payload.get("turns", [])):
        extra_turn_keys = set(t.keys()) - allowed_turn_keys
        if extra_turn_keys:
            raise SanitizationLeakError(
                f"Extra unauthorized keys in turn {idx}: {extra_turn_keys}"
            )


def format_conversation_for_judge(payload: Dict[str, Any]) -> str:
    """Format sanitized payload into a structured text prompt for the Judge."""
    assert_no_leakage(payload)
    lines = [
        f"Trajectory ID: {payload['blinded_run_id']}",
        f"Patient Scenario ID: {payload['patient_id']}",
        "--- Dialogue Transcript & Tool Trace ---",
    ]

    for t in payload.get("turns", []):
        lines.append(f"\n[Turn {t['turn']}]")
        lines.append(f"Patient: {t['patient_text']}")
        lines.append(f"Tools Exposed: {t['tools_exposed']}")
        lines.append(f"Tools Called: {json.dumps(t['tools_called'], ensure_ascii=False)}")
        lines.append(f"Assistant Output: {t['final_output']}")

    return "\n".join(lines)
