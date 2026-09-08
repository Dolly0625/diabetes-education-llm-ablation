# 工作流 5：盲測 Judge、統計與結果章

## 角色

你負責建立盲測 LLM Judge、驗證 Judge 基本可靠性、分析凍結後的結果，以及撰寫結果章。你不得修改原始軌跡，也不得在評分時得知 A–D 身分。

## 指定閱讀

- `../shared/RESEARCH_PROTOCOL.md`
- `../shared/EXPERIMENT_CONTRACT.md`
- `../shared/CLAIM_BOUNDARIES.md`
- `../../diabetes_chatbot/tests/test_clinical_full_alignment.py`
- `../../diabetes_chatbot/tests/test_safety_guard.py`

評分階段只讀技術主持人提供的 blinded transcripts；不得讀 condition mapping。

## 任務

1. 建立 0／1／2 分的固定 rubric：安全、工具使用、狀態一致性、對話規劃、實用性。
2. 建立 critical failure taxonomy。
3. 要求 Judge 對每項失敗引用具體 turn 與理由。
4. 建立明顯 pass／fail canary，Judge 未通過前不得正式評分。
5. 每條軌跡評兩次；critical failure 不一致時第三次裁決。
6. 由 script 計算工具、產卡、熔斷、問句、延遲與成本指標。
7. 在技術主持人解盲後產生 A–D 主結果表、失敗類型圖與代表性案例。
8. 撰寫結果與錯誤分析，不將 Judge 分數寫成臨床結論。

## 允許修改

- 本工作目錄。
- 技術主持人指定的 `artifacts/judge_raw/`、`artifacts/derived_results/` 與 `artifacts/figures/`。

## 禁止修改或讀取

- `diabetes_chatbot/`
- `diabetes-rag/`
- `.env`
- `artifacts/raw_transcripts/`
- 評分完成前的 A–D condition mapping
- 其他工作流的草稿程式

## 評估誠信

- Judge 與受測模型相同時必須列入限制。
- LLM Judge 結果須與程式可直接計算的指標分開呈現。
- 不得刪除 Judge 意見不一致的軌跡。
- 不得手動改分；所有裁決均保留原始回覆。
- 自然產生的違規與 fault injection 必須分表。

## 必交付

- `judge_prompt.md`
- `judge_schema.json`
- `critical_failure_taxonomy.md`
- canary 資料與通過報告。
- Judge runner、統計 script 與執行指令。
- `results.csv`、主結果表與至少一張失敗類型圖。
- 1,200–1,500 字評估方法、結果與錯誤分析素材。

## 主結果表最低欄位

| 系統 | Critical Failure Rate | Safety | Tool Use | State Consistency | Helpfulness | Latency |
|---|---:|---:|---:|---:|---:|---:|
| A |  |  |  |  |  |  |
| B |  |  |  |  |  |  |
| C |  |  |  |  |  |  |
| D |  |  |  |  |  |  |
