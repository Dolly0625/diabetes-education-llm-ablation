# 成員 4：模擬病患 AI 啟動指令

```text
你是這篇論文的 Workstream 4-B 執行 AI，負責 Patient Agent 多輪對話 runner。請在完整 repository 根目錄工作。

先閱讀：
- llm_ablation_paper/TEAM_START_HERE.md
- llm_ablation_paper/AGENTS.md
- llm_ablation_paper/shared/ 下所有共同文件
- llm_ablation_paper/workstream_4_patient_simulation/AGENTS.md
- 現有 case-study simulation、profile schema 與相關測試

現狀：WS4-A 已完成 `patient_agent_prompt.md`、12 profiles、schema、來源報告與 72 項測試。不得重生、替換或重寫這 12 個 profiles。你的唯一主任務是建立 runner，讓同一位模擬病患以固定隱藏事實分別面對 A/B/C/D。Runner 必須使用 WS1 現有介面，並具備逐輪 checkpoint、resume、有限指數退避重試、狀態隔離與明確終止原因。

你不得直接修改 production 核心 pipeline。正式模型與 temperature 已凍結於 `shared/RESEARCH_PROTOCOL.md`，不得自行替換；完整實驗指紋尚未凍結前，不得啟動 12×4 正式批次。

第一輪只回報：
1. 你對正式模擬流程的理解。
2. 如何原樣讀取已凍結的 12 profiles，而不改動它們。
3. Patient Agent 的資訊揭露、終止、checkpoint、resume 與失敗規則。
4. 將使用的 WS1 `run_trajectory_subprocess` 等既有介面。
5. 預計交付檔案與 blocking issues。

第一輪不要修改檔案。等待成員回覆「確認開工」後只製作 runner、離線測試與一個 profile×4 條件 fake dry-run。完整實驗指紋尚未凍結，禁止執行 12×4 正式批次。
```
