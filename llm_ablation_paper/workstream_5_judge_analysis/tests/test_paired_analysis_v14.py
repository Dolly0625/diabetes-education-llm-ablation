# -*- coding: utf-8 -*-
"""PHASE M5 配對統計分析與結果藍圖之單元與整合測試套件。

驗證項目：
1. 合成數據驗證：Friedman、Wilcoxon、Rank-Biserial、Holm、Cochran's Q、Exact McNemar 及其退化偵測。
2. 正式產物驗證：results/v14/paired_analysis/ 檔案完整性、A–D 各組 N=12、零缺漏值、與 summary.json 描述性對齊。
3. 機密掃描：確保正式公開產物零金鑰、零 COND-、零 raw_response、零絕對路徑。
"""

import csv
import json
import re
from pathlib import Path
import numpy as np
import pytest

from llm_ablation_paper.workstream_5_judge_analysis.paired_analysis_v14 import (
    calculate_descriptive_stats,
    run_omnibus_friedman,
    calculate_rank_biserial,
    run_pairwise_wilcoxon,
    apply_holm_bonferroni,
    run_cochran_q,
    run_pairwise_mcnemar,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PAIRED_ANALYSIS_DIR = REPO_ROOT / "llm_ablation_paper" / "results" / "v14" / "paired_analysis"
SUMMARY_V14_PATH = REPO_ROOT / "llm_ablation_paper" / "results" / "v14" / "summary.json"


# ==============================================================================
# 1. 合成數據檢定邏輯與退化偵測單元測試
# ==============================================================================

def test_friedman_synthetic_normal_and_degenerate():
    """驗證 Friedman 檢定在正常有變異數據與常數退化數據之表現。"""
    # 正常有顯著差異之數據
    normal_data = {
        "A": [1.0, 1.2, 1.1, 1.0, 1.3, 1.1, 1.2, 1.0, 1.1, 1.3, 1.2, 1.1],
        "B": [2.0, 2.2, 2.1, 2.0, 2.3, 2.1, 2.2, 2.0, 2.1, 2.3, 2.2, 2.1],
        "C": [3.0, 3.2, 3.1, 3.0, 3.3, 3.1, 3.2, 3.0, 3.1, 3.3, 3.2, 3.1],
        "D": [4.0, 4.2, 4.1, 4.0, 4.3, 4.1, 4.2, 4.0, 4.1, 4.3, 4.2, 4.1],
    }
    res_normal = run_omnibus_friedman(normal_data)
    assert res_normal["status"] == "TESTED"
    assert res_normal["statistic"] is not None
    assert res_normal["p_value"] < 0.001

    # 退化情況 1: 全體所有值完全為同一常數 (如 Safety 分數全 2.0)
    degenerate_all_same = {
        c: [2.0] * 12 for c in ["A", "B", "C", "D"]
    }
    res_degen1 = run_omnibus_friedman(degenerate_all_same)
    assert res_degen1["status"] == "DEGENERATE_NOT_TESTABLE"
    assert res_degen1["statistic"] is None
    assert res_degen1["p_value"] is None, "退化檢定嚴禁輸出 p=0"

    # 退化情況 2: 每位病人在 4 個條件下完全相同
    degenerate_patient_same = {
        "A": [1.0, 2.0, 3.0, 4.0, 1.0, 2.0, 3.0, 4.0, 1.0, 2.0, 3.0, 4.0],
        "B": [1.0, 2.0, 3.0, 4.0, 1.0, 2.0, 3.0, 4.0, 1.0, 2.0, 3.0, 4.0],
        "C": [1.0, 2.0, 3.0, 4.0, 1.0, 2.0, 3.0, 4.0, 1.0, 2.0, 3.0, 4.0],
        "D": [1.0, 2.0, 3.0, 4.0, 1.0, 2.0, 3.0, 4.0, 1.0, 2.0, 3.0, 4.0],
    }
    res_degen2 = run_omnibus_friedman(degenerate_patient_same)
    assert res_degen2["status"] == "DEGENERATE_NOT_TESTABLE"
    assert res_degen2["p_value"] is None


def test_wilcoxon_and_rank_biserial_synthetic():
    """驗證成對 Wilcoxon 檢定與 Matched-Pairs Rank-Biserial Correlation 計算。"""
    # 全正差值
    x = [2.0, 3.0, 4.0, 5.0, 6.0]
    y = [1.0, 2.0, 3.0, 4.0, 5.0]
    r_pos, n_pos = calculate_rank_biserial(x, y)
    assert r_pos == pytest.approx(1.0)
    assert n_pos == 5

    # 全負差值
    r_neg, n_neg = calculate_rank_biserial(y, x)
    assert r_neg == pytest.approx(-1.0)
    assert n_neg == 5

    # 全差為 0 (無變異)
    r_zero, n_zero = calculate_rank_biserial(x, x)
    assert r_zero == 0.0
    assert n_zero == 0

    cond_vecs = {"A": x, "B": x}
    pw_res = run_pairwise_wilcoxon(cond_vecs, [("A", "B")])
    assert pw_res["A-B"]["status"] == "NOT_TESTABLE/NO_VARIATION"
    assert pw_res["A-B"]["raw_p"] is None
    assert pw_res["A-B"]["rank_biserial_r"] == 0.0


def test_holm_bonferroni_synthetic():
    """驗證 Holm-Bonferroni 多重比較校正單調性與乘數遞減邏輯。"""
    pw_dict = {
        "pair_1": {"status": "TESTED", "raw_p": 0.01},
        "pair_2": {"status": "TESTED", "raw_p": 0.04},
        "pair_3": {"status": "TESTED", "raw_p": 0.03},
        "pair_4": {"status": "NOT_TESTABLE/NO_VARIATION", "raw_p": None},
    }
    apply_holm_bonferroni(pw_dict)

    # 3 個可檢定項目:
    # 0.01 * 3 = 0.03
    # 0.03 * 2 = 0.06
    # 0.04 * 1 = 0.04 -> 需維持單調性 max(0.06, 0.04) = 0.06
    assert pw_dict["pair_1"]["adjusted_p"] == pytest.approx(0.03)
    assert pw_dict["pair_3"]["adjusted_p"] == pytest.approx(0.06)
    assert pw_dict["pair_2"]["adjusted_p"] == pytest.approx(0.06)
    assert pw_dict["pair_4"]["adjusted_p"] is None


def test_cochran_q_synthetic_and_degenerate():
    """驗證 Cochran's Q 檢定在二元重複測量及常數退化下之表現。"""
    # 典型有差異矩陣
    # 12 個受試者 x 4 條件
    mat = np.array([
        [1, 1, 0, 0],
        [1, 1, 0, 1],
        [1, 1, 1, 1],
        [1, 1, 0, 0],
        [1, 1, 0, 1],
        [1, 1, 1, 1],
        [1, 1, 0, 0],
        [1, 1, 0, 1],
        [1, 1, 1, 1],
        [1, 1, 0, 0],
        [1, 1, 0, 1],
        [1, 1, 1, 1],
    ])
    res = run_cochran_q(mat)
    assert res["status"] == "TESTED"
    assert res["statistic"] is not None
    assert res["p_value"] is not None
    assert res["df"] == 3

    # 退化矩陣: 全 1
    mat_all_ones = np.ones((12, 4))
    res_degen = run_cochran_q(mat_all_ones)
    assert res_degen["status"] == "NOT_TESTABLE/NO_VARIATION"
    assert res_degen["p_value"] is None


def test_exact_mcnemar_synthetic_and_degenerate():
    """驗證 Exact McNemar 檢定在有分歧與零分歧下之表現。"""
    cond_binary = {
        "A": [1, 1, 1, 1, 0, 0],
        "B": [0, 0, 0, 0, 1, 1],
    }
    # b = 4 (A=1, B=0), c = 2 (A=0, B=1), n_disc = 6
    res = run_pairwise_mcnemar(cond_binary, [("A", "B")])
    assert res["A-B"]["status"] == "TESTED"
    assert res["A-B"]["b_count"] == 4
    assert res["A-B"]["c_count"] == 2
    assert res["A-B"]["n_discordant"] == 6
    assert 0.0 < res["A-B"]["raw_p"] <= 1.0

    # 無分歧配對 (完全一致)
    cond_identical = {
        "A": [1, 1, 1, 0, 0],
        "B": [1, 1, 1, 0, 0],
    }
    res_id = run_pairwise_mcnemar(cond_identical, [("A", "B")])
    assert res_id["A-B"]["status"] == "NOT_TESTABLE/NO_DISCORDANT_PAIRS"
    assert res_id["A-B"]["raw_p"] is None


# ==============================================================================
# 2. 正式輸出產物結構與數值對齊整合測試
# ==============================================================================

def test_formal_output_files_exist_and_non_empty():
    """驗證 results/v14/paired_analysis/ 目錄下所有必要產物皆存在且非空。"""
    assert PAIRED_ANALYSIS_DIR.exists(), f"目錄不存在: {PAIRED_ANALYSIS_DIR}"

    expected_files = [
        "paired_summary.json",
        "paired_tests.csv",
        "scenario_breakdown.csv",
        "paired_effects.md",
        "paired_metrics_plot.png",
        "PAPER_RESULTS_BLUEPRINT.md",
    ]
    for fn in expected_files:
        fp = PAIRED_ANALYSIS_DIR / fn
        assert fp.exists(), f"缺少必要產物檔案: {fn}"
        assert fp.stat().st_size > 0, f"產物檔案為空: {fn}"


def test_formal_output_sample_size_and_alignment_with_summary_json():
    """驗證正式配對摘要與 results/v14/summary.json 的描述性統計完全對齊且 N=12。"""
    summary_path = PAIRED_ANALYSIS_DIR / "paired_summary.json"
    paired_data = json.loads(summary_path.read_text(encoding="utf-8"))

    v14_summary_data = json.loads(SUMMARY_V14_PATH.read_text(encoding="utf-8"))

    conditions = ["A", "B", "C", "D"]
    desc = paired_data["descriptive_statistics"]

    # 1. 驗證所有評審分數對齊 (滿分 2.00 制)
    for c in conditions:
        orig_group = v14_summary_data["summary_by_group"][c]
        assert orig_group["sample_size"] == 12

        for s_key in ["safety", "tool_use", "state_consistency", "dialogue_planning", "helpfulness"]:
            orig_val = orig_group["scores_mean"][s_key]
            paired_val = round(desc[s_key][c]["mean"], 2)
            assert paired_val == orig_val, (
                f"條件 {c} 之 {s_key} 分數不對齊: paired {paired_val} vs orig {orig_val}"
            )

        # 2. 驗證客觀程式指標對齊
        orig_prog = orig_group["programmatic"]
        assert round(desc["avg_questions_per_turn"][c]["mean"], 2) == orig_prog["avg_questions_per_turn"]
        assert round(desc["avg_latency_ms"][c]["mean"], 1) == orig_prog["avg_latency_ms"]
        assert round(desc["total_tokens"][c]["mean"], 1) == orig_prog["avg_tokens_per_trajectory"]
        assert round(desc["model_calls_count"][c]["mean"], 1) == orig_prog["avg_model_calls_per_trajectory"]


def test_formal_scenario_breakdown_constraints():
    """驗證情境細分表符合 6 情境各 2 人 (總計 12 人) 且標註不進行檢定之約束。"""
    sc_csv_path = PAIRED_ANALYSIS_DIR / "scenario_breakdown.csv"
    with sc_csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 6 * 4, f"情境細分表行數必須為 6 情境 x 4 條件 = 24，實得 {len(rows)}"

    scenarios_seen = set()
    for row in rows:
        assert int(row["N_Patients"]) == 2, "每個情境之病患數必須為 2"
        scenarios_seen.add(row["Scenario_Type"])
        assert "嚴禁進行情境內統計顯著性檢定" in row["Analysis_Constraint_Note"]

    expected_scenarios = {
        "DAILY_DIET",
        "MEDICATION_SIDE_EFFECT",
        "MEDICATION_NONADHERENCE",
        "SUBACUTE_HYPOGLYCEMIA",
        "PREVISIT_SUMMARY",
        "FACT_CONTRADICTION",
    }
    assert scenarios_seen == expected_scenarios


def test_formal_output_secret_and_privacy_scanning():
    """機密與敏感資訊掃描：確保公開配對產物零金鑰、零 COND-、零 raw_response、零內部絕對路徑。"""
    text_extensions = {".json", ".csv", ".md"}
    text_files = [p for p in PAIRED_ANALYSIS_DIR.iterdir() if p.suffix.lower() in text_extensions]

    forbidden_patterns = [
        (re.compile(r"AIzaSy[A-Za-z0-9_-]{33}"), "Google API Key 格式"),
        (re.compile(r"\bCOND-[A-Za-z0-9_-]+"), "內部 Opaque 條件代號 (COND-*)"),
        (re.compile(r"raw_response"), "評審模型未脫敏原始回應 (raw_response)"),
        (re.compile(r"/Users/[a-zA-Z0-9_-]+"), "本機內部絕對路徑 (/Users/...)"),
        (re.compile(r"/home/[a-zA-Z0-9_-]+"), "本機內部絕對路徑 (/home/...)"),
        (re.compile(r"WS4-BATCH-SP-\d{3}-[A-D]"), "內部 Run ID 代號"),
        (re.compile(r"ws4_sp-\d{3}_[a-d]_batch"), "內部 User ID 代號"),
    ]

    for p in text_files:
        content = p.read_text(encoding="utf-8")
        for pattern, desc in forbidden_patterns:
            matches = pattern.findall(content)
            assert not matches, f"檔案 {p.name} 偵測到機密或內部敏感字串: {desc}, 匹配項: {matches[:3]}"


def test_ci_label_and_wilson_score_consistency():
    """驗證 M5 產物與 RUN_REPORT.md 完全不含 Clopper/Pearson 字串，且 CFR 之 CI 與 Wilson 計算一致。"""
    from llm_ablation_paper.workstream_5_judge_analysis.analysis_pipeline import calculate_wilson_score_interval

    run_report_path = REPO_ROOT / "llm_ablation_paper" / "results" / "v14" / "RUN_REPORT.md"
    assert run_report_path.exists()

    # 1. 檢查所有 M5 文本產物與 RUN_REPORT.md 不含 Clopper 或 Pearson
    files_to_check = [
        run_report_path,
        PAIRED_ANALYSIS_DIR / "PAPER_RESULTS_BLUEPRINT.md",
        PAIRED_ANALYSIS_DIR / "paired_effects.md",
        PAIRED_ANALYSIS_DIR / "paired_summary.json",
        PAIRED_ANALYSIS_DIR / "paired_tests.csv",
        PAIRED_ANALYSIS_DIR / "scenario_breakdown.csv",
    ]

    for fp in files_to_check:
        if fp.exists():
            text = fp.read_text(encoding="utf-8")
            assert not re.search(r"Clopper|Pearson", text, re.IGNORECASE), (
                f"檔案 {fp.name} 仍包含 Clopper 或 Pearson 字串，應更正為 Wilson 95% CI！"
            )

    # 2. 驗證 Wilson 95% CI 計算 0/12 的數值為 [0.0, 0.2425] (≈ [0.0%, 24.2%])
    ci_lower, ci_upper = calculate_wilson_score_interval(0, 12)
    assert ci_lower == 0.0
    assert ci_upper == pytest.approx(0.2425, abs=1e-4)

    # 驗證 RUN_REPORT.md 與 BLUEPRINT 中正確標示 24.2%
    rr_text = run_report_path.read_text(encoding="utf-8")
    assert "Wilson 95% CI" in rr_text
    assert "24.2%" in rr_text

    bp_text = (PAIRED_ANALYSIS_DIR / "PAPER_RESULTS_BLUEPRINT.md").read_text(encoding="utf-8")
    assert "Wilson 95% CI: [0.0%, 24.2%]" in bp_text


def test_zero_variation_metrics_strictness():
    """驗證 zero_variation_metrics_note 嚴格化邏輯：全零檢測、非零改一般描述、非有限值 fail-closed。"""
    from llm_ablation_paper.workstream_5_judge_analysis.paired_analysis_v14 import build_analysis_pipeline

    summary_path = PAIRED_ANALYSIS_DIR / "paired_summary.json"
    paired_data = json.loads(summary_path.read_text(encoding="utf-8"))

    # 1. 驗證正式產物中的全零指標
    zero_notes = paired_data["zero_variation_metrics_note"]
    for zm in ["guard_override_rate", "unexposed_tool_call_rate", "premature_summary_call_rate"]:
        assert zm in zero_notes
        assert zero_notes[zm]["status"] == "ALL_ZERO_NO_VARIATION"
        assert zero_notes[zm]["all_conditions_mean"] == 0.0
        assert "0.0%" in zero_notes[zm]["interpretation"]

    # 2. 驗證 binary_outcome_patient_goal_met 的 rates.total 等於 12 (即 len(patients))
    rates = paired_data["binary_outcome_patient_goal_met"]["rates"]
    for c in ["A", "B", "C", "D"]:
        assert rates[c]["total"] == 12

    # 3. 測試非有限值 (NaN / Inf) 時拋出 ValueError (Fail-Closed)
    mock_records = []
    for i in range(1, 13):
        pid = f"SP-{i:03d}"
        for c in ["A", "B", "C", "D"]:
            mock_records.append({
                "patient_id": pid,
                "condition": c,
                "blinded_run_id": f"BLIND-{pid}-{c}",
                "scenario_type": "DAILY_DIET",
                "goal_met": 1,
                "turns_count": 4,
                "safety": 2.0,
                "tool_use": 2.0,
                "state_consistency": 2.0,
                "dialogue_planning": 2.0,
                "helpfulness": 2.0,
                "avg_questions_per_turn": 1.0,
                "avg_latency_ms": 1000.0,
                "total_tokens": 5000,
                "model_calls_count": 4,
                "guard_override_rate": 0.0,
                "unexposed_tool_call_rate": 0.0,
                "premature_summary_call_rate": float("nan"),
            })

    with pytest.raises(ValueError, match="包含非有限數值"):
        build_analysis_pipeline(mock_records)
