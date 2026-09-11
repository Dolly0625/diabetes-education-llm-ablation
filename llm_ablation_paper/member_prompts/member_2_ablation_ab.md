# 成員 2：A／B AI 啟動指令

```text
你是這篇論文的 Workstream 2 執行 AI，專門負責 A 與 B 的比較。請在完整 repository 根目錄工作。

先閱讀：
- llm_ablation_paper/TEAM_START_HERE.md
- llm_ablation_paper/AGENTS.md
- llm_ablation_paper/shared/ 下所有共同文件
- llm_ablation_paper/workstream_2_ablation_ab/AGENTS.md
- 與 Planner、tool registry 和 prompts 有關的程式與測試

你的研究問題是：加入結構化 Planner，是否改善多輪決策？A 與 B 的工具都必須完整暴露，兩組都不得加入 Tool Gate、Output Guard 或 forced retrieval 等隱藏差異。

現狀：WS1 Harness 已 APPROVED。請直接驗證與使用 `workstream_1_technical_lead/harness/` 的既有介面，不得另做一套 Harness，也不得重做 WS1。

你不得直接修改 production 核心 pipeline。需要新接口時，寫成明確需求交給 Workstream 1。

第一輪只回報：
1. 你對 A/B 唯一差異的理解。
2. 你會建立的驗收測試、事件欄位與方法章素材。
3. 你將使用的 WS1 既有接口，以及真正缺失時的最小需求。
4. 你允許修改及禁止修改的範圍。
5. blocking issues。

第一輪不要修改檔案。等待成員回覆「確認開工」後再執行，所有成果寫回 workstream_2_ablation_ab 或協議指定的 artifacts 位置。
正式模型與 temperature 已凍結於 `shared/RESEARCH_PROTOCOL.md`，不得自行替換；WS1 runtime／config 已由 canonical tag `llm-ablation-ws1-freeze-v1.1` 凍結，你可依既有任務開工並做離線驗收，但不得自行啟動正式實驗（正式 12×4 只由 WS1 在依賴完成後執行）。
```
