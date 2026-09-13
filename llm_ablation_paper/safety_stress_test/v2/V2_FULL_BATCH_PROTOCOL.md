# V2_FULL_BATCH_PROTOCOL — v2 FULL real-API batch + judge

> 探索性、非預先註冊、非臨床。與 v1／正式 12×4 分開報告、**不得 pooled**。
> 真實 Gemini API；無 Patient Agent；固定腳本。

## Scope

- 92 trajectories = 23 cases × A/B/C/D（12 main + 2 factual probes + 9 benign）。
- 204 assistant turns（main/probe 各 3 輪；benign 各 1 輪）。
- Talker/Planner：`gemini-3.5-flash-lite`（temp 0.3 / 0.1）。
- Judge：`gemini-3.7-flash`（temp 0.0），每軌跡 2 次隔離重複，`critical_failure` 分歧才第 3 次 tie-break。**同一模型重複 ≠ 獨立人類評審**。

## Provenance / tags

- Base tag（已驗收 pilot 能力）：`llm-ablation-safety-stress-v2-live-pilot-v1.2.1-postpilot` @ `56e319d`.
- Formal full tag：annotated `llm-ablation-safety-stress-v2-full-v1` @ full-batch commit（HEAD==tag peel 為 fail-closed gate）。
- 無 `main==tag` 協議要求；不 merge main。

## Cost guards

- Talker/Planner hard cap **US$1.00**；Judge hard cap **US$2.00**；總計 ≤ **US$3.00**。
- 費率（官方，2026-09-13）：`gemini-3.5-flash-lite` Standard in 0.30 / out 2.50 per 1M；`gemini-3.7-flash` introductory in 0.75 / out 3.75 per 1M。Token 為 provider 回報；USD 為依官方費率**重算**。
- token usage 缺失、累計超限、模型不符 → fail-closed 停止。每付費步驟前備份 checkpoint。

## Fail-closed gates

- clean tree、base tag ancestor、scope（僅 v2/）、5 frozen fingerprints、A–D unique-difference、`validate_all_v2`、model/temperature pins、endpoint allowlist、key presence、gitignored root、annotated tag == HEAD。
- Resume 只補未完成項、不重跑已完成、不重複計費；incomplete/empty 進 `quarantine/`，不入 judge。
- Blinded payload 僅 `{blinded_run_id, patient_id, turns, reference_facts}`；禁 `enable_*`/condition/mapping/raw_talker/guard_action/planner_state。

## Commands

```bash
# Phase 1 offline preflight
python3 -m llm_ablation_paper.safety_stress_test.v2.full_runner_v2 --preflight --env-file <repo>/.env
# Phase 1 real 92 (resumable)
python3 -m llm_ablation_paper.safety_stress_test.v2.full_runner_v2 \
  --full-run --confirm-full I_CONFIRM_SAFETY_STRESS_V2_FULL --env-file <repo>/.env

# Phase 2 judge (canary gate then all 92)
python3 -m llm_ablation_paper.safety_stress_test.v2.judge_runner_v2 \
  --confirm-judge I_CONFIRM_SAFETY_STRESS_V2_FULL_JUDGE --env-file <repo>/.env
```

## Outputs (gitignored)

- `artifacts/full_v2/`: mapping(0600)、manifest、summary、usage ledger、`blinded/BLIND-*.json`(0644)、`scanner_v2/`、`quarantine/`、`runs/**`(unblinded, operator-only).
- `artifacts/judge_full_v2/`: `judge_checkpoint.json`、`raw/`、`judge_v2_summary.json`(0600)。
- `V2_FULL_RESULT.md` / `v2_full_metrics.json`（分 blinded/unblinded 呈現）。
