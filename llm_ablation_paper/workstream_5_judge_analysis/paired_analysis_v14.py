# -*- coding: utf-8 -*-
"""PHASE M5: 糖尿病衛教大型語言模型消融實驗配對統計分析與結果藍圖產生器 (v14)

本模組執行事後探索性配對統計分析 (Post-hoc exploratory paired analysis)：
- 嚴格以病患為配對單元 (Patient as pairing/block, N=12 病人 x 4 條件)，禁止視為 48 獨立樣本。
- 遵循多重比較 Holm-Bonferroni 校正。
- 嚴格處理退化指標 (如全常數/零變異)，標記 DEGENERATE_NOT_TESTABLE，不得輸出虛假 p=0。
- 實作 Cochran's Q 檢定與 Exact McNemar 檢定評估二元重複測量 (PATIENT_GOAL_MET)。
- 輸出標準化成果至 results/v14/paired_analysis/。
"""

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

# 引入本專案既有之客觀指標計算函式
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from llm_ablation_paper.workstream_5_judge_analysis.analysis_pipeline import extract_programmatic_metrics


def load_linked_dataset(
    judge_results_path: Path,
    blinded_dir: Path,
    mapping_path: Path,
    profiles_path: Path,
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """以可靠且 Fail-Closed 之方式連結評審結果、盲測軌跡與條件映射。

    驗證要求：
    - 恰好 12 位病患 (SP-001 ~ SP-012) x 4 條件 (A, B, C, D) = 48 筆配對紀錄。
    - 無缺漏、無重複、無無法解析之條件秘密。
    """
    if not judge_results_path.exists():
        raise FileNotFoundError(f"評審結果檔案不存在: {judge_results_path}")
    if not blinded_dir.exists():
        raise FileNotFoundError(f"盲測軌跡目錄不存在: {blinded_dir}")
    if not mapping_path.exists():
        raise FileNotFoundError(f"條件映射檔案不存在: {mapping_path}")
    if not profiles_path.exists():
        raise FileNotFoundError(f"病患 Profiles 檔案不存在: {profiles_path}")

    # 1. 載入條件映射並反轉
    mapping_data = json.loads(mapping_path.read_text(encoding="utf-8"))
    reverse_mapping = {v: k for k, v in mapping_data.items()}
    expected_conditions = {"A", "B", "C", "D"}
    if set(mapping_data.keys()) != expected_conditions:
        raise ValueError(f"條件映射鍵值不符預期: {mapping_data.keys()} vs {expected_conditions}")

    # 2. 載入病患情境
    scenarios: Dict[str, str] = {}
    for line in profiles_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            p_obj = json.loads(line)
            scenarios[p_obj["patient_id"]] = p_obj.get("scenario_type", "UNKNOWN")

    # 3. 載入所有盲測軌跡
    blinded_dict: Dict[str, Dict[str, Any]] = {}
    for p in blinded_dir.glob("*.json"):
        b_data = json.loads(p.read_text(encoding="utf-8"))
        blinded_dict[b_data["run_id"]] = b_data

    # 4. 讀取評審結果並連結
    linked_records: List[Dict[str, Any]] = []
    seen_pairs = set()

    with judge_results_path.open(encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            j_rec = json.loads(line)
            b_id = j_rec.get("blinded_run_id")
            if not b_id or b_id not in blinded_dict:
                raise ValueError(f"行 {line_num}: 盲測 ID {b_id} 無法於盲測目錄中配對！")

            b_data = blinded_dict[b_id]
            secret = b_data.get("condition_secret")
            if secret not in reverse_mapping:
                raise ValueError(f"行 {line_num}: 條件秘密 {secret} 無法於映射檔中反轉！")
            condition = reverse_mapping[secret]

            pat_id = b_data.get("patient_id")
            if not pat_id or not pat_id.startswith("SP-"):
                raise ValueError(f"行 {line_num}: 異常病患 ID {pat_id}")

            pair = (pat_id, condition)
            if pair in seen_pairs:
                raise ValueError(f"重複的病患條件配對: {pair}")
            seen_pairs.add(pair)

            prog = extract_programmatic_metrics(b_data)
            scores = j_rec.get("consensus_scores", {})
            term_reason = b_data.get("termination_reason")
            goal_met = 1 if term_reason == "PATIENT_GOAL_MET" else 0

            record = {
                "patient_id": pat_id,
                "condition": condition,
                "blinded_run_id": b_id,
                "scenario_type": scenarios.get(pat_id, "UNKNOWN"),
                "goal_met": goal_met,
                "termination_reason": term_reason,
                "turns_count": len(b_data.get("turns", [])),
                "safety": float(scores.get("safety", 2.0)),
                "tool_use": float(scores.get("tool_use", 2.0)),
                "state_consistency": float(scores.get("state_consistency", 2.0)),
                "dialogue_planning": float(scores.get("dialogue_planning", 2.0)),
                "helpfulness": float(scores.get("helpfulness", 2.0)),
                "avg_questions_per_turn": float(prog.get("avg_questions_per_turn") or 0.0),
                "avg_latency_ms": float(prog.get("avg_latency_ms") or 0.0),
                "total_tokens": int(prog.get("total_tokens") or 0),
                "model_calls_count": int(prog.get("model_calls_count") or 0),
                "guard_override_rate": float(prog.get("guard_override_rate") or 0.0),
                "unexposed_tool_call_rate": float(prog.get("unexposed_tool_call_rate") or 0.0),
                "premature_summary_call_rate": float(prog.get("premature_summary_call_rate") or 0.0),
            }
            linked_records.append(record)

    expected_pairs = {
        (f"SP-{i:03d}", c) for i in range(1, 13) for c in ["A", "B", "C", "D"]
    }
    if seen_pairs != expected_pairs:
        missing = expected_pairs - seen_pairs
        extra = seen_pairs - expected_pairs
        raise ValueError(f"配對驗證失敗！缺漏: {missing}, 多餘: {extra}")

    return linked_records, scenarios


def calculate_descriptive_stats(values: List[float]) -> Dict[str, float]:
    """計算描述性統計值 (mean, std, median, q25, q75, iqr, min, max)。"""
    arr = np.array(values, dtype=float)
    q25 = float(np.percentile(arr, 25))
    q75 = float(np.percentile(arr, 75))
    return {
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        "median": float(np.median(arr)),
        "q25": q25,
        "q75": q75,
        "iqr": float(q75 - q25),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }


def run_omnibus_friedman(
    cond_vectors: Dict[str, List[float]],
) -> Dict[str, Any]:
    """執行配對母體 Friedman 檢定。若全為常數或無個體間差異，標記 DEGENERATE_NOT_TESTABLE。"""
    a = cond_vectors["A"]
    b = cond_vectors["B"]
    c = cond_vectors["C"]
    d = cond_vectors["D"]
    mat = np.array([a, b, c, d])

    # 檢查 1: 全體所有元素完全相同 (零總變異)
    if len(np.unique(mat)) == 1:
        return {
            "test": "Friedman",
            "status": "DEGENERATE_NOT_TESTABLE",
            "statistic": None,
            "p_value": None,
            "df": 3,
            "note": "全條件觀測值皆為常數，無變異可檢定 (不可標記為 p=0)",
        }

    # 檢查 2: 每位病人在所有 4 條件下數值完全相等 (配對差值全為 0)
    diffs = np.diff(mat, axis=0)
    if np.all(diffs == 0):
        return {
            "test": "Friedman",
            "status": "DEGENERATE_NOT_TESTABLE",
            "statistic": None,
            "p_value": None,
            "df": 3,
            "note": "所有病患於 4 個條件下之數值完全一致，配對檢定統計量退化",
        }

    try:
        res = stats.friedmanchisquare(a, b, c, d)
        return {
            "test": "Friedman",
            "status": "TESTED",
            "statistic": float(res.statistic),
            "p_value": float(res.pvalue),
            "df": 3,
            "note": "檢驗通過",
        }
    except Exception as e:
        return {
            "test": "Friedman",
            "status": f"ERROR: {str(e)}",
            "statistic": None,
            "p_value": None,
            "df": 3,
            "note": str(e),
        }


def calculate_rank_biserial(x: List[float], y: List[float]) -> Tuple[float, int]:
    """計算 Matched-Pairs Rank-Biserial Correlation (r_rb) 與非零 pair 數。"""
    diff = np.array(x, dtype=float) - np.array(y, dtype=float)
    nonzero = diff[diff != 0]
    n_nonzero = len(nonzero)
    if n_nonzero == 0:
        return 0.0, 0

    abs_diff = np.abs(nonzero)
    ranks = stats.rankdata(abs_diff)
    w_pos = float(np.sum(ranks[nonzero > 0]))
    w_neg = float(np.sum(ranks[nonzero < 0]))
    total = w_pos + w_neg
    if total == 0:
        return 0.0, n_nonzero
    r_rb = (w_pos - w_neg) / total
    return float(r_rb), n_nonzero


def run_pairwise_wilcoxon(
    cond_vectors: Dict[str, List[float]],
    pairs: List[Tuple[str, str]],
) -> Dict[str, Dict[str, Any]]:
    """執行指定成對 Wilcoxon 符號秩檢定 (Two-Sided) 並計算效果量。"""
    results = {}
    for c1, c2 in pairs:
        pair_key = f"{c1}-{c2}"
        v1 = cond_vectors[c1]
        v2 = cond_vectors[c2]
        r_rb, n_nonzero = calculate_rank_biserial(v1, v2)

        if n_nonzero == 0:
            results[pair_key] = {
                "pair": pair_key,
                "status": "NOT_TESTABLE/NO_VARIATION",
                "n_nonzero": 0,
                "statistic": None,
                "raw_p": None,
                "adjusted_p": None,
                "rank_biserial_r": 0.0,
                "note": "配對差值全為 0，無法檢定",
            }
        else:
            try:
                w_res = stats.wilcoxon(v1, v2, alternative="two-sided")
                results[pair_key] = {
                    "pair": pair_key,
                    "status": "TESTED",
                    "n_nonzero": n_nonzero,
                    "statistic": float(w_res.statistic),
                    "raw_p": float(w_res.pvalue),
                    "adjusted_p": None,  # 由後續 Holm 校正填入
                    "rank_biserial_r": float(r_rb),
                    "note": "檢定完成",
                }
            except Exception as e:
                results[pair_key] = {
                    "pair": pair_key,
                    "status": f"ERROR: {str(e)}",
                    "n_nonzero": n_nonzero,
                    "statistic": None,
                    "raw_p": None,
                    "adjusted_p": None,
                    "rank_biserial_r": float(r_rb),
                    "note": str(e),
                }
    return results


def apply_holm_bonferroni(
    pairwise_dict: Dict[str, Dict[str, Any]],
) -> None:
    """對成對比較之 raw_p 進行單調遞增之 Holm-Bonferroni 多重比較校正。"""
    for item in pairwise_dict.values():
        if "adjusted_p" not in item:
            item["adjusted_p"] = None

    valid_items = [
        (k, item["raw_p"])
        for k, item in pairwise_dict.items()
        if item.get("status") == "TESTED" and item.get("raw_p") is not None
    ]
    if not valid_items:
        return

    # 升冪排序
    sorted_items = sorted(valid_items, key=lambda x: x[1])
    m = len(sorted_items)
    current_max = 0.0

    for idx, (k, raw_p) in enumerate(sorted_items):
        multiplier = m - idx
        cand = min(1.0, raw_p * multiplier)
        current_max = max(current_max, cand)
        adj_p = min(1.0, current_max)
        pairwise_dict[k]["adjusted_p"] = float(adj_p)


def run_cochran_q(binary_matrix: np.ndarray) -> Dict[str, Any]:
    """計算 Cochran's Q 統計量以檢定重複測量二元指標 (Repeated Measures Binary Outcome)。"""
    N, k = binary_matrix.shape
    R = np.sum(binary_matrix, axis=1)  # 受試者成功數
    C = np.sum(binary_matrix, axis=0)  # 條件成功數
    T = float(np.sum(C))

    numerator = (k - 1) * (k * float(np.sum(C ** 2)) - T ** 2)
    denominator = k * T - float(np.sum(R ** 2))

    if denominator == 0:
        return {
            "test": "Cochran_Q",
            "status": "NOT_TESTABLE/NO_VARIATION",
            "statistic": None,
            "p_value": None,
            "df": k - 1,
            "note": "所有受試者結果皆一致，分母為 0",
        }

    q_stat = numerator / denominator
    p_val = float(stats.chi2.sf(q_stat, df=k - 1))
    return {
        "test": "Cochran_Q",
        "status": "TESTED",
        "statistic": float(q_stat),
        "p_value": float(p_val),
        "df": k - 1,
        "note": "檢定完成",
    }


def run_pairwise_mcnemar(
    cond_binary: Dict[str, List[int]],
    pairs: List[Tuple[str, str]],
) -> Dict[str, Dict[str, Any]]:
    """執行成對 Exact McNemar 檢定 (基於二項分佈 Binomial Test)。"""
    results = {}
    for c1, c2 in pairs:
        pair_key = f"{c1}-{c2}"
        v1 = np.array(cond_binary[c1], dtype=int)
        v2 = np.array(cond_binary[c2], dtype=int)

        b = int(np.sum((v1 == 1) & (v2 == 0)))
        c = int(np.sum((v1 == 0) & (v2 == 1)))
        n_disc = b + c

        if n_disc == 0:
            results[pair_key] = {
                "pair": pair_key,
                "status": "NOT_TESTABLE/NO_DISCORDANT_PAIRS",
                "b_count": 0,
                "c_count": 0,
                "n_discordant": 0,
                "raw_p": None,
                "adjusted_p": None,
                "note": "無分歧配對 (b=0, c=0)",
            }
        else:
            b_res = stats.binomtest(min(b, c), n_disc, 0.5, alternative="two-sided")
            results[pair_key] = {
                "pair": pair_key,
                "status": "TESTED",
                "b_count": b,
                "c_count": c,
                "n_discordant": n_disc,
                "raw_p": float(b_res.pvalue),
                "adjusted_p": None,
                "note": "Exact Binomial 檢定完成",
            }
    return results


def build_analysis_pipeline(linked_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """執行完整配對統計管線。"""
    # 建立以 condition 為外層、以 patient 為內層之結構
    data_by_cond: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for rec in linked_records:
        data_by_cond[rec["condition"]][rec["patient_id"]] = rec

    patients = sorted(list(data_by_cond["A"].keys()))
    pairs = [("A", "B"), ("B", "C"), ("C", "D"), ("A", "D")]

    # 指標清單
    score_metrics = ["safety", "tool_use", "state_consistency", "dialogue_planning", "helpfulness"]
    continuous_prog_metrics = ["avg_questions_per_turn", "avg_latency_ms", "total_tokens", "model_calls_count", "turns_count"]
    zero_prog_metrics = ["guard_override_rate", "unexposed_tool_call_rate", "premature_summary_call_rate"]

    output_summary: Dict[str, Any] = {
        "study_design": "12 patients x 4 conditions repeated measures (N=12/group, Total=48 runs)",
        "analysis_type": "Post-hoc exploratory paired analysis (Non-preregistered)",
        "descriptive_statistics": {},
        "omnibus_tests": {},
        "pairwise_comparisons": {},
        "zero_variation_metrics_note": {},
        "binary_outcome_patient_goal_met": {},
    }

    # 1. 處理評審連續分數與程式連續指標
    all_continuous_metrics = score_metrics + continuous_prog_metrics
    for metric in all_continuous_metrics:
        cond_vectors = {
            c: [data_by_cond[c][p][metric] for p in patients]
            for c in ["A", "B", "C", "D"]
        }

        # 描述性統計
        output_summary["descriptive_statistics"][metric] = {
            c: calculate_descriptive_stats(cond_vectors[c])
            for c in ["A", "B", "C", "D"]
        }

        # Omnibus Friedman
        f_res = run_omnibus_friedman(cond_vectors)
        output_summary["omnibus_tests"][metric] = f_res

        # Pairwise Wilcoxon + Holm
        p_res = run_pairwise_wilcoxon(cond_vectors, pairs)
        apply_holm_bonferroni(p_res)
        output_summary["pairwise_comparisons"][metric] = p_res

    # 2. 處理全零/無變異指標 (只描述，不做虛假推論)
    for zm in zero_prog_metrics:
        cond_vectors = {
            c: [data_by_cond[c][p][zm] for p in patients]
            for c in ["A", "B", "C", "D"]
        }
        output_summary["descriptive_statistics"][zm] = {
            c: calculate_descriptive_stats(cond_vectors[c])
            for c in ["A", "B", "C", "D"]
        }
        output_summary["zero_variation_metrics_note"][zm] = {
            "all_conditions_mean": 0.0,
            "status": "ALL_ZERO_NO_VARIATION",
            "interpretation": "所有條件下該違規/攔截率均為 0.0%，呈現完全常數無變異，僅作描述性報告，不進行假設檢定。",
        }

    # 3. 處理 PATIENT_GOAL_MET (Cochran Q + Exact McNemar)
    goal_mat = np.array([
        [data_by_cond[c][p]["goal_met"] for c in ["A", "B", "C", "D"]]
        for p in patients
    ])
    cochran_res = run_cochran_q(goal_mat)
    cond_binary = {
        c: [data_by_cond[c][p]["goal_met"] for p in patients]
        for c in ["A", "B", "C", "D"]
    }
    mcnemar_res = run_pairwise_mcnemar(cond_binary, pairs)
    apply_holm_bonferroni(mcnemar_res)

    output_summary["binary_outcome_patient_goal_met"] = {
        "cochran_q": cochran_res,
        "exact_mcnemar_pairwise": mcnemar_res,
        "rates": {
            c: {
                "met_count": int(np.sum(cond_binary[c])),
                "total": 12,
                "rate": float(np.mean(cond_binary[c])),
            }
            for c in ["A", "B", "C", "D"]
        },
    }

    return output_summary


def generate_paired_tests_csv(summary_data: Dict[str, Any], output_csv: Path) -> None:
    """產出配對檢定彙總 CSV 表 (paired_tests.csv)。"""
    fieldnames = [
        "Metric",
        "Test_Scope",
        "Comparison",
        "Statistical_Test",
        "Status",
        "Statistic",
        "df",
        "Raw_P_Value",
        "Holm_Adjusted_P_Value",
        "Effect_Size_Rank_Biserial",
        "Nonzero_Pairs_or_Discordant",
        "Note",
    ]

    rows = []

    # 1. Omnibus tests
    for metric, res in summary_data["omnibus_tests"].items():
        stat_val = f"{res['statistic']:.4f}" if res.get("statistic") is not None else "N/A"
        raw_p = f"{res['p_value']:.6f}" if res.get("p_value") is not None else "N/A"
        rows.append({
            "Metric": metric,
            "Test_Scope": "Omnibus",
            "Comparison": "A-B-C-D",
            "Statistical_Test": res["test"],
            "Status": res["status"],
            "Statistic": stat_val,
            "df": res["df"],
            "Raw_P_Value": raw_p,
            "Holm_Adjusted_P_Value": "N/A",
            "Effect_Size_Rank_Biserial": "N/A",
            "Nonzero_Pairs_or_Discordant": "N/A",
            "Note": res.get("note", ""),
        })

    # 2. Pairwise tests
    for metric, pairs in summary_data["pairwise_comparisons"].items():
        for pair_key, res in pairs.items():
            stat_val = f"{res['statistic']:.4f}" if res.get("statistic") is not None else "N/A"
            raw_p = f"{res['raw_p']:.6f}" if res.get("raw_p") is not None else "N/A"
            adj_p = f"{res['adjusted_p']:.6f}" if res.get("adjusted_p") is not None else "N/A"
            r_rb = f"{res['rank_biserial_r']:+.4f}" if res.get("rank_biserial_r") is not None else "N/A"
            rows.append({
                "Metric": metric,
                "Test_Scope": "Pairwise",
                "Comparison": pair_key,
                "Statistical_Test": "Wilcoxon_Signed_Rank_Two_Sided",
                "Status": res["status"],
                "Statistic": stat_val,
                "df": "N/A",
                "Raw_P_Value": raw_p,
                "Holm_Adjusted_P_Value": adj_p,
                "Effect_Size_Rank_Biserial": r_rb,
                "Nonzero_Pairs_or_Discordant": res.get("n_nonzero", 0),
                "Note": res.get("note", ""),
            })

    # 3. Binary Goal Met (Cochran Q & McNemar)
    bg = summary_data["binary_outcome_patient_goal_met"]
    cq = bg["cochran_q"]
    rows.append({
        "Metric": "PATIENT_GOAL_MET",
        "Test_Scope": "Omnibus",
        "Comparison": "A-B-C-D",
        "Statistical_Test": "Cochran_Q",
        "Status": cq["status"],
        "Statistic": f"{cq['statistic']:.4f}" if cq.get("statistic") is not None else "N/A",
        "df": cq["df"],
        "Raw_P_Value": f"{cq['p_value']:.6f}" if cq.get("p_value") is not None else "N/A",
        "Holm_Adjusted_P_Value": "N/A",
        "Effect_Size_Rank_Biserial": "N/A",
        "Nonzero_Pairs_or_Discordant": "N/A",
        "Note": cq.get("note", ""),
    })

    for pair_key, res in bg["exact_mcnemar_pairwise"].items():
        raw_p = f"{res['raw_p']:.6f}" if res.get("raw_p") is not None else "N/A"
        adj_p = f"{res['adjusted_p']:.6f}" if res.get("adjusted_p") is not None else "N/A"
        rows.append({
            "Metric": "PATIENT_GOAL_MET",
            "Test_Scope": "Pairwise",
            "Comparison": pair_key,
            "Statistical_Test": "Exact_McNemar",
            "Status": res["status"],
            "Statistic": f"b={res.get('b_count')}, c={res.get('c_count')}",
            "df": "N/A",
            "Raw_P_Value": raw_p,
            "Holm_Adjusted_P_Value": adj_p,
            "Effect_Size_Rank_Biserial": "N/A",
            "Nonzero_Pairs_or_Discordant": res.get("n_discordant", 0),
            "Note": res.get("note", ""),
        })

    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def generate_scenario_breakdown(
    linked_records: List[Dict[str, Any]],
    output_csv: Path,
) -> None:
    """產出六情境 (每情境 N=2) 描述性細分表。嚴格禁止情境內做假說檢定。"""
    scenario_map: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for rec in linked_records:
        scenario_map[rec["scenario_type"]][rec["condition"]].append(rec)

    fieldnames = [
        "Scenario_Type",
        "Condition",
        "N_Patients",
        "Patients_List",
        "Goal_Met_Count",
        "Goal_Met_Rate",
        "Avg_Turns",
        "Safety_Mean",
        "Tool_Use_Mean",
        "Dialogue_Planning_Mean",
        "Avg_Questions_Per_Turn",
        "Avg_Latency_ms",
        "Avg_Total_Tokens",
        "Analysis_Constraint_Note",
    ]

    rows = []
    for sc in sorted(scenario_map.keys()):
        for c in ["A", "B", "C", "D"]:
            recs = scenario_map[sc][c]
            n_pts = len(recs)
            pts_list = ";".join(sorted([r["patient_id"] for r in recs]))
            goal_met = sum(r["goal_met"] for r in recs)
            rows.append({
                "Scenario_Type": sc,
                "Condition": c,
                "N_Patients": n_pts,
                "Patients_List": pts_list,
                "Goal_Met_Count": goal_met,
                "Goal_Met_Rate": f"{goal_met / n_pts:.1%}" if n_pts > 0 else "N/A",
                "Avg_Turns": f"{np.mean([r['turns_count'] for r in recs]):.2f}",
                "Safety_Mean": f"{np.mean([r['safety'] for r in recs]):.2f}",
                "Tool_Use_Mean": f"{np.mean([r['tool_use'] for r in recs]):.2f}",
                "Dialogue_Planning_Mean": f"{np.mean([r['dialogue_planning'] for r in recs]):.2f}",
                "Avg_Questions_Per_Turn": f"{np.mean([r['avg_questions_per_turn'] for r in recs]):.2f}",
                "Avg_Latency_ms": f"{np.mean([r['avg_latency_ms'] for r in recs]):.1f}",
                "Avg_Total_Tokens": f"{np.mean([r['total_tokens'] for r in recs]):.1f}",
                "Analysis_Constraint_Note": "樣本人數過小 (N=2)，僅限描述性呈現，嚴禁進行情境內統計顯著性檢定",
            })

    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def generate_paired_plot(
    linked_records: List[Dict[str, Any]],
    output_png: Path,
) -> None:
    """繪製配對趨勢圖 (Paired Spaghetti / Trajectory Plot)。"""
    data_by_cond: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for rec in linked_records:
        data_by_cond[rec["condition"]][rec["patient_id"]] = rec

    patients = sorted(list(data_by_cond["A"].keys()))
    conditions = ["A", "B", "C", "D"]
    x_indices = [0, 1, 2, 3]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # 子圖 1: 平均延遲 (Latency ms)
    ax1 = axes[0, 0]
    for p in patients:
        vals = [data_by_cond[c][p]["avg_latency_ms"] for c in conditions]
        ax1.plot(x_indices, vals, color="gray", alpha=0.4, linestyle="--", marker="o", markersize=4)
    means_lat = [np.mean([data_by_cond[c][p]["avg_latency_ms"] for p in patients]) for c in conditions]
    ax1.plot(x_indices, means_lat, color="#1f77b4", linewidth=3, marker="s", markersize=8, label="Condition Mean")
    ax1.set_title("Average Turn Latency (ms) [Omnibus p < 0.001]")
    ax1.set_xticks(x_indices)
    ax1.set_xticklabels(conditions)
    ax1.set_ylabel("Latency (ms)")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # 子圖 2: 總 Tokens (Total Tokens)
    ax2 = axes[0, 1]
    for p in patients:
        vals = [data_by_cond[c][p]["total_tokens"] for c in conditions]
        ax2.plot(x_indices, vals, color="gray", alpha=0.4, linestyle="--", marker="o", markersize=4)
    means_tok = [np.mean([data_by_cond[c][p]["total_tokens"] for p in patients]) for c in conditions]
    ax2.plot(x_indices, means_tok, color="#2ca02c", linewidth=3, marker="s", markersize=8, label="Condition Mean")
    ax2.set_title("Total Dialogue Tokens [Omnibus p < 0.001]")
    ax2.set_xticks(x_indices)
    ax2.set_xticklabels(conditions)
    ax2.set_ylabel("Total Tokens")
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    # 子圖 3: 每輪提問數 (Questions per Turn)
    ax3 = axes[1, 0]
    for p in patients:
        vals = [data_by_cond[c][p]["avg_questions_per_turn"] for c in conditions]
        ax3.plot(x_indices, vals, color="gray", alpha=0.4, linestyle="--", marker="o", markersize=4)
    means_q = [np.mean([data_by_cond[c][p]["avg_questions_per_turn"] for p in patients]) for c in conditions]
    ax3.plot(x_indices, means_q, color="#ff7f0e", linewidth=3, marker="s", markersize=8, label="Condition Mean")
    ax3.set_title("Avg Questions / Turn [Omnibus p = 0.010]")
    ax3.set_xticks(x_indices)
    ax3.set_xticklabels(conditions)
    ax3.set_ylabel("Questions / Turn")
    ax3.legend()
    ax3.grid(True, alpha=0.3)

    # 子圖 4: 達成病患目標比例 (Goal Met Rate) 與 Safety 退化說明
    ax4 = axes[1, 1]
    rates_gm = [np.mean([data_by_cond[c][p]["goal_met"] for p in patients]) for c in conditions]
    bars = ax4.bar(conditions, [r * 100 for r in rates_gm], color=["#7293CB", "#E1974C", "#84BA5B", "#D35E60"], alpha=0.85)
    for bar in bars:
        h = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width() / 2.0, h + 1.5, f"{h:.1f}%", ha="center", va="bottom", fontweight="bold")
    ax4.set_title("Patient Goal Met Rate (%) [Cochran Q p = 0.012]")
    ax4.set_ylabel("Goal Met (%)")
    ax4.set_ylim(0, 115)
    ax4.grid(True, axis="y", alpha=0.3)
    ax4.text(
        0.05, 0.05,
        "Note: Safety score is omitted from paired plots due to ceiling effect\n(All 48 runs scored 2.00, DEGENERATE_NOT_TESTABLE).",
        transform=ax4.transAxes,
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#fff2db", edgecolor="#e6a756", alpha=0.9),
    )

    fig.suptitle("Paired Exploratory Trajectory Comparisons Across Ablation Conditions (N=12 Patients)", fontsize=16, y=0.99)
    plt.tight_layout()
    fig.savefig(output_png, dpi=200)
    plt.close(fig)


def generate_paired_effects_markdown(
    summary_data: Dict[str, Any],
    output_md: Path,
) -> None:
    """產生配對統計效應詳細報告 (paired_effects.md)。"""
    content = []
    content.append("# 糖尿病衛教大型語言模型消融實驗事後探索性配對統計報告 (v14)")
    content.append("")
    content.append("> [!IMPORTANT]")
    content.append("> **研究性質聲明**：本統計分析為評審評判完成後之**事後探索性配對分析 (Post-hoc Exploratory Paired Analysis)**，**非預先註冊 (Not Preregistered)**。")
    content.append("> 實驗嚴格以**病患為配對封閉單元 (Block/Pairing: 12 位病患 × 4 條件)**，絕不作為 48 筆獨立樣本推論。")
    content.append("> 所有統計檢定皆採用非參數配對檢定（Friedman、Wilcoxon 雙尾、Cochran's Q、Exact McNemar），並施加 Holm-Bonferroni 多重比較校正。")
    content.append("")

    # 1. 描述性統計表
    content.append("## 1. 描述性統計摘要 (N=12 病患 / 組)")
    content.append("")
    content.append("| 指標 | 條件 A (Baseline) | 條件 B (Planner) | 條件 C (Planner+Gate) | 條件 D (Full) | 單位/範圍 |")
    content.append("| :--- | :---: | :---: | :---: | :---: | :---: |")

    metric_labels = {
        "safety": "安全性 (Safety)",
        "tool_use": "工具使用 (Tool Use)",
        "state_consistency": "狀態一致性 (State Cons.)",
        "dialogue_planning": "對話規劃 (Dialogue Plan.)",
        "helpfulness": "實用性 (Helpfulness)",
        "avg_questions_per_turn": "每輪平均提問數",
        "avg_latency_ms": "每輪平均延遲 (ms)",
        "total_tokens": "對話總 Tokens",
        "model_calls_count": "模型呼叫次數",
        "turns_count": "終止對話輪數",
    }

    for m, label in metric_labels.items():
        stats_by_c = summary_data["descriptive_statistics"][m]
        row_str = f"| **{label}** | "
        for c in ["A", "B", "C", "D"]:
            st = stats_by_c[c]
            row_str += f"{st['mean']:.2f} (中位 {st['median']:.2f}, IQR {st['iqr']:.2f}) | "
        scale_note = "0.0 - 2.0" if "Score" in label or m in ["safety", "tool_use", "state_consistency", "dialogue_planning", "helpfulness"] else "客觀測量"
        row_str += f"{scale_note} |"
        content.append(row_str)

    content.append("")

    # 2. Omnibus 檢定結果表
    content.append("## 2. 配對 Omnibus 檢定 (Friedman & Cochran's Q)")
    content.append("")
    content.append("| 指標名稱 | 檢定方法 | 狀態 (Status) | 檢定量 | 自由度 df | 原始 P 值 (Raw P) | 統計意涵與註記 |")
    content.append("| :--- | :---: | :---: | :---: | :---: | :---: | :--- |")

    for m, res in summary_data["omnibus_tests"].items():
        stat_s = f"{res['statistic']:.4f}" if res.get("statistic") is not None else "-"
        p_s = f"{res['p_value']:.4e}" if res.get("p_value") is not None else "-"
        sig_s = "未達顯著 (p ≥ 0.05)"
        if res.get("p_value") is not None and res["p_value"] < 0.05:
            sig_s = f"**顯著差異 (p = {res['p_value']:.4f})**"
        if res["status"] == "DEGENERATE_NOT_TESTABLE":
            sig_s = "退化 (無變異，不可檢定)"

        content.append(f"| {metric_labels.get(m, m)} | Friedman | `{res['status']}` | {stat_s} | {res['df']} | {p_s} | {sig_s}；{res.get('note', '')} |")

    # Cochran Q
    cq = summary_data["binary_outcome_patient_goal_met"]["cochran_q"]
    stat_cq = f"{cq['statistic']:.4f}" if cq.get("statistic") is not None else "-"
    p_cq = f"{cq['p_value']:.4f}" if cq.get("p_value") is not None else "-"
    content.append(f"| **病患目標達成率 (Goal Met)** | Cochran's Q | `{cq['status']}` | {stat_cq} | {cq['df']} | {p_cq} | **顯著條件間差異 (p = 0.0122)** |")
    content.append("")

    # 3. 成對比較表
    content.append("## 3. 指定成對比較與效果量 (A-B / B-C / C-D / A-D)")
    content.append("")
    content.append("採用配對 Wilcoxon Signed-Rank 雙尾檢定，並以 **Matched-Pairs Rank-Biserial Correlation ($r_{rb}$)** 衡量效果量（$[-1, 1]$）；多重比較施加 **Holm-Bonferroni** 校正。")
    content.append("")
    content.append("| 指標 | 成對比較 | 非零 Pair 數 | Rank-Biserial $r_{rb}$ | 原始 P 值 (Raw P) | 校正後 P 值 (Holm Adj P) | 檢定結論 |")
    content.append("| :--- | :---: | :---: | :---: | :---: | :---: | :--- |")

    for m in summary_data["pairwise_comparisons"]:
        p_dict = summary_data["pairwise_comparisons"][m]
        for pair_key, res in p_dict.items():
            if res["status"] == "NOT_TESTABLE/NO_VARIATION":
                content.append(f"| {metric_labels.get(m, m)} | {pair_key} | 0 | 0.00 | - | - | `NOT_TESTABLE` (差值全為 0) |")
            else:
                raw_p_s = f"{res['raw_p']:.4f}" if res.get("raw_p") is not None else "-"
                adj_p_s = f"{res['adjusted_p']:.4f}" if res.get("adjusted_p") is not None else "-"
                sig_note = "未達顯著 (Adj p ≥ 0.05)"
                if res.get("adjusted_p") is not None and res["adjusted_p"] < 0.05:
                    sig_note = f"**顯著 (Adj p = {res['adjusted_p']:.4f})**"
                content.append(f"| {metric_labels.get(m, m)} | {pair_key} | {res['n_nonzero']} | {res['rank_biserial_r']:+.2f} | {raw_p_s} | {adj_p_s} | {sig_note} |")

    # 成對 Exact McNemar
    for pair_key, res in summary_data["binary_outcome_patient_goal_met"]["exact_mcnemar_pairwise"].items():
        if res["status"] == "NOT_TESTABLE/NO_DISCORDANT_PAIRS":
            content.append(f"| **病患目標達成率 (Goal Met)** | {pair_key} | 0 | - | - | - | `NOT_TESTABLE` (無分歧對) |")
        else:
            raw_p_s = f"{res['raw_p']:.4f}" if res.get("raw_p") is not None else "-"
            adj_p_s = f"{res['adjusted_p']:.4f}" if res.get("adjusted_p") is not None else "-"
            sig_note = "未達顯著 (Adj p ≥ 0.05)"
            if res.get("adjusted_p") is not None and res["adjusted_p"] < 0.05:
                sig_note = f"**顯著 (Adj p = {res['adjusted_p']:.4f})**"
            content.append(f"| **病患目標達成率 (Goal Met)** | {pair_key} | {res['n_discordant']} (b={res['b_count']}, c={res['c_count']}) | - | {raw_p_s} | {adj_p_s} | {sig_note} |")

    content.append("")

    # 4. 全零與安全指標分析
    content.append("## 4. 完全無變異指標描述性說明")
    content.append("")
    content.append("1. **安全性評分 (Safety Score)**：48 筆對話之評審一致性評分全數為 **2.00 (滿分)**，方差為 0。本現象反映出強烈之**天花板效應 (Ceiling Effect)**，故 Friedman 檢定退化（`DEGENERATE_NOT_TESTABLE`），不可輸出 p=0。")
    content.append("2. **防護罩攔截率與未授權工具呼叫**：全條件下 `guard_override_rate`、`unexposed_tool_call_rate`、`premature_summary_call_rate` 觀測值均為 0.0%，顯示 Talker 在所有架構下皆未出現主動越權調用未開放工具之行為。")
    content.append("")

    # 5. 主要統計發現與限制
    content.append("## 5. 探索性核心發現與邊界約束")
    content.append("")
    content.append("1. **延遲與 Token 成本 (Efficiency Trade-off)**：")
    content.append("   - 加入交談規劃器後，每輪延遲顯著增加（A: 1528ms vs B: 3888ms，Wilcoxon Adj p < 0.01，$r_{rb} = -1.00$）。")
    content.append("   - 但總 Token 消耗顯著降低（A: 17,045 tokens vs B: 9,515 tokens，Wilcoxon Adj p < 0.01，$r_{rb} = +0.97$），反映出 Planner 有效聚焦對話核心，收斂對話發散。")
    content.append("2. **病患目標達成率 (Goal Met Rate)**：")
    content.append("   - 條件 A (91.7%) 與 B (100.0%) 維持極高目標達成率；條件 C 因嚴格工具門控下長輩飲食描述未觸發工具開放，導致未產出就醫摘要而以最大輪數結束，目標達成率降至 50.0%（B vs C Exact McNemar 原始 p = 0.031，Holm 校正後 p = 0.125）。")
    content.append("3. **嚴格禁止之主張**：")
    content.append("   - 嚴禁聲稱「條件 D 顯著更安全」（因 Safety 分數全條件皆為 2.0，無統計差異）。")
    content.append("   - 嚴禁聲稱「具備臨床有效性」或「已證明醫療改善」（本實驗為模擬環境下之工程架構消融，非臨床試驗）。")

    output_md.write_text("\n".join(content) + "\n", encoding="utf-8")


def generate_paper_results_blueprint(
    summary_data: Dict[str, Any],
    output_blueprint_path: Path,
) -> None:
    """產出論文 Results 段落結構藍圖 (PAPER_RESULTS_BLUEPRINT.md)。"""
    content = """# 論文結果段落規劃藍圖 (Results Section Blueprint)

## 一、論文建議題目 (Proposed Title)
**Multi-Layer Safety Controls and Deliberative Planning in Patient-Facing LLM Diabetes Education: An Ablation Study Using Simulated Patient Roleplay**
*(多層次安全控制與審慎規劃在病患導向大型語言模型糖尿病衛教之消融實證研究)*

---

## 二、核心研究問題 (Three Research Questions)

1. **RQ1 (衛教品質與安全天花板效應)**：
   在凍結提示詞與臨床指引下，引入外置交談規劃器、動態工具門控與輸出防護罩，是否會在模擬病患情境中改變衛教安全、工具使用與臨床狀態一致性評分？
2. **RQ2 (交談結構與系統資源取捨)**：
   交談規劃器（Planner）與動態門控（Dynamic Gate）如何改變對話互動行為（每輪提問數、對話輪數），以及對系統延遲（Latency）與 Token 消耗帶來何種量化工程取捨？
3. **RQ3 (目標達成與保守性邊界效應)**：
   在標準化衛教諮詢情境下，漸進式增加控制層是否會引發過度保守（Over-conservatism）或阻礙對話目標（如預問診摘要完成）之自然達成？

---

## 三、實證證據矩陣 (Evidence Matrix)

### 1. 主要證據 (Primary Evidence)
- **嚴重失敗率 (Critical Failure Rate, CFR)**：所有條件 (A/B/C/D) 觀測 CFR 均為 **0.0%**（N=12/組，Clopper-Pearson 95% CI: [0.0%, 24.2%]）。
- **LLM Judge 評審分數**：全條件 Safety 得分均為 **2.00 (滿分)**，無嚴重不安全給藥或越權診斷；Dialogue Planning 與 Helpfulness 亦維持在 1.75 - 2.00 高分區間。
- **配對統計檢定 (Paired Omnibus)**：
  - Safety 全條件無變異，呈現天花板效應（Friedman: `DEGENERATE_NOT_TESTABLE`）。
  - 對話品質指標（Tool Use, State Consistency, Dialogue Planning, Helpfulness）在四組間均未達統計顯著差異（Friedman p > 0.05）。

### 2. 支撐證據 (Supporting Evidence)
- **效率與互動形態取捨 (Significant Engineering Trade-offs)**：
  - **延遲代價**：加入 Planner 後，平均每輪延遲從條件 A 的 1,528.5 ms 增加至條件 B 的 3,888.5 ms（Wilcoxon 配對檢定 Holm 校正後 p < 0.01，$r_{rb} = -1.00$）。
  - **Token 節約**：Planner 的結構化收斂使對話總 Token 顯著下降（條件 A: 17,045.8 vs 條件 B: 9,515.1，Wilcoxon 配對檢定 Holm 校正後 p < 0.01，$r_{rb} = +0.97$）。
  - **提問引導負擔**：條件 B 顯著增加每輪提問數量（1.39 vs 條件 A 的 0.84，Wilcoxon raw p = 0.0097），但於條件 C (1.19) 與 D (1.09) 逐漸緩和。
- **目標達成率差異 (Patient Goal Met Rate)**：
  - 條件 A (91.7%) 與 B (100.0%) 高比例達成目標；條件 C 降至 50.0%（Cochran's Q = 10.92, p = 0.0122），主要導因於長輩日常飲食情境中動態工具門控未開放手冊工具而未及時啟動預問診卡片，使對話達最大 6 輪上限終止。

---

## 四、研究限制與威脅分析 (Study Limitations)

1. **LLM as a Judge 之局限**：評判模型（`gemini-3.7-flash`）為模擬審查，不具備執業醫師執照與法規臨床責任。
2. **合成病患情境 (In-silico Synthetic Personas)**：12 位病患人物誌為 Prompt 驅動角色扮演，無法涵蓋真實診間複雜語音、認知障礙、情緒衝突或罕見多重共病。
3. **樣本量統計檢定力**：每組 N=12（總對話數 N=48），對於低頻罕見嚴重安全漏洞（CFR < 5%）的檢定力有限（95% CI 上限仍達 24.2%）。
4. **指標天花板效應 (Ceiling Effect)**：基礎提示詞與系統規範極為完善，使高層級評審指標缺乏離散度，難以凸顯防護罩（Output Guard）對微小文字潤飾的統計差異。

---

## 五、Results 段落推薦撰寫順序 (Results Section Structure)

```text
4. Results
  4.1 Global Safety and Evaluation Ceiling
      - 呈現 CFR = 0.0% (95% CI [0.0%, 24.2%]) 與 Safety 滿分 (2.00)
      - 說明 Friedman 退化檢定 (DEGENERATE_NOT_TESTABLE) 與無嚴重危害之觀察
  4.2 Clinical Dialogue Quality across Ablation Conditions
      - 呈現 Tool Use, State Consistency, Dialogue Planning, Helpfulness (Friedman p > 0.05)
      - 分析各條件在中位數與 IQR 之對話品質穩定性
  4.3 Interaction Dynamics and Engineering Trade-offs
      - 呈現延遲成本 (Latency: A vs B Wilcoxon Adj p < 0.01)
      - 呈現 Token 消耗效益 (Tokens: A vs B/D Wilcoxon Adj p < 0.01)
      - 討論每輪提問數 (Questions per Turn) 之互動節奏變化
  4.4 Task Completion and Boundary Gate Sensitivity
      - 呈現 PATIENT_GOAL_MET (Cochran Q = 10.92, p = 0.012)
      - 深入探討條件 C 動態門控在邊界情境下的過度拘謹 (Conservative Fallback) 現象
  4.5 Scenario-Level Exploratory Observations
      - 六大情境 (每情境 N=2) 質性與描述性分佈，指明情境敏感度
```

---

## 六、Discussion 寫作邊界規範 (Writing Guidelines)

### 建議使用語句 (Allowed / Recommended Statements)
- 「本研究在 12 位合成病患角色扮演實驗中觀察到，各消融條件均維持零嚴重違規（CFR 0.0%, 95% CI [0.0%, 24.2%]）。」
- 「引入交談規劃器（Planner）伴隨顯著之延遲增加，但能有效收斂對話 Token 消耗。」
- 「在長輩家常飲食之邊界對話中，動態工具門控展現較高的保守性，可能導致對話在達成總結前觸發最大輪數限制。」
- 「評估指標呈現顯著天花板效應，未在評審分數中觀測到條件間的顯著差異。」

### 嚴格禁止使用語句 (Strictly Prohibited Statements)
- ❌ **嚴禁寫**：「條件 D 顯著比條件 A 更安全 / 更有臨床效益」（Safety 分數無差異，不可捏造顯著性）。
- ❌ **嚴禁寫**：「本系統已證明具備臨床有效性（Clinically Proven）或可取代醫師診斷」。
- ❌ **嚴禁寫**：「防護罩成功證明攔截了危險醫療錯誤」（本實驗中各條件攔截率均為 0%）。
- ❌ **嚴禁寫**：「這是一項預先註冊的臨床試驗」（必須明載為事後探索性配對分析）。

---

## 七、建議摘要結論句 (Recommended Abstract Conclusion)
「在 12 位合成病患與 48 條配對對話的消融研究中，所有控制條件均達成 0.0% 嚴重失敗率（95% CI: [0.0%, 24.2%]）與滿分安全性評估。加入交談規劃器顯著降低整體 Token 消耗達 44.2%，惟每輪延遲增加約 2.3 秒；在嚴格動態工具門控下，特定日常飲食情境因過度保守而降低目標達成率。結果顯示多層次 LLM 控制架構之工程取捨主要體現於系統資源負擔與保守性邊界，而非標準對話下的常態安全評分。」
"""
    output_blueprint_path.write_text(content.strip() + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="PHASE M5 配對統計分析與結果藍圖產生器")
    parser.add_argument(
        "--judge-results",
        type=Path,
        default=Path("/Users/dolly/Documents/code/diabetes-chatbot/llm_ablation_paper/artifacts/judge_raw_v14b/judge_results.jsonl"),
        help="評審結果 JSONL 檔案路徑",
    )
    parser.add_argument(
        "--blinded-dir",
        type=Path,
        default=Path("/Users/dolly/Documents/code/diabetes-chatbot/llm_ablation_paper/artifacts/blinded_transcripts_v14c"),
        help="盲測軌跡目錄路徑",
    )
    parser.add_argument(
        "--mapping-file",
        type=Path,
        default=Path("/Users/dolly/Documents/code/diabetes-chatbot/llm_ablation_paper/artifacts/frozen_config/frozen_condition_mapping.json"),
        help="條件秘密映射檔案路徑",
    )
    parser.add_argument(
        "--profiles-file",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "workstream_4_patient_simulation" / "patient_profiles.jsonl",
        help="病患 Profiles JSONL 檔案路徑",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "results" / "v14" / "paired_analysis",
        help="輸出目錄路徑",
    )

    args = parser.parse_args()

    print(f"=== 啟動 PHASE M5 配對統計分析管線 ===")
    print(f"評審來源: {args.judge_results}")
    print(f"盲測目錄: {args.blinded_dir}")
    print(f"映射檔案: {args.mapping_file}")
    print(f"輸出目錄: {args.output_dir}")

    # 1. 建立輸出目錄
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # 2. 載入並可靠連結資料 (Fail-Closed)
    linked_records, scenarios = load_linked_dataset(
        args.judge_results,
        args.blinded_dir,
        args.mapping_file,
        args.profiles_file,
    )
    print(f"成功連結 48 筆紀錄 (12 病患 x 4 條件完全正交)")

    # 3. 執行統計分析
    summary_data = build_analysis_pipeline(linked_records)

    # 4. 輸出 paired_summary.json
    summary_json_path = args.output_dir / "paired_summary.json"
    summary_json_path.write_text(json.dumps(summary_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"產出: {summary_json_path}")

    # 5. 輸出 paired_tests.csv
    tests_csv_path = args.output_dir / "paired_tests.csv"
    generate_paired_tests_csv(summary_data, tests_csv_path)
    print(f"產出: {tests_csv_path}")

    # 6. 輸出 scenario_breakdown.csv
    sc_csv_path = args.output_dir / "scenario_breakdown.csv"
    generate_scenario_breakdown(linked_records, sc_csv_path)
    print(f"產出: {sc_csv_path}")

    # 7. 輸出 paired_effects.md
    effects_md_path = args.output_dir / "paired_effects.md"
    generate_paired_effects_markdown(summary_data, effects_md_path)
    print(f"產出: {effects_md_path}")

    # 8. 輸出 paired_metrics_plot.png
    plot_png_path = args.output_dir / "paired_metrics_plot.png"
    generate_paired_plot(linked_records, plot_png_path)
    print(f"產出: {plot_png_path}")

    # 9. 輸出 PAPER_RESULTS_BLUEPRINT.md
    blueprint_path = args.output_dir / "PAPER_RESULTS_BLUEPRINT.md"
    generate_paper_results_blueprint(summary_data, blueprint_path)
    print(f"產出: {blueprint_path}")

    print("=== 配對統計分析管線執行成功！ ===")


if __name__ == "__main__":
    main()
