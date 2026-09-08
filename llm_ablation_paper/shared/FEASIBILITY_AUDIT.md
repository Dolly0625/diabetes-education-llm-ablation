# 現有程式可行性稽核

本檔記錄以實際程式碼驗證的 Day 1 工程風險及目前修復狀態，不是待辦工作單。AI 或組員提出的新觀察必須先回到程式確認，不能只依註解或自評。

## 稽核結論

| 項目 | 目前狀態 | 原始程式事實 | 已採用處理 |
|---|---|---|---|
| Input Guard 歸屬 | 協議已解決 | `guard.py::inspect()` 原本只實作提示注入與自傷；醫療急症沒有對應判斷 | 四組每輪固定開啟；觸發案例只做 invariant check，不進主要 A–D 效果 |
| 主流程無消融開關 | WS1 已修復並驗收 | 原始 `process_patient_message()` 沒有 config injection | 已建立唯一共用 Harness 與 `AblationConfig`；其他工作流不得重建 |
| 跨條件狀態污染 | WS1 已修復並驗收 | production 病患 JSON 與 process-global `_SESSION_CACHE` 可能共享狀態 | Harness 使用每軌跡獨立 process、temp state directory 與唯一 ID |
| Forced retrieval 混淆 A／B | WS1 已修復並驗收 | 強制檢索依賴 `planner.retrieval_domain` 並額外注入證據 | 主要 A–D 全部關閉 forced retrieval；A／B 工具均全開 |
| 缺少角色扮演 runner | WS4-B 待完成 | 原有 case study 只有固定輸入序列 | WS4-A profiles 已驗收；WS4-B 只建立可續跑 runner，不重做 profiles |
| 額外輸出後處理混淆 D | WS1 已修復並驗收 | production 除 `inspect_output_guard` 外另有問句截斷、emoji 清理與固定警語 | 主要 D 只增加 `inspect_output_guard`；其餘固定關閉 |

## WS1 已通過、整合後須再驗證的工程門檻

1. `AblationConfig` 能表示四組，且可輸出完整 config diff。
2. Planner 關閉時不執行 Planner、不注入 guidance、不驅動 forced retrieval，但 logging schema 仍完整。
3. A、B 工具集合相同；C、D 工具集合由同一 gate 決定。
4. D 相對 C 只增加 `inspect_output_guard`。
5. 同一病患的 A、B、C、D 各自從全新、相同初始狀態開始。
6. dry run 中斷後能從 checkpoint 繼續，不重跑已完成軌跡。
7. 所有 API error、retry 與最終失敗都保留在 artifact。

WS1 已以離線測試與 dry run 通過上述七項。WS2–WS5 整合後仍須由 WS1 重跑整合驗收；若出現 regression，不得開始正式四十八條軌跡。

## 凍結狀態

已凍結：

- Talker/Planner、Patient Agent、Judge 的模型 ID 與各角色 temperature。
- max turns、seed、common Input Guard 每輪執行。
- Judge disagreement 以相同模型及相同參數進行第三次裁決。

仍待 WS1 凍結：

- Talker 與 Planner prompt 版本／雜湊。
- 工具「全部暴露」的精確 schema 清單／雜湊。
- 正式 Git commit 指紋與 opaque condition mapping。
