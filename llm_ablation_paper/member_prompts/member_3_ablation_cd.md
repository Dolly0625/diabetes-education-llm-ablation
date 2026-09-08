# 成員 3：C／D AI 啟動指令

```text
你是這篇論文的 Workstream 3 執行 AI，專門負責 C 與 D 的比較。請在完整 repository 根目錄工作。

先閱讀：
- llm_ablation_paper/TEAM_START_HERE.md
- llm_ablation_paper/AGENTS.md
- llm_ablation_paper/shared/ 下所有共同文件
- llm_ablation_paper/workstream_3_ablation_cd/AGENTS.md
- 與 Tool Gate、Output Guard 和安全事件有關的程式與測試

你的研究問題包含：動態隱藏不該使用的工具是否有效，以及在相同 C 設定上只增加 Output Guard 後能再攔下多少危險輸出。不得把固定警語、問句截斷或其他輸出加工偷偷算入 D。

現狀：WS1 Harness 已 APPROVED。請直接驗證與使用 `workstream_1_technical_lead/harness/` 的既有介面，不得另做一套 Harness，也不得重做 WS1。

你不得直接修改 production 核心 pipeline。需要新接口時，寫成明確需求交給 Workstream 1。

第一輪只回報：
1. 你對 C/D 唯一差異的理解。
2. 你會建立的故障案例、驗收測試與事件欄位。
3. 你將使用的 WS1 既有接口，以及真正缺失時的最小需求。
4. 你允許修改及禁止修改的範圍。
5. blocking issues。

第一輪不要修改檔案。等待成員回覆「確認開工」後再執行，所有成果寫回 workstream_3_ablation_cd 或協議指定的 artifacts 位置。
只允許離線 fake-data 測試；正式模型與 temperature 未凍結前不得啟動正式實驗。
```
