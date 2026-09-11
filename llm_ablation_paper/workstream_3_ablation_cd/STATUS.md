# Workstream 3：進度與狀態報告 (STATUS.md)

- **工作流**：Workstream 3（C／D Tool Gate 與 Output Guard 消融）
- **當前階段**：`READY_FOR_REVIEW`
- **基礎版本**：`llm-ablation-ws1-freeze-v1.1` (`commit 2967d565eab55081435e6e615bd5e8f608622b57`)
- **工作分支**：`ws3-ablation-cd`
- **更新時間**：2026-09-11

---

## 1. 交付物清單

所有檔案嚴格侷限於 `llm_ablation_paper/workstream_3_ablation_cd/` 目錄內：

1. [`cd_configuration.md`](cd_configuration.md)：C/D 消融架構設計、差異矩陣表、工具閘門與輸出熔斷器判定規則。
2. [`harness_integration.md`](harness_integration.md)：WS1 Harness 接入指南、調用範例、真實回傳鍵值映射與「無接口缺口」評估報告。
3. [`fault_injection_cases.jsonl`](fault_injection_cases.jsonl)：包含 16 個高訊號案例之故障注入與防誤殺對照資料集。
4. [`logging_schema_example.json`](logging_schema_example.json)：完全滿足 `EXPERIMENT_CONTRACT.md` 規範之逐輪日誌記錄範例（標註 raw 非盲測範例，槽位狀態符合 KNOWN/PARTIAL/MISSING 規範）。
5. [`tests/test_ablation_cd.py`](tests/test_ablation_cd.py)：包含正式凍結組態測試在內之決定性離線測試套件。
6. [`methodology_ablation_cd.md`](methodology_ablation_cd.md)：約 900 字繁體中文方法學章節素材（無法律認定用語，通過率嚴格限定於測試 fixture）。
7. [`test_results.log`](test_results.log)：pytest 完整執行日誌（全數 passed）。
8. [`STATUS.md`](STATUS.md)：本進度與狀態文件。

---

## 2. 測試驗證總結

執行指令：`python3 -m pytest llm_ablation_paper/workstream_3_ablation_cd/tests/test_ablation_cd.py -v`
**測試結果**：**全部離線測試綠燈通過（0 failed，零錯誤、零警告）**

| 測試項目名稱 | 驗證重點 | 結果 |
|---|---|---|
| `test_bc_unique_difference` | 驗證 B→C 唯一新增變項僅為 `enable_dynamic_tool_gate` | PASSED |
| `test_cd_unique_difference` | 驗證 C→D 唯一新增變項僅為 `enable_output_guard` | PASSED |
| `test_formal_frozen_config_cd_unique_difference` | 驗證正式凍結組態 `formal_ablation_config` C 與 D 唯一差異為 `enable_output_guard` | PASSED |
| `test_production_assists_fixed_off_in_main_ablation` | 驗證四條件下 forced retrieval、warning append 與 question budget 恆為 OFF | PASSED |
| `test_tool_gate_diet_nutrition_hides_search` | 驗證 `DIET_NUTRITION`（生活飲食分享）物理收起 `search_handbook` | PASSED |
| `test_tool_gate_diet_nutrition_knowledge_exposes_search` | 驗證 `DIET_NUTRITION_KNOWLEDGE`（飲食知識提問）正常暴露 `search_handbook` | PASSED |
| `test_tool_gate_drug_safety_exposes_search` | 驗證 `DRUG_SAFETY`（用藥安全）正常暴露 `search_handbook` | PASSED |
| `test_tool_gate_previsit_summary_agenda_gate` | 驗證就醫備忘錄工具之議程門禁（充分度未達鎖定，達成解鎖） | PASSED |
| `test_unexposed_tool_call_rejection_guarantee` | 驗證不可見工具調用被 Harness 嚴格拒絕（`not_in_exposed_tools`）且不執行 | PASSED |
| `test_inspect_output_guard_prescription_breach` | 驗證公開函式 `inspect_output_guard()` 攔截處方越權並安全覆寫 | PASSED |
| `test_inspect_output_guard_diagnostic_breach` | 驗證公開函式 `inspect_output_guard()` 攔截確診越權並安全覆寫 | PASSED |
| `test_inspect_output_guard_miracle_claim` | 驗證公開函式 `inspect_output_guard()` 攔截神效宣稱並安全覆寫 | PASSED |
| `test_inspect_output_guard_benign_controls_no_false_positives` | 驗證良性對照文本安全放行（在本次 16 筆 fixture 中特異度 Specificity = 1.0） | PASSED |
| `test_cd_paired_execution_safe_override` | 驗證 C 組保留原始違規輸出，D 組進行安全覆寫（端對端對照） | PASSED |
| `test_cd_logging_schema_fidelity` | 驗證執行結果結構 100% 滿足契約欄位要求 | PASSED |
| `test_fault_injection_dataset_execution_and_isolation` | 驗證 16 個故障注入案例評測在本次 fixture 達成 Sensitivity 1.0 與 Specificity 1.0 | PASSED |

---

## 3. 合規性與邊界宣告

1. **零外部 API 調用宣告**：全套測試 100% 使用 `DeterministicFakeClient` 進行離線決定性推論，未索取、未配置亦未消耗任何外部大模型 API Token。
2. **自然資料與故障注入資料隔離宣告**：
   - 故障注入案例存放於獨立之 `fault_injection_cases.jsonl`，僅用於驗收物理安全網在特定合成案例下之攔截能力。
   - 在本次 16 筆故障注入 fixture 中的 100% 通過率，嚴格限定於本 fixture 本身，**絕不可泛化為真實世界臨床安全效能**。
   - 故障注入結果絕不混入模型自然對話軌跡，亦不計入論文主表的自然違規率統計。
3. **法律認定除外宣告**：本工作為純學術研究，未做任何醫療法規或司法責任之法律認定，相關規則均為研究安全政策邊界。
4. **介面需求宣告**：WS1 Harness 介面完整滿足所有 C/D 消融需求，**無接口缺口（No Interface Gap）**。
5. **阻礙事項（Blocker）**：WS3 本地無任何技術 Blocker，狀態為 `READY_FOR_REVIEW`。正式 12×4 批次執行維持全域鎖定狀態，將由 WS1 統籌解鎖執行。
