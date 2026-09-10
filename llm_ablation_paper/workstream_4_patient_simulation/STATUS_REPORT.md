# Workstream 4 狀態報告（WS4-A 與 WS4-B）

> 範圍：資料篩選、12 份合成 profiles、schema 與驗證，以及 WS4-B roleplay runner。本報告不把模擬情境稱為真實臨床驗證。

## 1. 目前判定

`APPROVED`（WS4-A 與 WS4-B）

WS4-A 核心產物已重新產生並通過本機驗證。WS4-B roleplay runner、checkpoint／resume／retry 與 fake dry-run 已完成，經 WS1 技術驗收後合併至 `main`。正式 12×4 批次仍未執行，須待整體實驗指紋凍結。

## 2. 本輪修正與產物

| 檔案 | 狀態 | 說明 |
| --- | --- | --- |
| `scripts/build_patient_profiles.py` | 已修正 | 嚴格內分泌科篩選、情境 bucket 抽樣、OpenCC fail closed；`source_role` 依實際用途統一為 `background_seed` |
| `patient_profiles.jsonl` | 已重生 | 固定 seed 的 12 筆 profiles，六類各二 |
| `candidate_filter_report.json` | 已重生 | 全量、寬鬆探索池、嚴格池與 bucket 統計 |
| `source_manifest.json` | 已重生 | 來源 commit、SHA、編碼與轉換記錄 |
| `tests/test_real_artifact_integration.py` | 已加強 | 直接回讀原始 CSV，不以合成 profile 文字自我驗證 |
| `DATASET_CARD.md` | 已更新 | 正式篩選規則、資料邊界與來源角色已對齊實際產物 |

未修改 `artifacts/`、`shared/`、`diabetes_chatbot/`、`diabetes-rag/`、`.env` 或其他 Workstream，也未 commit。

## 3. 可追溯資料統計

- 來源：`Data_数据/IM_内科/内科5000-33000.csv`
- commit：`26724a4357fcd142f0cab81188cacf1a2dd8a827`
- SHA-256：`9fd5a19caa5b37aa6f7a3fa4bf5e9ce97716f0407c94a41ade951627f2f4db20`
- 全量：220606 rows；成功解析 220606；損壞 0
- 內分泌科原始筆數：21745
- 寬鬆探索池：51970（去重前）／49373（去重後）
- 內分泌科且命中糖尿病、血糖或指定藥物詞的嚴格池：6645（去重前）／6306（去重後）
- PII regex 排除：22
- 隨機種子：42

情境 bucket：DAILY_DIET 586、MEDICATION_SIDE_EFFECT 52、MEDICATION_NONADHERENCE 386、SUBACUTE_HYPOGLYCEMIA 136、PREVISIT_SUMMARY 971、FACT_CONTRADICTION 6306。

## 4. 12 筆正式 profiles

| 病患 | 情境 | row_index | source_role | max_turns |
| --- | --- | ---: | --- | ---: |
| SP-001 | DAILY_DIET | 10254 | background_seed | 6 |
| SP-002 | DAILY_DIET | 876 | background_seed | 6 |
| SP-003 | MEDICATION_SIDE_EFFECT | 1743 | background_seed | 6 |
| SP-004 | MEDICATION_SIDE_EFFECT | 66179 | background_seed | 6 |
| SP-005 | MEDICATION_NONADHERENCE | 80120 | background_seed | 6 |
| SP-006 | MEDICATION_NONADHERENCE | 89917 | background_seed | 6 |
| SP-007 | SUBACUTE_HYPOGLYCEMIA | 96707 | background_seed | 6 |
| SP-008 | SUBACUTE_HYPOGLYCEMIA | 154842 | background_seed | 6 |
| SP-009 | PREVISIT_SUMMARY | 197763 | background_seed | 6 |
| SP-010 | PREVISIT_SUMMARY | 1373 | background_seed | 6 |
| SP-011 | FACT_CONTRADICTION | 95242 | background_seed | 6 |
| SP-012 | FACT_CONTRADICTION | 9129 | background_seed | 6 |

12 筆全部來自原始 `内分泌科`，命中 strict terms 並符合各自 bucket。`source_record_sha256`、`matched_source_terms` 與 `matched_scenario_terms` 均由原始 `department/title/ask` 重算比對。

## 5. 來源角色與合成邊界

原始 QA 只提供科別與關鍵概念錨點，公開 profile 並未複製原始 `title/ask/answer`。年齡、數值、用藥細節、情境目標、hidden facts、reveal policy 與矛盾 perturbation 皆為合成內容，因此所有 profiles 標示 `source_role=background_seed`。

本資料不可支持真實病患、醫師審查、臨床驗證或臨床安全率等主張。

## 6. 驗收結果

驗收指令：

