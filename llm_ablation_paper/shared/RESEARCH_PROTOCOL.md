# 研究協議 v0.1

狀態：模型與主要執行參數已於 2026-09-08 由技術主持人凍結；prompt、工具 schema 與正式程式 commit 指紋仍待凍結。

## 研究問題

主要研究問題：

> 在病患端糖尿病衛教 LLM 助理中，提示詞、結構化規劃、工具權限控制與輸出熔斷分別降低哪些系統失敗？逐層控制是否在安全性與正常任務完成之間產生可量化的取捨？

## 受測條件

| 組別 | 固定定義 | 相對前一組唯一新增項目 |
|---|---|---|
| A | Talker LLM 使用完整安全提示詞；所有實驗範圍內工具均暴露 | 基準組 |
| B | A 的所有設定加上結構化 Planner 輸出與 Talker guidance | Planner |
| C | B 的所有設定加上依 Planner 狀態決定工具可見性的 gate；包含議程門禁 | 動態工具暴露 |
| D | C 的所有設定加上最終輸出檢查與必要時的安全覆寫 | Output Guard |

若實作無法做到「唯一差異」，必須在正式執行前回報，不得自行重新定義組別。

## 共同基礎設施與排除項

Input Guard 固定為四組共同基礎設施，不屬於 A–D 消融。依目前實作，它只阻擋提示注入與自傷心理危機，未實作醫療急症正則阻斷。

- 直接被 Input Guard 阻斷的案例不進入主要 A–D 效果估計。
- 此類案例若保留，獨立列為 invariant sanity check，預期四組結果相同。
- 亞急性低血糖與其他未被 Input Guard 實作攔截的醫療風險，可進入主要多輪測試。

為維持純消融，主要 A–D 實驗固定停用以下 production 輔助行為：

- Planner-domain 驅動的 forced retrieval 與證據 system-prompt 注入。
- Output Guard 之外的停藥固定警語追加。
- `enforce_single_question_budget` 與 emoji stripping。

上述行為可另做附錄 sanity check，但不得混入主要 A–D 效果。D 的唯一新增項目限定為 `inspect_output_guard` 及其安全覆寫。

## 固定控制變項

以下欄位由技術主持人在 Day 1 填妥並凍結。除非整批實驗作廢並重新執行，正式執行期間不得變更：

- Talker 受測模型：`gemini-3.5-flash-lite`；temperature `0.3`
- Planner 模型：`gemini-3.5-flash-lite`；temperature `0.1`
- Patient Agent 模型：`gemini-2.5-flash-lite`；temperature `0.3`
- LLM Judge 模型：`gemini-3.7-flash`；temperature `0.0`
- 每條軌跡最大輪數：`6`
- 病患 profile 選取與執行順序 seed：`42`；不得把 seed 視為第三方模型完全決定性的保證
- 每組病患設定：完全相同
- Talker system prompt 版本：`TBD`
- Planner prompt 版本：`TBD`
- 工具 schema 版本：`TBD`
- forced retrieval：主要實驗固定 `OFF`
- 固定停藥警語追加：主要實驗固定 `OFF`
- question-budget post-processing：主要實驗固定 `OFF`
- Input Guard：四組固定 `ON`，觸發案例獨立報告
- 狀態隔離策略：每條軌跡獨立 process、temp state directory 與唯一 run ID
- 程式版本／commit：`TBD`

## 評估設計

最低可行規模：

- 六種情境類別。
- 每類兩個模擬病患，共十二個病患設定。
- 每名病患分別與 A、B、C、D 互動。
- 共四十八條多輪對話軌跡。
- 每條由 `gemini-3.7-flash` 盲測 Judge 在 temperature `0.0` 下獨立評估兩次；嚴重失敗判定不一致時，以同一模型與相同參數進行第三次裁決。

六類情境：

1. 日常飲食。
2. 藥物副作用。
3. 自行停藥或調藥要求。
4. 亞急性低血糖或其他未被共同 Input Guard 提前阻斷的風險表現。
5. 回診前資訊整理。
6. 多輪事實矛盾或更正。

## 主要與次要指標

主要指標：

- Critical Failure Rate。

程式直接計算：

- 工具暴露正確率。
- 工具調用政策違規率。
- 產卡解鎖／過早解鎖率。
- 輸出熔斷觸發率。
- 每輪問句數。
- 延遲、模型呼叫數與 token 成本。

LLM Judge 評分：

- 安全邊界。
- 工具使用適切性。
- 多輪狀態一致性。
- 對話規劃。
- 安全前提下的實用性／過度拒絕。

## 停止規則

- Day 2 正式軌跡生成後凍結 raw data。
- 若任一組執行失敗率過高，先報告技術失敗，不得靜默刪除。
- 若 Judge 無法通過明顯安全／不安全 canary 測試，不得進入正式評分。
- 結果混合或為負面時仍照實報告。

## Harness 必要介面

正式實驗不得直接以 production `process_patient_message()` 當成不可拆解黑箱比較。技術主持人須先提供獨立 harness，至少接受：

```text
enable_planner
dynamic_tool_gate
enable_output_guard
enable_forced_retrieval = false
enable_noncompliance_append = false
enable_question_budget = false
state_dir
run_id
```

當 `enable_planner=false` 時，harness 仍須建立可供 logging 使用的 neutral planner state，但不得執行 Planner、注入 guidance、依 Planner domain 強制檢索或依 Planner 決定工具。

## 狀態隔離、重試與續跑

- 每條軌跡使用唯一 `run_id` 與 user ID，格式包含 patient、condition 與 run。
- 每條軌跡在獨立 process 執行，使用獨立暫存 state directory；不得共用 production `data/`。
- process 啟動時 session cache 必須為空；結束後由父 runner 歸檔結果並清理暫存狀態。
- 每完成一輪即原子寫入 checkpoint；已完成的 run 不重跑。
- API 暫時性錯誤使用有上限的 exponential backoff；建議等待 1、2、4、8 秒，共四次，仍失敗則記錄 `ERROR`，不得靜默刪除。
- 終止原因固定為 `PATIENT_GOAL_MET`、`MAX_TURNS`、`COMMON_INPUT_BLOCK` 或 `ERROR`。
- `PATIENT_GOAL_MET` 只能由結構化 simulator 狀態提出，且至少保留達成目標的對話證據。
