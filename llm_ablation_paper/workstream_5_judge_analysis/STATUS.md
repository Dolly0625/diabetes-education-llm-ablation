# Workstream 5（盲測 LLM Judge 與統計）狀態與進度報告

- **負責工作流**：Workstream 5（盲測 LLM Judge、統計、報表與結果章素材）
- **當前分支**：`m22-ws5-deblind-env`
- **基準 Commit**：`2e0e78d4a8bfd1825e2ba9e7ba95cf15f84485c0`（main）
- **當前狀態**：`READY_FOR_REVIEW`（M2.2 修正完成：WS1 mapping 嚴格校驗與反轉、安全 .env 載入、artifacts 路徑錨定，39 項離線測試全數通過）
- **正式評估阻塞判定**：`BLOCKED`（等待 M3 正式執行授權，以及 WS1 交付 48 條正式 blinded transcripts 與外部 opaque condition mapping）

---

## 一、 交付項目與修正清單

| 檔案名稱 | 類型 | 實作與研究誠信細節 |
|---|---|---|
| `run_judge.py` | CLI 執行器 | 評估 CLI 入口，預設路徑錨定至 `PROJECT_ROOT/llm_ablation_paper/artifacts`。安全載入 canonical `.env`（`override=False`）；實作 `GEMINI_API_KEY` 於任何 Canary/API 呼叫前之 fail-closed 驗證且絕不洩漏金鑰；提供 `--confirm-formal-judge` 閘門、48 條（12×4）完整性檢驗、拒絕 pilot/canary/raw 洩漏、支援 resume 與原子寫入 `judge_results.jsonl`，固定模型與溫度。 |
| `run_analysis.py` | CLI 分析器 | 統計產表 CLI 入口，預設路徑錨定至 `PROJECT_ROOT/llm_ablation_paper/artifacts`。接收 WS1 標準 mapping（A–D → opaque ID），以 WS1 `validate_condition_mapping` 嚴格驗證後**反轉**為 opaque ID → A–D 傳給下游 `aggregate_pipeline`；杜絕模糊或反向格式（反向格式直接 fail-closed 拒絕）；原子產出 `summary.json`、`main_table.md`、`main_table.tex`、`results.csv` 與長條圖。 |
| `judge_prompt.md` | 評審指引 | LLM Judge 系統提示詞、五大維度（0/1/2 分）錨點與防條件洩漏約束。 |
| `judge_schema.json` | 契約約束 | 符合 Draft-7 規範之嚴格 JSON Schema，限制分數值域、枚舉分類與引證格式。 |
| `critical_failure_taxonomy.md` | 分類標準 | 定義六大嚴重失敗（處方越權、確診、神效、急症 canary、認可危險、證據錨定矛盾）。主資料集對齊亞急性低血糖情境。 |
| `canary_trajectories.jsonl` | 檢驗資料集 | 包含 PASS 與各大類別 FAIL 的基準對話軌跡，附帶預期 critical flag 與 expected_failure_types。 |
| `sanitizer.py` | 脫敏與防洩漏 | 物理剝除敏感欄位；新增 `validate_blinded_input_trajectory` 嚴格拒絕未盲化輸入；智慧放行正常臨床英文字母（如維他命 C）。 |
| `judge_runner.py` | 執行器核心 | Draft 7 嚴格驗證、跨欄位不變量檢驗、暫態錯誤專用指數退避重試（1/2/4/8s）、安全金鑰與端點校驗、raw/parsed 分開保存、failure_types 多數決共識、原子 Checkpoint 寫入與 Resume。 |
| `analysis_pipeline.py` | 統計管線核心 | 補齊未暴露工具調用率、未解鎖產卡率、模型調用數；實作 Missing != Zero 規範（N=0 時輸出 None 並保留分母）；Wilson score 嚴格限制 confidence=0.95。 |
| `format_results.py` | 表格格式化 | 產出 Markdown、LaTeX 表格（安全處理 None/null），並提供空白未填入假數據的 `results.csv` 模板。 |
| `plot_failure_taxonomy.py` | 視覺化 | 產出 ASCII 長條圖與 Headless Matplotlib PNG 圖形生成腳本。 |
| `results.csv` | 空白模板 | 僅包含欄位表頭與 A/B/C/D 留白行，絕不填入偽造數據。 |
| `evaluation_methodology.md` | 方法素材 | 評估方法、指標定義、研究誠信防護與論文主張邊界指引。 |
| `tests/` | 測試套件 | 包含完整的單元與 CLI 整合測試，涵蓋 mapping 反轉、.env 安全載入、API Key 檢查、路徑錨定及端到端解盲驗證（共 39 項測試）。 |

---

## 二、 研究誠信與無洩漏證明

1. **零外部 API 呼叫**：全套開發與測試基於確定性 Mock 與 Fake Fixtures，未索取亦未呼叫付費 Gemini API。
2. **零條件洩漏**：Sanitizer 與 Runner 保證傳送至 LLM Judge 之 Payload 中絕不包含 `condition`、`condition_secret`、`enable_*` 開關、`planner_state` 或 `guard_action`。
3. **客觀事實錨定**：`CF_GROUNDED_CONTRADICTION` 嚴格約束僅以對話中病患已揭露事實或手冊凍結依據為準。
4. **亞急性低血糖情境對齊**：主資料集以亞急性低血糖為基準，急性昏迷危機獨立列為 Canary 測試項。
5. **指標嚴格分表與 Missing != Zero**：程式指標與 LLM 主觀評分分開呈現；樣本數為 0 時如實標示為 None/--，絕不以 0.0 假裝零失敗。
6. **模板留白**：`results.csv` 與主結果表模板維持空白，絕不填入未經盲測之虛假數據。
7. **Mapping 嚴格單向反轉與防篡改**：由外部載入之 WS1 canonical condition mapping 必須且僅能為 real condition A–D → opaque ID；經 WS1 官方 validator 驗證後嚴格反轉為 opaque ID → A–D 供下游 aggregation pipeline 對照，反向或非標格式立即 fail-closed。
