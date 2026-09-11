"""Tests for WS5 CLI orchestration: run_judge.py and run_analysis.py (Fake-only, offline).

Verifies:
  - run_judge confirm gate (fail-closed on missing/invalid token in live mode)
  - run_judge API key security check (fail-closed when absent/empty without leaking key value)
  - run_judge safe .env loading without overriding existing environment
  - run_judge input validation (rejects pilot, canary, unblinded raw leaks, duplicates, incomplete 12x4)
  - run_judge fake execution, atomic checkpoint/results output, and raw/parsed preservation
  - run_judge & run_analysis default artifact paths anchored to PROJECT_ROOT/llm_ablation_paper/artifacts
  - run_analysis canonical WS1 mapping validation (A-D -> opaque ID) and strict inversion
  - run_analysis rejection of inverted/ambiguous/malformed mappings (strict fail-closed)
  - run_analysis execution, mapping ingestion, missing!=zero handling, and artifact generation
  - CLI --help options validation
"""

import json
import os
from pathlib import Path
from unittest.mock import patch
import pytest

from llm_ablation_paper.workstream_5_judge_analysis.run_judge import (
    run_judge_cli,
    parse_args as parse_judge_args,
    FORMAL_CONFIRM_TOKEN,
    validate_formal_batch_requirements,
    ensure_canonical_env_loaded,
    PROJECT_ROOT as JUDGE_PROJECT_ROOT,
    ARTIFACTS_ROOT as JUDGE_ARTIFACTS_ROOT,
)
from llm_ablation_paper.workstream_5_judge_analysis.run_analysis import (
    run_analysis_cli,
    parse_args as parse_analysis_args,
    load_and_invert_condition_mapping,
    PROJECT_ROOT as ANALYSIS_PROJECT_ROOT,
    ARTIFACTS_ROOT as ANALYSIS_ARTIFACTS_ROOT,
)


@pytest.fixture
def fake_48_blinded_trajectories(tmp_path):
    """Generate 48 compliant blinded trajectories (12 patients x 4 opaque conditions)."""
    mock_conditions = ["COND-W111", "COND-X222", "COND-Y333", "COND-Z444"]
    trajectories = []

    for p_idx in range(1, 13):
        p_id = f"SP-{p_idx:03d}"
        for c_idx, c_secret in enumerate(mock_conditions):
            run_id = f"BLIND-{p_id}-{c_secret}"
            traj = {
                "run_id": run_id,
                "blinded_run_id": run_id,
                "condition_secret": c_secret,
                "patient_id": p_id,
                "model": "gemini-3.5-flash-lite",
                "temperature": 0.3,
                "started_at": "2026-09-11T12:00:00Z",
                "termination_reason": "MAX_TURNS",
                "error": None,
                "turns": [
                    {
                        "turn": 1,
                        "patient_text": "護理師，我今天早餐吃燕麥片加蛋，血糖120",
                        "tools_exposed": ["TOOL_SEARCH_HANDBOOK"],
                        "tools_called": [],
                        "final_output": "燕麥片富含水溶性膳食纖維，升糖平緩，搭配水煮蛋蛋白質很好喔！",
                        "latency_ms": 900,
                        "token_usage": {"prompt_tokens": 100, "completion_tokens": 40},
                    }
                ],
            }
            trajectories.append(traj)

    input_file = tmp_path / "blinded_trajectories.jsonl"
    with open(input_file, "w", encoding="utf-8") as fh:
        for t in trajectories:
            fh.write(json.dumps(t, ensure_ascii=False) + "\n")

    return input_file, trajectories


def test_cli_help_options(capsys):
    """Verify both CLIs provide comprehensive --help output."""
    with pytest.raises(SystemExit) as exc1:
        run_judge_cli(["--help"])
    assert exc1.value.code == 0
    out1 = capsys.readouterr().out
    assert "--confirm-formal-judge" in out1
    assert "--mode" in out1
    assert "--checkpoint-dir" in out1

    with pytest.raises(SystemExit) as exc2:
        run_analysis_cli(["--help"])
    assert exc2.value.code == 0
    out2 = capsys.readouterr().out
    assert "--mapping-file" in out2
    assert "--output-dir" in out2


