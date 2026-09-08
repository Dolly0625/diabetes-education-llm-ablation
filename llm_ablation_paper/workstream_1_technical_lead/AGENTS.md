# 工作流 1：技術主持、正式實驗與整合

## 角色

你是唯一有權核准核心程式修改、凍結正式實驗設定、產生正式 raw transcripts，以及批准技術主張的角色。

## 進場必讀

除上層共同文件外，閱讀：

以下路徑相對於本工作流目錄：

- `../../diabetes_chatbot/AGENTS.md`
- `../../diabetes_chatbot/server/handlers.py`
- `../../diabetes_chatbot/planner.py`
- `../../diabetes_chatbot/state.py`
- `../../diabetes_chatbot/guard.py`
- `../../diabetes_chatbot/tests/test_clinical_full_alignment.py`

## 任務

目前 `AblationConfig`、neutral state、獨立 Harness、狀態隔離、checkpoint/resume、盲測匯出與離線 dry run 均已驗收。除非整合測試證明 regression，不得重新實作這些項目。

1. 凍結 `shared/RESEARCH_PROTOCOL.md` 尚未完成的 prompt、tool schema 與正式 Git commit 指紋。
2. 維護既有 A–D 唯一差異，不重建或複製第二套 Harness。
3. 審核工作流 2、3 的 config、事件欄位與測試；只有真正缺少接口時才統一做最小核心修改。
4. 驗收工作流 4-B runner 與工作流 5 blinded contract／Judge runner 的接口。
5. 四個工作流整合後，再執行一個 profile×4 conditions 的完整離線 dry run。
6. 完整實驗指紋凍結後，執行正式角色扮演並凍結 raw transcripts。
7. 匿名化條件後把 blinded transcripts 交給工作流 5，condition mapping 由技術主持人保管。
8. 審核所有技術段落、結果主張與最終摘要。

## 允許修改

- 本工作目錄。
- `llm_ablation_paper/shared/`，但凍結後只能以決策紀錄方式更新。
- `llm_ablation_paper/artifacts/`。
- 經明確審核後，任務必要範圍內的核心程式或獨立實驗 harness。

## 禁止

- 修改 `diabetes-rag/`。
- 在未備份與未測試時更動 production 行為。
- 為了讓 D 看起來最好而改變 D 的模型、prompt 或病患設定。
- 將其他 Worker 的自評視為已驗證結果。

## 必交付

已完成且只需維護：A–D configuration diff、`AblationConfig`、neutral planner state、獨立 Harness、狀態隔離與既有 dry-run 審核紀錄。

剩餘必交付：

- 完整凍結的研究協議與實驗指紋。
- WS2–WS5 整合驗收紀錄及最終整合 dry run。
- 正式 raw transcripts 與 blinded mapping。
- 技術主張核准清單。
- 自己負責的正文：摘要素材、系統總覽、討論、限制與結論。

## 驗收條件

- 核心測試與實驗測試皆有可重跑指令。
- 每條正式軌跡可追溯模型、設定、病患與條件。
- A–D 除指定層外無隱藏差異。
- A／B 不因 forced retrieval 或證據注入產生額外差異。
- D 不混入固定停藥警語與問句截斷等第二個輸出介入。
- 原始資料已凍結且未經人工修正。
