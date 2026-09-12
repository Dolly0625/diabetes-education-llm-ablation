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


# ==============================================================================
# 3. Fault-injection 回歸測試 (M5b WS5)：load_linked_dataset 嚴格 Fail-Closed
# ==============================================================================

from llm_ablation_paper.workstream_5_judge_analysis import paired_analysis_v14 as _pa
from llm_ablation_paper.workstream_5_judge_analysis.paired_analysis_v14 import (
    load_linked_dataset,
)

_FI_SCENARIOS = [
    "DAILY_DIET", "DAILY_DIET",
    "MEDICATION_SIDE_EFFECT", "MEDICATION_SIDE_EFFECT",
    "MEDICATION_NONADHERENCE", "MEDICATION_NONADHERENCE",
    "SUBACUTE_HYPOGLYCEMIA", "SUBACUTE_HYPOGLYCEMIA",
    "PREVISIT_SUMMARY", "PREVISIT_SUMMARY",
    "FACT_CONTRADICTION", "FACT_CONTRADICTION",
]
_FI_SECRETS = {"A": "SECRET-A", "B": "SECRET-B", "C": "SECRET-C", "D": "SECRET-D"}


def _fi_valid_turn():
    return {
        "turn": 1,
        "patient_text": "我飯後血糖偏高怎麼辦？",
        "tools_exposed": ["TOOL_SEARCH_HANDBOOK"],
        "tools_called": [{"name": "TOOL_SEARCH_HANDBOOK", "arguments": {}}],
        "guard_action": {"is_blocked": False},
        "final_output": "建議您維持規律飲食，並注意監測血糖，好嗎？",
        "latency_ms": 1200,
        "token_usage": {"prompt_tokens": 150, "completion_tokens": 50},
    }


def _fi_write_valid_set(root: Path):
    """寫入一組完全合法之 48 筆輸入，回傳 (judge_path, blinded_dir, mapping_path, profiles_path)。"""
    judge_path = root / "judge_results.jsonl"
    blinded_dir = root / "blinded"
    blinded_dir.mkdir(parents=True, exist_ok=True)
    mapping_path = root / "mapping.json"
    profiles_path = root / "profiles.jsonl"

    mapping_path.write_text(json.dumps(_FI_SECRETS), encoding="utf-8")
    with profiles_path.open("w", encoding="utf-8") as f:
        for i in range(1, 13):
            f.write(json.dumps({"patient_id": f"SP-{i:03d}", "scenario_type": _FI_SCENARIOS[i - 1]}) + "\n")

    with judge_path.open("w", encoding="utf-8") as jf:
        for i in range(1, 13):
            pid = f"SP-{i:03d}"
            for c in ["A", "B", "C", "D"]:
                run_id = f"BLIND-{pid}-{c}"
                b_data = {
                    "run_id": run_id,
                    "condition_secret": _FI_SECRETS[c],
                    "patient_id": pid,
                    "termination_reason": "PATIENT_GOAL_MET",
                    "turns": [_fi_valid_turn()],
                }
                (blinded_dir / f"{run_id}.json").write_text(json.dumps(b_data), encoding="utf-8")
                jf.write(json.dumps({
                    "blinded_run_id": run_id,
                    "consensus_scores": {
                        "safety": 2.0, "tool_use": 2.0, "state_consistency": 2.0,
                        "dialogue_planning": 2.0, "helpfulness": 2.0,
                    },
                }) + "\n")
    return judge_path, blinded_dir, mapping_path, profiles_path


def _fi_load_all(judge_path: Path, blinded_dir: Path, mapping_path: Path, profiles_path: Path):
    return load_linked_dataset(judge_path, blinded_dir, mapping_path, profiles_path)


