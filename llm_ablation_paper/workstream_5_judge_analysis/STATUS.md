# Workstream 5（盲測 LLM Judge 與統計）狀態與進度報告

- **負責工作流**：Workstream 5（盲測 LLM Judge、統計、報表與結果章素材）
- **當前分支**：`ws5-judge-analysis`
- **基準 Tag**：`llm-ablation-ws1-freeze-v1.1`（Commit: `2967d56`）
- **當前狀態**：`READY_FOR_REVIEW`（P0/P1 全部修正項已就緒，Schema/Invariants、暫態重試、Canary、原子 Checkpoint/Resume 與統計管線離線測試全數通過）
- **正式評估阻塞判定**：`BLOCKED`（等待 WS1 執行並交付 48 條正式 blinded transcripts，以及外部 opaque condition mapping）

---

## 一、 交付項目與修正清單

| 檔案名稱 | 類型 | 實作與研究誠信細節 |
|---|---|---|
| `judge_prompt.md` | 評審指引 | LLM Judge 系統提示詞、五大維度（0/1/2 分）錨點與防條件洩漏約束。 |
| `judge_schema.json` | 契約約束 | 符合 Draft-7 規範之嚴格 JSON Schema，限制分數值域、枚舉分類與引證格式。 |
| `critical_failure_taxonomy.md` | 分類標準 | 定義六大嚴重失敗（處方越權、確診、神效、急症 canary、認可危險、證據錨定矛盾）。主資料集對齊亞急性低血糖情境。 |
| `canary_trajectories.jsonl` | 檢驗資料集 | 包含 PASS 與各大類別 FAIL 的基準對話軌跡，附帶預期 critical flag 與 expected_failure_types。 |
| `sanitizer.py` | 脫敏與防洩漏 | 物理剝除敏感欄位；新增 `validate_blinded_input_trajectory` 嚴格拒絕未盲化輸入；智慧放行正常臨床英文字母（如維他命 C）。 |
| `judge_runner.py` | 執行器 | Draft 7 嚴格驗證、跨欄位不變量檢驗、暫態錯誤專用指數退避重試（1/2/4/8s）、安全金鑰與端點校驗、raw/parsed 分開保存、failure_types 多數決共識、原子 Checkpoint 寫入與 Resume。 |
| `analysis_pipeline.py` | 統計管線 | 補齊未暴露工具調用率、未解鎖產卡率、模型調用數；實作 Missing != Zero 規範（N=0 時輸出 None 並保留分母）；Wilson score 嚴格限制 confidence=0.95。 |
| `format_results.py` | 表格格式化 | 產出 Markdown、LaTeX 表格（安全處理 None/null），並提供空白未填入假數據的 `results.csv` 模板。 |
| `plot_failure_taxonomy.py` | 視覺化 | 產出 ASCII 長條圖與 Headless Matplotlib PNG 圖形生成腳本。 |
| `results.csv` | 空白模板 | 僅包含欄位表頭與 A/B/C/D 留白行，絕不填入偽造數據。 |
| `evaluation_methodology.md` | 方法素材 | 評估方法、指標定義、研究誠信防護與論文主張邊界指引。 |
| `tests/` | 測試套件 | 包含完整的單元與整合測試，覆蓋全部 P0/P1 要求。 |

---

## 二、 研究誠信與無洩漏證明

1. **零外部 API 呼叫**：全套開發與測試基於確定性 Mock 與 Fake Fixtures，未索取亦未呼叫付費 Gemini API。
2. **零條件洩漏**：Sanitizer 與 Runner 保證傳送至 LLM Judge 之 Payload 中絕不包含 `condition`、`condition_secret`、`enable_*` 開關、`planner_state` 或 `guard_action`。
3. **客觀事實錨定**：`CF_GROUNDED_CONTRADICTION` 嚴格約束僅以對話中病患已揭露事實或手冊凍結依據為準。
4. **亞急性低血糖情境對齊**：主資料集以亞急性低血糖為基準，急性昏迷危機獨立列為 Canary 測試項。
5. **指標嚴格分表與 Missing != Zero**：程式指標與 LLM 主觀評分分開呈現；樣本數為 0 時如實標示為 None/--，絕不以 0.0 假裝零失敗。
6. **模板留白**：`results.csv` 與主結果表模板維持空白，絕不填入未經盲測之虛假數據。
