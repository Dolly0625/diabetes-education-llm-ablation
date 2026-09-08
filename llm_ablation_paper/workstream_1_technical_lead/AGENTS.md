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

1. 填妥並凍結 `shared/RESEARCH_PROTOCOL.md` 的 TBD。
2. 決定 A–D 的實作方式，確保相鄰條件只差一層。
3. 建立獨立 `AblationConfig` 與 harness；production 預設行為不得改變。
4. 明確處理 Planner-off 時的 neutral state、forced retrieval 關閉與額外 post-processing 關閉。
5. 實作每條軌跡獨立 process、temp state directory、唯一 user ID 與 session cache 隔離。
6. 審核工作流 2、3 提出的 patch；不得無審核直接套用。
7. 將核准的實驗程式整合到獨立實驗目錄，避免破壞 production path。
8. 執行一個病患的 A–D dry run，驗證 config diff 與狀態隔離。
9. 執行正式角色扮演並凍結 raw transcripts。
10. 匿名化條件後交給工作流 5。
11. 審核所有技術段落、結果主張與最終摘要。

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

- 凍結後的研究協議。
- A–D configuration diff 表。
- `AblationConfig`、neutral planner state 與獨立 harness。
- 狀態隔離、checkpoint、retry 與 resume 測試。
- dry run 審核紀錄。
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
