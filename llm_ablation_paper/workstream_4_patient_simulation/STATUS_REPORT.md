# Workstream 4 狀態報告（WS4-A 與 WS4-B）

> 範圍：資料篩選、12 份合成 profiles、schema 與驗證，以及 WS4-B roleplay runner。本報告不把模擬情境稱為真實臨床驗證。

## 1. 目前判定

`APPROVED`（WS4-B 正式就緒強化；WS4-A 維持已通過）

WS4-A 核心產物維持已通過。WS4-B roleplay runner 已於 `ws1-formal-readiness` 分支完成正式就緒強化（Gemini-only provider 配對、fake dry-run 改走逐輪正式路徑、retry 分類、可注入 timeout、`research_patient_id` 解耦、Input Guard canary、`WS4_REQUIRE_SOURCE_CSV`），並已補齊 execution envelope 閘門，經 WS1 驗收並以 `llm-ablation-ws1-freeze-v1` 完成 final freeze。**正式 12×4 批次仍為 `BLOCKED`**，不得寫成 READY 或 APPROVED；剩餘 blockers：(1) WS2、WS3、WS5 尚未完成；(2) opaque condition mapping 尚未產生（依程序於盲測匯出前由技術主持私下產生）。

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
- Pytest：`139 passed`（WS4 目錄全套，含 WS4-A profiles/validator 與 WS4-B runner／formal-readiness；最新數字見第 10 節）。
- 來源追溯：本機以固定上游 CSV（Toyhom commit `26724a4`，SHA-256 `9fd5a19c…f2f4db20`）完整重跑 `test_01`–`test_04` 並全數通過。未提供該 100 MB 上游 CSV 的機器上，未設 `WS4_REQUIRE_SOURCE_CSV` 時此四項會 **skip（非 fail）**；設為 `1` 時缺 CSV 或 SHA 不符則 **fail closed**（見第 10 節）。
- Fake dry-run：A/B/C/D 四條軌跡各 6 輪、終止原因 `MAX_TURNS`；config 唯一差異映射為 A OFF-OFF-OFF／B ON-OFF-OFF／C ON-ON-OFF／D ON-ON-ON，三項輔助固定 OFF；A/B 兩工具全暴露、C/D 經 gate 收斂；另含一條獨立 Input Guard canary（`COMMON_INPUT_BLOCK`，不列入 A–D 比較）。

驗收判定：**通過（已合併）**。無越界修改、測試通過、dry-run 可重現；原列待強化項目已於 `ws1-formal-readiness` 全數解決（詳見第 9、10 節）。正式 12×4 仍為 `BLOCKED`，不宣稱正式批次就緒。

## 9. 正式執行前待強化（原始 WS1 記錄）—狀態更新

原列六項已於 `ws1-formal-readiness` 分支（`4039992` 與本次 commit）解決：

- ~~fake 路徑以輪數推斷 `PATIENT_GOAL_MET`~~ → 已移除單一 subprocess 路徑，fake dry-run 改走正式逐輪 `run_condition`，終止原因一律取自結構化 state。
- ~~`_is_transient_error` 未涵蓋正式 API 例外~~ → 已改為類別判斷（`openai.APITimeoutError/APIConnectionError/RateLimitError/InternalServerError` 與 status `{408,409,429,500,502,503,504}`），4xx 與 schema 錯誤永不重試。
- ~~fake 與正式路徑拓撲不同~~ → 已統一為逐輪 subprocess；fake dry-run 端到端覆蓋正式路徑。
- ~~Harness `patient_id` 被寫成 `user_id`~~ → 已解耦 `research_patient_id`（`SP-001`）與狀態隔離 `user_id`，blinded export 明確帶研究 ID 且不含 `ws4_*`。
- ~~30 秒 timeout 偏緊~~ → 已改為可注入 `subprocess_timeout_seconds`（預設 30s 向後相容、非正數 fail-closed）；freeze candidate 正式值為 120 秒，待 final tag 生效。
- ~~`WS4_REQUIRE_SOURCE_CSV` 待決定~~ → 已實作；未設定時缺 CSV 允許 skip，設為 `1` 時 fail closed。

仍待處理（**正式實驗 blocker，維持 BLOCKED**）：

- P0-1：核心 production 髒檔（`ablation_core.py`、`guard.py`、`state.py`、`planner.py`、`tools.py`、`handlers.py`）尚未逐項審核、未納入 frozen candidate，故 `ab30eff` 仍不代表可執行行為。
- 正式 commit、Talker/Planner prompt SHA 與 tool schema SHA 已記入 freeze candidate（待 final freeze 與 final tag）；opaque condition mapping 尚未產生；timeout 正式值為 freeze candidate 120 秒，待 final tag 生效。
- WS2、WS3、WS5 尚未完成；正式 raw transcripts 尚未產生。

## 10. WS1／WS4 正式就緒強化（2026-09-10，分支 `ws1-formal-readiness`）

本輪在乾淨 worktree 完成，未動原 working tree 既有修改、未動 frozen profiles、未修改 production、未呼叫付費 API、未執行正式 12×4。

修正：

- **Provider 配對（Gemini-only）**：正式執行只接受 `GEMINI_API_KEY`，不使用 `OPENAI_API_KEY`；`provider_config.provider` 非 `gemini` 一律 fail-closed；`provider_config.base_url` 或 `GEMINI_BASE_URL` 指向非 Gemini endpoint 時拒絕，避免 Gemini 金鑰被配到其他服務；金鑰只從環境讀取，不寫入 artifact／checkpoint／log／錯誤訊息。
- **Fake dry-run 走正式逐輪路徑**：`run_condition` 每條件 6 次 subprocess，共 24 assistant turns；終止原因取自結構化 state。
- **artifact 隔離**：新增向後相容 `artifacts_dir` override，run 完整自治於自身 `state_dir`，不再回退共用 `artifacts/workstream_1/<run_id>`。
- **Retry**：類別＋status 分類，保留 1/2/4/8s 與 attempts metadata。
- **Timeout**：可注入、預設 30s、非正數 fail-closed。
- **`research_patient_id`**：與狀態 `user_id` 解耦。
- **Input Guard canary**：`run_input_block_canary` 併入 `--fake-dry-run`；summary 記錄 `termination_reason=COMMON_INPUT_BLOCK`、`canary=true`、`is_canary=true`、`counted_in_comparison=false`；若 canary 未觸發 `COMMON_INPUT_BLOCK`，dry-run 直接 fail-closed，不得靜默成 `MAX_TURNS`。
- **`WS4_REQUIRE_SOURCE_CSV`**：fail-closed 模式。

重新產生 checked-in artifact：`artifacts/fake_dry_run_batch/`（含 `canary_input_block/`）。新 artifact 的 `harness_turn.patient_id`／`research_patient_id` 皆為 `SP-001`、`user_id` 保留條件隔離 ID、records 含 `patient_retry_metadata`、A/B/C/D 各 6 輪且各自獨立 user_id 與 state directory。

測試（乾淨 worktree，`PYTHONPATH="$PWD"`）：WS1 `59 passed`；WS4 `139 passed`；`test_ablation_backward_compat.py` `5 passed`；validator `PASS`；0 skipped（本機具上游 CSV，provenance 01–04 實跑通過）。

本輪強化已於 2026-09-10 經 WS1 驗收並合併至 `main`（核准 feature commit `a7f4b72`），判定 `APPROVED`。正式 12×4 維持 `BLOCKED`。
