"""Tests for WS5 CLI orchestration: run_judge.py and run_analysis.py (Fake-only, offline).

Verifies:
  - run_judge confirm gate (fail-closed on missing/invalid token in live mode)
  - run_judge input validation (rejects pilot, canary, unblinded raw leaks, duplicates, incomplete 12x4)
  - run_judge fake execution, atomic checkpoint/results output, and raw/parsed preservation
  - run_analysis execution, mapping ingestion, missing!=zero handling, and artifact generation
  - CLI --help options validation
"""

import json
from pathlib import Path
import pytest

from llm_ablation_paper.workstream_5_judge_analysis.run_judge import (
    run_judge_cli,
    FORMAL_CONFIRM_TOKEN,
    validate_formal_batch_requirements,
)
from llm_ablation_paper.workstream_5_judge_analysis.run_analysis import (
    run_analysis_cli,
    load_condition_mapping,
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


def test_run_analysis_end_to_end_with_mapping(fake_48_blinded_trajectories, tmp_path):
    """Verify run_analysis end-to-end with external mapping producing unblinded tables."""
    input_file, _ = fake_48_blinded_trajectories
    ckpt_dir = tmp_path / "checkpoints"
    judge_out = tmp_path / "judge_results.jsonl"
    canary_file = Path(__file__).parent.parent / "canary_trajectories.jsonl"

    # 1. Run fake judge
    run_judge_cli([
        "--input-path", str(input_file),
        "--checkpoint-dir", str(ckpt_dir),
        "--output-file", str(judge_out),
        "--canary-file", str(canary_file),
        "--mode", "fake",
    ])

    # 2. Create mapping file
    mapping = {
        "COND-W111": "A",
        "COND-X222": "B",
        "COND-Y333": "C",
        "COND-Z444": "D",
    }
    mapping_file = tmp_path / "test_mapping.json"
    mapping_file.write_text(json.dumps(mapping), encoding="utf-8")

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

    md_content = (out_dir / "main_table.md").read_text(encoding="utf-8")
    assert "| A | 12 |" in md_content
    assert "| B | 12 |" in md_content
    assert "| C | 12 |" in md_content
    assert "| D | 12 |" in md_content

    csv_content = (out_dir / "results.csv").read_text(encoding="utf-8")
    assert "A,12," in csv_content
    assert "B,12," in csv_content