def _fi_rewrite_judge_scores(judge_path: Path, mutate):
    lines = [json.loads(line) for line in judge_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    mutate(lines)
    judge_path.write_text("\n".join(json.dumps(r, allow_nan=True) for r in lines) + "\n", encoding="utf-8")


def test_fi_valid_set_loads_48_records(tmp_path):
    """合法輸入必須完整連結 48 筆 (12 病患 x 4 條件)。"""
    paths = _fi_write_valid_set(tmp_path)
    records, scenarios = _fi_load_all(*paths)
    assert len(records) == 48
    assert len(scenarios) == 12


def test_load_linked_dataset_strict_validation_fault_injections(tmp_path):
    """第二輪故障注入測試：
    1. termination_reason 僅接受 PATIENT_GOAL_MET 或 MAX_TURNS (None, ERROR, 未知一律 fail-closed)
    2. total_tokens 與 model_calls_count 拒絕 fractional float
    3. unexposed_tool_calls <= tool_calls_count 約束
    4. 所有 rate 嚴格限制在 [0.0, 1.0]
    """
    # 測試 termination_reason = None
    paths = _fi_write_valid_set(tmp_path / "case_term_none")
    target = paths[1] / "BLIND-SP-001-A.json"
    b_data = json.loads(target.read_text(encoding="utf-8"))
    b_data["termination_reason"] = None
    target.write_text(json.dumps(b_data), encoding="utf-8")
    with pytest.raises(ValueError, match="termination_reason 僅接受 PATIENT_GOAL_MET 或 MAX_TURNS"):
        _fi_load_all(*paths)

    # 測試 termination_reason = "ERROR"
    paths = _fi_write_valid_set(tmp_path / "case_term_error")
    target = paths[1] / "BLIND-SP-001-A.json"
    b_data = json.loads(target.read_text(encoding="utf-8"))
    b_data["termination_reason"] = "ERROR"
    target.write_text(json.dumps(b_data), encoding="utf-8")
    with pytest.raises(ValueError, match="termination_reason 僅接受 PATIENT_GOAL_MET 或 MAX_TURNS"):
        _fi_load_all(*paths)

    # 測試 termination_reason = "COMMON_INPUT_BLOCK"
    paths = _fi_write_valid_set(tmp_path / "case_term_unknown")
    target = paths[1] / "BLIND-SP-001-A.json"
    b_data = json.loads(target.read_text(encoding="utf-8"))
    b_data["termination_reason"] = "COMMON_INPUT_BLOCK"
    target.write_text(json.dumps(b_data), encoding="utf-8")
    with pytest.raises(ValueError, match="termination_reason 僅接受 PATIENT_GOAL_MET 或 MAX_TURNS"):
        _fi_load_all(*paths)

    # 測試 total_tokens 包含小數 (fractional float)
    paths = _fi_write_valid_set(tmp_path / "case_tok_frac")
    target = paths[1] / "BLIND-SP-001-A.json"
    b_data = json.loads(target.read_text(encoding="utf-8"))
    b_data["turns"][0]["token_usage"]["prompt_tokens"] = 100.5
    target.write_text(json.dumps(b_data), encoding="utf-8")
    with pytest.raises(ValueError, match="必須為非負整數，拒絕小數浮點數"):
        _fi_load_all(*paths)

    # 測試 model_calls_count 包含小數
    import llm_ablation_paper.workstream_5_judge_analysis.paired_analysis_v14 as mod_paired
    orig_extract = mod_paired.extract_programmatic_metrics
    try:
        def fake_extract_float_calls(b_data):
            res = orig_extract(b_data)
            res["model_calls_count"] = 4.2
            return res
        mod_paired.extract_programmatic_metrics = fake_extract_float_calls
        paths = _fi_write_valid_set(tmp_path / "case_call_frac")
        with pytest.raises(ValueError, match="必須為非負整數，拒絕小數浮點數"):
            _fi_load_all(*paths)
    finally:
        mod_paired.extract_programmatic_metrics = orig_extract

    # 測試 unexposed_tool_calls > tool_calls_count 違背約束
    try:
        def fake_extract_invalid_tool_calls(b_data):
            res = orig_extract(b_data)
            res["tool_calls_count"] = 2
            res["unexposed_tool_calls"] = 5
            return res
        mod_paired.extract_programmatic_metrics = fake_extract_invalid_tool_calls
        paths = _fi_write_valid_set(tmp_path / "case_tool_calls_viol")
        with pytest.raises(ValueError, match="不得大於 tool_calls_count"):
            _fi_load_all(*paths)
    finally:
        mod_paired.extract_programmatic_metrics = orig_extract

    # 測試 unexposed_tool_call_rate 超出 [0.0, 1.0]
    try:
        def fake_extract_invalid_unexposed_rate(b_data):
            res = orig_extract(b_data)
            res["unexposed_tool_call_rate"] = 1.5
            return res
        mod_paired.extract_programmatic_metrics = fake_extract_invalid_unexposed_rate
        paths = _fi_write_valid_set(tmp_path / "case_unexposed_rate_viol")
        with pytest.raises(ValueError, match=r"unexposed_tool_call_rate.*超出合法範圍"):
            _fi_load_all(*paths)
    finally:
        mod_paired.extract_programmatic_metrics = orig_extract

    # 測試 premature_summary_call_rate 超出 [0.0, 1.0]
    try:
        def fake_extract_invalid_premature_rate(b_data):
            res = orig_extract(b_data)
            res["premature_summary_call_rate"] = 1.2
            return res
        mod_paired.extract_programmatic_metrics = fake_extract_invalid_premature_rate
        paths = _fi_write_valid_set(tmp_path / "case_premature_rate_viol")
        with pytest.raises(ValueError, match=r"premature_summary_call_rate.*超出合法範圍"):
            _fi_load_all(*paths)
    finally:
        mod_paired.extract_programmatic_metrics = orig_extract


def test_m5b_claim_audit_and_formatting_invariants():
    """驗證 M5b claim-audit 規範約束：
    1. 不得出現 '0.0000' 虛假 p 值，應標記 'p < 0.0001'。
    2. 措辭應為 '48 trajectories arranged in 12 matched patient blocks' 與 'condition-blinded LLM judge consensus observations'。
    3. C 之 goal failure 跨 4 類情境描述性現象，機制須質性審閱，移除 gate 因果斷言。
    4. B-C McNemar 明寫 Holm 校正後 p=0.125 不顯著。
    5. zeros 敘述說明 A/B 全工具暴露結構下資訊有限、A-C 未啟用 guard 不能證明自我約束。
    6. 因果語氣全面修訂為伴隨/相關，並重申非預先註冊與單次隨機軌跡限制。
    7. 盲化評判術語校正：禁止「雙盲」，必須使用「對條件身分盲化的 LLM Judge」或「condition-blinded LLM judge」。
    """
    bp_text = (PAIRED_ANALYSIS_DIR / "PAPER_RESULTS_BLUEPRINT.md").read_text(encoding="utf-8")
    eff_text = (PAIRED_ANALYSIS_DIR / "paired_effects.md").read_text(encoding="utf-8")
    sum_text = (PAIRED_ANALYSIS_DIR / "paired_summary.json").read_text(encoding="utf-8")

    # 1. p 值格式：無 0.0000，且含 p < 0.0001
    assert "p = 0.0000" not in eff_text
    assert "p = 0.0000" not in bp_text
    assert "p < 0.0001" in eff_text or "p<0.0001" in eff_text
    assert "p < 0.0001" in bp_text or "p<0.0001" in bp_text

    # 2. 措辭規範
    assert "48 trajectories arranged in 12 matched patient blocks" in bp_text
    assert "48 trajectories arranged in 12 matched patient blocks" in eff_text
    assert "condition-blinded LLM judge consensus observations" in bp_text
    assert "condition-blinded LLM judge consensus observations" in eff_text

    # 3. C 的 6 個 goal failures 跨 4 類情境且機制須質性審閱
    assert "4 類情境" in bp_text
    assert "4 類情境" in eff_text
    assert "質性審閱" in bp_text
    assert "質性審閱" in eff_text
    # 斷言不再包含「主要導因於長輩日常飲食情境中動態工具門控」
    assert "主要導因於長輩日常飲食" not in bp_text
    assert "主要導因於長輩日常飲食" not in eff_text

    # 4. B-C McNemar 標示 Holm 校正後不顯著
    assert "Holm-adjusted p=.125" in bp_text or "Holm 校正後 p = 0.125" in bp_text
    assert "Holm-adjusted p=.125" in eff_text or "Holm 校正後 p = 0.125" in eff_text
    assert "not significant" in bp_text or "未達統計顯著" in bp_text or "不顯著" in bp_text

    # 5. zeros 敘述結構限制
    assert "全工具暴露" in eff_text
    assert "資訊量有限" in eff_text or "資訊有限" in eff_text or "structurally uninformative" in eff_text
    assert "自我約束" in eff_text or "self-restraint" in eff_text
    assert "全工具暴露" in sum_text or "all tools exposed" in sum_text

    # 6. 因果語氣改為伴隨/相關，且重申非預先註冊與單次隨機軌跡限制
    assert "單次隨機軌跡" in bp_text or "single random trajectory" in bp_text or "one stochastic trajectory" in bp_text
    assert "單次隨機軌跡" in eff_text or "single random trajectory" in eff_text or "one stochastic trajectory" in eff_text
    assert "事後探索性配對分析" in bp_text or "事後探索" in bp_text
    assert "非預先註冊" in bp_text

    # 7. 盲化評判術語校正
    assert "雙盲" not in eff_text
    assert "雙盲" not in bp_text
    assert "對條件身分盲化的 LLM Judge" in eff_text
    assert "對條件身分盲化的 LLM Judge" in bp_text
    assert "condition-blinded LLM judge" in eff_text
    assert "condition-blinded LLM judge" in bp_text


def test_fi_scores_missing_key_raises(tmp_path):
    """consensus_scores 缺少任一指標鍵即 ValueError (拒絕預設 2.0)。"""
    paths = _fi_write_valid_set(tmp_path)
    _fi_rewrite_judge_scores(paths[0], lambda lines: lines[0]["consensus_scores"].pop("helpfulness"))
    with pytest.raises(ValueError, match="缺少必要指標"):
        _fi_load_all(*paths)


@pytest.mark.parametrize("bad_value", ["high", None, float("nan"), float("inf"), -1, 2.5, True])
def test_fi_scores_invalid_values_raise(tmp_path, bad_value):
    """評分非數值 / None / NaN / Inf / 越界 / 布林即 ValueError。"""
    paths = _fi_write_valid_set(tmp_path)

    def mutate(lines):
        lines[5]["consensus_scores"]["safety"] = bad_value

    _fi_rewrite_judge_scores(paths[0], mutate)
    with pytest.raises(ValueError):
        _fi_load_all(*paths)
def test_fi_prog_none_latency_raises(tmp_path):
    """空 turns 導致 avg_latency_ms 為 None，必須 ValueError (不可補 0)。"""
    paths = _fi_write_valid_set(tmp_path)
    judge_path, blinded_dir, mapping_path, profiles_path = paths
    target = blinded_dir / "BLIND-SP-001-A.json"
    b_data = json.loads(target.read_text(encoding="utf-8"))
    b_data["turns"] = []
    target.write_text(json.dumps(b_data), encoding="utf-8")
    with pytest.raises(ValueError, match="為 None"):
        _fi_load_all(*paths)


def test_fi_prog_inf_and_negative_raise(tmp_path):
    """latency Inf 與負值必須 ValueError。"""
    paths = _fi_write_valid_set(tmp_path)
    judge_path, blinded_dir, mapping_path, profiles_path = paths
    target = blinded_dir / "BLIND-SP-002-B.json"
    b_data = json.loads(target.read_text(encoding="utf-8"))
    b_data["turns"][0]["latency_ms"] = float("inf")
    target.write_text(json.dumps(b_data, allow_nan=True), encoding="utf-8")
    with pytest.raises(ValueError, match="非有限數值"):
        _fi_load_all(*paths)

    b_data["turns"][0]["latency_ms"] = -50
    target.write_text(json.dumps(b_data), encoding="utf-8")
    with pytest.raises(ValueError, match="為負值"):
        _fi_load_all(*paths)


def test_fi_prog_missing_guard_override_rate_raises(tmp_path, monkeypatch):
    """prog 缺少 guard_override_rate 即 ValueError (不可靜默衍生)。"""
    paths = _fi_write_valid_set(tmp_path)
    from llm_ablation_paper.workstream_5_judge_analysis.analysis_pipeline import (
        extract_programmatic_metrics as _real_extract,
    )

    def _extract_without_guard(trajectory):
        prog = _real_extract(trajectory)
        prog.pop("guard_override_rate", None)
        return prog

    monkeypatch.setattr(_pa, "extract_programmatic_metrics", _extract_without_guard)
    with pytest.raises(ValueError, match="guard_override_rate"):
        _fi_load_all(*paths)


def test_fi_prog_none_rate_raises(tmp_path, monkeypatch):
    """prog 指標為 None (如上游缺失) 即 ValueError。"""
    paths = _fi_write_valid_set(tmp_path)
    from llm_ablation_paper.workstream_5_judge_analysis.analysis_pipeline import (
        extract_programmatic_metrics as _real_extract,
    )

    def _extract_with_none(trajectory):
        prog = _real_extract(trajectory)
        prog["unexposed_tool_call_rate"] = None
        return prog

    monkeypatch.setattr(_pa, "extract_programmatic_metrics", _extract_with_none)
    with pytest.raises(ValueError, match="為 None"):
        _fi_load_all(*paths)


def test_fi_duplicate_blinded_run_id_raises(tmp_path):
    """兩個盲測檔案共用同一 run_id 必須 ValueError (不可靜默覆寫)。"""
    paths = _fi_write_valid_set(tmp_path)
    judge_path, blinded_dir, mapping_path, profiles_path = paths
    src = blinded_dir / "BLIND-SP-001-A.json"
    dup = blinded_dir / "BLIND-DUP-SP-001-A.json"
    dup.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValueError, match="重複的盲測 run_id"):
        _fi_load_all(*paths)


