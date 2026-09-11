"""CLI Analysis and Results Formatter for Workstream 5.

Features:
  - Validates that Judge evaluations are complete before execution.
  - Ingests WS1 canonical condition mapping (A-D -> opaque ID), validates it with
    WS1 validate_condition_mapping, and strictly inverts it to (opaque ID -> A-D)
    for downstream aggregate_pipeline deblinding.
  - Aggregates programmatic metrics and LLM judge scores via analysis_pipeline.
  - Generates derived results: summary.json, main_table.md, main_table.tex, results.csv.
  - Generates failure taxonomy visualizations (ASCII terminal chart + Matplotlib PNG).
  - Condition mapping (--mapping-file) is strictly optional and used ONLY downstream for unblinding.
  - Ensures missing != zero (empty conditions report None/-- with preserved denominators).
  - Artifact paths anchored to PROJECT_ROOT/llm_ablation_paper/artifacts.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
ARTIFACTS_ROOT = PROJECT_ROOT / "llm_ablation_paper" / "artifacts"

from llm_ablation_paper.workstream_5_judge_analysis.analysis_pipeline import aggregate_pipeline
from llm_ablation_paper.workstream_5_judge_analysis.format_results import (
    format_markdown_table,
    format_latex_table,
    generate_blank_results_csv,
    BLANK_MAIN_TABLE_CSV_HEADER,
    _fmt_pct,
    _fmt_num,
)
from llm_ablation_paper.workstream_5_judge_analysis.plot_failure_taxonomy import (
    generate_ascii_failure_chart,
    plot_failure_distribution_figure,
)

DEFAULT_TRAJECTORIES_PATH = ARTIFACTS_ROOT / "blinded_transcripts"
DEFAULT_JUDGE_RESULTS_PATH = ARTIFACTS_ROOT / "judge_raw" / "judge_results.jsonl"
DEFAULT_OUTPUT_DIR = ARTIFACTS_ROOT / "derived_results"
DEFAULT_FIGURES_DIR = ARTIFACTS_ROOT / "figures"


def load_json_or_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Load items from a file (.jsonl or .json) or a directory."""
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")

    items: List[Dict[str, Any]] = []
    if path.is_file():
        files = [path]
    else:
        files = sorted(list(path.glob("*.json")) + list(path.glob("*.jsonl")))

    if not files:
        raise ValueError(f"No json/jsonl files found in {path}")

    for f in files:
        if f.name.endswith(".jsonl"):
            with open(f, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        items.append(json.loads(line))
        else:
            with open(f, "r", encoding="utf-8") as fh:
                content = fh.read().strip()
                if content:
                    items.append(json.loads(content))

    return items


def load_and_invert_condition_mapping(mapping_path: Optional[Path]) -> Optional[Dict[str, str]]:
    """Load, strictly validate with WS1 validator, and invert condition mapping for deblinding.

    WS1 frozen mapping format:
      {"A": "COND-...", "B": "COND-...", "C": "COND-...", "D": "COND-..."}
    Inverted format returned:
      {"COND-...": "A", ...}
    Fails closed on any non-canonical or ambiguous formats.
    """
    if not mapping_path:
        return None
    if not mapping_path.exists():
        raise FileNotFoundError(f"Mapping file does not exist: {mapping_path}")

    with open(mapping_path, "r", encoding="utf-8") as fh:
        raw_map = json.load(fh)

    # 1. Strictly validate using WS1 canonical validator
    from llm_ablation_paper.workstream_1_technical_lead.harness.runner import validate_condition_mapping
    canonical_map = validate_condition_mapping(raw_map)

    # 2. Strictly invert: canonical format is real condition (A-D) -> opaque_id;
    #    aggregate_pipeline deblinding requires opaque_id -> real condition (A-D).
    inverted_map = {opaque_id: real_cond for real_cond, opaque_id in canonical_map.items()}
    if len(inverted_map) != 4:
        raise ValueError("Inverted condition mapping must contain exactly 4 unique opaque IDs.")

    return inverted_map


# Backwards compatibility alias
load_condition_mapping = load_and_invert_condition_mapping


def format_unblinded_results_csv(summary_by_group: Dict[str, Any]) -> str:
    """Format an unblinded A-D main table CSV."""
    csv_lines = [BLANK_MAIN_TABLE_CSV_HEADER.strip()]

    for cond in ["A", "B", "C", "D"]:
        data = summary_by_group.get(cond)
        if not data:
            csv_lines.append(f"{cond},,,,,,,,,,,,,,,,")
            continue

        n = data.get("sample_size", 0)
        cf_rate = data.get("critical_failure_rate")
        ci = data.get("critical_failure_ci_95") or [None, None]
        sm = data.get("scores_mean", {})
        prog = data.get("programmatic", {})

        row = [
            cond,
            str(n),
            _fmt_pct(cf_rate),
            _fmt_pct(ci[0]),
            _fmt_pct(ci[1]),
            _fmt_num(sm.get("safety")),
            _fmt_num(sm.get("tool_use")),
            _fmt_num(sm.get("state_consistency")),
            _fmt_num(sm.get("dialogue_planning")),
            _fmt_num(sm.get("helpfulness")),
            _fmt_num(prog.get("avg_questions_per_turn")),
            _fmt_pct(prog.get("guard_override_rate")),
            _fmt_pct(prog.get("unexposed_tool_call_rate")),
            _fmt_pct(prog.get("premature_summary_call_rate")),
            _fmt_num(prog.get("avg_latency_ms"), decimals=1),
            _fmt_num(prog.get("avg_tokens_per_trajectory"), decimals=1),
            _fmt_num(prog.get("avg_model_calls_per_trajectory"), decimals=1),
        ]
        csv_lines.append(",".join(row))

    return "\n".join(csv_lines) + "\n"


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="WS5: Generate Statistical Analysis, Derived Tables, and Visualizations."
    )
    parser.add_argument(
        "--trajectories-path",
        type=Path,
        default=DEFAULT_TRAJECTORIES_PATH,
        help="Path to blinded trajectories (default: PROJECT_ROOT/llm_ablation_paper/artifacts/blinded_transcripts)",
    )
    parser.add_argument(
        "--judge-results-path",
        type=Path,
        default=DEFAULT_JUDGE_RESULTS_PATH,
        help="Path to Judge results file (.jsonl) or checkpoints directory (default: PROJECT_ROOT/llm_ablation_paper/artifacts/judge_raw/judge_results.jsonl)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to save summary.json, main_table.md, main_table.tex, results.csv (default: PROJECT_ROOT/llm_ablation_paper/artifacts/derived_results)",
    )
    parser.add_argument(
        "--figures-dir",
        type=Path,
        default=DEFAULT_FIGURES_DIR,
        help="Directory to save failure taxonomy distribution figure (default: PROJECT_ROOT/llm_ablation_paper/artifacts/figures)",
    )
    parser.add_argument(
        "--mapping-file",
        type=Path,
        default=None,
        help="Optional external condition mapping JSON file (A-D -> opaque ID) provided by WS1 for unblinding",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Allow running analysis when some trajectories lack judge evaluations",
    )
    return parser.parse_args(args)


