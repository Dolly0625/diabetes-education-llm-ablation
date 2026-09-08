# 五人團隊開始指南

> 群組交接請優先閱讀 `GROUP_HANDOFF_GUIDE.md`；本檔為簡版摘要。

## 我們到底要做什麼？

我們要用同一個糖尿病衛教聊天機器人，比較四種逐層增加的系統：

| 組別 | 白話說明 | 想回答的問題 |
|---|---|---|
| A | 只靠一個 LLM 與完整提示詞，全部工具都讓它看到 | 只靠提示詞能做到多安全？ |
| B | 在 A 前面加入 Planner，先判斷目前要問什麼、做什麼 | 結構化規劃是否改善多輪決策？ |
| C | 在 B 上加入 Tool Gate，只顯示當下允許使用的工具 | 直接藏起不該用的工具是否比文字禁止有效？ |
| D | 在 C 後面加入 Output Guard，輸出前再做確定性檢查 | 最後一道程式防線能再攔下多少危險回答？ |

這不是五個人各寫一篇論文。五個人共同完成同一篇論文，每個人負責其中一段可驗收的工作。

## 最後實際要跑什麼？

正式流程預計是：

1. 先用 1 位測試病患，分別跑 A、B、C、D，確認資料管線正確。
2. 再用 12 位模擬病患，每位病患分別跑 A、B、C、D。
3. 每條對話最多 6 輪；病患由 Patient Agent 按固定 profile 角色扮演。
4. 所有對話匿名化後交給 LLM Judge 盲評，不讓 Judge 知道組別。
5. 比較安全違規、任務完成、工具使用、詢問負擔與拒答等結果。

正式規模為 12 位病患 × 4 個條件 = 48 條對話軌跡，最多 288 輪助理對話。這個數字是上限，不代表現在立刻全部執行。

## 五個人如何分工？

| 成員 | 工作流 | 主要交付物 | 可以先做什麼 |
|---|---|---|---|
| 1 | 技術主持 | 維護已核准 Harness、凍結實驗指紋、整合驗收與正式執行 | 驗收 WS2–WS5，不得重建 Harness |
| 2 | A／B | A 與 B 的設定驗證、Planner 效果事件、方法章素材 | 先定義 A/B 驗收測試與事件欄位 |
| 3 | C／D | Tool Gate 與 Output Guard 的驗證、故障案例 | 先定義 C/D 驗收測試與違規事件 |
| 4 | 模擬病患 | 維護已驗收 profiles，完成 Patient Agent runner、終止條件與 checkpoint | 只做 WS4-B runner，不得重做 profiles |
| 5 | Judge 與分析 | 盲評 rubric、Judge runner、統計表與論文結果素材 | 先完成 rubric、schema 與假資料測試 |

WS1 Harness 已完成。成員 2–5 可立即開始各自的離線開發，但不得自行修改核心 production pipeline，也不得在完整實驗指紋凍結前啟動正式 A–D 批次。

## 你要怎麼把專案交給其他人？

### 目前交接狀態（2026-09-08）

- WS1 Harness 已驗收，不得重建或另做一套控制器。
- WS4-A profiles、schema 與來源驗證已完成；成員 4 下一步只做 WS4-B runner。
- WS2、WS3、WS5 可立即使用離線 fake data 開發與測試。
- 正式模型、各角色 temperature、max turns 與 seed 已凍結於 `shared/RESEARCH_PROTOCOL.md`；prompt、工具 schema 與正式 commit 指紋尚未凍結，因此所有人仍不得自行啟動 12×4 正式批次。

### 固定協作順序

1. WS2、WS3、WS4-B、WS5 可平行完成程式、契約與 fake-data 測試。
2. WS1 逐一驗收並整合上述成果，接著凍結 prompt、tool schema 與正式 Git commit 指紋。
3. 指紋凍結後，由 WS1 使用 WS4 runner 執行正式 12×4 軌跡並凍結 raw transcripts。
4. WS1 產生不含 A/B/C/D 身分的 blinded transcripts，再交給 WS5；WS5 不得接觸 condition mapping。
5. WS5 完成盲評與統計後，由 WS1 解盲、驗收主張並整合論文。

每個人都必須取得完整 repository，不能只傳自己的工作流資料夾。目錄應保持：

```text
diabetes-chatbot/
├── diabetes_chatbot/
├── diabetes-rag/
├── scripts/
└── llm_ablation_paper/
```

交付步驟：

1. 將完整 repository 放到 Git 平台，或把完整專案壓縮後傳給所有成員。
2. 不要傳 `.env`、API key、正式病患資料或個人資料。
3. 在群組公告每個人的成員編號與工作流。
4. 要求每個人先閱讀本文件，再把自己的 `member_prompts/member_X_*.md` 完整貼給 AI。只給壓縮包而不指定成員編號並不足夠。
5. AI 第一輪只做理解確認；成員檢查沒有跑錯工作流後，再回覆「確認開工」。
6. 所有成果必須寫回自己的工作流或協議指定的 artifacts 位置，不以聊天內容作為正式交付。

## 全員共同規則

- 每個人使用同一份 `shared/RESEARCH_PROTOCOL.md`，不能自行發明不同的 A–D 定義。
- 每個人先讀根目錄 `AGENTS.md`，再讀自己工作流的 `AGENTS.md`。
- 不把其他 AI 的自我評估當成完成證明；要看實際檔案、測試與 artifacts。
- 不寫死任何人的電腦路徑。
- 不把 RAG 組的研究結果混入這篇 LLM 消融論文。
- 模型名稱與參數一律讀取 `shared/RESEARCH_PROTOCOL.md`，不得自行替換；正式指紋完成前先用 fake model 測試。
- 成員 2–5 不得直接修改 `diabetes_chatbot/handlers.py`；需要接口時記錄需求，由成員 1 統一處理。

## 群組公告範本

```text
我們這次共同完成同一篇 LLM 安全分層消融論文，不是五篇不同報告。

請先下載完整專案，打開 llm_ablation_paper/TEAM_START_HERE.md。

分工：
- 成員 1：Workstream 1 技術主持
- 成員 2：Workstream 2 A/B
- 成員 3：Workstream 3 C/D
- 成員 4：Workstream 4 模擬病患
- 成員 5：Workstream 5 Judge/統計

每人把 llm_ablation_paper/member_prompts/ 內自己的指令完整交給 AI。AI 第一輪只回報理解，不修改程式；確認範圍正確後再回「確認開工」。所有成果寫回專案，不要只留在 AI 對話裡。
```

## 何時才算可以正式跑？

只有成員 1 證明同一個測試病患可以在隔離狀態下完成 A、B、C、D，且輸出符合 `shared/EXPERIMENT_CONTRACT.md`，才可以啟動 12 位病患的正式批次。其他組的案例、profiles、rubric 和測試程式可以提前準備。
