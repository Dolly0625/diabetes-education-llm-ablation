"""Claim-boundary enforcement tests on the generated report."""
from __future__ import annotations

from pathlib import Path

import pytest

from llm_ablation_paper.safety_stress_test import analysis as A
from llm_ablation_paper.safety_stress_test import runner as R

FORBIDDEN_UNQUALIFIED = [
    "臨床驗證",
    "真人病患",
    "降低住院",
    "100%安全",
    "完全無幻覺",
    "等同醫師",
    "零風險",
    "測試通過率等於臨床安全率",
]

MANDATORY = [
    "Zero observed is not zero risk",
    "Canaries",
    "pipeline",
    "非預先註冊",
    "Wilson",
    "非臨床事實",
]


def test_result_md_disclaimers(tmp_path: Path):
    dry_root = tmp_path / "dry"
    summary = R.run_fake_dry_run(dry_root, case_limit=1, benign_limit=1)
    A.analyze_dry_run(dry_root, summary)
    result_md = dry_root / "RESULT.md"
    assert result_md.exists()
    text = result_md.read_text(encoding="utf-8")
    for phrase in MANDATORY:
        assert phrase in text, f"missing mandatory disclaimer: {phrase}"
    for phrase in FORBIDDEN_UNQUALIFIED:
        assert phrase not in text, f"forbidden overclaim present: {phrase}"


def test_metrics_json_missing_not_zero(tmp_path: Path):
    dry_root = tmp_path / "dry2"
    summary = R.run_fake_dry_run(dry_root, case_limit=1, benign_limit=1)
    agg = A.analyze_dry_run(dry_root, summary)
    # every rate carries its own N and a Wilson interval; zero-denominator is null not 0.0
    for cond, m in agg["per_condition"].items():
        assert "wilson_95" in m["cfr_judge"]
        assert m["cfr_judge"]["n"] >= 0
        if m["cfr_judge"]["n"] == 0:
            assert m["cfr_judge"]["rate"] is None


def test_wilson_zero_observed_has_upper_bound():
    lo, hi = A.wilson(0, 12)
    assert lo == 0.0
    assert hi is not None and 0.20 < hi < 0.30  # ~24.2%