def test_fi_missing_blinded_run_id_raises(tmp_path):
    """盲測檔案缺少 run_id 必須 ValueError。"""
    paths = _fi_write_valid_set(tmp_path)
    judge_path, blinded_dir, mapping_path, profiles_path = paths
    target = blinded_dir / "BLIND-SP-001-A.json"
    b_data = json.loads(target.read_text(encoding="utf-8"))
    b_data.pop("run_id")
    target.write_text(json.dumps(b_data), encoding="utf-8")
    with pytest.raises(ValueError, match="缺少 run_id"):
        _fi_load_all(*paths)


def test_fi_profiles_unknown_scenario_raises(tmp_path):
    """未知 scenario_type 必須 ValueError。"""
    paths = _fi_write_valid_set(tmp_path)
    judge_path, blinded_dir, mapping_path, profiles_path = paths
    lines = profiles_path.read_text(encoding="utf-8").splitlines()
    obj = json.loads(lines[0])
    obj["scenario_type"] = "MIDNIGHT_SNACK"
    lines[0] = json.dumps(obj)
    profiles_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="未知情境型別"):
        _fi_load_all(*paths)


def test_fi_profiles_duplicate_patient_id_raises(tmp_path):
    """重複 patient_id 必須 ValueError。"""
    paths = _fi_write_valid_set(tmp_path)
    judge_path, blinded_dir, mapping_path, profiles_path = paths
    lines = profiles_path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[0]
    profiles_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="重複的 patient_id"):
        _fi_load_all(*paths)


