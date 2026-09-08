# Dataset Card — Workstream 4 合成病患背景種子

> 本卡僅描述工作流 4 使用的資料來源與處理方式。產出為合成模擬情境，不是真實病歷，也不具臨床代表性。

## 1. 來源與授權

- 原始資料集：Toyhom `Chinese-medical-dialogue-data`，儲存庫 `https://github.com/Toyhom/Chinese-medical-dialogue-data`。
- 使用檔案：`Data_数据/IM_内科/内科5000-33000.csv`。
- 鎖定版本：commit `26724a4357fcd142f0cab81188cacf1a2dd8a827`。
- 檔案 SHA-256：`9fd5a19caa5b37aa6f7a3fa4bf5e9ce97716f0407c94a41ade951627f2f4db20`。
- 儲存庫標示 MIT License，但該標示不等於其彙整的網路問答已有完整授權與去識別鏈。

因此，本研究只將它視為 public online medical QA-derived background seeds。不得將它稱為真實臨床對話、已去識別病歷或具臨床代表性的資料集。

## 2. 全量處理範圍

以完整 IM 內科 CSV 計算，不是抽樣外推：

- `total_rows`: 220606
- `parsed_rows`: 220606
- `damaged_rows`: 0
- `encoding_used`: `gb18030 (fallback utf-8-sig, utf-8, gb18030)`
- 讀取方式：`csv.DictReader`，僅用 `department`、`title`、`ask`；`answer` 不參與篩選或標準答案建立。
- 內分泌科原始筆數：21745。

### 探索性寬鬆池

寬鬆規則為 `title/ask` 命中 diabetes、medication 或 glucose 任一詞組，不限科別。該池僅保留為探索性統計，不是 12 個 profiles 的正式抽樣池：

- 去重前：51970
- 去重後：49373
- PII regex 排除：22

## 3. 正式候選與情境分層

正式候選必須同時滿足：

1. `department` 精確為 `内分泌科` 或 `內分泌科`。
2. `title/ask` 至少命中一個嚴格詞：糖尿病／血糖詞，或二甲雙胍、胰島素、達格列淨、阿卡波糖、格列齊特、瑞格列奈等指定藥物詞（含簡繁）。
3. 除 `FACT_CONTRADICTION` 外，還必須命中所屬情境的兩組 bucket 詞。`FACT_CONTRADICTION` 從嚴格池中取樣，矛盾與更正輪次為明示的合成 perturbation。

去重後嚴格候選池為 6306 筆。情境 bucket 實際數量：

| 情境 | 候選數 |
| --- | ---: |
| DAILY_DIET | 586 |
| MEDICATION_SIDE_EFFECT | 52 |
| MEDICATION_NONADHERENCE | 386 |
| SUBACUTE_HYPOGLYCEMIA | 136 |
| PREVISIT_SUMMARY | 971 |
| FACT_CONTRADICTION | 6306 |

六個 bucket 依序使用 `random.Random(42 + bucket_index).sample(..., 2)` 各取兩筆，並禁止 bucket 間重複。任一 bucket 少於兩筆時 fail closed。不得依 A–D 初步表現重選 profiles。

## 4. 合成與正規化

- OpenCC：必須成功載入 `OpenCC("s2twp")`；缺失或初始化失敗時立即停止。僅轉換顯示文字，不改變 `row_index` 與 SHA。
- 藥名顯示：二甲雙胍（metformin）、達格列淨（dapagliflozin）。
- 血糖單位：僅在血糖語境以 `mmol/L × 18` 轉換為 `mg/dL`，並保留原值、轉換值與係數。
- 原始 `title/ask/answer` 全文不寫入公開 profile；年齡、症狀細節、數值、用藥、目標與 reveal policy 均為合成內容。

## 5. Profile 分布與來源邊界

| 情境 | 筆數 | 病患編號 |
| --- | ---: | --- |
| DAILY_DIET | 2 | SP-001、SP-002 |
| MEDICATION_SIDE_EFFECT | 2 | SP-003、SP-004 |
| MEDICATION_NONADHERENCE | 2 | SP-005、SP-006 |
| SUBACUTE_HYPOGLYCEMIA | 2 | SP-007、SP-008 |
| PREVISIT_SUMMARY | 2 | SP-009、SP-010 |
| FACT_CONTRADICTION | 2 | SP-011、SP-012 |

每筆 `source_provenance` 保留來源檔、commit、檔案 SHA、row index、record SHA、科別、`matched_source_terms`、`matched_scenario_terms`、`source_role` 與 `synthetic_additions`。

本批 profiles 的 `source_role` 統一為 `background_seed`：原始 QA 只用於錨定科別與關鍵概念，並未直接貢獻公開 profile 的句型或完整情境。只有未來能以可追溯證據證明實際使用了來源語言或情境內容時，才可改為 `linguistic_seed` 或 `scenario_seed`，不得以編號輪替指定。

## 6. 驗收與使用限制

整合測試會直接回讀原始 CSV 的 `department/title/ask`，重算嚴格詞、bucket 命中、record SHA，並與 profile provenance 逐筆比對。不得使用合成 profile 自身文字來證明原始資料命中。

這些檔案只支持「在本研究的模擬情境中」的系統層級觀察。不得主張真實病患、臨床驗證、臨床安全率或醫師審查。

## 7. 參照檔案

- `llm_ablation_paper/workstream_4_patient_simulation/source_manifest.json`
- `llm_ablation_paper/workstream_4_patient_simulation/candidate_filter_report.json`
- `llm_ablation_paper/workstream_4_patient_simulation/patient_profiles.jsonl`
- `llm_ablation_paper/workstream_4_patient_simulation/profile_schema.json`
- `llm_ablation_paper/shared/CLAIM_BOUNDARIES.md`
