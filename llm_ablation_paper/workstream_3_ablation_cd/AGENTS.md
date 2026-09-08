# 工作流 3：C／D、安全事件紀錄與故障注入

## 角色

你負責把動態工具暴露與輸出熔斷做成可分離、可觀察的 C／D 消融，並設計故障注入。你不得直接修改核心程式或正式資料。

## 指定閱讀

以下路徑相對於本工作流目錄：

- `../../diabetes_chatbot/state.py`
- `../../diabetes_chatbot/guard.py`
- `../../diabetes_chatbot/tools.py`
- `../../diabetes_chatbot/server/handlers.py`
- `../../diabetes_chatbot/tests/test_clinical_full_alignment.py`
- `../../diabetes_chatbot/tests/test_safety_guard.py`

## 任務

WS1 Harness 已驗收。你只能接入既有 Harness，不得建立、複製或改寫另一套。

1. 列出 C 的工具 gate 判定點、工具集合與議程門禁。
2. 定義 C 如何在 B 上只增加動態工具暴露。
3. 列出 D 的輸出檢查、覆寫與問句限制順序。
4. 定義 D 如何在 C 上只增加 Output Guard。
5. 將固定停藥警語追加、問句截斷與 emoji stripping 從主要 D 定義排除，避免同時加入多個輸出介入。
6. 設計逐輪 logging：tools exposed、tools called、raw output、guard action、final output。
7. 建立明顯安全／不安全輸出的故障注入集，分開報告自然產生與注入結果。
8. 建立 C／D configuration tests 與 safety event tests。

## 允許修改

- 本工作目錄內的程式、測試、報告與 patch 檔。

## 禁止修改

- `diabetes_chatbot/`
- `diabetes-rag/`
- `.env`
- 其他工作流目錄
- 正式 artifacts

## 固定條件

- C 相對 B 唯一新增動態工具暴露與議程門禁。
- D 相對 C 唯一新增最終輸出熔斷。
- D 的熔斷限定為 `inspect_output_guard`；主要實驗不啟用固定警語追加或 question-budget post-processing。
- D 必須保存熔斷前後內容。
- Fault injection 結果不可混入模型自然違規率。

## 必交付

- `cd_configuration.md`
- C／D config 差異表。
- logging schema 與範例。
- 既有 WS1 Harness 接入說明；若無缺口，明確記錄「無接口需求」，若有缺口才附最小需求文件。
- fault-injection 資料與測試。
- 測試輸出。
- 800–1,000 字方法章素材。
