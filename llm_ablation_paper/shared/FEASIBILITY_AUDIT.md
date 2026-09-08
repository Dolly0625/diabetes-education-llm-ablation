# 現有程式可行性稽核

本檔記錄以實際程式碼驗證的 Day 1 工程風險。AI 或組員提出的新觀察必須先回到程式確認，不能只依註解或自評。

## 稽核結論

| 項目 | 判定 | 程式事實 | 協議決策 |
|---|---|---|---|
| Input Guard 歸屬 | 部分成立 | `guard.py::inspect()` 目前只實作提示注入與自傷；醫療急症只出現在檔頭說明，沒有對應判斷 | 四組固定開啟；觸發案例只做 invariant check，不進主要 A–D 效果 |
| 主流程無消融開關 | 成立 | `process_patient_message()` 直接呼叫 Planner、Tool Gate 與 Output Guard，沒有 config injection | 工作流 1 先建立獨立 harness 與 `AblationConfig` |
| 跨條件狀態污染 | 成立 | 病患 JSON 寫入 `diabetes_chatbot/data/`，對話另存於 process-global `_SESSION_CACHE` | 每條軌跡獨立 process、temp state directory、唯一 ID，禁止共用 production data |
| Forced retrieval 混淆 A／B | 成立 | 強制檢索依賴 `planner.retrieval_domain`，並額外注入證據 system prompt | 主要 A–D 全部關閉 forced retrieval；A／B 工具均全開，由模型自行決定 function call |
| 缺少角色扮演 runner | 成立 | 現有 case study 是固定輸入序列，沒有 Patient Agent、checkpoint 或 retry | 工作流 4 建立結構化 simulator 與可續跑 runner |
| 額外輸出後處理混淆 D | 成立，原評論未列 | 主流程除 `inspect_output_guard` 外，還有問句截斷、emoji 清理與停藥固定警語追加 | 主要 D 只增加 `inspect_output_guard`；其餘關閉或另列附錄 |

## Day 1 必須通過的工程門檻

1. `AblationConfig` 能表示四組，且可輸出完整 config diff。
2. Planner 關閉時不執行 Planner、不注入 guidance、不驅動 forced retrieval，但 logging schema 仍完整。
3. A、B 工具集合相同；C、D 工具集合由同一 gate 決定。
4. D 相對 C 只增加 `inspect_output_guard`。
5. 同一病患的 A、B、C、D 各自從全新、相同初始狀態開始。
6. dry run 中斷後能從 checkpoint 繼續，不重跑已完成軌跡。
7. 所有 API error、retry 與最終失敗都保留在 artifact。

未通過上述七項，不得開始正式四十八條軌跡。

## 仍待技術主持人凍結

- 受測 Talker、Patient Agent 與 Judge 的實際模型。
- 三類模型各自的 temperature。
- 工具「全部暴露」的精確 schema 清單。
- common Input Guard 是否在 simulator 對話每一輪都執行。
- Judge disagreement 的第三次裁決是否使用相同模型或另一模型。
