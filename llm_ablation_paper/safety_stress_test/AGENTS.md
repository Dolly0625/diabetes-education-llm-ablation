# safety_stress_test — 工作流規則（AGENTS）

本目錄為**探索性安全壓力測試**工作流。它**不屬於**正式 12×4 主實驗，兩者必須分開報告。

## 目標

在已凍結主實驗之外，建立可重現、可稽核的離線壓力測試環境，回答正常情境無法回答的問題：
A／B／C／D 遭遇危險要求、持續施壓、工具誘導與 prompt injection 時，各層防線是否有作用。

## 允許修改

- `llm_ablation_paper/safety_stress_test/` 內所有檔案。

## 絕對禁止

- 修改 `diabetes_chatbot/`、`diabetes-rag/`、`.env`、`scripts/`。
- 修改已凍結的 `artifacts/raw_transcripts*`、`artifacts/blinded_transcripts*`、`artifacts/frozen_config/`、
  `artifacts/judge_raw*`、`artifacts/derived_results*`、`results/`。
- 在正式 execution envelope 之外啟動任何真實模型呼叫（本工作流僅允許 deterministic fake）。
- 建立或寫入 `artifacts/frozen_config/frozen_condition_mapping.json`（凍結狀態為 `NOT_GENERATED`）。
- 把 canary 混入主 CFR／ASR 比較。
- 把 guard-reachability fault injection 當成模型安全效果。
- 把 refusal rate 等同安全、把 zero observed 寫成零風險、把 LLM Judge 寫成醫師、把本工作流寫成臨床驗證。

## 單一真實來源

- 主實驗規格：`../shared/RESEARCH_PROTOCOL.md`
- 資料與軌跡格式：`../shared/EXPERIMENT_CONTRACT.md`
- 主張邊界：`../shared/CLAIM_BOUNDARIES.md`
- 系統全貌：`../shared/SYSTEM_OVERVIEW.md`
- 本工作流協定：`./STRESS_TEST_PROTOCOL.md`

## 執行規則

- 僅能重用 `workstream_1_technical_lead/harness` 的介面；不得 fork harness。
- 所有測試必須離線、確定性；不得以 skip／xfail 假裝通過。
- 任何 fail-closed 驗證（mapping、frozen config、canary、CF code、PII、guard 可達性）失敗時必須中止，不得降級為警告。
- 交付時需附：修改檔案、執行指令、passed／failed／skipped、artifact 數量、是否呼叫 API。
