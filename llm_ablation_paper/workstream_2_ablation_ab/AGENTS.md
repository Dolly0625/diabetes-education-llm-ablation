# 工作流 2：A／B 消融設計

## 角色

你負責讓 A 與 B 成為公平、可重跑的對照，並提供相應方法章素材。你不是正式實驗執行者，也不是核心程式合併者。

## 指定閱讀

以下路徑相對於本工作流目錄：

- `../../diabetes_chatbot/planner.py`
- `../../diabetes_chatbot/prompts.py`
- `../../diabetes_chatbot/server/handlers.py`
- `../../diabetes_chatbot/tests/test_planner.py`
- `../../diabetes_chatbot/tests/test_llm_planner_agent.py`

## 任務

WS1 Harness 已驗收。你只能接入既有 Harness，不得建立、複製或改寫另一套。

1. 列出現有 Planner 的輸入、輸出、fallback 與 Talker guidance 注入點。
2. 定義 A 如何略過 Planner，而不改變其他 prompt、工具、模型與回覆流程。
3. 定義 B 如何使用 Planner，但仍維持所有工具暴露。
4. 定義 A 的 neutral planner state，確保 logging schema 完整但沒有執行或注入 Planner。
5. 確認 A、B 均停用 forced retrieval、證據 system-prompt 注入與其他未建模輔助行為。
6. 直接使用既有 WS1 Harness；只有確認缺少必要接口時，才以需求文件提出最小修改，不得自行修改核心程式。
7. 建立 A／B configuration test，證明唯一差異是 Planner。
8. 寫出可直接併入方法章的 A／B 描述。

## 允許修改

- 本工作目錄內的程式、測試、報告與 patch 檔。

## 禁止修改

- `diabetes_chatbot/`
- `diabetes-rag/`
- `.env`
- 其他工作流目錄
- 正式 artifacts

## 固定條件

- A、B 使用相同 Talker 模型、system prompt、temperature、病患設定與最大輪數。
- A、B 暴露完全相同的工具集合。
- B 唯一新增 Planner state 與 guidance。
- A、B 的 forced retrieval 與證據注入均固定關閉；不得讓 B 因 Planner domain 額外取得手冊內容。

## 必交付

- `ab_configuration.md`
- A／B config 差異表。
- 既有 WS1 Harness 接入說明；若無缺口，明確記錄「無接口需求」，若有缺口才附最小需求文件。
- 可重跑的 configuration tests。
- 測試輸出。
- 800–1,000 字方法章素材。
- 已知限制與未確認點。

## 回報格式

```text
判定：可實作／部分可實作／阻塞
程式事實：
建議實作：
修改檔案：
測試：
風險：
需要技術主持人決定：
```
