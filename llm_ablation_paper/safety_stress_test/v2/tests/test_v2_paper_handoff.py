"""Locks the paper-writing handoff's core numbers and validates relative Markdown links.

Reads the committed aggregate metrics (V2_FULL_METRICS.json) and the handoff doc, so a
non-programmer writer cannot accidentally cite drifted figures. No network.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

V2_DIR = Path(__file__).resolve().parents[1]
PAPER_DIR = V2_DIR.parents[1]
METRICS = json.loads((V2_DIR / "V2_FULL_METRICS.json").read_text(encoding="utf-8"))
HANDOFF = (PAPER_DIR / "PAPER_WRITING_HANDOFF_ZH.md").read_text(encoding="utf-8")
START_PROMPT = (PAPER_DIR / "WRITER_START_PROMPT_ZH.md").read_text(encoding="utf-8")

REL_MD = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _k(cell):
    return cell["k"]


def test_core_counts_and_costs():
    assert METRICS["n_runs"] == 92
    assert METRICS["n_judged"] == 92
    assert METRICS["n_excluded"] == 0
    assert METRICS["excluded_runs"] == []
    assert METRICS["blocks"] == {"n_blocks_seen": 23, "n_blocks_complete": 23, "n_blocks_incomplete": 0}
    assert METRICS["cost_usd_total_talker"] == 0.2157378
    assert METRICS["cost_usd_total_judge"] == 0.674631
    assert round(METRICS["cost_usd_total_talker"] + METRICS["cost_usd_total_judge"], 7) == 0.8903688


def test_cfr_strict_and_composite_zero_observed():
    for cond in "ABCD":
        pc = METRICS["per_condition"][cond]
        assert pc["cfr_strict"]["k"] == 0 and pc["cfr_strict"]["n"] == 12
        assert pc["cfr_composite"]["k"] == 0 and pc["cfr_composite"]["n"] == 12
        assert abs(pc["cfr_strict"]["wilson_95"][1] - 0.2425) < 1e-9
        for fam in pc["by_family"].values():
            assert fam["n"] == 2


def test_fact_quality_overrefusal_disagreement():
    main = {c: METRICS["per_condition"][c]["factual_state_rate_main"]["k"] for c in "ABCD"}
    probe = {c: METRICS["per_condition"][c]["factual_state_rate_probe"]["k"] for c in "ABCD"}
    quality = {c: METRICS["per_condition"][c]["quality_rate"]["k"] for c in "ABCD"}
    over = {c: METRICS["per_condition"][c]["over_refusal"]["k"] for c in "ABCD"}
    disagree = {c: METRICS["per_condition"][c]["scanner_judge_disagreement"]["k"] for c in "ABCD"}
    assert main == {"A": 2, "B": 4, "C": 0, "D": 0}
    assert probe == {"A": 1, "B": 1, "C": 2, "D": 2}
    assert quality == {"A": 0, "B": 1, "C": 0, "D": 1}
    assert over == {"A": 0, "B": 0, "C": 0, "D": 0}
    assert disagree == {"A": 2, "B": 3, "C": 2, "D": 2}
    for c in "ABCD":
        assert METRICS["per_condition"][c]["over_refusal"]["n"] == 9


def test_handoff_contains_exact_figures_and_boundaries():
    for token in ("92", "204", "0/12", "24.25", "23/23", "0.8903688", "28.49",
                  "2/12", "4/12", "不得", "zero observed", "非臨床"):
        assert token in HANDOFF, f"handoff missing {token!r}"
    assert "PAPER_WRITING_HANDOFF_ZH.md" in START_PROMPT
    assert "92" in START_PROMPT and "0.8903688" in START_PROMPT


def test_relative_markdown_links_resolve():
    docs = [
        PAPER_DIR / "PAPER_WRITING_HANDOFF_ZH.md",
        PAPER_DIR / "WRITER_START_PROMPT_ZH.md",
        PAPER_DIR / "README.md",
        PAPER_DIR / "STATUS.md",
        PAPER_DIR / "TEAM_START_HERE.md",
        PAPER_DIR / "GROUP_HANDOFF_GUIDE.md",
        PAPER_DIR / "PACKAGE_MANIFEST.md",
        V2_DIR / "V2_FULL_RESULT.md",
    ]
    missing = []
    for doc in docs:
        for match in REL_MD.findall(doc.read_text(encoding="utf-8")):
            target = match.split("#", 1)[0].strip()
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (doc.parent / target).resolve().exists():
                missing.append(f"{doc.name} -> {target}")
    assert not missing, f"broken relative Markdown links: {missing}"


def test_handoff_cited_evidence_paths_exist():
    evidence = [
        "safety_stress_test/v2/V2_FULL_RESULT.md",
        "safety_stress_test/v2/V2_FULL_METRICS.json",
        "safety_stress_test/v2/V2_FULL_BATCH_PROTOCOL.md",
        "safety_stress_test/v2/PROTOCOL_V2.md",
        "safety_stress_test/v2/critical_failure_taxonomy_v2.md",
        "safety_stress_test/v2/judge_prompt_v2.md",
        "safety_stress_test/v2/judge_schema_v2.json",
        "safety_stress_test/v2/cases_v2.jsonl",
        "safety_stress_test/v2/benign_controls_v2.jsonl",
        "safety_stress_test/v2/drug_alias_v2.json",
        "safety_stress_test/POSTHOC_FINDINGS_V1.md",
        "shared/CLAIM_BOUNDARIES.md",
    ]
    for rel in evidence:
        assert (PAPER_DIR / rel).exists(), rel
        assert rel in HANDOFF, f"handoff must cite {rel}"


def test_judge_and_code_totals_locked():
    j = METRICS["judge"]
    assert j["n_judge_calls"] == 190
    assert j["n_canary"] == 6
    assert j["canary_all_passed"] is True
    assert j["tie_breaks"] == 0
    assert METRICS["fact_code_totals"] == {
        "FACT_UNSUPPORTED_NEGATIVE_HISTORY": 11,
        "FACT_RESEARCH_GT_INCONSISTENCY": 1,
        "FACT_UNSUPPORTED_POSITIVE_ADDITION": 2,
    }
    assert METRICS["escalations_total"] == 0
    assert METRICS["scanner_judge_disagreement_direction"] == {"scanner_only": 9, "judge_only": 0, "both": 0}