def test_fi_profiles_missing_scenario_type_raises(tmp_path):
    """缺少 scenario_type 必須 ValueError。"""
    paths = _fi_write_valid_set(tmp_path)
    judge_path, blinded_dir, mapping_path, profiles_path = paths
    lines = profiles_path.read_text(encoding="utf-8").splitlines()
    obj = json.loads(lines[2])
    obj.pop("scenario_type")
    lines[2] = json.dumps(obj)
    profiles_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="缺少 scenario_type"):
        _fi_load_all(*paths)


def test_fi_profiles_unbalanced_types_raise(tmp_path):
    """某情境 3 人 (另一情境僅 1 人) 必須 ValueError。"""
    paths = _fi_write_valid_set(tmp_path)
    judge_path, blinded_dir, mapping_path, profiles_path = paths
    lines = profiles_path.read_text(encoding="utf-8").splitlines()
    obj = json.loads(lines[11])
    obj["scenario_type"] = "DAILY_DIET"
    lines[11] = json.dumps(obj)
    profiles_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="須恰好為 2"):
        _fi_load_all(*paths)


def test_fmt_p_formatting():
    """fmt_p：微小 p 顯示 p<0.0001，其餘 p=4 位小數，None 顯示 -。"""
    from llm_ablation_paper.workstream_5_judge_analysis.paired_analysis_v14 import fmt_p
    assert fmt_p(1.0008e-05) == "p<0.0001"
    assert fmt_p(None) == "-"
    assert fmt_p(0.0122) == "p=0.0122"
    assert fmt_p(0.39163) == "p=0.3916"
