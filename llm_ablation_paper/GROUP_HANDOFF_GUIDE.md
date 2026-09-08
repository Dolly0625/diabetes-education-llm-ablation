# LLM 消融論文：團隊交接與執行說明

> 請全體成員先讀完這份文件，再開始使用 AI。我們是五個人共同完成同一篇論文，不是五個人各做一篇。

## 1. 我們要做什麼？

我們要比較同一個糖尿病衛教 LLM 助理，在逐層加入不同系統控制後，安全性、多輪狀態一致性、工具使用與任務完成度會如何改變。

暫定題目：

> 從提示詞到程式防線：糖尿病衛教 LLM 助理之分層安全控制消融研究

這不是 RAG 檢索效能論文。我們不比較 Recall@K、RRF、向量與圖譜優劣，也不調整 `diabetes-rag/` 的檢索門檻。

## 2. A、B、C、D 四組實驗

| 條件 | 白話說明 | 要回答的問題 |
| --- | --- | --- |
| A | 單一 Talker LLM＋完整安全提示詞＋所有實驗工具都看得到 | 只靠提示詞能做到什麼程度？ |
| B | A＋結構化 Planner | 先規劃再回答，是否改善多輪決策與狀態追蹤？ |
| C | B＋動態工具暴露與議程門禁 | 讓模型直接看不到當下不該使用的工具，是否比文字禁止更有效？ |
| D | C＋最終 Output Guard | 最後一道確定性輸出防線，能再攔下多少越權回答？ |

公平比較規則：

- A–D 使用同一個 Talker 模型、system prompt、temperature、病患 profiles 與最大輪數。
- A/B 看到相同的完整工具集合，唯一主要差異是 Planner。
- C 相對 B 只加入 Tool Gate；D 相對 C 只加入 Output Guard。
- 主實驗固定關閉 forced retrieval、固定警語追加、問句截斷等未建模的輔助行為。
- 不得看到初步結果後替換病患或改變條件。

## 3. 資料集與模擬病患

來源為 Toyhom `Chinese-medical-dialogue-data` 的 IM 內科 CSV。我們只從內分泌科且命中糖尿病、血糖或指定藥物詞的資料中，依六種情境挑選背景種子。

重要邊界：

- 原始資料是公開網路醫療問答彙整，不是本研究招募的真實病患。
- 我們只把來源 QA 視為 `background_seed`，不將醫師 `answer` 當成 gold answer。
- 12 份 profiles 都是合成案例，不得宣稱為真實病歷、臨床資料或臨床驗證。
- 公開 profile 不收錄原始 `title`、`ask`、`answer` 全文或真實個資。

12 份 profiles 分為六類，每類兩份：

1. `DAILY_DIET`：日常飲食。
2. `MEDICATION_SIDE_EFFECT`：用藥不適。
3. `MEDICATION_NONADHERENCE`：忘記吃藥或自行停藥。
4. `SUBACUTE_HYPOGLYCEMIA`：可進入主流程的亞急性低血糖表現。
5. `PREVISIT_SUMMARY`：回診前資料彙整與產卡時機。
6. `FACT_CONTRADICTION`：病患後續更正前面說過的資料。

每份 profile 有固定 hidden facts 與 reveal policy。病患只有在被適當詢問時才揭露資訊，不會因為 A–D 組別不同而改變人設。

詳細來源與數字請看：

- `workstream_4_patient_simulation/DATASET_CARD.md`
- `workstream_4_patient_simulation/STATUS_REPORT.md`
- `workstream_4_patient_simulation/patient_profiles.jsonl`

## 4. 最後怎麼評估？

正式規模為 12 位模擬病患×4 條件，共 48 條對話軌跡，每條最多 6 輪，最多 288 個 assistant turns。

評估分成兩類：

1. 程式可直接計算：工具暴露與呼叫、產卡時機、熔斷事件、延遲、模型呼叫數、token 與終止原因。
2. 盲測 LLM-as-a-Judge：安全性、工具使用、狀態一致性、對話規劃與實用性。

Judge 只能看到 opaque condition ID，不能知道 A、B、C、D 真實身分。Judge 的分數不等於醫師評審或臨床安全率。

## 5. 目前進度

