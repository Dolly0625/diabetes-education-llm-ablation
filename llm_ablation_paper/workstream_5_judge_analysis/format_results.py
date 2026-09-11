"""Results Formatting and Table Generation for Workstream 5.

Generates:
  - Blank results.csv template (No fabricated numbers)
  - Main Table Markdown and LaTeX formatters
  - Separate reporting for programmatic metrics vs. LLM judge scores.
"""

from typing import Any, Dict, List, Optional


BLANK_MAIN_TABLE_CSV_HEADER = (
    "Condition,N,Critical_Failure_Rate,CI_95_Lower,CI_95_Upper,"
    "Safety,Tool_Use,State_Consistency,Dialogue_Planning,Helpfulness,"
    "Avg_Questions_Per_Turn,Guard_Override_Rate,Avg_Latency_ms,Avg_Tokens\n"
)

BLANK_MAIN_TABLE_CSV_BODY = """A,,,,,,,,,,,,
B,,,,,,,,,,,,
C,,,,,,,,,,,,
D,,,,,,,,,,,,
"""


def generate_blank_results_csv() -> str:
    """Return an unpopulated, blank CSV template for formal experimental results."""
    return BLANK_MAIN_TABLE_CSV_HEADER + BLANK_MAIN_TABLE_CSV_BODY


def format_markdown_table(summary_by_group: Dict[str, Any]) -> str:
    """Format aggregated summary into an academic Markdown table."""
    lines = [
        "| Condition | N | Critical Failure Rate (95% CI) | Safety | Tool Use | State Cons. | Plan | Help | Avg Q/turn | Guard Override | Latency (ms) |",
        "|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    for grp, data in sorted(summary_by_group.items()):
        n = data.get("sample_size", 0)
        cf_rate = data.get("critical_failure_rate", 0.0)
        ci = data.get("critical_failure_ci_95", [0.0, 0.0])
        cf_str = f"{cf_rate:.1%} [{ci[0]:.1%}, {ci[1]:.1%}]"

        sm = data.get("scores_mean", {})
        safety = sm.get("safety", 0.0)
        tool = sm.get("tool_use", 0.0)
        cons = sm.get("state_consistency", 0.0)
        plan = sm.get("dialogue_planning", 0.0)
        help_ = sm.get("helpfulness", 0.0)

        prog = data.get("programmatic", {})
        avg_q = prog.get("avg_questions_per_turn", 0.0)
        guard = prog.get("guard_override_rate", 0.0)
        guard_str = f"{guard:.1%}"
        lat = prog.get("avg_latency_ms", 0.0)

        line = (
            f"| {grp} | {n} | {cf_str} | {safety:.2f} | {tool:.2f} | {cons:.2f} | "
            f"{plan:.2f} | {help_:.2f} | {avg_q:.2f} | {guard_str} | {lat:.1f} |"
        )
        lines.append(line)

    return "\n".join(lines)


def format_latex_table(summary_by_group: Dict[str, Any]) -> str:
    """Format aggregated summary into standard academic LaTeX table format."""
    latex_lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\small",
        r"\caption{Ablation Study Results: Comparing Multi-layer Controls on Patient-facing Diabetes Education LLM}",
        r"\label{tab:main_ablation_results}",
        r"\begin{tabular}{lccccccccccc}",
        r"\toprule",
        r"Condition & N & CF Rate (95\% CI) & Safe & Tool & Cons & Plan & Help & Q/turn & Guard Over. & Latency \\",
        r"\midrule",
    ]

    for grp, data in sorted(summary_by_group.items()):
        n = data.get("sample_size", 0)
        cf_rate = data.get("critical_failure_rate", 0.0)
        ci = data.get("critical_failure_ci_95", [0.0, 0.0])
        cf_str = f"{cf_rate * 100:.1f}\\% [{ci[0]*100:.1f}\\%, {ci[1]*100:.1f}\\%]"

        sm = data.get("scores_mean", {})
        prog = data.get("programmatic", {})

        line = (
            f"{grp} & {n} & {cf_str} & {sm.get('safety', 0):.2f} & {sm.get('tool_use', 0):.2f} & "
            f"{sm.get('state_consistency', 0):.2f} & {sm.get('dialogue_planning', 0):.2f} & "
            f"{sm.get('helpfulness', 0):.2f} & {prog.get('avg_questions_per_turn', 0):.2f} & "
            f"{prog.get('guard_override_rate', 0)*100:.1f}\\% & {prog.get('avg_latency_ms', 0):.0f}ms \\\\"
        )
        latex_lines.append(line)

    latex_lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table*}",
    ])
    return "\n".join(latex_lines)
