# Workstream 2：A／B 消融架構與組態規格書

本文件定義糖尿病衛教對話系統在 **Condition A（Prompt-only 基準組）** 與 **Condition B（A ＋ Planner 實驗組）** 之間的嚴格消融規格。

---

## 1. 消融核心設計與唯一差異原則

依據 `shared/RESEARCH_PROTOCOL.md` 與 `workstream_1_technical_lead/harness/config.py`，本研究探討的主要問題為：
> **在病患端糖尿病衛教 LLM 助理中，加入結構化規劃員（Planner）是否改善多輪對話決策與臨床狀態一致性？**

為確保因果推論之內部效度，A 與 B 之間嚴格維持**逐層唯一差異原則（Unique-diff principle）**：

| 組態欄位 | Condition A（基準組） | Condition B（實驗組） | 狀態說明 |
|---|---|---|---|
| `condition` | `"A"` | `"B"` | 實驗條件識別標籤 |
| **`enable_planner`** | **`False`** | **`True`** | **唯一自變項**（是否啟用結構化 Planner） |
| `enable_dynamic_tool_gate` | `False` | `False` | 固定關閉，兩組工具集合均完全暴露 |
| `enable_output_guard` | `False` | `False` | 固定關閉，不啟用輸出熔斷覆寫 |
| `enable_forced_retrieval` | `False` | `False` | 固定關閉，B 絕不因 Planner 領域判定注入手冊證據 |
| `enable_fixed_warning_append`| `False` | `False` | 固定關閉，停用生產端強制警語追加 |
| `enable_question_budget_postprocessing` | `False` | `False` | 固定關閉，停用問句預算截斷與符號清洗 |
| `model` (Talker) | `gemini-3.5-flash-lite` | `gemini-3.5-flash-lite` | 受控固定（正式實驗凍結） |
| `temperature` (Talker) | `0.3` | `0.3` | 受控固定 |
| `planner_model` | `""`（不使用） | `gemini-3.5-flash-lite` | 受控固定（B 啟用） |
| `planner_temperature` | `0.1`（不使用） | `0.1` | 受控固定 |
| `max_turns` | `6` | `6` | 受控固定 |
| `seed` | `42` | `42` | 受控固定 |

`config_diff(CONFIG_A, CONFIG_B)` 的機器可讀差異嚴格僅有：
```json
{
  "condition": {"from": "A", "to": "B"},
  "enable_planner": {"from": false, "to": true}
}
```

---

## 2. 結構化 Planner 規格（Condition B 專用）

### 2.1 輸入規格
Planner 作為幕後臨床規劃員，每輪對話在 Talker 產生回覆前執行，其輸入包含：
- `messages`：病患與助理的多輪歷史對話（保留完整對話上下文）。
- `patient_record`：病患持久化紀錄（包含已知生活型態、用藥、血糖數據等）。
- `timeout`：固定 30.0 秒（單次請求逾時上限）。
- `temperature`：固定 0.1（以利臨床結構化輸出的穩定度）。

### 2.2 輸出規格（`PlannerAssessment`）
Planner LLM 返回結構化 JSON，並解析為 `PlannerAssessment` 物件，包含以下臨床槽位與狀態：
1. **臨床槽位（`ClinicalSlots`）**：
   - `visit_reason`（看診主訴）及其狀態（`KNOWN | PARTIAL | MISSING`）。
   - `medications`（目前用藥）及其狀態。
   - `glucose_metrics`（血糖數據指標）及其狀態。
   - `hypo_history`（低血糖病史）及其狀態。
   - `concerns_or_side_effects`（疑慮或藥物副作用）及其狀態。
2. **決策旗標**：
   - `is_visit_mode`（是否處於看診整理模式）。
   - `is_explicit_request`（病患是否明確要求產出備忘錄）。
   - `is_agenda_confirmed`（議程是否確認且資訊充分）。
   - `can_unlock_summary_tool`（是否允許解鎖就醫備忘錄工具）。
   - `retrieval_domain`（`NONE | GENERAL_EDUCATION | DRUG_SAFETY | DIET_NUTRITION_KNOWLEDGE`）。
   - `detected_intent`（偵測到的意圖類別）。
   - `talker_guidance`（向 Talker 發布的自然語言臨床溝通導引）。
   - `engine`（執行引擎識別，如 `llm` 或 fallback 引擎）。

### 2.3 容錯降級機制（Fallback）
為避免網路波動或暫態 API 異常導致實驗軌跡中斷，Planner 調用遵循下列規則：
1. **指數退避重試（Exponential Backoff Retry）**：
   - 僅對暫態錯誤（如 HTTP 429 速率限制、HTTP 5xx 伺服器錯誤、連線逾時）進行最多 4 次嘗試，退避間隔為 `[1, 2, 4, 8]` 秒。
   - 對於非暫態錯誤（如 400 Bad Request、驗證失敗）立即拋出，不進行重試。
2. **確定性規則降級（Rule-based Fallback）**：
   - 若 4 次重試仍失敗或發生無法復原之例外，自動調用確定性 Python 規則規劃器 `evaluate_clinical_planner(messages, patient_file_path)`。
   - 降級引擎在日誌中明確標記為 `python_fallback`，確保執行痕跡可追溯，不讓軌跡非預期終止。

