# Relation 風險等級查證

## 查證目的

本文件用於查證 `src/rag_retrieval/risk.py` 中 relation 與
`evidence_risk_level` 的對映理由。本專案目前是架構驗證，以下分級尚未經
臨床專業人員審核，不應解讀為正式臨床風險分級。

## 查證方法與限制

- 風險等級以 `src/rag_retrieval/risk.py` 的 `_RISK_TABLE` 為準，本次不修改程式。
- 實例數以 `src/rag_retrieval/data/bronze_triples_retrievable.json` 為準。
- TFDA 原文以 `../data/data/tfda_dataset_129/raw/drug_risk_communication.json`
  為核對來源；該檔可正常解析，共 129 筆。本文件使用發布日期、藥品成分、
  適應症及「藥品安全有關資訊分析及描述」欄位定位原文。
- openFDA 原文以 `../data/data/openfda_labels/` 內的 JSON 為核對來源；本文件
  使用 `metformin_combo_zituvimet.json` 的 `source`、`query`、
  `generic_name` 與 `dosage_and_administration` 欄位。
- 下載資料目前多包一層 `data/data/`，所以本文件記錄的是實際存在路徑，與
  `CLAUDE.md` 原先預期的 `data/` 路徑不同；這是路徑問題，不影響本次逐字核對。
- Bronze 資料是模型或規則抽取的結果；「有三元組」不等於「已經人工確認正確」。

## 1. `CONTRAINDICATED_FOR` — HIGH

- 契約等級：HIGH
- 本語料實例數：0
- 來源：本可檢索語料無實例。
- 原文摘錄：本語料無實例。
- 為什麼符合此等級：從 relation 的語意來看，「禁忌」代表特定情況不得使用，若未攔截可能直接造成嚴重傷害，因此契約設為 HIGH。
- 為什麼不應升級：HIGH 已是目前最高等級。
- 為什麼不應降級：降級可能讓系統把「不得使用」誤當成一般提醒。
- 限制或待確認事項：openFDA 原始標示雖含 `contraindicated` 文字，但經複方展開與可檢索性過濾後，`bronze_triples_retrievable.json` 中仍為 0 筆；本節依任務規則標示「本語料無實例」，不把原始文字自行補成可檢索三元組。

## 2. `INDUCES` — HIGH

- 契約等級：HIGH
- 本語料實例數：5
- 代表關係：`canagliflozin --INDUCES--> 急性腎損傷`
- 來源：`../data/data/tfda_dataset_129/raw/drug_risk_communication.json`；發布日期 `2016/7/14`，藥品成分 `Canagliflozin及dapagliflozin`，「藥品安全有關資訊分析及描述」欄位。
- 原文摘錄：「1.美國FDA從不良事件通報資料庫（FAERS）中發現101件與使用含canagliflozin成分（73件）及含dapagliflozin成分（28件）藥品具時序相關性之急性腎損傷確診的通報案例，部分案例需住院治療及透析。」
- 為什麼符合此等級：內容涉及用藥後發生「急性腎損傷」的嚴重安全事件；契約把 `INDUCES` 當作嚴重不良事件訊號，因此列為 HIGH。
- 為什麼不應升級：HIGH 已是目前最高等級。
- 為什麼不應降級：若系統忽略此訊號，可能漏掉需要優先呈現的嚴重傷害資訊。
- 限制或待確認事項：「具時序相關性」只代表時間上相關，不等於已證實因果；目前 relation 使用 `INDUCES` 可能強於原文，應由資料或臨床人員人工確認。

## 3. `TRIGGERS` — HIGH

- 契約等級：HIGH
- 本語料實例數：6
- 代表關係：`急症 --TRIGGERS--> DKA`
- 來源：`../data/data/tfda_dataset_129/raw/drug_risk_communication.json`；發布日期 `2015/6/25`，藥品成分 `SGLT2抑制劑類`，「藥品安全有關資訊分析及描述」第 3 點。
- 原文摘錄：「潛在誘發 DKA 之因素包括：急症（例如：泌尿道感染、尿路敗血症、腸胃炎、流行性感冒或外傷）、熱量或液體攝取減少及降低胰島素劑量。」
- 為什麼符合此等級：原文明確使用「潛在誘發」，且 DKA 是可能需要急診或住院處理的急性事件，因此契約將觸發訊號設為 HIGH。
- 為什麼不應升級：HIGH 已是目前最高等級。
- 為什麼不應降級：降級可能讓系統不突出誘發 DKA 的重要條件，影響安全提醒。
- 限制或待確認事項：「潛在」表示不是每位病人都一定發生；HIGH 表示要優先處理，不表示已確定發生。

