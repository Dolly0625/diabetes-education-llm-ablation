"""Locks the 4-person writing-task package: required sections, fixed numbers, relative links.

No network. Ensures a non-programmer team cannot ship task briefs with missing scope,
missing boundaries, drifted numbers, or broken relative paths.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PAPER_DIR = Path(__file__).resolve().parents[3]
WT = PAPER_DIR / "writing_tasks"
TASKS = [
    "writer_1_intro_related_work.md",
    "writer_2_system_ablation_method.md",
    "writer_3_dataset_evaluation_results.md",
    "writer_4_discussion_integration.md",
]
REQUIRED_SECTIONS = ["負責", "不負責", "必讀", "固定數字", "禁止主張", "交付檔名", "引用占位", "圖表責任", "完成定義", "prompt"]
BACKTICK_REL = re.compile(r"`((?:\.\.?/)[^`\s]+\.(?:md|json|jsonl))`")
REL_MD = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
REPO_ROOT_REF = re.compile(r"`(llm_ablation_paper/[^`\s]+\.(?:md|json|jsonl))`")
METRICS = json.loads((PAPER_DIR / "safety_stress_test" / "v2" / "V2_FULL_METRICS.json").read_text(encoding="utf-8"))


def test_files_exist():
    assert (WT / "README.md").exists()
    for name in TASKS:
        assert (WT / name).exists(), name


def test_each_task_has_required_sections():
    for name in TASKS:
        text = (WT / name).read_text(encoding="utf-8")
        for section in REQUIRED_SECTIONS:
            assert section in text, f"{name} missing section marker {section!r}"


def test_readme_has_claim_dependency_return():
    readme = (WT / "README.md").read_text(encoding="utf-8")
    for token in ("認領表", "branch", "依賴順序", "回傳方式", "避免重複", "尚未被認領"):
        assert token in readme, f"README missing {token!r}"
    for name in TASKS:
        assert name in readme, name


def test_fixed_numbers_present_and_consistent():
    readme = (WT / "README.md").read_text(encoding="utf-8")
    w3 = (WT / "writer_3_dataset_evaluation_results.md").read_text(encoding="utf-8")
    for token in ("92/92", "204", "23/23", "0/12", "24.25", "A **2**", "0.8903688", "28.49"):
        assert token in readme, f"README missing fixed number {token!r}"
    for token in ("0/12", "24.25", "0.8903688", "28.49", "190", "6/6"):
        assert token in w3, f"writer_3 missing fixed number {token!r}"
    w4 = (WT / "writer_4_discussion_integration.md").read_text(encoding="utf-8")
    assert "0/12" in w4 and "0.8903688" in w4


def test_backticked_relative_paths_resolve():
    missing = []
    for path in [WT / "README.md"] + [WT / n for n in TASKS]:
        for match in BACKTICK_REL.findall(path.read_text(encoding="utf-8")):
            target = match.split("#", 1)[0].strip()
            if not (WT / target).resolve().exists():
                missing.append(f"{path.name} -> {match}")
    assert not missing, f"broken relative paths: {missing}"


def test_strict_markdown_links_resolve():
    missing = []
    for path in [WT / "README.md"] + [WT / n for n in TASKS]:
        for match in REL_MD.findall(path.read_text(encoding="utf-8")):
            target = match.split("#", 1)[0].strip()
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (path.parent / target).resolve().exists():
                missing.append(f"{path.name} -> {target}")
    assert not missing, f"broken markdown links: {missing}"


def test_handoff_and_start_prompt_point_to_writing_tasks():
    handoff = (PAPER_DIR / "PAPER_WRITING_HANDOFF_ZH.md").read_text(encoding="utf-8")
    start = (PAPER_DIR / "WRITER_START_PROMPT_ZH.md").read_text(encoding="utf-8")
    assert "writing_tasks/README.md" in handoff
    assert "writing_tasks/README.md" in start
    for name in TASKS:
        assert name in start, name


def test_page_budget_locked():
    readme = (WT / "README.md").read_text(encoding="utf-8")
    for token in ("2.5", "2.2", "3.3", "2.6", "1.4", "12.0"):
        assert token in readme, f"README missing page budget {token!r}"
    w1 = (WT / "writer_1_intro_related_work.md").read_text(encoding="utf-8")
    assert "1.1" in w1 and "1.4" in w1
    for name in TASKS:
        assert "預估頁數" in (WT / name).read_text(encoding="utf-8"), name


def test_related_work_threads_and_literature_rules():
    w1 = (WT / "writer_1_intro_related_work.md").read_text(encoding="utf-8")
    for token in ("模擬病患", "adversarial", "tool gating", "LLM-as-a-Judge",
                  "LITERATURE_EVALUATION_METHODS_ZH.md", "不可引用", "不可發明 DOI",
                  "12–18", "研究缺口", "scanner–judge", "至少四個脈絡"):
        assert token in w1, f"writer_1 missing literature rule {token!r}"


def test_writer4_page_and_reference_rules():
    w4 = (WT / "writer_4_discussion_integration.md").read_text(encoding="utf-8")
    for token in ("不得靠刪除限制段落壓頁", "精簡重複背景", "可擴充版本", "不得自行假設"):
        assert token in w4, f"writer_4 missing {token!r}"


def test_review_rules_section():
    readme = (WT / "README.md").read_text(encoding="utf-8")
    for token in ("Review 檢查規則", "不得靠刪除限制段落壓頁", "LITERATURE_EVALUATION_METHODS_ZH.md",
                  "Introduction ≈1.1 頁", "Related Work ≈1.4 頁"):
        assert token in readme, f"README review rules missing {token!r}"


def test_narrative_blueprint_locked():
    bp = (PAPER_DIR / "PAPER_NARRATIVE_BLUEPRINT_ZH.md").read_text(encoding="utf-8")
    for token in ("錯誤分布", "非單調", "error redistribution", "context-dependent safeguards",
                  "不得因小樣本做因果推論", "不得宣稱 D 最佳", "三種禁止敘事",
                  "200–250", "英文摘要寫作骨架", "12 頁"):
        assert token in bp, f"blueprint missing {token!r}"


def test_forbidden_narratives_present():
    readme = (WT / "README.md").read_text(encoding="utf-8")
    for token in ("zero failure 等於安全", "LLM judge 等於醫師", "v1/v2/12×4 pooled"):
        assert token in readme, f"README missing forbidden-narrative {token!r}"


def test_blueprint_linked_everywhere():
    for rel in ("PAPER_WRITING_HANDOFF_ZH.md", "WRITER_START_PROMPT_ZH.md"):
        assert "PAPER_NARRATIVE_BLUEPRINT_ZH.md" in (PAPER_DIR / rel).read_text(encoding="utf-8"), rel
    assert "PAPER_NARRATIVE_BLUEPRINT_ZH.md" in (WT / "README.md").read_text(encoding="utf-8")
    for name in TASKS:
        assert "PAPER_NARRATIVE_BLUEPRINT_ZH.md" in (WT / name).read_text(encoding="utf-8"), name


ALL_DOCS = [WT / "README.md"] + [WT / n for n in TASKS] + [
    PAPER_DIR / "PAPER_NARRATIVE_BLUEPRINT_ZH.md",
    PAPER_DIR / "PAPER_WRITING_HANDOFF_ZH.md",
    PAPER_DIR / "WRITER_START_PROMPT_ZH.md",
]


def test_cross_doc_backticked_paths_resolve_or_future():
    missing = []
    for doc in ALL_DOCS:
        text = doc.read_text(encoding="utf-8")
        for match in BACKTICK_REL.findall(text):
            target = match.split("#", 1)[0].strip()
            if target.startswith("drafts/"):
                continue
            candidates = [(doc.parent / target).resolve(), (PAPER_DIR.parent / target).resolve()]
            if not any(c.exists() for c in candidates):
                missing.append(f"{doc.name} -> {target}")
        for match in REPO_ROOT_REF.findall(text):
            if not (PAPER_DIR.parent / match).exists():
                missing.append(f"{doc.name} -> {match}")
    assert not missing, f"broken cross-doc paths: {missing}"


def test_numbers_match_metrics_json():
    pc = METRICS["per_condition"]
    assert all(pc[c]["cfr_strict"]["k"] == 0 and pc[c]["cfr_strict"]["n"] == 12 for c in "ABCD")
    assert all(pc[c]["cfr_composite"]["k"] == 0 and pc[c]["cfr_composite"]["n"] == 12 for c in "ABCD")
    assert {c: pc[c]["factual_state_rate_main"]["k"] for c in "ABCD"} == {"A": 2, "B": 4, "C": 0, "D": 0}
    assert {c: pc[c]["factual_state_rate_probe"]["k"] for c in "ABCD"} == {"A": 1, "B": 1, "C": 2, "D": 2}
    assert {c: pc[c]["quality_rate"]["k"] for c in "ABCD"} == {"A": 0, "B": 1, "C": 0, "D": 1}
    assert {c: pc[c]["over_refusal"]["k"] for c in "ABCD"} == {"A": 0, "B": 0, "C": 0, "D": 0}
    assert all(pc[c]["over_refusal"]["n"] == 9 for c in "ABCD")
    assert {c: pc[c]["scanner_judge_disagreement"]["k"] for c in "ABCD"} == {"A": 2, "B": 3, "C": 2, "D": 2}
    assert METRICS["judge"]["n_judge_calls"] == 190 and METRICS["judge"]["tie_breaks"] == 0
    assert METRICS["blocks"]["n_blocks_complete"] == 23


def test_writer3_pairs_strict_and_composite():
    w3 = (WT / "writer_3_dataset_evaluation_results.md").read_text(encoding="utf-8")
    for token in ("CFR_strict", "CFR_composite", "24.25", "0/12"):
        assert token in w3, token
