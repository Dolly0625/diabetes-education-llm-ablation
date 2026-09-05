# Boundary A — 風險等級查證交付說明

更新日期：2026-08-31

## 交付項目

- 任務書：`RAG_boundary/04_boundary_a_risk_table.md`
- Repository：`diabetes-rag`
- 工作分支：`member/Lee/boundary_A`
- 交付文件：`docs/risk_table_justification.md`
- 任務性質：文件查證，不修改程式。

## 完成內容

1. 逐項說明 `src/rag_retrieval/risk.py` 中 10 種 relation 的風險等級與設計理由。
2. 以 `bronze_triples_retrievable.json` 核對 relation 實例數。
3. 直接使用 TFDA 129 筆原始 JSON 與 openFDA 標示 JSON 逐字核對來源。
4. 10 種 relation 中，有 5 種找到真實原文佐證：
   `INDUCES`、`TRIGGERS`、`RISK_FACTOR_FOR`、`CAUTION_FOR`、`TREATS`。
5. 另外 5 種在可檢索語料中沒有實例：
   `CONTRAINDICATED_FOR`、`INTERACTS_WITH`、`REQUIRES_MONITORING`、
   `CAUSES_SIDE_EFFECT`、`IS_A`。
6. `RISK_FACTOR_FOR` 因目前沒有可檢索的 `CONTRAINDICATED_FOR` 正例，
   暫時維持 MEDIUM，並在文件中記錄未來可實作的升級條件與限制。

## Git 檢查結果

- 已建立並使用組員分支：`member/Lee/boundary_A`。
- 已完成兩筆 commit：
  - `5695f46 docs(risk): document relation risk rationale for step 7`
  - `c1df0c5 docs(risk): verify relation rationale against source data`
- 相對 `main` 只新增一個檔案：

```text
A  docs/risk_table_justification.md
```

- `src/rag_retrieval/risk.py` 經 `git diff main...HEAD` 檢查，結果為
  `NO_CHANGES`，確認完全沒有修改。
- 2026-08-31 檢查時，遠端尚未找到 `member/Lee/boundary_A`，本機分支也尚未
  設定 upstream；因此仍須先 push，才能建立 Merge Request。

## 驗收說明

Boundary A 任務書的驗收條件明確寫為「不用跑程式」，交件時提供：

1. `docs/risk_table_justification.md` 文件本身。
2. 一句話說明找到真實原文佐證的 relation 數量。

交件句：

> 10 種 relation 中，有 5 種在現有 TFDA／openFDA 原始資料找到真實原文佐證；另外 5 種在可檢索語料中沒有實例。

## 尚未完成與交付順序

1. Push 工作分支：

```powershell
git push -u origin member/Lee/boundary_A
```

2. 在 GitLab 建立 Merge Request，source 選 `member/Lee/boundary_A`，target 選
   `main`。
3. 將本交付說明與 Merge Request 提供給 RAG 組 Erich 確認。
4. **確認前不得 merge。**
5. 核准後，才由有權限的人員將 Merge Request 合併到 `main`。

## 待確認事項

- `INDUCES` 是否比 TFDA 原文的「具時序相關性」表達更強。
- ZITUVIMET 複方拆分後，eGFR 限制應歸屬於 Metformin、Sitagliptin，或整個複方。
- 未來 `RISK_FACTOR_FOR` 從 MEDIUM 升為 HIGH 的圖路徑規則。
- 本次沒有要求修改 `risk.py`；若未來需要更動風險表，必須先經 Boundary 與
  LLM 兩組同意。