## 4. `RISK_FACTOR_FOR` — MEDIUM

- 契約等級：MEDIUM
- 本語料實例數：7
- 代表關係：`慢性腎病 --RISK_FACTOR_FOR--> 急性腎損傷`
- 來源：`../data/data/tfda_dataset_129/raw/drug_risk_communication.json`；發布日期 `2016/7/14`，藥品成分 `Canagliflozin及dapagliflozin`，「藥品安全有關資訊分析及描述」第 2 點。
- 原文摘錄：「部分病人有慢性腎病或急性腎損傷病史、脫水、低血壓，或於用藥期間併用血管張力素轉換酶抑制劑（ACEIs）、利尿劑或非類固醇抗發炎藥（NSAIDs）。」
- 為什麼符合此等級：風險因子表示發生機率可能增加，但不是「必然造成」，也不是「不得使用」，所以一般情況採 MEDIUM。
- 為什麼不應升級：目前沒有可檢索的 `CONTRAINDICATED_FOR` 關係，無法證明這筆風險因子位於禁忌路徑。
- 為什麼不應降級：它仍可能影響用藥評估與風險提示，不應視為一般背景知識。
- 限制或待確認事項：這段文字描述通報個案中曾出現的病史或共病，不能單靠此句證明每一項都是獨立因果風險因子。

## 5. `CAUTION_FOR` — MEDIUM

- 契約等級：MEDIUM
- 本語料實例數：2
- 代表關係：`Metformin --CAUTION_FOR--> eGFR 30 至 <45 mL/min/1.73 m²`
- 來源：`../data/data/openfda_labels/metformin_combo_zituvimet.json`；`source` 為 `openFDA Drug Label API (api.fda.gov/drug/label.json)`，查詢為 `openfda.generic_name:"metformin hydrochloride"`，藥品為 ZITUVIMET（Sitagliptin and Metformin Hydrochloride）。
- 原文摘錄：「Renal dosing: do not use if eGFR < 30 mL/min/1.73 m^2; not recommended if eGFR 30 to <45 mL/min/1.73 m^2.」
- 為什麼符合此等級：`not recommended` 是有條件的「不建議」，強度高於一般提醒，但沒有使用 `contraindicated` 表示絕對禁用，因此對應 MEDIUM。
- 為什麼不應升級：不能把 `not recommended` 自動改寫成 `contraindicated`；這也是 `risk.py` 明確禁止把 `CAUTION_FOR` 升成禁忌的原因。
- 為什麼不應降級：這個腎功能區間會影響是否建議用藥，不能當成一般 LOW 資訊。
- 限制或待確認事項：原標示屬複方藥 ZITUVIMET，Bronze 資料將關係拆到 Metformin 與 Sitagliptin，且標記 `requires_manual_split: true`；必須人工確認這項限制實際適用哪個成分。另外，這份本地 JSON 沒有擷取日期或標示版本欄位，因此本文件不再宣稱版本為 `ZITUVIMET-2023`。

## 6. `INTERACTS_WITH` — MEDIUM

- 契約等級：MEDIUM
- 本語料實例數：0
- 來源：本語料無實例。
- 原文摘錄：本語料無實例。
- 為什麼符合此等級：從 relation 的語意來看，交互作用可能改變療效或安全性，需要提醒與判斷，因此契約設為 MEDIUM。
- 為什麼不應升級或降級：沒有原文實例，現階段無法用資料驗證特定交互作用的嚴重度。
- 限制或待確認事項：不能把所有交互作用一律視為相同嚴重度；未來需要原文與條件才能判斷。

## 7. `REQUIRES_MONITORING` — MEDIUM

- 契約等級：MEDIUM
- 本語料實例數：0
- 來源：本語料無實例。
- 原文摘錄：本語料無實例。
- 為什麼符合此等級：從 relation 的語意來看，需要監測代表有可管理但不能忽略的安全條件，因此契約設為 MEDIUM。
- 為什麼不應升級或降級：沒有原文實例，無法判斷監測項目與臨床急迫性。
- 限制或待確認事項：未來須記錄監測項目、頻率與觸發條件，不能只保留 relation 名稱。

