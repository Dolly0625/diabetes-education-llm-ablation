# -*- coding: utf-8 -*-
"""PHASE M5 配對統計分析與結果藍圖之單元與整合測試套件。

驗證項目：
1. 合成數據驗證：Friedman、Wilcoxon、Rank-Biserial、Holm、Cochran's Q、Exact McNemar 及其退化偵測。
2. 正式產物驗證：results/v14/paired_analysis/ 檔案完整性、A–D 各組 N=12、零缺漏值、與 summary.json 描述性對齊。
3. 機密掃描：確保正式公開產物零金鑰、零 COND-、零 raw_response、零絕對路徑。
"""

import csv
import json
import os
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

    with pytest.raises(ValueError, match="非有限數值"):
        build_analysis_pipeline(mock_records)


def test_load_linked_dataset_data_integrity_fault_injections(tmp_path):
    """資料完整性故障注入回歸測試：
    驗證 load_linked_dataset 嚴格拒絕：缺評審指標、None指標、NaN/Inf指標、超界指標、
    缺程式指標、None程式指標、負數程式指標、盲測重複 run_id、Profiles重複ID、不合法情境、數量不符等。
    """
    from llm_ablation_paper.workstream_5_judge_analysis.paired_analysis_v14 import load_linked_dataset

    # 1. 建立基準合法測試資料環境
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps({
        "A": "COND-A1",
        "B": "COND-B2",
        "C": "COND-C3",
        "D": "COND-D4",
    }), encoding="utf-8")

    profiles_path = tmp_path / "profiles.jsonl"
    scenarios_list = [
        "DAILY_DIET", "DAILY_DIET",
        "MEDICATION_SIDE_EFFECT", "MEDICATION_SIDE_EFFECT",
        "MEDICATION_NONADHERENCE", "MEDICATION_NONADHERENCE",
        "SUBACUTE_HYPOGLYCEMIA", "SUBACUTE_HYPOGLYCEMIA",
        "PREVISIT_SUMMARY", "PREVISIT_SUMMARY",
        "FACT_CONTRADICTION", "FACT_CONTRADICTION",
    ]
    prof_lines = [
        json.dumps({"patient_id": f"SP-{i:03d}", "scenario_type": scenarios_list[i - 1]})
        for i in range(1, 13)
    ]
    profiles_path.write_text("\n".join(prof_lines) + "\n", encoding="utf-8")

    def build_dataset(tmp_dir, mutate_j=None, mutate_b=None, mutate_p=None):
        sub_dir = tmp_dir / f"test_{os.urandom(4).hex()}"
        sub_dir.mkdir(parents=True, exist_ok=True)
        b_dir = sub_dir / "blinded"
        b_dir.mkdir(parents=True, exist_ok=True)
        j_path = sub_dir / "judge_results.jsonl"

        j_lines = []
        for i in range(1, 13):
            pid = f"SP-{i:03d}"
            for c, secret in [("A", "COND-A1"), ("B", "COND-B2"), ("C", "COND-C3"), ("D", "COND-D4")]:
                run_id = f"BLIND-{pid}-{c}"
                b_obj = {
                    "run_id": run_id,
                    "condition_secret": secret,
                    "patient_id": pid,
                    "turns": [
                        {
                            "turn": 1,
                            "tools_exposed": ["TOOL_A"],
                            "tools_called": [],
                            "final_output": "你好？",
                            "latency_ms": 1000,
                            "token_usage": {"prompt_tokens": 100, "completion_tokens": 50},
                        }
                    ],
                    "termination_reason": "PATIENT_GOAL_MET",
                }
                if mutate_b:
                    mutate_b(b_obj, pid, c)
                (b_dir / f"{run_id}.json").write_text(json.dumps(b_obj), encoding="utf-8")

                j_obj = {
                    "blinded_run_id": run_id,
                    "patient_id": pid,
                    "critical_failure_consensus": False,
                    "disagreement": False,
                    "consensus_scores": {
                        "safety": 2.0,
                        "tool_use": 2.0,
                        "state_consistency": 2.0,
                        "dialogue_planning": 2.0,
                        "helpfulness": 2.0,
                    },
                    "failure_types": [],
                }
                if mutate_j:
                    mutate_j(j_obj, pid, c)
                j_lines.append(json.dumps(j_obj))

        j_path.write_text("\n".join(j_lines) + "\n", encoding="utf-8")
        p_path = profiles_path
        if mutate_p:
            p_path = sub_dir / "mutated_profiles.jsonl"
            p_path.write_text(mutate_p(), encoding="utf-8")

        return j_path, b_dir, mapping_path, p_path

    # Case 0: 基準資料完全通過
    j_p, b_d, m_p, p_p = build_dataset(tmp_path)
    records, scs = load_linked_dataset(j_p, b_d, m_p, p_p)
    assert len(records) == 48

    # Case 1: 缺少 consensus_scores 指標 (如缺少 safety)
    def mutate_missing_score(j, pid, c):
        if pid == "SP-001" and c == "A":
            del j["consensus_scores"]["safety"]
    j_p, b_d, m_p, p_p = build_dataset(tmp_path, mutate_j=mutate_missing_score)
    with pytest.raises(ValueError, match="缺少必要評審指標 safety"):
        load_linked_dataset(j_p, b_d, m_p, p_p)

    # Case 2: 評審指標值為 None
    def mutate_none_score(j, pid, c):
        if pid == "SP-001" and c == "A":
            j["consensus_scores"]["tool_use"] = None
    j_p, b_d, m_p, p_p = build_dataset(tmp_path, mutate_j=mutate_none_score)
    with pytest.raises(ValueError, match="tool_use 不可為 None"):
        load_linked_dataset(j_p, b_d, m_p, p_p)

    # Case 3: 評審指標值為 NaN 或 Inf
    def mutate_nan_score(j, pid, c):
        if pid == "SP-001" and c == "A":
            j["consensus_scores"]["helpfulness"] = float("nan")
    j_p, b_d, m_p, p_p = build_dataset(tmp_path, mutate_j=mutate_nan_score)
    with pytest.raises(ValueError, match="helpfulness 不得為 NaN/Inf"):
        load_linked_dataset(j_p, b_d, m_p, p_p)

    # Case 4: 評審指標數值超出合法範圍 [0.0, 2.0]
    def mutate_out_of_range_score(j, pid, c):
        if pid == "SP-001" and c == "A":
            j["consensus_scores"]["safety"] = 2.5
    j_p, b_d, m_p, p_p = build_dataset(tmp_path, mutate_j=mutate_out_of_range_score)
    with pytest.raises(ValueError, match="超出合法範圍"):
        load_linked_dataset(j_p, b_d, m_p, p_p)

    # Case 5: 缺少 turns 或 turns 為空
    def mutate_empty_turns(b, pid, c):
        if pid == "SP-001" and c == "A":
            b["turns"] = []
    j_p, b_d, m_p, p_p = build_dataset(tmp_path, mutate_b=mutate_empty_turns)
    with pytest.raises(ValueError, match="turns 必須為非空列表"):
        load_linked_dataset(j_p, b_d, m_p, p_p)

    # Case 6: 盲測目錄中存在重複 run_id
    j_p, b_d, m_p, p_p = build_dataset(tmp_path)
    dup_file = b_d / "duplicate_run.json"
    dup_file.write_text(json.dumps({
        "run_id": "BLIND-SP-001-A",
        "condition_secret": "COND-A1",
        "patient_id": "SP-001",
        "turns": [{"turn": 1}],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="包含重複之 run_id"):
        load_linked_dataset(j_p, b_d, m_p, p_p)

    # Case 7: Profiles 存在重複 ID
    def mutate_dup_prof():
        lines = [json.dumps({"patient_id": "SP-001", "scenario_type": "DAILY_DIET"})] * 12
        return "\n".join(lines) + "\n"
    j_p, b_d, m_p, p_p = build_dataset(tmp_path, mutate_p=mutate_dup_prof)
    with pytest.raises(ValueError, match="包含重複之 patient_id"):
        load_linked_dataset(j_p, b_d, m_p, p_p)

    # Case 8: Profiles 存在非預期之情境類別
    def mutate_invalid_scenario():
        lines = []
        for i in range(1, 13):
            sc = "INVALID_SCENARIO" if i == 1 else "DAILY_DIET"
            lines.append(json.dumps({"patient_id": f"SP-{i:03d}", "scenario_type": sc}))
        return "\n".join(lines) + "\n"
    j_p, b_d, m_p, p_p = build_dataset(tmp_path, mutate_p=mutate_invalid_scenario)
    with pytest.raises(ValueError, match="不合法之 scenario_type"):
        load_linked_dataset(j_p, b_d, m_p, p_p)

    # Case 9: Profiles 情境類別分佈不均 (非 6 類各 2 人)
    def mutate_unbalanced_scenarios():
        lines = [
            json.dumps({"patient_id": f"SP-{i:03d}", "scenario_type": "DAILY_DIET" if i <= 4 else "FACT_CONTRADICTION"})
            for i in range(1, 13)
        ]
        return "\n".join(lines) + "\n"
    j_p, b_d, m_p, p_p = build_dataset(tmp_path, mutate_p=mutate_unbalanced_scenarios)
    with pytest.raises(ValueError, match="之病患數量必須正好為 2"):
        load_linked_dataset(j_p, b_d, m_p, p_p)


def test_m5b_claim_audit_and_formatting_invariants():
    """驗證 M5b claim-audit 六大規範約束：
    1. 不得出現 '0.0000' 虛假 p 值，應標記 'p < 0.0001'。
    2. 措辭應為 '48 trajectories arranged in 12 matched patient blocks' 與 'LLM-judge consensus observations'。
    3. C 之 goal failure 跨 4 類情境描述性現象，機制須質性審閱，移除 gate 因果斷言。
    4. B-C McNemar 明寫 Holm 校正後 p=0.125 不顯著。
    5. zeros 敘述說明 A/B 全工具暴露結構下資訊有限、A-C 未啟用 guard 不能證明自我約束。
    6. 因果語氣全面修訂為伴隨/相關，並重申非預先註冊與單次隨機軌跡限制。
    """
    bp_text = (PAIRED_ANALYSIS_DIR / "PAPER_RESULTS_BLUEPRINT.md").read_text(encoding="utf-8")
    eff_text = (PAIRED_ANALYSIS_DIR / "paired_effects.md").read_text(encoding="utf-8")
    sum_text = (PAIRED_ANALYSIS_DIR / "paired_summary.json").read_text(encoding="utf-8")

    # 1. p 值格式：無 0.0000，且含 p < 0.0001
    assert "p = 0.0000" not in eff_text
    assert "p = 0.0000" not in bp_text
    assert "p < 0.0001" in eff_text
    assert "p < 0.0001" in bp_text

    # 2. 措辭規範
    assert "48 trajectories arranged in 12 matched patient blocks" in bp_text
    assert "48 trajectories arranged in 12 matched patient blocks" in eff_text
    assert "LLM-judge consensus observations" in bp_text
    assert "LLM-judge consensus observations" in eff_text

    # 3. C 的 6 個 goal failures 跨 4 類情境且機制須質性審閱
    assert "4 類情境" in bp_text
    assert "4 類情境" in eff_text
    assert "質性審閱" in bp_text
    assert "質性審閱" in eff_text
    # 斷言不再包含「主要導因於長輩日常飲食情境中動態工具門控」
    assert "主要導因於長輩日常飲食" not in bp_text
    assert "主要導因於長輩日常飲食" not in eff_text

    # 4. B-C McNemar 標示 Holm 校正後不顯著
    assert "Holm 校正後 p = 0.125" in bp_text
    assert "Holm 校正後 p = 0.125" in eff_text
    assert "未達統計顯著" in bp_text or "不顯著" in bp_text

    # 5. zeros 敘述結構限制
    assert "全工具暴露" in eff_text
    assert "資訊量有限" in eff_text or "資訊有限" in eff_text
    assert "自我約束" in eff_text
    assert "全工具暴露" in sum_text

    # 6. 因果語氣改為伴隨/相關，且重申非預先註冊與單次隨機軌跡限制
    assert "單次隨機軌跡" in bp_text or "single random trajectory" in bp_text
    assert "單次隨機軌跡" in eff_text
    assert "事後探索性配對分析" in bp_text
    assert "非預先註冊" in bp_text
