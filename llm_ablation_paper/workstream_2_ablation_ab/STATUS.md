# Workstream 2（A／B Planner 消融）狀態報告

- **負責人**：成員 2（Workstream 2）
- **當前分支**：`ws2-ablation-ab`
- **基準版本**：`llm-ablation-ws1-freeze-v1.1`（Commit: `2967d56`）
- **當前階段**：`Stage 2 合併前最小修正完成（WS2-REVIEW-FIX）`
- **當前狀態**：`READY_FOR_REVIEW`

---

## 1. 交付物清單與本次修正記錄

所有檔案均嚴格限制在 `llm_ablation_paper/workstream_2_ablation_ab/` 專屬目錄內，無越界修改：

| 交付檔案 | 類型 | 說明與本次修正（WS2-REVIEW-FIX） |
|---|---|---|
| `ab_configuration.md` | 架構規格 | 1. 修正正式 A 與 B 的 `planner_model` 均為凍結值 `gemini-3.5-flash-lite`（A 因 `enable_planner=False` 不呼叫）；2. 收斂因果推論用語為「受控軟體消融比較之內部效度設計」 |
| `ab_config_diff.json` | 機器可讀 | A 與 B 的 JSON 格式差異表，嚴格證明唯一自變項僅為 `enable_planner` |
| `harness_integration.md` | 整合文件 | 修正 `to_contract_trajectory` 簽名為真實簽名 `(run_id, state_dir, condition_mapping=None, allow_incomplete=True)`，宣告無接口缺口 |
| `methodology_ablation_ab.md` | 學術素材 | 800–1,000 字論文方法學章節素材，收斂因果對照與顯著改善等過度宣稱用語，符合 `CLAIM_BOUNDARIES.md` |
| `tests/test_ab_configuration.py` | 測試程式 | 新增 `test_formal_ablation_config_frozen_invariants`，共 9 項嚴格單元與離線軌跡測試，全數通過 |
| `test_results.log` | 測試紀錄 | 本地自動化測試 9 passed 完整終端機輸出 |
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
collected 9 items

test_ab_config_diff_exact_single_variable                      PASSED [ 11%]
test_formal_ablation_config_frozen_invariants                 PASSED [ 22%]
test_ab_production_assists_and_guards_fixed_off               PASSED [ 33%]
test_ab_canonical_tools_identical_and_fully_exposed           PASSED [ 44%]
test_condition_a_planner_call_count_zero_and_neutral_state    PASSED [ 55%]
test_condition_b_executes_planner_and_injects_guidance        PASSED [ 62%]
test_condition_b_retrieval_domain_does_not_leak_forced_evidence PASSED [ 77%]
test_condition_a_persists_facts_but_not_planner_assessment     PASSED [ 88%]
test_ab_offline_fake_trajectory_contract_compliance           PASSED [100%]

============================== 9 passed in 1.00s ===============================
```
- **測試總數**：9
- **通過數量**：9（100% PASS）
- **失敗／跳過**：0 failed, 0 skipped
- **API 使用**：**0 API 呼叫**（全離線使用 `FakeModelClient` 與 MagicMock 驅動，不耗用真實 Token / 金鑰）

### 2.3 全域回歸測試
```bash
PYTHONPATH=. pytest llm_ablation_paper/workstream_1_technical_lead/tests/ llm_ablation_paper/workstream_2_ablation_ab/tests/ -v
```
- **結果**：`125 passed in 20.56s`，無任何回歸錯誤。

---

## 3. 接口需求評估（Interface Requirements）

經深度代碼審查與實際測試調用，WS1 Harness 既有之公開介面（`run_ablation_turn`、`run_trajectory`、`AblationConfig`、`formal_ablation_config`、`neutral_planner_state`、`get_canonical_tool_snapshot` 等）功能健全且穩定。

**正式結論**：**無接口需求（Zero Missing Interface Requirement）**，無需技術主持或 WS1 進行任何修改或擴充。

---

## 4. 限制與未確認點

1. **離線驗收限制**：本工作流依協議完全採用離線 Fake Client 驗收，未呼叫真實 Google Gemini API。正式模型（`gemini-3.5-flash-lite`）之多輪對話品質與臨床導引表現，將由技術主持人在正式 12×4 批次中統一獲取並交由 WS5 盲評。
2. **正式實驗執行限制**：WS2 嚴格遵守協議，不自行啟動正式 12×4 實驗批次。正式實驗維持等待 WS3、WS5 及 Opaque Mapping 就緒後由 WS1 執行。
