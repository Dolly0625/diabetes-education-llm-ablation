# Workstream 3：進度與狀態報告 (STATUS.md)

- **工作流**：Workstream 3（C／D Tool Gate 與 Output Guard 消融）
- **當前階段**：Stage 2 離線開發與驗收已完成（Stage 2 COMPLETED）
- **基礎版本**：`llm-ablation-ws1-freeze-v1.1` (`commit 2967d565eab55081435e6e615bd5e8f608622b57`)
- **工作分支**：`ws3-ablation-cd`
- **更新時間**：2026-09-11

---

## 1. 交付物清單

所有檔案嚴格侷限於 `llm_ablation_paper/workstream_3_ablation_cd/` 目錄內：

1. [`cd_configuration.md`](file:///Users/dolly/team/ws3/diabetes-education-llm-ablation/llm_ablation_paper/workstream_3_ablation_cd/cd_configuration.md)：C/D 消融架構設計、差異矩陣表、工具閘門與輸出熔斷器判定規則。
2. [`harness_integration.md`](file:///Users/dolly/team/ws3/diabetes-education-llm-ablation/llm_ablation_paper/workstream_3_ablation_cd/harness_integration.md)：WS1 Harness 接入指南、調用範例與「無接口缺口」評估報告。
3. [`fault_injection_cases.jsonl`](file:///Users/dolly/team/ws3/diabetes-education-llm-ablation/llm_ablation_paper/workstream_3_ablation_cd/fault_injection_cases.jsonl)：包含 16 個高訊號案例之故障注入與防誤殺對照資料集。
4. [`logging_schema_example.json`](file:///Users/dolly/team/ws3/diabetes-education-llm-ablation/llm_ablation_paper/workstream_3_ablation_cd/logging_schema_example.json)：完全滿足 `EXPERIMENT_CONTRACT.md` 規範之逐輪日誌記錄範例。
5. [`tests/test_ablation_cd.py`](file:///Users/dolly/team/ws3/diabetes-education-llm-ablation/llm_ablation_paper/workstream_3_ablation_cd/tests/test_ablation_cd.py)：15 項嚴格斷言之決定性離線測試套件。
6. [`methodology_ablation_cd.md`](file:///Users/dolly/team/ws3/diabetes-education-llm-ablation/llm_ablation_paper/workstream_3_ablation_cd/methodology_ablation_cd.md)：約 900 字繁體中文方法學章節素材。
7. [`test_results.log`](file:///Users/dolly/team/ws3/diabetes-education-llm-ablation/llm_ablation_paper/workstream_3_ablation_cd/test_results.log)：pytest 完整執行日誌（15 passed）。
8. [`STATUS.md`](file:///Users/dolly/team/ws3/diabetes-education-llm-ablation/llm_ablation_paper/workstream_3_ablation_cd/STATUS.md)：本進度與狀態文件。

---

## 2. 測試驗證總結

執行指令：`python3 -m pytest llm_ablation_paper/workstream_3_ablation_cd/tests/test_ablation_cd.py -v`
**測試結果**：**15 passed in 0.63s（全數綠燈通過，零錯誤、零警告）**

| 測試項目名稱 | 驗證重點 | 結果 |
|---|---|---|
| `test_bc_unique_difference` | 驗證 B→C 唯一新增變項僅為 `enable_dynamic_tool_gate` | PASSED |
| `test_cd_unique_difference` | 驗證 C→D 唯一新增變項僅為 `enable_output_guard` | PASSED |
| `test_production_assists_fixed_off_in_main_ablation` | 驗證四條件下 forced retrieval、warning append 與 question budget 恆為 OFF | PASSED |
| `test_tool_gate_diet_nutrition_hides_search` | 驗證 `DIET_NUTRITION`（生活飲食分享）物理收起 `search_handbook` | PASSED |
| `test_tool_gate_diet_nutrition_knowledge_exposes_search` | 驗證 `DIET_NUTRITION_KNOWLEDGE`（飲食知識提問）正常暴露 `search_handbook` | PASSED |
| `test_tool_gate_drug_safety_exposes_search` | 驗證 `DRUG_SAFETY`（用藥安全）正常暴露 `search_handbook` | PASSED |
| `test_tool_gate_previsit_summary_agenda_gate` | 驗證就醫備忘錄工具之議程門禁（充分度未達鎖定，達成解鎖） | PASSED |
| `test_unexposed_tool_call_rejection_guarantee` | 驗證不可見工具調用被 Harness 嚴格拒絕（`not_in_exposed_tools`）且不執行 | PASSED |
| `test_inspect_output_guard_prescription_breach` | 驗證公開函式 `inspect_output_guard()` 攔截處方越權並安全覆寫 | PASSED |
| `test_inspect_output_guard_diagnostic_breach` | 驗證公開函式 `inspect_output_guard()` 攔截確診越權並安全覆寫 | PASSED |
| `test_inspect_output_guard_miracle_claim` | 驗證公開函式 `inspect_output_guard()` 攔截神效宣稱並安全覆寫 | PASSED |
| `test_inspect_output_guard_benign_controls_no_false_positives` | 驗證良性對照文本 100% 安全放行（特異度 Specificity = 1.0） | PASSED |
| `test_cd_paired_execution_safe_override` | 驗證 C 組保留原始違規輸出，D 組進行物理安全覆寫（端對端對照） | PASSED |
| `test_cd_logging_schema_fidelity` | 驗證執行結果結構 100% 滿足契約欄位要求 | PASSED |
| `test_fault_injection_dataset_execution_and_isolation` | 驗證 16 個故障注入案例評測達成 Sensitivity 1.0 與 Specificity 1.0 | PASSED |

---

## 3. 合規性與邊界宣告

1. **零 API 調用宣告**：全套測試均使用 `DeterministicFakeClient` 進行離線決定性推論，未索取、未配置亦未消耗任何外部大模型 API Token。
2. **自然資料與故障注入資料隔離宣告**：
   - 故障注入案例存放於獨立之 `fault_injection_cases.jsonl`，僅用於驗收物理安全網之靈敏度與特異度。
   - 故障注入結果絕不混入模型自然對話軌跡，亦不計入論文主表格中的 Critical Failure Rate 自然違規率。
3. **介面需求宣告**：WS1 Harness 介面完整滿足所有 C/D 消融需求，**無接口缺口（No Interface Gap）**。
4. **阻礙事項（Blocker）**：WS3 工作流本地無任何技術 Blocker。正式 12×4 批次執行目前處於全域協議鎖定狀態，將嚴格等待 WS1 完成全域整體驗收後統一執行。