def run_analysis_cli(args: Optional[List[str]] = None) -> int:
    opts = parse_args(args)

    print("================================================================")
    print("  WS5: Statistical Analysis & Output Formatter")
    print("================================================================")
    print(f"Project Root:        {PROJECT_ROOT}")
    print(f"Trajectories Path:   {opts.trajectories_path}")
    print(f"Judge Results Path:  {opts.judge_results_path}")
    print(f"Output Dir:          {opts.output_dir}")
    print(f"Figures Dir:         {opts.figures_dir}")
    print(f"Mapping File:        {opts.mapping_file or '[NONE - Opaque Blinded Mode]'}")
    print("================================================================")

    # 1. Load Data
    try:
        trajectories = load_json_or_jsonl(opts.trajectories_path)
        print(f"Loaded {len(trajectories)} trajectory records.")
    except Exception as e:
        print(f"\n[ERROR] Failed to load trajectories: {e}", file=sys.stderr)
        return 1

    try:
        judge_evaluations = load_json_or_jsonl(opts.judge_results_path)
        print(f"Loaded {len(judge_evaluations)} Judge evaluation records.")
    except Exception as e:
        print(f"\n[ERROR] Failed to load Judge evaluations: {e}", file=sys.stderr)
        return 1

    # 2. Check Completeness
    valid_trajs = [
        t for t in trajectories
        if t.get("termination_reason") not in ("COMMON_INPUT_BLOCK", "ERROR")
        and t.get("termination_reason") is not None
    ]
    eval_ids = {e.get("blinded_run_id") for e in judge_evaluations if not e.get("excluded")}
    missing_ids = [
        (t.get("run_id") or t.get("blinded_run_id"))
        for t in valid_trajs
        if (t.get("run_id") or t.get("blinded_run_id")) not in eval_ids
    ]

    if missing_ids and not opts.allow_incomplete:
        print(
            f"\n[ERROR] Analysis blocked: Judge evaluations are incomplete! "
            f"Missing evaluations for {len(missing_ids)} trajectories: {missing_ids[:5]}...",
            file=sys.stderr,
        )
        return 1

    # 3. Load and Invert Mapping (if provided)
    try:
        condition_mapping = load_and_invert_condition_mapping(opts.mapping_file)
        if condition_mapping:
            print(f"Loaded and verified canonical mapping with {len(condition_mapping)} conditions.")
    except Exception as e:
        print(f"\n[ERROR] Failed to validate condition mapping: {e}", file=sys.stderr)
        return 1

    # 4. Run Aggregation Pipeline
    try:
        summary = aggregate_pipeline(
            trajectories=trajectories,
            judge_evaluations=judge_evaluations,
            condition_mapping=condition_mapping,
        )
    except Exception as e:
        print(f"\n[ERROR] Statistical aggregation failed: {e}", file=sys.stderr)
        return 1

    summary_by_group = summary["summary_by_group"]
    excluded_runs = summary["excluded_runs"]

    # 5. Output Artifacts (Atomic write)
    opts.output_dir.mkdir(parents=True, exist_ok=True)
    opts.figures_dir.mkdir(parents=True, exist_ok=True)

    # 5-1. summary.json
    summary_file = opts.output_dir / "summary.json"
    tmp_summary = summary_file.with_suffix(".tmp")
    tmp_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_summary, summary_file)

    # 5-2. main_table.md
    md_file = opts.output_dir / "main_table.md"
    tmp_md = md_file.with_suffix(".tmp")
    tmp_md.write_text(format_markdown_table(summary_by_group), encoding="utf-8")
    os.replace(tmp_md, md_file)

    # 5-3. main_table.tex
    tex_file = opts.output_dir / "main_table.tex"
    tmp_tex = tex_file.with_suffix(".tmp")
    tmp_tex.write_text(format_latex_table(summary_by_group), encoding="utf-8")
    os.replace(tmp_tex, tex_file)

    # 5-4. results.csv
    csv_file = opts.output_dir / "results.csv"
    tmp_csv = csv_file.with_suffix(".tmp")
    if condition_mapping:
        csv_content = format_unblinded_results_csv(summary_by_group)
    else:
        # Blinded mode: output template preserving blank format
        csv_content = generate_blank_results_csv()
    tmp_csv.write_text(csv_content, encoding="utf-8")
    os.replace(tmp_csv, csv_file)

    # 5-5. failure_distribution.png
    fig_file = opts.figures_dir / "failure_distribution.png"
    try:
        plot_failure_distribution_figure(summary_by_group, fig_file)
        print(f"Generated failure distribution plot: {fig_file}")
    except Exception as e:
        print(f"[WARNING] Failed to plot figure: {e}", file=sys.stderr)

    # 6. Terminal Summary & ASCII Chart
    print("\n" + generate_ascii_failure_chart(summary_by_group))
    print("\n--- Summary Table (Markdown) ---")
    print(format_markdown_table(summary_by_group))
    print("\n================ Analysis Complete ================")
    print(f"Groups Analyzed: {len(summary_by_group)}")
    print(f"Excluded Runs:   {len(excluded_runs)}")
    print(f"Saved artifacts to: {opts.output_dir}")
    print("====================================================")
    return 0


if __name__ == "__main__":
    sys.exit(run_analysis_cli())
