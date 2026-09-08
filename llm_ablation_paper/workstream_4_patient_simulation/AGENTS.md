# 工作流 4：模擬病患與多輪角色扮演

## 角色

你負責建立可重跑且不偏袒 A–D 的 Patient Agent、十二份結構化病患設定與批次角色扮演流程。你不負責判定哪組比較好。

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

1. 撰寫 Patient Agent system prompt。
2. 為六種情境各建立兩份病患設定。
3. 設計 reveal policy：只有被適當詢問時才揭露隱藏事實。
4. 確保病患不提供專業醫療答案、不知道 A–D 身分、不迎合系統錯誤。
5. 建立 profile schema validator。
6. 建立或提出批次角色扮演 runner。
7. runner 必須具備逐輪 checkpoint、resume、有限次 exponential backoff 與明確終止原因。
8. 每條軌跡使用唯一 user ID、獨立 process 與暫存 state directory，禁止跨條件共享記憶。
9. 以同一批 profiles 與隨機種子跑 A–D；正式執行由技術主持人完成。

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

- `patient_agent_prompt.md`
- `patient_profiles.jsonl`
- `profile_schema.json`
- schema validator 與測試。
- roleplay runner 或介面規格。
- checkpoint、resume、retry 與 state-isolation 測試。
- 一份 profile 的 dry-run 示例。
- 600–800 字模擬病患與實驗設定章素材。
- 一張可轉成論文圖的流程圖草案。