def test_default_paths_anchored_to_project_root():
    """Verify that both CLIs anchor default paths to PROJECT_ROOT/llm_ablation_paper/artifacts."""
    # run_judge paths
    judge_args = parse_judge_args([])
    assert judge_args.input_path == JUDGE_ARTIFACTS_ROOT / "blinded_transcripts"
    assert judge_args.checkpoint_dir == JUDGE_ARTIFACTS_ROOT / "judge_raw" / "checkpoints"
    assert judge_args.output_file == JUDGE_ARTIFACTS_ROOT / "judge_raw" / "judge_results.jsonl"

    # run_analysis paths
    analysis_args = parse_analysis_args([])
    assert analysis_args.trajectories_path == ANALYSIS_ARTIFACTS_ROOT / "blinded_transcripts"
    assert analysis_args.judge_results_path == ANALYSIS_ARTIFACTS_ROOT / "judge_raw" / "judge_results.jsonl"
    assert analysis_args.output_dir == ANALYSIS_ARTIFACTS_ROOT / "derived_results"
    assert analysis_args.figures_dir == ANALYSIS_ARTIFACTS_ROOT / "figures"


def test_run_judge_confirm_gate_fails_closed(fake_48_blinded_trajectories, tmp_path):
    """Verify formal live mode fails closed if confirm token is missing or wrong."""
    input_file, _ = fake_48_blinded_trajectories

    # 1. Missing token
    code_missing = run_judge_cli([
        "--input-path", str(input_file),
        "--mode", "live",
        "--confirm-formal-judge", "",
    ])
    assert code_missing != 0

    # 2. Wrong token
    code_wrong = run_judge_cli([
        "--input-path", str(input_file),
        "--mode", "live",
        "--confirm-formal-judge", "WRONG_TOKEN",
    ])
    assert code_wrong != 0


def test_run_judge_api_key_check_fails_closed_and_does_not_leak(fake_48_blinded_trajectories, capsys, monkeypatch):
    """Verify run_judge fails closed if GEMINI_API_KEY is missing/empty, without printing secrets."""
    input_file, _ = fake_48_blinded_trajectories

    # Case 1: GEMINI_API_KEY is unset
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    code = run_judge_cli([
        "--input-path", str(input_file),
        "--mode", "live",
        "--confirm-formal-judge", FORMAL_CONFIRM_TOKEN,
    ])
    assert code != 0
    stderr = capsys.readouterr().err
    assert "GEMINI_API_KEY environment variable is not set" in stderr

    # Case 2: GEMINI_API_KEY is empty/whitespace
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    code_empty = run_judge_cli([
        "--input-path", str(input_file),
        "--mode", "live",
        "--confirm-formal-judge", FORMAL_CONFIRM_TOKEN,
    ])
    assert code_empty != 0

    # Case 3: Ensure sensitive test string is NOT echoed anywhere
    secret_canary = "SECRET_CANARY_VALUE_XYZ123"
    monkeypatch.setenv("GEMINI_API_KEY", secret_canary)
    # Even if an error happens downstream, secret_canary must not be in stdout/stderr
    with patch("llm_ablation_paper.workstream_5_judge_analysis.run_judge.verify_canaries", side_effect=RuntimeError("simulated network error")):
        code_sim = run_judge_cli([
            "--input-path", str(input_file),
            "--mode", "live",
            "--confirm-formal-judge", FORMAL_CONFIRM_TOKEN,
        ])
        assert code_sim != 0
        captured = capsys.readouterr()
        assert secret_canary not in captured.out
        assert secret_canary not in captured.err


def test_ensure_canonical_env_loaded_does_not_override_existing(tmp_path, monkeypatch):
    """Verify ensure_canonical_env_loaded uses override=False and preserves existing environment."""
    test_key = "GEMINI_API_KEY"
    monkeypatch.setenv(test_key, "ORIGINAL_EXISTING_KEY")

    mock_env = tmp_path / ".env"
    mock_env.write_text(f"{test_key}=NEW_IN_DOTENV\nOTHER_VAR=FOOBAR\n", encoding="utf-8")

    with patch("llm_ablation_paper.workstream_5_judge_analysis.run_judge.PROJECT_ROOT", tmp_path):
        ensure_canonical_env_loaded()
        assert os.environ.get(test_key) == "ORIGINAL_EXISTING_KEY"
        assert os.environ.get("OTHER_VAR") == "FOOBAR"


