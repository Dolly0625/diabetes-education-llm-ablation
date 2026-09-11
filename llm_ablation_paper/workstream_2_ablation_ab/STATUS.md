# Workstream 2（A／B Planner 消融）狀態報告

- **負責人**：成員 2（Workstream 2）
- **當前分支**：`ws2-ablation-ab`
- **基準版本**：`llm-ablation-ws1-freeze-v1.1`（Commit: `2967d56`）
- **當前階段**：`Stage 2 完成，等待技術主持驗收`
- **當前狀態**：`READY_FOR_REVIEW`

---

## 1. 交付物清單

所有檔案均嚴格限制在 `llm_ablation_paper/workstream_2_ablation_ab/` 專屬目錄內，無越界修改：

| 交付檔案 | 類型 | 說明 |
|---|---|---|
| `ab_configuration.md` | 架構規格 | A/B 詳細架構設計、Planner 輸入/輸出/降級規範、Neutral 狀態定義、工具暴露策略與生產輔助關閉規範 |
| `ab_config_diff.json` | 機器可讀 | A 與 B 的 JSON 格式差異表，嚴格證明唯一自變項僅為 `enable_planner` |
| `harness_integration.md` | 整合文件 | WS1 Harness 公開接口接入說明（`run_ablation_turn`、`run_trajectory` 等），宣告無接口缺口 |
| `methodology_ablation_ab.md` | 學術素材 | 800–1,000 字論文方法學章節素材，符合 `CLAIM_BOUNDARIES.md` 與 AMIE 啟發模擬規範 |
| `tests/test_ab_configuration.py` | 測試程式 | 包含 8 項嚴格單元與離線軌跡測試，全覆蓋唯一差異、工具暴露、Neutral 狀態、Guidance 注入與合約相容性 |
| `test_results.log` | 測試紀錄 | 本地自動化測試 8 passed 完整終端機輸出 |
| `STATUS.md` | 進度報告 | 本狀態追蹤報告 |

---

## 2. 測試結果與指令

### 2.1 測試指令
```bash
PYTHONPATH=. pytest llm_ablation_paper/workstream_2_ablation_ab/tests/test_ab_configuration.py -v
```

### 2.2 測試覆蓋項目與結果
```text
============================= test session starts ==============================
collected 8 items

test_ab_config_diff_exact_single_variable                      PASSED [ 12%]
test_ab_production_assists_and_guards_fixed_off               PASSED [ 25%]
test_ab_canonical_tools_identical_and_fully_exposed           PASSED [ 37%]
test_condition_a_planner_call_count_zero_and_neutral_state    PASSED [ 50%]
test_condition_b_executes_planner_and_injects_guidance        PASSED [ 62%]
test_condition_b_retrieval_domain_does_not_leak_forced_evidence PASSED [ 75%]
test_condition_a_persists_facts_but_not_planner_assessment     PASSED [ 87%]
test_ab_offline_fake_trajectory_contract_compliance           PASSED [100%]

============================== 8 passed in 1.00s ===============================
```
- **測試總數**：8
- **通過數量**：8（100% PASS）
- **失敗／跳過**：0 failed, 0 skipped
- **API 使用**：**0 API 呼叫**（全離線使用 `FakeModelClient` 與 MagicMock 驅動，不耗用真實 Token / 金鑰）

### 2.3 全域回歸測試
```bash
PYTHONPATH=. pytest llm_ablation_paper/workstream_1_technical_lead/tests/ llm_ablation_paper/workstream_2_ablation_ab/tests/ -v
```
- **結果**：`124 passed in 19.84s`，無任何回歸錯誤。

---

## 3. 接口需求評估（Interface Requirements）

經深度代碼審查與實際測試調用，WS1 Harness 既有之公開介面（`run_ablation_turn`、`run_trajectory`、`AblationConfig`、`neutral_planner_state`、`get_canonical_tool_snapshot` 等）功能健全且穩定。

**正式結論**：**無接口需求（Zero Missing Interface Requirement）**，無需技術主持或 WS1 進行任何修改或擴充。

---

## 4. 限制與未確認點

1. **離線驗收限制**：本工作流依協議完全採用離線 Fake Client 驗收，未呼叫真實 Google Gemini API。正式模型（`gemini-3.5-flash-lite`）之多輪對話品質與臨床導引表現，將由技術主持人在正式 12×4 批次中統一獲取並交由 WS5 盲評。
2. **正式實驗執行限制**：WS2 嚴格遵守協議，不自行啟動正式 12×4 實驗批次。正式實驗維持等待 WS3、WS5 及 Opaque Mapping 就緒後由 WS1 執行。
