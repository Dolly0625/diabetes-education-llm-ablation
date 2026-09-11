"""Results Formatting and Table Generation for Workstream 5.

Generates:
  - Blank results.csv template (No fabricated numbers)
  - Main Table Markdown and LaTeX formatters with graceful handling of None/null missing values
  - Separate reporting for programmatic metrics vs. LLM judge scores.
"""

from typing import Any, Dict, List, Optional


BLANK_MAIN_TABLE_CSV_HEADER = (
    "Condition,N,Critical_Failure_Rate,CI_95_Lower,CI_95_Upper,"
    "Safety,Tool_Use,State_Consistency,Dialogue_Planning,Helpfulness,"
    "Avg_Questions_Per_Turn,Guard_Override_Rate,Unexposed_Tool_Rate,Premature_Card_Rate,Avg_Latency_ms,Avg_Tokens,Avg_Model_Calls\n"
)

BLANK_MAIN_TABLE_CSV_BODY = """A,,,,,,,,,,,,,,,,
B,,,,,,,,,,,,,,,,
C,,,,,,,,,,,,,,,,
D,,,,,,,,,,,,,,,,
"""


def generate_blank_results_csv() -> str:
    """Return an unpopulated, blank CSV template for formal experimental results."""
    return BLANK_MAIN_TABLE_CSV_HEADER + BLANK_MAIN_TABLE_CSV_BODY


def _fmt_pct(val: Optional[float]) -> str:
    return f"{val:.1%}" if val is not None else "--"


def _fmt_num(val: Optional[float], decimals: int = 2) -> str:
    return f"{val:.{decimals}f}" if val is not None else "--"


def format_markdown_table(summary_by_group: Dict[str, Any]) -> str:
    """Format aggregated summary into an academic Markdown table with None safety."""
    lines = [
        "| Condition | N | Critical Failure Rate (95% CI) | Safety | Tool Use | State Cons. | Plan | Help | Avg Q/turn | Guard Over. | Unexposed Tools | Latency (ms) |",
        "|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    for grp, data in sorted(summary_by_group.items()):
        n = data.get("sample_size", 0)
        cf_rate = data.get("critical_failure_rate")
        ci = data.get("critical_failure_ci_95")

        if cf_rate is not None and ci is not None and ci[0] is not None and ci[1] is not None:
            cf_str = f"{cf_rate:.1%} [{ci[0]:.1%}, {ci[1]:.1%}]"
        elif cf_rate is not None:
            cf_str = f"{cf_rate:.1%}"
        else:
            cf_str = "--"

        sm = data.get("scores_mean", {})
        safety_str = _fmt_num(sm.get("safety"))
        tool_str = _fmt_num(sm.get("tool_use"))
        cons_str = _fmt_num(sm.get("state_consistency"))
        plan_str = _fmt_num(sm.get("dialogue_planning"))
        help_str = _fmt_num(sm.get("helpfulness"))

        prog = data.get("programmatic", {})
        avg_q_str = _fmt_num(prog.get("avg_questions_per_turn"))
        guard_str = _fmt_pct(prog.get("guard_override_rate"))
        unexposed_str = _fmt_pct(prog.get("unexposed_tool_call_rate"))
        lat_str = _fmt_num(prog.get("avg_latency_ms"), decimals=1)

        line = (
            f"| {grp} | {n} | {cf_str} | {safety_str} | {tool_str} | {cons_str} | "
            f"{plan_str} | {help_str} | {avg_q_str} | {guard_str} | {unexposed_str} | {lat_str} |"
        )
        lines.append(line)

    return "\n".join(lines)


def format_latex_table(summary_by_group: Dict[str, Any]) -> str:
    """Format aggregated summary into standard academic LaTeX table format with None safety."""
    latex_lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\small",
        r"\caption{Ablation Study Results: Comparing Multi-layer Controls on Patient-facing Diabetes Education LLM}",
        r"\label{tab:main_ablation_results}",
        r"\begin{tabular}{lcccccccccccc}",
        r"\toprule",
        r"Condition & N & CF Rate (95\% CI) & Safe & Tool & Cons & Plan & Help & Q/turn & Guard Over. & Unexposed & Latency \\",
        r"\midrule",
    ]

    for grp, data in sorted(summary_by_group.items()):
        n = data.get("sample_size", 0)
        cf_rate = data.get("critical_failure_rate")
        ci = data.get("critical_failure_ci_95")

        if cf_rate is not None and ci is not None and ci[0] is not None and ci[1] is not None:
            cf_str = f"{cf_rate * 100:.1f}\\% [{ci[0]*100:.1f}\\%, {ci[1]*100:.1f}\\%]"
        elif cf_rate is not None:
            cf_str = f"{cf_rate * 100:.1f}\\%"
        else:
            cf_str = "--"

        sm = data.get("scores_mean", {})
        prog = data.get("programmatic", {})

        s_safe = _fmt_num(sm.get("safety"))
        s_tool = _fmt_num(sm.get("tool_use"))
        s_cons = _fmt_num(sm.get("state_consistency"))
        s_plan = _fmt_num(sm.get("dialogue_planning"))
        s_help = _fmt_num(sm.get("helpfulness"))
        p_q = _fmt_num(prog.get("avg_questions_per_turn"))
        p_guard = _fmt_pct(prog.get("guard_override_rate")).replace("%", r"\%")
        p_unexp = _fmt_pct(prog.get("unexposed_tool_call_rate")).replace("%", r"\%")
        p_lat = f"{prog.get('avg_latency_ms'):.0f}ms" if prog.get("avg_latency_ms") is not None else "--"

        line = (
            f"{grp} & {n} & {cf_str} & {s_safe} & {s_tool} & {s_cons} & {s_plan} & "
            f"{s_help} & {p_q} & {p_guard} & {p_unexp} & {p_lat} \\\\"
        )
        latex_lines.append(line)

    latex_lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table*}",
    ])
    return "\n".join(latex_lines)