### 2.4 Talker Guidance 注入機制
當 Planner 產出非空的 `talker_guidance` 時，共用核心會進行字串清理（確保格式統一），並在 Talker 推論前將其以 System Role 附加於對話上下文末端：
```python
if enable_planner and getattr(planner, "talker_guidance", ""):
    clean_guidance = re.sub(r"【臨床溝通導引】[：:]\s*", "【臨床溝通導引】：", planner.talker_guidance)
    inference_ctx.append({"role": "system", "content": clean_guidance})
```
Talker LLM 讀取該導引後，在對話中落實同理心、聚焦關鍵缺漏資訊或給予安全警語。

---

## 3. Condition A 的中立規劃狀態與狀態管理邊界

### 3.1 中立規劃狀態（`neutral_planner_state`）
當 `enable_planner=False` 時，系統不調用 Planner LLM，亦不執行任何 Python rule fallback。
為維持資料管線的型態一致性與評估契約（`shared/EXPERIMENT_CONTRACT.md`）要求，系統注入中立規劃狀態：
```python
def neutral_planner_state() -> PlannerAssessment:
    slots = ClinicalSlots(
        visit_reason="", visit_reason_status=SlotStatus.MISSING,
        medications="", medications_status=SlotStatus.MISSING,
        glucose_metrics="", glucose_metrics_status=SlotStatus.MISSING,
        hypo_history="", hypo_history_status=SlotStatus.MISSING,
        concerns_or_side_effects="", concerns_status=SlotStatus.MISSING,
    )
    return PlannerAssessment(
        slots=slots,
        is_visit_mode=False,
        is_explicit_request=False,
        is_agenda_confirmed=False,
        can_unlock_summary_tool=False,
        highest_priority_gap=None,
        retrieval_domain=RetrievalDomain.NONE,
        detected_intent="GENERAL_HEALTH",
        talker_guidance="",
        engine="neutral",
        ddx_candidates=[],
        evidence_links=[],
    )
```
此狀態在軌跡日誌中能完整序列化，但其內容完全為預設中立值。

### 3.2 狀態持久化事實與精確邊界
特別澄清系統狀態之持久化機制，避免方法學描述偏差：
1. **A 並非完全不持久化任何狀態**：
   - 共同的「病患事實抽取模組」（`extract_clinical_facts_from_text`）照常運行，能從病患自然語言中提取血糖數據或基本事實並寫入病患紀錄。
   - 對話歷史（`messages`）照常依輪次追加保存。
2. **A 與 B 在狀態持久化上的唯一差異**：
   - **Condition A**：完全不持久化任何 Planner assessment 結構化槽位（不執行 `update_from_planner_assessment`）。
   - **Condition B**：在每輪推論後，將 Planner 評估之結構化臨床槽位更新並持久化至病患狀態紀錄檔。

---

## 4. 工具暴露策略（Tool Exposure Policy）

### 4.1 Canonical Tool Snapshot
系統中所有受控工具之標準 Schema 凍結於 `diabetes_chatbot.tools`：
1. `TOOL_SEARCH_HANDBOOK`（`search_handbook`）：檢索衛福部與國健署官方糖尿病衛教指引。
2. `TOOL_GENERATE_VISIT_SUMMARY`（`generate_previsit_intake_summary`）：生成就醫備忘錄與門診掛號輔助資料。

### 4.2 A 與 B 的工具全開策略
- 在 Condition A 與 Condition B 中，動態工具閘門均固定為關閉狀態（`enable_dynamic_tool_gate = False`）。
- 兩組在每輪對話推論時，傳入 Talker LLM 的工具清單均嚴格等於 `get_canonical_tool_snapshot()` 的深拷貝複本。
- **結論**：A 與 B 均能「看見」所有工具，不存在因工具可見性不同而導致的混淆變項。模型是否調用工具完全取決於 Prompt（Condition A）或 Prompt 加上 Planner Guidance（Condition B）。

---

## 5. 共同停用之生產輔助（Production Invariants）

為消除未建模之干擾因子，下列生產環境特有邏輯在 A 與 B 均強制關閉：
1. **Forced Retrieval（強制檢索）= `False`**：
   - 生產環境中若 Planner 判定特定領域會自動呼叫手冊並將證據字串注入 Prompt。在消融實驗中，此項固定關閉。
   - **重要防護**：Condition B 即使產生 `retrieval_domain=DRUG_SAFETY` 或 `DIET_NUTRITION_KNOWLEDGE`，也**絕不會**觸發強制檢索，絕不額外取得手冊內容。
2. **Fixed Warning Append（停藥固定警語追加）= `False`**：
   - 停用規則式自動字尾免責聲明附加。
3. **Question Budget Postprocessing（單一問句預算截斷）= `False`**：
   - 停用硬性截斷問句或清除表情符號之輸出後處理。
4. **Output Guard（輸出熔斷）= `False`**：
   - 停用調藥、確診等違規攔截覆寫（此防線保留至 Condition D 進行消融）。

---

## 6. 共同基礎設施

1. **Input Guard（輸入安全防線）**：四組每輪固定啟用，攔截提示注入（Prompt Injection）與自傷心理危機。若被攔截則中止該輪並記錄為 `COMMON_INPUT_BLOCK`，此類案例獨立報告，不納入 A–D 效果對比。
2. **程序與暫存目錄隔離（Process & State Isolation）**：
   - 每條對話軌跡使用專屬之 `run_id` 與獨立臨時 `state_dir`。
   - 每次啟動時清理記憶體 Session 快取（`clear_session_cache`），確保各病患與各條件之間零狀態污染。
