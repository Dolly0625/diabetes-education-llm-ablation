# Live Judge Pilot RESULT 模板

> 由 `live_judge_pilot.py` 執行後自動產生 `JUDGE_RESULT.md`（0600）；本檔為欄位模板。

## 執行

- execution_mode：`safety_stress_live_judge`
- source live tag / SHA：`llm-ablation-safety-live-pilot-v1` / `b63f9997f00cdc5569950d5f5c88e7f0309b7b3e`
- judge model / temperature：`gemini-3.7-flash` / `0.0`
- source block sha256（首次錨定，非事前凍結）：`<block_sha256>`
- mapping sha256（僅哈希，不含 mapping 值）：`<mapping_sha256>`
- canary：PASS（1 PASS + 5 FAIL 全數符合）
- n_judged：4

## 每軌跡

| condition | blinded_run_id | critical_failure | failure_types | n_runs | total_tokens |
|---|---|---|---|---|---|
| A | BLIND-________ | | | | |
| B | BLIND-________ | | | | |
| C | BLIND-________ | | | | |
| D | BLIND-________ | | | | |

## 邊界

- 探索性、非預先註冊、單病例；association not causation。
- Judge 非醫師；scanner 非 ground truth；canary 非準確率。
- zero observed 不代表零風險；不得與正式 12×4 混合；不得改寫 frozen v1 主指標。
