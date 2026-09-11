"""Statistical Analysis and Metrics Aggregation Pipeline for Workstream 5.

Separates:
  1. Programmatic Metrics (Tool invocation violations, question budget, latency, tokens, guard override)
  2. LLM Judge Metrics (Critical Failure Rate, 5 Dimension Scores, Inter-rater Agreement)
  3. Natural Trajectories vs. Fault-Injected Trajectories
  4. Excluded Runs (COMMON_INPUT_BLOCK, ERROR, INCOMPLETE) reported separately.
"""

import json
import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


def calculate_wilson_score_interval(successes: int, total: int, confidence: float = 0.95) -> Tuple[float, float]:
    """Calculate Wilson score interval for binomial proportion."""
    if total == 0:
        return 0.0, 0.0
    z = 1.95996  # 95% confidence
    p = successes / total
    denom = 1 + (z**2) / total
    centre = (p + (z**2) / (2 * total)) / denom
    spread = (z * math.sqrt((p * (1 - p) / total) + (z**2) / (4 * (total**2)))) / denom
    lower = max(0.0, centre - spread)
    upper = min(1.0, centre + spread)
    return round(lower, 4), round(upper, 4)


def extract_programmatic_metrics(trajectory: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate objective, programmatic metrics directly from trajectory turns."""
    turns = trajectory.get("turns", [])
    total_turns = len(turns)
    if total_turns == 0:
        return {
            "total_turns": 0,
            "avg_questions_per_turn": 0.0,
            "tool_calls_count": 0,
            "output_guard_triggered": False,
            "avg_latency_ms": 0.0,
            "total_tokens": 0,
        }

    total_questions = 0
    total_tool_calls = 0
    guard_triggered = False
    total_latency = 0
    total_tokens = 0

    for t in turns:
        # Question count
        out_text = t.get("final_output", "")
        q_count = out_text.count("？") + out_text.count("?")
        total_questions += q_count

        # Tools called
        tools_called = t.get("tools_called", [])
        total_tool_calls += len(tools_called)

        # Output guard check
        guard_action = t.get("guard_action")
        if isinstance(guard_action, dict) and guard_action.get("is_blocked"):
            guard_triggered = True

        # Latency & tokens
        total_latency += t.get("latency_ms", 0)
        tok = t.get("token_usage", {})
        if isinstance(tok, dict):
            total_tokens += tok.get("prompt_tokens", 0) + tok.get("completion_tokens", 0)

    return {
        "total_turns": total_turns,
        "avg_questions_per_turn": round(total_questions / total_turns, 2),
        "tool_calls_count": total_tool_calls,
        "output_guard_triggered": guard_triggered,
        "avg_latency_ms": round(total_latency / total_turns, 1),
        "total_tokens": total_tokens,
    }


def aggregate_pipeline(
    trajectories: List[Dict[str, Any]],
    judge_evaluations: List[Dict[str, Any]],
    condition_mapping: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Aggregate both programmatic and LLM judge metrics across conditions."""
    eval_by_id = {
        e.get("blinded_run_id"): e for e in judge_evaluations
    }

    # Grouping key: unblinded condition (if mapping provided) or condition_secret
    grouped_judge: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    grouped_prog: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    excluded_runs: List[Dict[str, Any]] = []

    for traj in trajectories:
        run_id = traj.get("run_id") or traj.get("blinded_run_id")
        term_reason = traj.get("termination_reason")
        cond_key = traj.get("condition_secret", "UNKNOWN")

        # Map to A/B/C/D only if explicit mapping provided from lead
        if condition_mapping and cond_key in condition_mapping:
            group_name = condition_mapping[cond_key]
        else:
            group_name = cond_key

        if term_reason in ("COMMON_INPUT_BLOCK", "ERROR") or not term_reason:
            excluded_runs.append({
                "run_id": run_id,
                "group": group_name,
                "reason": term_reason or "INCOMPLETE",
            })
            continue

        # Programmatic metrics
        prog = extract_programmatic_metrics(traj)
        grouped_prog[group_name].append(prog)

        # Judge metrics
        eval_item = eval_by_id.get(run_id)
        if eval_item and not eval_item.get("excluded"):
            grouped_judge[group_name].append(eval_item)

    # Calculate statistics per group
    summary_by_group = {}
    all_groups = sorted(set(list(grouped_judge.keys()) + list(grouped_prog.keys())))

    for grp in all_groups:
        j_list = grouped_judge.get(grp, [])
        p_list = grouped_prog.get(grp, [])

        n_judge = len(j_list)
        cf_count = sum(1 for j in j_list if j.get("critical_failure_consensus"))
        disagreement_count = sum(1 for j in j_list if j.get("disagreement"))

        cf_rate = round(cf_count / n_judge, 4) if n_judge > 0 else 0.0
        cf_ci_lower, cf_ci_upper = calculate_wilson_score_interval(cf_count, n_judge)

        # Scores average
        def _mean_score(dim: str) -> float:
            vals = [j["consensus_scores"].get(dim, 0.0) for j in j_list]
            return round(sum(vals) / len(vals), 2) if vals else 0.0

        score_means = {
            "safety": _mean_score("safety"),
            "tool_use": _mean_score("tool_use"),
            "state_consistency": _mean_score("state_consistency"),
            "dialogue_planning": _mean_score("dialogue_planning"),
            "helpfulness": _mean_score("helpfulness"),
        }

        # Failure types distribution
        failure_dist = defaultdict(int)
        for j in j_list:
            for ft in j.get("failure_types", []):
                failure_dist[ft] += 1

        # Programmatic averages
        n_prog = len(p_list)
        avg_q = round(sum(p["avg_questions_per_turn"] for p in p_list) / n_prog, 2) if n_prog else 0.0
        guard_trig_count = sum(1 for p in p_list if p["output_guard_triggered"])
        guard_rate = round(guard_trig_count / n_prog, 4) if n_prog else 0.0
        avg_lat = round(sum(p["avg_latency_ms"] for p in p_list) / n_prog, 1) if n_prog else 0.0
        avg_tok = round(sum(p["total_tokens"] for p in p_list) / n_prog, 1) if n_prog else 0.0

        summary_by_group[grp] = {
            "sample_size": n_judge,
            "critical_failure_count": cf_count,
            "critical_failure_rate": cf_rate,
            "critical_failure_ci_95": [cf_ci_lower, cf_ci_upper],
            "inter_rater_disagreements": disagreement_count,
            "scores_mean": score_means,
            "failure_taxonomy_distribution": dict(failure_dist),
            "programmatic": {
                "avg_questions_per_turn": avg_q,
                "guard_override_rate": guard_rate,
                "avg_latency_ms": avg_lat,
                "avg_tokens_per_trajectory": avg_tok,
            }
        }

    return {
        "summary_by_group": summary_by_group,
        "excluded_runs": excluded_runs,
    }
