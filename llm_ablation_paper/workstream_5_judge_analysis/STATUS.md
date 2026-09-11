# Workstream 5（盲測 LLM Judge 與統計）狀態與進度報告

- **負責工作流**：Workstream 5（盲測 LLM Judge、統計、報表與結果章素材）
- **當前分支**：`ws5-judge-analysis`
- **基準 Tag**：`llm-ablation-ws1-freeze-v1.1`（Commit: `2967d56`）
- **當前狀態**：`APPROVED`（Stage 2 離線架構、Prompt、Schema、Canary、Runner、統計管線與 19 項自動化測試全數通過）
- **正式評估阻塞判定**：`BLOCKED`（等待 WS1 執行並交付 48 條正式 blinded transcripts，以及外部 opaque condition mapping）

---

## 一、 Stage 2 交付項目清單

| 檔案名稱 | 類型 | 說明 |
|---|---|---|
| `judge_prompt.md` | 評審指引 | LLM Judge 系統提示詞、五大維度（0/1/2 分）錨點與防條件洩漏約束。 |
| `judge_schema.json` | 契約約束 | 符合 Draft-7 規範之嚴格 JSON Schema，限制分數值域、枚舉分類與引證格式。 |
| `critical_failure_taxonomy.md` | 分類標準 | 定義六大嚴重失敗（處方越權、確診、神效、急症 canary、認可危險、證據錨定矛盾）。 |
| `canary_trajectories.jsonl` | 檢驗資料集 | 包含標準合規 PASS 與各大類別 FAIL 的 Canary 基準對話軌跡。 |
| `sanitizer.py` | 脫敏與防洩漏 | 物理剝除 `condition_secret`、`planner_state`、`guard_action`、開關等敏感欄位。 |
| `judge_runner.py` | 執行器 | 支援 Canary fail-closed、雙評審、第 3 次 Tie-breaker 裁決、指數退避重試與 Checkpoint。 |
| `analysis_pipeline.py` | 統計管線 | 排除無效 run（ERROR/COMMON_INPUT_BLOCK），分開計算程式客觀指標與 Judge 分數。 |
| `format_results.py` | 表格格式化 | 產出 Markdown、LaTeX 表格，並提供空白未填入假數據的 `results.csv` 模板。 |
| `plot_failure_taxonomy.py` | 視覺化 | 產出 ASCII 長條圖與 Headless Matplotlib PNG 圖形腳本。 |
| `results.csv` | 空白模板 | 僅包含欄位標頭與 A/B/C/D 空白行，絕不填入偽造數據。 |
| `evaluation_methodology.md` | 方法素材 | 完整的評估方法、指標定義、研究誠信防護與論文主張邊界指引（1,300+ 字）。 |
| `tests/` | 測試套件 | 包含 5 個測試檔，共計 19 項單元與整合測試。 |

---

## 二、 自動化測試與驗證結果

執行指令：
```bash
PYTHONPATH=. python3 -m pytest llm_ablation_paper/workstream_5_judge_analysis/tests/ -v
```

測試結果：**19 passed in 3.03s**
1. `test_canary.py`（3 tests）：
   - `test_canary_passes_with_fake_judge`：PASS
   - `test_canary_fail_closed_on_false_positive`：PASS
   - `test_canary_fail_closed_on_false_negative`：PASS
2. `test_judge_schema.py`（6 tests）：
   - `test_schema_validity`：PASS
   - `test_valid_judge_output_passes`：PASS
   - `test_scores_strictly_0_1_2`：PASS
   - `test_unauthorized_failure_type_rejected`：PASS
   - `test_no_extra_properties_allowed`：PASS
   - `test_evidence_requires_turn_and_reason`：PASS
3. `test_sanitizer.py`（3 tests）：
   - `test_sanitizer_removes_forbidden_fields`：PASS
   - `test_sanitizer_leak_detection_raises_error`：PASS
   - `test_formatted_text_contains_no_leaks`：PASS
4. `test_judge_runner.py`（5 tests）：
   - `test_dual_evaluation_consensus_agreement`：PASS
   - `test_dual_evaluation_disagreement_triggers_tiebreaker`：PASS
   - `test_retry_on_transient_failure`：PASS
   - `test_retry_exhaustion_raises_error`：PASS
   - `test_checkpointing_and_exclusion`：PASS
5. `test_fake_statistics_pipeline.py`（2 tests）：
   - `test_full_pipeline_with_opaque_grouping`（48 條端到端離線閉環）：PASS
   - `test_full_pipeline_with_unblinded_mapping`：PASS

---

## 三、 研究誠信與無洩漏證明

1. **零外部 API 呼叫**：全套開發與測試 100% 基於確定性 Mock 與 Fake Fixtures，未索取亦未呼叫付費 Gemini API。
2. **零條件洩漏**：Sanitizer 與測試保證傳送至 LLM Judge 之 Payload 中絕不包含 `condition`、`condition_secret`、`enable_*` 開關、`planner_state` 或 `guard_action`。
3. **客觀事實錨定**：`CF_GROUNDED_CONTRADICTION` 嚴格約束僅以對話中病患已揭露事實或手冊凍結依據為準。
4. **亞急性低血糖情境對齊**：主資料集以亞急性低血糖為基準，急性昏迷危機獨立列為 Canary 測試項。
5. **指標嚴格分表**：程式指標（工具調用違規、問句預算、延遲、熔斷）與 LLM 主觀評分分開呈現。
6. **模板留白**：`results.csv` 與主結果表模板維持空白，絕不填入未經盲測之虛假數據。
