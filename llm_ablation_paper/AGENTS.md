# 五人 AI 協作總規則

本檔適用於 `llm_ablation_paper/` 下所有工作流。子目錄的 `AGENTS.md` 可以增加限制，但不得放寬本檔規則。

## 共同研究目標

比較同一糖尿病衛教 LLM 助理逐層加入四種控制後的差異：

- A：單一 LLM、完整提示詞、所有工具均暴露。
- B：A 加上結構化 Planner。
- C：B 加上動態工具暴露與議程門禁。
- D：C 加上輸出熔斷器。

評估方法採用模擬病患多輪角色扮演、盲測 LLM-as-a-Judge，以及可由程式直接計算的軌跡指標。

## 進場前必讀

依序閱讀：

1. `README.md`
2. `shared/RESEARCH_PROTOCOL.md`
3. `shared/SYSTEM_OVERVIEW.md`
4. `shared/EXPERIMENT_CONTRACT.md`
5. `shared/CLAIM_BOUNDARIES.md`
6. `shared/FEASIBILITY_AUDIT.md`
7. 自己工作目錄內的 `AGENTS.md`
8. 自己工作目錄內 `AGENTS.md` 指定的程式檔

## 兩階段工作規則

### 階段一：只讀理解

第一次進場不得修改檔案。必須先回報：

1. 用自己的話解釋 A、B、C、D。
2. 本工作流的任務與非任務。
3. 允許讀取與修改的路徑。
4. 固定不變的實驗條件。
5. 預計交付物。
6. 仍不確定、需要技術主持人回答的問題。

### 階段二：取得組員確認後才執行

執行時必須：

- 只修改工作流明確允許的路徑。
- 不猜測未確認的架構行為。
- 區分實測結果、程式事實、推論與建議。
- 每次交付附上修改檔案、執行指令、測試結果和風險。
- 發現規格衝突時停止，更新 `STATUS.md` 的 blocker，不自行改研究問題。

## 全域禁止事項

以下路徑均以 `llm_ablation_paper/` 為起點。除工作流 1 的技術主持人外，所有工作流均禁止直接修改：

- `../diabetes_chatbot/`
- `../diabetes-rag/`
- `../.env`
- 已凍結的 raw transcripts、Judge 原始回覆及正式結果表

所有人均禁止：

- 更換模型、temperature、最大輪數或工具設定後仍與其他組直接比較。
- 讓 A–D 同時出現多個未記錄差異。
- 在主要 A–D 實驗啟用 production 的 forced retrieval、停藥警語追加或問句截斷，造成未建模的額外差異。
- 看到結果後刪除不利病患或重挑案例。
- 手動修改統計結果以符合預期。
- 將模擬病患或 LLM Judge 寫成真人病患、醫師或臨床驗證。
- 將程式測試通過率寫成臨床安全率。
- 評估 RAG 的 Recall@K、RRF、向量／圖譜優劣或門檻校準。
- 新增未經來源支持的法規、臨床效果或使用者研究主張。

## 單一真實來源

- 研究規格：`shared/RESEARCH_PROTOCOL.md`
- 系統定義：`shared/SYSTEM_OVERVIEW.md`
- 實驗資料格式：`shared/EXPERIMENT_CONTRACT.md`
- 可用與禁用主張：`shared/CLAIM_BOUNDARIES.md`
- 進度與阻塞：`STATUS.md`
- 已驗證工程風險：`shared/FEASIBILITY_AUDIT.md`

口頭決定若未更新到上述文件，不視為正式研究規格。

## 合併前驗收

每份輸出只允許三種判定：通過、部分通過、不通過。技術主持人依序檢查：

1. 是否越界修改。
2. A–D 是否只差指定層。
3. 數字是否可追溯到 artifact。
4. 結論是否超出資料。
5. 是否能在四天內強化主論點。
