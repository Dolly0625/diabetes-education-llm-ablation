"""CLI Runner for Workstream 5: Blinded LLM Judge Evaluation.

Enforces:
  - Strict formal execution gate (--confirm-formal-judge <token>)
  - Pre-flight Canary verification before batch evaluation
  - Immutable model (gemini-3.7-flash) and temperature (0.0)
  - Formal 12x4 batch input validation (48 trajectories, 12 patients x 4 opaque conditions)
  - Rejection of pilot, canary, and raw A-D condition leaks
  - Safe loading of canonical project .env without leaking secrets
  - Pre-flight API key check fail-closed before any external calls
  - Atomic persistence of checkpoints and final judge_results.jsonl
  - Artifact paths anchored to PROJECT_ROOT/llm_ablation_paper/artifacts
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
ARTIFACTS_ROOT = PROJECT_ROOT / "llm_ablation_paper" / "artifacts"

from llm_ablation_paper.workstream_5_judge_analysis.judge_runner import (
    JudgeRunner,
    deterministic_fake_judge,
    live_gemini_judge_adapter,
    verify_canaries,
    CANONICAL_JUDGE_MODEL,
    CANONICAL_JUDGE_TEMPERATURE,
)
from llm_ablation_paper.workstream_5_judge_analysis.sanitizer import (
    validate_blinded_input_trajectory,
    BlindedContractViolationError,
)

FORMAL_CONFIRM_TOKEN = "CONFIRM_FORMAL_WS5_JUDGE_RUN"
DEFAULT_CANARY_PATH = Path(__file__).parent / "canary_trajectories.jsonl"
DEFAULT_INPUT_DIR = ARTIFACTS_ROOT / "blinded_transcripts"
DEFAULT_CHECKPOINT_DIR = ARTIFACTS_ROOT / "judge_raw" / "checkpoints"
DEFAULT_OUTPUT_FILE = ARTIFACTS_ROOT / "judge_raw" / "judge_results.jsonl"


def ensure_canonical_env_loaded() -> None:
    """Safely load canonical .env from project root with override=False without leaking secrets."""
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=env_file, override=False)
        except ImportError:
            pass


def load_blinded_trajectories(input_path: Path) -> List[Dict[str, Any]]:
    """Load blinded trajectories from a directory of JSON/JSONL files or a single file."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    trajectories: List[Dict[str, Any]] = []

    if input_path.is_file():
        files = [input_path]
    else:
        files = sorted(list(input_path.glob("*.json")) + list(input_path.glob("*.jsonl")))

    if not files:
        raise ValueError(f"No trajectory files (.json/.jsonl) found in {input_path}")

    for f in files:
        if f.name.endswith(".jsonl"):
            with open(f, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        trajectories.append(json.loads(line))
        else:
            with open(f, "r", encoding="utf-8") as fh:
                content = fh.read().strip()
                if content:
                    trajectories.append(json.loads(content))

    if not trajectories:
        raise ValueError(f"Loaded 0 trajectories from {input_path}")

    return trajectories


def validate_formal_batch_requirements(
    trajectories: List[Dict[str, Any]],
    allow_partial: bool = False,
) -> None:
    """Strictly validate that trajectories meet blinded formal batch requirements.

    Rejects:
      - Pilot trajectories (e.g. ID contains PILOT)
      - Canary trajectories in batch
      - Raw unblinded condition leaks (RUN-*, condition A-D, enable_* flags)
      - Duplicate run_ids
      - Incomplete batch (unless allow_partial=True)
    """
    seen_run_ids: Set[str] = set()
    patient_conditions: Dict[str, Set[str]] = defaultdict(set)
    unique_conditions: Set[str] = set()

    for idx, traj in enumerate(trajectories, 1):
        if not isinstance(traj, dict):
            raise ValueError(f"Item {idx} is not a valid trajectory dictionary.")

        run_id = str(traj.get("run_id") or traj.get("blinded_run_id") or "")
        patient_id = str(traj.get("patient_id") or "")
        cond_secret = str(traj.get("condition_secret") or "")

        if not run_id:
            raise ValueError(f"Trajectory {idx} missing run_id / blinded_run_id.")

        # 1. Reject Pilot
        if "PILOT" in run_id.upper() or "PILOT" in patient_id.upper():
            raise ValueError(
                f"Pilot trajectory rejected from formal evaluation: run_id={run_id!r}, patient_id={patient_id!r}."
            )

        # 2. Reject Canary in batch
        if "CANARY" in run_id.upper() or "CANARY" in patient_id.upper():
            raise ValueError(
                f"Canary trajectory rejected from formal batch: run_id={run_id!r}. "
                f"Canaries must only run during pre-flight canary verification."
            )

        # 3. Reject duplicates
        if run_id in seen_run_ids:
            raise ValueError(f"Duplicate run_id detected in batch: {run_id!r}.")
        seen_run_ids.add(run_id)

        # 4. Strict blinded contract validation (rejects RUN-*, condition A-D, enable_* flags)
        validate_blinded_input_trajectory(traj, require_completed=True)

        if patient_id and cond_secret:
            patient_conditions[patient_id].add(cond_secret)
            unique_conditions.add(cond_secret)

    if not allow_partial:
        # Formal 12x4 requirements: exactly 48 trajectories, 12 patients, 4 conditions
        if len(trajectories) != 48:
            raise ValueError(
                f"Formal evaluation requires exactly 48 trajectories (12 patients x 4 conditions), "
                f"but found {len(trajectories)}."
            )
        if len(patient_conditions) != 12:
            raise ValueError(
                f"Formal evaluation requires exactly 12 unique patients, found {len(patient_conditions)}."
            )
        if len(unique_conditions) != 4:
            raise ValueError(
                f"Formal evaluation requires exactly 4 opaque conditions, found {len(unique_conditions)}: {unique_conditions}."
            )
        for p_id, c_set in patient_conditions.items():
            if len(c_set) != 4:
                raise ValueError(
                    f"Patient {p_id} has {len(c_set)} conditions, expected exactly 4."
                )


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="WS5: Execute Blinded LLM Judge Evaluation on 12x4 Ablation Trajectories."
    )
    parser.add_argument(
        "--input-path",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Path to blinded trajectories directory or .jsonl file (default: PROJECT_ROOT/llm_ablation_paper/artifacts/blinded_transcripts)",
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=DEFAULT_CHECKPOINT_DIR,
        help="Directory for atomic checkpoint storage and resume (default: PROJECT_ROOT/llm_ablation_paper/artifacts/judge_raw/checkpoints)",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help="Path for aggregate JSONL results file (default: PROJECT_ROOT/llm_ablation_paper/artifacts/judge_raw/judge_results.jsonl)",
    )
    parser.add_argument(
        "--canary-file",
        type=Path,
        default=DEFAULT_CANARY_PATH,
        help="Path to Canary trajectories fixture (default: canary_trajectories.jsonl)",
    )
    parser.add_argument(
        "--mode",
        choices=["fake", "live"],
        default="live",
        help="Evaluation mode: 'live' (canonical Gemini 3.7 Flash) or 'fake' (offline deterministic mock)",
    )
    parser.add_argument(
        "--confirm-formal-judge",
        type=str,
        default="",
        help=f"Mandatory security gate for formal live evaluation. Must match {FORMAL_CONFIRM_TOKEN!r}.",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Allow fewer than 48 trajectories (only permitted in offline fake mode)",
    )
    return parser.parse_args(args)