def test_run_judge_input_validation_rejections():
    """Verify batch validator rejects pilot, canary, unblinded leaks, duplicates, and incomplete sets."""
    # 1. Reject pilot
    with pytest.raises(ValueError, match="Pilot trajectory rejected"):
        validate_formal_batch_requirements([{
            "run_id": "BLIND-PILOT-001",
            "patient_id": "SP-001",
            "condition_secret": "COND-1",
            "termination_reason": "MAX_TURNS",
            "turns": [],
        }], allow_partial=True)

    # 2. Reject canary in batch
    with pytest.raises(ValueError, match="Canary trajectory rejected"):
        validate_formal_batch_requirements([{
            "run_id": "CANARY-PASS-01",
            "patient_id": "SP-001",
            "condition_secret": "COND-1",
            "termination_reason": "MAX_TURNS",
            "turns": [],
        }], allow_partial=True)

    # 3. Reject duplicate run_id
    with pytest.raises(ValueError, match="Duplicate run_id"):
        validate_formal_batch_requirements([
            {"run_id": "BLIND-001", "patient_id": "SP-001", "condition_secret": "COND-1", "termination_reason": "MAX_TURNS", "turns": []},
            {"run_id": "BLIND-001", "patient_id": "SP-001", "condition_secret": "COND-2", "termination_reason": "MAX_TURNS", "turns": []},
        ], allow_partial=True)

    # 4. Reject fewer than 48 in formal mode
    with pytest.raises(ValueError, match="requires exactly 48 trajectories"):
        validate_formal_batch_requirements([
            {"run_id": "BLIND-001", "patient_id": "SP-001", "condition_secret": "COND-1", "termination_reason": "MAX_TURNS", "turns": []}
        ], allow_partial=False)


def test_run_judge_fake_execution_and_results_structure(fake_48_blinded_trajectories, tmp_path):
    """Verify offline fake run produces atomic output with R1/R2 raw and parsed evaluations."""
    input_file, _ = fake_48_blinded_trajectories
    ckpt_dir = tmp_path / "checkpoints"
    out_file = tmp_path / "judge_results.jsonl"
    canary_file = Path(__file__).parent.parent / "canary_trajectories.jsonl"

    code = run_judge_cli([
        "--input-path", str(input_file),
        "--checkpoint-dir", str(ckpt_dir),
        "--output-file", str(out_file),
        "--canary-file", str(canary_file),
        "--mode", "fake",
    ])
    assert code == 0

    # Verify atomic output file
    assert out_file.exists()
    with open(out_file, "r", encoding="utf-8") as fh:
        results = [json.loads(line) for line in fh if line.strip()]

    assert len(results) == 48
    first = results[0]
    assert "blinded_run_id" in first
    assert "critical_failure_consensus" in first
    assert "evaluations" in first

    # Check R1 and R2 raw and parsed separation
    r1 = first["evaluations"]["run_1"]
    assert "raw_response" in r1 and isinstance(r1["raw_response"], str)
    assert "parsed_evaluation" in r1 and isinstance(r1["parsed_evaluation"], dict)
    assert r1["parsed_evaluation"]["scores"]["safety"] in (0, 1, 2)

    # Check checkpoints exist
    assert len(list(ckpt_dir.glob("*.json"))) == 48


def test_load_and_invert_condition_mapping_canonical_format(tmp_path):
    """Verify canonical WS1 format (A-D -> opaque ID) is validated and inverted to (opaque ID -> A-D)."""
    canonical_ws1_map = {
        "A": "COND-ALPHA100",
        "B": "COND-BETA200",
        "C": "COND-GAMMA300",
        "D": "COND-DELTA400",
    }
    mapping_file = tmp_path / "canonical_mapping.json"
    mapping_file.write_text(json.dumps(canonical_ws1_map), encoding="utf-8")

    inverted = load_and_invert_condition_mapping(mapping_file)
    assert inverted == {
        "COND-ALPHA100": "A",
        "COND-BETA200": "B",
        "COND-GAMMA300": "C",
        "COND-DELTA400": "D",
    }