```bash
python3 llm_ablation_paper/workstream_4_patient_simulation/scripts/validate_profiles.py
python3 -m pytest llm_ablation_paper/workstream_4_patient_simulation/tests -q
```

最終實測結果：

- Validator：`PASS: 12 profiles validated (6 types x2, IDs unique, max_turns=6, no PII/flags, glucose context ok)`
- Pytest：`72 passed`
- OpenCC 缺失時 fail closed。
- 整合測試直接從原始 CSV 重算科別、strict terms、scenario terms 與 record SHA。

## 7. 尚未執行與風險

- 未執行 A、B、C、D 正式角色扮演或比較；未產生任何正式 transcripts。
- WS4-B runner、checkpoint／resume／retry 與 fake dry-run 已完成（見第 8 節），但只使用 deterministic fake model。
- 上游網路問答權利與去識別方式不明，只能稱為 background seeds。
- 合成 persona 並未經臨床驗證。
- 未寫入正式 `llm_ablation_paper/artifacts/`，未呼叫付費 API。

## 8. WS4-B 交付與 WS1 驗收（2026-09-10）

分支 `ws4-runner`（`daa839b`、`e9d0ac7`）經 WS1 技術主持驗收，無越界修改（全部變更集中於本工作流目錄）。驗收於 `e9d0ac7` 的獨立 worktree 執行，未觸動正式資料或其他工作流。

交付：

- `scripts/run_patient_simulation.py`：批次 roleplay runner，透過既有 WS1 Harness 的 `run_trajectory_subprocess` 執行，未另寫控制器；CLI 僅開放 `--fake-dry-run`，正式模式在指紋凍結前被硬性拒絕。
- `tests/test_roleplay_runner.py`：checkpoint／resume／retry／state isolation／config injection 測試。
- `artifacts/fake_dry_run_batch/`：1 個 profile × 4 條件（A/B/C/D）的 deterministic fake dry-run 產物。
- `METHODS_DRAFT.md`（約 700 字）與 `FLOWCHART_DRAFT.md`。

驗收指令與結果：

```bash
python3 llm_ablation_paper/workstream_4_patient_simulation/scripts/validate_profiles.py
python3 -m pytest llm_ablation_paper/workstream_4_patient_simulation/tests -q
python3 llm_ablation_paper/workstream_4_patient_simulation/scripts/run_patient_simulation.py --fake-dry-run --output-root <fresh-temp-dir>
```

- Validator：`PASS: 12 profiles validated (6 types x2, IDs unique, max_turns=6, no PII/flags, glucose context ok)`
- Pytest：`84 passed`（WS4-A 72 項 + runner 12 項）。
- 來源追溯：本機以固定上游 CSV（Toyhom commit `26724a4`，SHA-256 `9fd5a19c…f2f4db20`）完整重跑 `test_01`–`test_04` 並全數通過。此四項測試在未提供該 100 MB 上游 CSV 的機器上會 **skip（非 fail）**，其餘 `test_05`–`test_10` 與 runner 測試不受影響；此為可攜性取捨，並不代表來源追溯被弱化，正式論文引用前應於具 CSV 的環境重跑。
- Fake dry-run：A/B/C/D 四條軌跡各 6 輪、終止原因 `MAX_TURNS`；config 唯一差異映射為 A OFF-OFF-OFF／B ON-OFF-OFF／C ON-ON-OFF／D ON-ON-ON，三項輔助固定 OFF；A/B 兩工具全暴露、C/D 經 gate 收斂。

驗收判定：**部分通過（可合併）**。無越界修改、測試通過、dry-run 可重現；惟來源追溯測試的可攜性 skip 語意已如上明示，且正式執行前仍有待強化項目（詳見第 9 節），故不宣稱正式批次就緒。

## 9. 正式執行前待強化（WS1 記錄，不阻擋本次合併）

- `run_patient_simulation.py` fake 路徑以輪數推斷 `PATIENT_GOAL_MET`（第 664 行）而非讀取結構化 `termination_reason`；目前不可達，但正式化前應改為推導並斷言。
- `_is_transient_error` 僅認得內建 `TimeoutError`／`ConnectionError` 與字串標記，正式 API 例外（如 `openai.APIConnectionError`）可能未被重試；正式執行前應放寬。
- 正式路徑 `run_condition` 為逐輪 subprocess，fake dry-run 走單一 subprocess 軌跡路徑，兩者拓撲不同，dry-run 未端到端覆蓋正式路徑。
- Harness 的 `patient_id` 實際寫入合成的 `user_id`；下游消費者需知悉此映射。
- 30 秒 subprocess timeout 對正式多工具回合可能偏緊。
- 是否為來源追溯測試加入 `WS4_REQUIRE_SOURCE_CSV` 環境變數以在 CI／驗收強制 fail-closed，待團隊決定。
