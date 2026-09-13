"""v1 immutability: frozen v1 files must be byte-identical to the frozen tag."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
TAG = "llm-ablation-safety-live-judge-pilot-v1"

FROZEN_FILES = [
    "llm_ablation_paper/safety_stress_test/cases.jsonl",
    "llm_ablation_paper/safety_stress_test/benign_controls.jsonl",
    "llm_ablation_paper/safety_stress_test/canaries.jsonl",
    "llm_ablation_paper/safety_stress_test/case_schema.json",
    "llm_ablation_paper/safety_stress_test/rule_based_scanner.py",
    "llm_ablation_paper/safety_stress_test/runner.py",
    "llm_ablation_paper/safety_stress_test/live_runner.py",
    "llm_ablation_paper/safety_stress_test/live_judge_pilot.py",
    "llm_ablation_paper/safety_stress_test/validate_cases.py",
    "llm_ablation_paper/safety_stress_test/analysis.py",
    "llm_ablation_paper/safety_stress_test/STRESS_TEST_PROTOCOL.md",
    "llm_ablation_paper/safety_stress_test/SCANNER_RULES_CHANGELOG.md",
    "llm_ablation_paper/workstream_5_judge_analysis/judge_prompt.md",
    "llm_ablation_paper/workstream_5_judge_analysis/judge_schema.json",
    "llm_ablation_paper/workstream_5_judge_analysis/critical_failure_taxonomy.md",
]


@pytest.mark.parametrize("rel", FROZEN_FILES)
def test_v1_file_unchanged_vs_frozen_tag(rel):
    proc = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{TAG}:{rel}"],
        capture_output=True,
    )
    assert proc.returncode == 0, f"cannot read frozen tag for {rel}"
    current = (REPO / rel).read_bytes()
    assert current == proc.stdout, f"frozen v1 file modified: {rel}"


def test_scanner_and_tag_versions_are_independent():
    from llm_ablation_paper.safety_stress_test import rule_based_scanner as S1
    from llm_ablation_paper.safety_stress_test.v2 import rule_based_scanner_v2 as S2

    assert S1.RULES_VERSION == "sst-v1.0.1-posthoc"
    assert S2.RULES_VERSION == "sst-v2.0"
