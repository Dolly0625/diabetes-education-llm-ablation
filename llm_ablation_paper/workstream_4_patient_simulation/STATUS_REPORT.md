# Workstream 4-A 狀態報告

> 範圍：資料篩選、12 份合成 profiles、schema 與驗證。本報告不把模擬情境稱為真實臨床驗證。

## 1. 目前判定

`READY_FOR_TECHNICAL_APPROVAL`

WS4-A 核心產物已重新產生並通過本機驗證。本階段尚未建立 roleplay runner，也未執行 A–D 正式實驗。

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

- 未執行 A、B、C、D 正式角色扮演或比較。
- 未建立 WS4-B runner、checkpoint、resume、retry 或 transcripts。
- 上游網路問答權利與去識別方式不明，只能稱為 background seeds。
- 合成 persona 並未經臨床驗證。
- 未寫入正式 `artifacts/`，未呼叫付費 API，未 commit。
