# v2 Agent 家規（subagent 進場先讀這份）

## 這包是什麼

LINE 糖尿病衛教＋看診前整理助理。主流程全在 `server/handlers.py::process_patient_message`
（CLI 版 `chat.py` 同邏輯）：感知 → 輸入警衛 → 抽事實入病歷 → LLM 臨床規劃
（2 秒超時降 rule 備援）→ 動態工具門 → 護理師回話 → 輸出熔斷＋問號只留一個 → 記 log。

## 三條政策（ нарушения = 打回）

1. **閒聊靠嘴，定義跟藥靠書，救命靠反射**（詳見 `docs/rag-trigger-policy.md`，
   改行為前先讀它）。飲食題物理隱藏檢索，成因/藥/數字強制先查。
2. **出處只印不念**：RAG 回來的東西只進就醫備忘錄小字，絕不進聊天正文；
   自述歸阿嬤、出處歸書，沒查不印，禁編頁碼。
3. **台灣紅線**：禁調藥指示、禁確診斷言（只寫待確認）、處方欄永遠留白給醫師。

## 四條工程鐵律

1. **禁碰**：`guard.py` 安全正則、`tools.py` 圖譜去污、`diabetes-rag/` 全目錄
  （RAG 組地盤，subgit 邊界）、`.env` 與 `v2/data/*.json` 病人檔。
2. **禁 git 操作**：不 stash、不 checkout、不 commit、不碰遠端；一次只改被分派的檔案。
3. **順序**：`inspect_output_guard` 永遠先於 `enforce_single_question_budget`；
   背景線程複用主線 assessment，不准重打 LLM。
4. **改完必跑**：`pytest diabetes_chatbot/tests/test_clinical_full_alignment.py -k "not live"`
   ＋相關套件全綠才算完；live 測試 flaky 屬正常，掛 mark 不當門神。

## 關鍵字現況（別再問為什麼還在）

- `guard.py` 正則＝保險絲，永不刪；`memory.py` 萃取＝熱路徑唯一寫入，不准刪；
  `planner.py` rule＝斷網備援，加固不刪；LLM 已覆蓋的裝飾位（C 區）可刪，動前先跑測試。
- 新關鍵字一律用正則（吃夾字、台語變體），禁用死板 `in` 比對。

## 命名

- 對外：**就醫備忘錄**（禁小卡）、**臨床衛教大腦**（禁 AMIE，研究引用 `references/` 除外）。
- 對內：函式/變數名不動；審計日誌標題：專科臨床大腦審計日誌。