## 8. `CAUSES_SIDE_EFFECT` — LOW

- 契約等級：LOW
- 本語料實例數：0
- 來源：本語料無實例。
- 原文摘錄：本語料無實例。
- 為什麼符合此等級：契約將一般副作用和嚴重不良事件分開；一般副作用預設 LOW，嚴重事件則應由 `INDUCES` 等較高風險 relation 表示。
- 為什麼不應升級或降級：沒有原文實例，無法確認副作用嚴重度；LOW 也是目前最低等級。
- 限制或待確認事項：若未來原文描述嚴重或致命事件，不應只因 relation 名稱而固定視為一般 LOW，需跨組確認 relation 抽取規則。

## 9. `TREATS` — LOW

- 契約等級：LOW
- 本語料實例數：9
- 代表關係：`SGLT2抑制劑類 --TREATS--> 第二型糖尿病`
- 來源：`../data/data/tfda_dataset_129/raw/drug_risk_communication.json`；發布日期 `2015/6/25`，「藥品成分」與「適應症」欄位。
- 原文摘錄：「藥品成分：SGLT2抑制劑類」「適應症：第二型糖尿病。」
- 為什麼符合此等級：這是藥品適應症／用途資訊，不是禁忌、嚴重不良事件或警告，因此契約設為 LOW。
- 為什麼不應升級：僅憑「用於治療」不能推出高風險安全訊號。
- 為什麼不應降級：LOW 已是目前最低等級。
- 限制或待確認事項：`TREATS` 只表示適應症關係，不代表適合每位病人，也不能取代個別用藥判斷。

## 10. `IS_A` — LOW

- 契約等級：LOW
- 本語料實例數：0
- 來源：本語料無實例。
- 原文摘錄：本語料無實例。
- 為什麼符合此等級：從 relation 的語意來看，它只是分類／隸屬關係，本身不是安全警告，因此契約設為 LOW。
- 為什麼不應升級：不能從分類關係直接推論禁忌或傷害。
- 為什麼不應降級：LOW 已是目前最低等級。
- 限制或待確認事項：目前沒有可檢索實例，無法用本語料驗證。

## `RISK_FACTOR_FOR` 特別判斷

- 可寫成程式的候選規則：只有在同一查詢／用藥情境中，該 `RISK_FACTOR_FOR`
  三元組的風險因子實體，能以相同標準化 ID 連到一筆已人工確認、未否定且可檢索的
  `CONTRAINDICATED_FOR` 三元組時，才升為 HIGH；僅文字相似不能升級。
- 現有資料是否足以實作與驗證：不足。現有可檢索資料中
  `CONTRAINDICATED_FOR` 為 0 筆，沒有正例可測試，也沒有已定義的跨 relation
  路徑與同一病人／藥品情境規則。
- 結論：目前維持 MEDIUM。
- 理由：現在若升級，只能靠猜測或文字相似，容易把一般風險因子誤報成禁忌。
  等未來有人工確認的禁忌資料、統一實體 ID 和路徑測試案例後，再由 Boundary 與 LLM
  兩組共同確認是否實作升級規則。

## 查證結論

- relation 總數：10
- 找到現有資料文字佐證的 relation 數：5
- 本語料無實例的 relation 數：5
- 有實例者：`INDUCES`、`TRIGGERS`、`RISK_FACTOR_FOR`、`CAUTION_FOR`、`TREATS`
- 無實例者：`CONTRAINDICATED_FOR`、`INTERACTS_WITH`、`REQUIRES_MONITORING`、`CAUSES_SIDE_EFFECT`、`IS_A`
- 待跨組確認：`INDUCES` 是否強於「時序相關性」原文、ZITUVIMET 複方拆分歸屬，以及未來 `RISK_FACTOR_FOR` 升為 HIGH 的圖路徑規則。
- 逐字核對結果：TFDA 原始 JSON 支持 `INDUCES`、`TRIGGERS`、`RISK_FACTOR_FOR`、`TREATS`；openFDA 標示 JSON 支持 `CAUTION_FOR`。原始資料阻礙已解除。
- 交件說明：10 種 relation 中，有 5 種在現有原始資料找到文字佐證，另外 5 種在可檢索語料中沒有實例。