def run_judge_cli(args: Optional[List[str]] = None) -> int:
    ensure_canonical_env_loaded()
    opts = parse_args(args)

    print("================================================================")
    print("  WS5: Blinded LLM-as-a-Judge Evaluation Runner")
    print("================================================================")
    print(f"Mode:              {opts.mode.upper()}")
    print(f"Model (Canonical): {CANONICAL_JUDGE_MODEL} (temp={CANONICAL_JUDGE_TEMPERATURE})")
    print(f"Project Root:      {PROJECT_ROOT}")
    print(f"Input Path:        {opts.input_path}")
    print(f"Checkpoint Dir:    {opts.checkpoint_dir}")
    print(f"Output File:       {opts.output_file}")
    print(f"Canary Path:       {opts.canary_file}")
    print("================================================================")

    # 1. Formal Confirmation Gate & Key Verification (Fail-closed before ANY network/canary calls)
    if opts.mode == "live":
        if opts.confirm_formal_judge != FORMAL_CONFIRM_TOKEN:
            print(
                f"\n[ERROR] Formal live judge evaluation blocked! "
                f"Missing or invalid --confirm-formal-judge token.\n"
                f"Expected: {FORMAL_CONFIRM_TOKEN!r}",
                file=sys.stderr,
            )
            return 1
        if opts.allow_partial:
            print(
                "\n[ERROR] --allow-partial is strictly forbidden in live formal evaluation.",
                file=sys.stderr,
            )
            return 1

        # Check API key presence safely without printing value
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key or not str(api_key).strip():
            print(
                "\n[ERROR] GEMINI_API_KEY environment variable is not set. "
                "Formal live evaluation requires a valid API key.",
                file=sys.stderr,
            )
            return 1

    # 2. Load Trajectories
    try:
        trajectories = load_blinded_trajectories(opts.input_path)
        print(f"Loaded {len(trajectories)} trajectory records from {opts.input_path}.")
    except Exception as e:
        print(f"\n[ERROR] Failed to load trajectories: {e}", file=sys.stderr)
        return 1

    # 3. Input Validation
    try:
        validate_formal_batch_requirements(
            trajectories, allow_partial=(opts.allow_partial or opts.mode == "fake")
        )
        print("Input validation passed: no pilot/canary/raw leaks detected.")
    except Exception as e:
        print(f"\n[ERROR] Input validation failed: {e}", file=sys.stderr)
        return 1

    # 4. Setup Evaluator
    if opts.mode == "live":
        evaluator_fn = live_gemini_judge_adapter
    else:
        evaluator_fn = deterministic_fake_judge

    # 5. Pre-flight Canary Verification
    print("\n--- Running Pre-flight Canary Verification ---")
    try:
        verify_canaries(opts.canary_file, evaluator_fn)
        print("[PASS] Pre-flight Canary verification succeeded.")
    except Exception as e:
        print(f"\n[ERROR] Pre-flight Canary verification failed: {e}", file=sys.stderr)
        return 1

    # 6. Execute Batch with Checkpoint and Resume
    print("\n--- Running Trajectory Evaluations ---")
    runner = JudgeRunner(evaluator_fn=evaluator_fn, checkpoint_dir=opts.checkpoint_dir)

    try:
        results = runner.run_batch(trajectories, canary_path=None)
    except Exception as e:
        print(f"\n[ERROR] Evaluation execution failed: {e}", file=sys.stderr)
        return 1

    # 7. Atomic Output Persistence
    opts.output_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_output = opts.output_file.with_suffix(".tmp")
    with open(tmp_output, "w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp_output, opts.output_file)
    print(f"\n[DONE] Aggregate results atomically saved to {opts.output_file}")

    # Summary report
    resumed_cnt = sum(1 for r in results if r.get("resumed"))
    excluded_cnt = sum(1 for r in results if r.get("excluded"))
    evaluated_cnt = len(results) - excluded_cnt - resumed_cnt
    cf_cnt = sum(1 for r in results if r.get("critical_failure_consensus"))

    print("\n================ Execution Summary ================")
    print(f"Total Trajectories:    {len(results)}")
    print(f"Resumed from CKPT:     {resumed_cnt}")
    print(f"Newly Evaluated:       {evaluated_cnt}")
    print(f"Excluded:              {excluded_cnt}")
    print(f"Consensus Critical CF: {cf_cnt}")
    print("====================================================")
    return 0


if __name__ == "__main__":
    sys.exit(run_judge_cli())