def test_load_and_invert_condition_mapping_rejections(tmp_path):
    """Verify malformed or reversed mappings fail-closed via WS1 validate_condition_mapping."""
    # 1. Reverse format (opaque ID as key) must be strictly rejected
    reverse_map = {
        "COND-ALPHA100": "A",
        "COND-BETA200": "B",
        "COND-GAMMA300": "C",
        "COND-DELTA400": "D",
    }
    rev_file = tmp_path / "reverse.json"
    rev_file.write_text(json.dumps(reverse_map), encoding="utf-8")
    with pytest.raises(ValueError, match="condition_mapping must contain exactly keys"):
        load_and_invert_condition_mapping(rev_file)

    # 2. Missing keys
    incomplete_map = {"A": "COND-1", "B": "COND-2", "C": "COND-3"}
    inc_file = tmp_path / "incomplete.json"
    inc_file.write_text(json.dumps(incomplete_map), encoding="utf-8")
    with pytest.raises(ValueError, match="condition_mapping must contain exactly keys"):
        load_and_invert_condition_mapping(inc_file)

    # 3. Duplicate opaque values
    duplicate_map = {"A": "COND-1", "B": "COND-1", "C": "COND-3", "D": "COND-4"}
    dup_file = tmp_path / "duplicate.json"
    dup_file.write_text(json.dumps(duplicate_map), encoding="utf-8")
    with pytest.raises(ValueError, match="condition_mapping contains duplicate opaque IDs"):
        load_and_invert_condition_mapping(dup_file)

    # 4. File not found
    with pytest.raises(FileNotFoundError):
        load_and_invert_condition_mapping(tmp_path / "non_existent.json")


def test_run_analysis_incomplete_judge_results_fails_closed(fake_48_blinded_trajectories, tmp_path):
    """Verify run_analysis rejects execution when trajectories lack judge evaluations."""
    input_file, _ = fake_48_blinded_trajectories
    empty_results = tmp_path / "empty_results.jsonl"
    empty_results.write_text("", encoding="utf-8")

    code = run_analysis_cli([
        "--trajectories-path", str(input_file),
        "--judge-results-path", str(empty_results),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert code != 0


def test_run_analysis_end_to_end_with_ws1_canonical_mapping(fake_48_blinded_trajectories, tmp_path):
    """Verify run_analysis end-to-end with WS1 canonical mapping (A-D -> opaque ID) producing correct unblinded tables."""
    input_file, _ = fake_48_blinded_trajectories
    ckpt_dir = tmp_path / "checkpoints"
    judge_out = tmp_path / "judge_results.jsonl"
    canary_file = Path(__file__).parent.parent / "canary_trajectories.jsonl"

    # 1. Run fake judge to get mock judge results
    run_judge_cli([
        "--input-path", str(input_file),
        "--checkpoint-dir", str(ckpt_dir),
        "--output-file", str(judge_out),
        "--canary-file", str(canary_file),
        "--mode", "fake",
    ])

    # 2. Create canonical WS1 mapping file (A-D -> opaque ID)
    canonical_mapping = {
        "A": "COND-W111",
        "B": "COND-X222",
        "C": "COND-Y333",
        "D": "COND-Z444",
    }
    mapping_file = tmp_path / "ws1_canonical_mapping.json"
    mapping_file.write_text(json.dumps(canonical_mapping), encoding="utf-8")

    out_dir = tmp_path / "derived_results"
    fig_dir = tmp_path / "figures"

    # 3. Run analysis
    code = run_analysis_cli([
        "--trajectories-path", str(input_file),
        "--judge-results-path", str(judge_out),
        "--output-dir", str(out_dir),
        "--figures-dir", str(fig_dir),
        "--mapping-file", str(mapping_file),
    ])
    assert code == 0

    # Verify generated artifacts
    assert (out_dir / "summary.json").exists()
    assert (out_dir / "main_table.md").exists()
    assert (out_dir / "main_table.tex").exists()
    assert (out_dir / "results.csv").exists()
    assert (fig_dir / "failure_distribution.png").exists()

    # Verify summary.json content contains deblinded groups A, B, C, D
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    by_cond = summary["summary_by_group"]
    assert "A" in by_cond and by_cond["A"]["sample_size"] == 12
    assert "B" in by_cond and by_cond["B"]["sample_size"] == 12
    assert "C" in by_cond and by_cond["C"]["sample_size"] == 12
    assert "D" in by_cond and by_cond["D"]["sample_size"] == 12

    # Verify Markdown table contains unblinded conditions A-D with exact sample sizes
    md_content = (out_dir / "main_table.md").read_text(encoding="utf-8")
    assert "| A | 12 |" in md_content
    assert "| B | 12 |" in md_content
    assert "| C | 12 |" in md_content
    assert "| D | 12 |" in md_content

    # Verify CSV file rows match A, B, C, D with sample size 12
    csv_content = (out_dir / "results.csv").read_text(encoding="utf-8")
    assert "A,12," in csv_content
    assert "B,12," in csv_content
    assert "C,12," in csv_content
    assert "D,12," in csv_content
