# Workstream 1 接手與第三次驗收清單

## WS1 Final Freeze 狀態（2026-09-11）

- 狀態：`APPROVED`（已以 `llm-ablation-ws1-freeze-v1` 完成 final freeze）。
- 原功能備份：`backup/original-features-20260911`（完整保存原 working tree 29 項修改）。
- 核准 runtime commit：`a61c32a93c24a3e698ee266246da30103da5d38a`（凍結正式 config：Talker `gemini-3.5-flash-lite`/0.3、Planner 0.1、Patient Agent `gemini-2.5-flash-lite`/0.3、max turns 6、seed 42、Planner request timeout 30s、subprocess timeout 120s；第二次 Talker 改用凍結 temperature；同步 planner persist；單病患 formal pilot 入口；fail-closed execution envelope 閘門）。
- Talker 指紋：`talker_base_prompt_sha256` 僅涵蓋 `NURSE_SYSTEM_PROMPT`；`talker_prompt_template_bundle_sha256` 另涵蓋 `build_nurse_system_prompt` 的注入模板來源，因此 base SHA 不等於完整模板 SHA。`patient_context` 為輸入資料，不納入任何指紋。
- 指紋與正式 config 固定值記錄於 `FREEZE_CANDIDATE_MANIFEST.json`，並由 `tests/test_freeze_candidate.py` 與 `tests/test_formal_freeze_readiness.py` 精確比對（非僅長度檢查）。
- `RESEARCH_PROTOCOL.md` 已回填 prompt／tool schema／commit lineage／planner timeout／subprocess timeout；opaque mapping 尚未產生（由技術主持於盲測匯出前私下產生，WS5 不得接觸）。
- 正式 12×4：`BLOCKED`（待 WS2／WS3／WS5 完成與 opaque mapping 產生）。

## 目前判定

狀態為 `APPROVED`。WS1 核心、Harness、A–D config、測試與 execution envelope 閘門已通過完整驗證並完成 final freeze。正式 12×4 實驗維持 `BLOCKED`，禁止提前執行或呼叫付費 API。

## 已驗證可保留

- A 使用 neutral planner；B／C／D 可走 LLM Planner 注入路徑。
- A／B 暴露 canonical full tools；C／D 共用動態 gate。
- 相同 raw breach 下，只有 D 會由 Output Guard 覆寫。
- Harness 與 production handler 已改為呼叫 `diabetes_chatbot/server/ablation_core.py` 共用核心。
- tool-call 執行、兩輪 history、基本 checkpoint 與 contract adapter 已有測試骨架。
- 指定的 72 項測試於 2026-09-07 可重現通過。
- 公平的 1 fake patient × A／B／C／D × 2 turns dry run 可重現。

## 交接前必修問題

1. `to_contract_trajectory()` 必須從 turn record 取得真正的 `patient_id`；目前會錯把第一句 `patient_text` 當 ID。
2. `condition_secret` 不得直接輸出 A／B／C／D；需接受凍結的 opaque condition mapping，且 blinded artifact 不得洩漏主要 flags。
3. `run_trajectory_subprocess()` 目前忽略傳入的真實 client，實際只建立 fake client。正式 child process 必須透過可序列化 provider config／factory 建立 client；API key 只從 child 環境讀取。
4. state directory 已有相同 run ID 時，`resume=False` 仍可能放行。凡已有 config、trajectory 或 checkpoint 都應拒絕；只有 `resume=True` 且 run／condition／patient 完全一致時可續跑。
5. pending-card 提前返回路徑必須遵守 A–D flags；A／B／C 不得執行 Output Guard。`PENDING_CARD_DELIVERY*` 應是 event，不得成為研究協議以外的 termination reason。
6. retry 只處理 timeout、429、暫時網路錯誤與可重試 5xx，並記錄 attempt/backoff/error metadata；模型 usage 應記錄 tokens，無資料時填 `null`。
7. `AblationConfig` 必須驗證 A／B／C／D 的三個主要 flags 完全符合固定 mapping；run ID 與 config provenance 必須一致；非最後一輪不得誤標 `MAX_TURNS`。

## 必加測試

- contract `patient_id` 精確相等。
- blinded artifact 不含 A／B／C／D 與主要開關名稱。
- subprocess 確實呼叫 provider/client factory，不偷換 fake。
- 相同 run ID 且 `resume=False` 必須拒絕。
- A／B／C／D pending-card 路徑遵守 Output Guard 設定。
- retry 分類、attempt/backoff metadata 與 token usage。
- 非法 condition/flag 組合與 run ID 不一致會失敗。

## 測試注意事項

直接在 repository 根目錄執行完整 `pytest` 目前會因多個同名 `tests` package 發生 collection collision；`diabetes_chatbot/tests/test_tool.py` 還會在 import 階段呼叫外部 API。不得把這兩項誤報為 Harness regression，也不得宣稱完整 repository suite 已通過。請使用明確測試路徑，並將測試基礎設施限制記入回報。

## 完成回報

只需回報上述七項的修改檔案、測試名稱與結果、更新後 dry-run artifact，以及仍存在的風險。不要執行 12 位病患正式批次，不要建立 Patient Agent、Judge 或統計分析。