| 工作流 | 目前狀態 | 下一步 |
| --- | --- | --- |
| WS1 技術主持 | `APPROVED` | 保持 Harness 不重做；驗收其他組與凍結正式設定 |
| WS2 A/B | `NOT_STARTED` | 建立 A/B config、事件與公平性驗收 |
| WS3 C/D | `NOT_STARTED` | 建立 C/D logging、guard 事件與 fault injection |
| WS4 模擬病患 | `IN_PROGRESS` | WS4-A profiles 已完成；現在只做 WS4-B runner |
| WS5 Judge/分析 | `NOT_STARTED` | 建 rubric、schema、canary、runner 與假資料統計 |

WS1 Harness 是全組唯一的共用實驗控制器。WS2、WS3 與 WS4 不得另寫一套 Harness。

## 6. 五人分工

| 成員 | 使用的 AI 指令 | 只負責 |
| --- | --- | --- |
| 1 | `member_prompts/member_1_technical_lead.md` | 技術整合、介面驗收、正式設定凍結清單 |
| 2 | `member_prompts/member_2_ablation_ab.md` | A/B 設定驗證、事件測試與方法章素材 |
| 3 | `member_prompts/member_3_ablation_cd.md` | C/D Tool Gate、Output Guard、logging 與 fault injection |
| 4 | `member_prompts/member_4_patient_simulation.md` | WS4-B roleplay runner、checkpoint、resume、retry 與離線 dry-run |
| 5 | `member_prompts/member_5_judge_analysis.md` | Judge rubric、schema、canary、統計程式與結果樣板 |

每個人都需要完整 repository 才能讓 AI 理解依賴，但原則上只修改自己的 Workstream。

## 7. 每位成員的操作流程

### 步驟 1：下載完整專案

校內 GitLab：

`http://140.125.81.71:8080/M11423014/diabetes-chatbot`

登入後確認位於 `main` 分支，由 Code 功能下載原始碼 ZIP，然後解壓縮。

### 步驟 2：用 AI 開啟完整專案

使用 OpenCode、Codex 或其他 coding AI 開啟解壓後的專案根目錄。不要只開自己的子資料夾。

### 步驟 3：交給 AI 對應指令

將自己的 `member_prompts/member_X_*.md` 完整交給 AI。不要自行刪改指令。

### 步驟 4：第一輪只讀驗收

AI 第一輪只能閱讀與回報，不得修改檔案。成員將這份回報傳回群組，等待技術驗收。

### 步驟 5：確認後開工

收到「可以開工」後，回覆 AI：

```text
確認開工。請進入 Stage 2，完成實作、測試與狀態回報。
```

### 步驟 6：回傳成果

完成後只壓縮自己的 Workstream 資料夾：

- 成員 2：`workstream_2_ablation_ab/`
- 成員 3：`workstream_3_ablation_cd/`
- 成員 4：`workstream_4_patient_simulation/`
- 成員 5：`workstream_5_judge_analysis/`

成員 1 若有必要的核心整合修改，必須逐檔列出，不可只回傳不明的整包覆蓋。

回傳時必須附上：

1. 修改與新增檔案。
2. 執行指令。
3. 實際測試結果。
4. 尚存風險或 blocker。
5. 確認沒有修改其他 Workstream、`.env` 或正式 artifacts。

## 8. 大家現在需要的資源

- 可開啟完整專案的 coding AI。
- Python 3.9 以上，建議 3.10 或 3.11。
- 網路連線與約 2–5 GB 套件空間。
- WS4 若要跑完整來源驗證，需 `opencc-python-reimplemented==0.1.7` 與上游內科 CSV。

目前 WS2、WS3、WS4-B、WS5 都可以使用 fake data 離線開發，不需要付費 API key 或 GPU。

## 9. 目前禁止執行的事情

- 禁止重做或另建 WS1 Harness。
- 禁止重生、替換或改寫已驗收的 12 profiles。
- 禁止直接修改其他人的 Workstream。
- 禁止上傳 `.env`、API key、真實病患資料、模型檔或 cache。
- 禁止捏造正式 transcripts、Judge 分數或 A–D 結果。
- 禁止在模型、temperature、prompt 版本與 commit 尚未凍結時啟動正式 12×4 批次。

## 10. 什麼時候才能正式跑實驗？

必須同時滿足：

1. WS2、WS3、WS4-B、WS5 的程式與離線測試通過。
2. WS1 完成整合 dry-run 與介面驗收。
3. Talker/Planner、Patient Agent、Judge 的精確模型 ID 與 temperature 已凍結。
4. prompt 版本、tool schema、程式 commit、max turns 與 opaque condition mapping 已記錄。
5. 使用的 API key 由技術主持人保管，不寫入 Git 或聊天室。

在這之前，大家的任務是把各自的程式、測試與契約準備好，不是自行跑正式結果。
