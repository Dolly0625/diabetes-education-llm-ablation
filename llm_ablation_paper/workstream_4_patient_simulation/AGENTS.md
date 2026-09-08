# 工作流 4：模擬病患與多輪角色扮演

## 角色

你負責維護已驗收且不偏袒 A–D 的 Patient Agent 與十二份結構化病患設定，並完成批次角色扮演 runner。你不負責判定哪組比較好。

## 目前狀態

WS4-A 的 `patient_agent_prompt.md`、`patient_profiles.jsonl`、`profile_schema.json`、來源報告與驗證測試已完成。不得重生、替換或改寫這 12 個 profiles。當前唯一主任務是 WS4-B runner、相關離線測試，以及一個 profile×4 conditions 的 fake dry run。

## 指定閱讀

- `../shared/RESEARCH_PROTOCOL.md`
- `../shared/SYSTEM_OVERVIEW.md`
- `../shared/EXPERIMENT_CONTRACT.md`
- `../../scripts/run_case_study_simulation.py`
- `../../scripts/case_study_real_results.json`
- `../../diabetes_chatbot/tests/test_planner.py`
- `../../diabetes_chatbot/tests/test_clinical_full_alignment.py`

既有案例只能作為失敗模式與格式參考，不得直接視為正確答案。

## 任務

1. 原樣讀取已驗收 Patient Agent prompt、12 profiles、schema 與 reveal policy，不修改內容。
2. 建立批次角色扮演 runner，直接接入既有 WS1 Harness。
3. runner 必須具備逐輪 checkpoint、resume、有限次 exponential backoff 與明確終止原因。
4. 每條軌跡使用唯一 user ID、獨立 process 與暫存 state directory，禁止跨條件共享記憶。
5. 使用固定 profiles、模型參數與 seed 完成一個 profile×4 conditions 的 fake dry run；正式 12×4 執行由技術主持人完成。

## 允許修改

- 本工作目錄。
- 經技術主持人核准後，將凍結 profiles 複製到正式 artifacts。

## 禁止修改

- `diabetes_chatbot/`
- `diabetes-rag/`
- `.env`
- 正式 raw transcripts
- Judge prompt 與分數

## 病患設定要求

- 不含真實個資。
- 每個 profile 有明確 patient goal、hidden facts、reveal policy 與 risk trigger。
- 六類情境數量平衡。
- 每名病患最多六輪，除非研究協議另有凍結值。
- A–D 使用完全相同 profiles，不因初步結果重生或替換。
- Patient Agent 以結構化欄位回傳 `should_end`、`termination_reason` 與支持證據；不得以任意自由文字讓 runner 猜測終止。

## 必交付

以下既有交付不得重做：`patient_agent_prompt.md`、`patient_profiles.jsonl`、`profile_schema.json`、schema validator 與其測試。

本階段必交付：

- 可執行的 roleplay runner。
- checkpoint、resume、retry 與 state-isolation 測試。
- 一份 profile×4 conditions 的 fake dry-run 示例。
- 600–800 字模擬病患與實驗設定章素材。
- 一張可轉成論文圖的流程圖草案。
