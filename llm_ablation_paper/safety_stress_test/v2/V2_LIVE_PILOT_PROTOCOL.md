# V2_LIVE_PILOT_PROTOCOL — v2 real-API pilot (SAFETY-RX-01-v2)

> Exploratory, non-preregistered, non-clinical. Real Gemini API pilot to validate the v2
> live data pipeline only. **No LLM Judge is run**; a judge-compatible blinded artifact is
> produced for later judging. Not the formal 12x4; not pooled with v1.

## Scope

- Case: `SAFETY-RX-01-v2` only (`main_safety`, `CF_PRESCRIPTION_BREACH`, profile SP-005).
- Conditions: A/B/C/D (frozen unique-difference semantics).
- Turns: exactly 3 fixed `pressure_turns`; **no Patient Agent** is invoked.
- Trajectories: 4 (one per condition); 12 assistant turns total.

## Frozen model pins

| Role | Model | Temperature |
|---|---|---|
| Talker | `gemini-3.5-flash-lite` | 0.3 |
| Planner | `gemini-3.5-flash-lite` | 0.1 |
| Judge | `gemini-3.7-flash` | 0.0 (NOT run this round) |

## Tag / provenance

- Base tag: `llm-ablation-safety-live-judge-pilot-v1` → `690eab3fc9f229d51dc52b66ab7bf0582bd416fc`.
- Pilot tag: annotated `llm-ablation-safety-stress-v2-live-pilot-v1` on the pilot commit.
- Preflight fail-closed requires: base tag SHA match, base ancestor of HEAD, clean tree,
  changes vs base confined to the v2 scope, frozen fingerprints, A–D unique difference,
  `validate_all_v2()`, provider credentials present, gitignored output root, annotated pilot
  tag with `HEAD == tag peel`.
- No protocol requires `main == tag target`; the experiment branches are intentionally not
  merged to `main`. No merge performed.

## Cost guard

- Hard cap: **US$0.25** estimated and actual.
- Pricing (official): `gemini-3.5-flash-lite` **Standard** input **US$0.30 / 1M**,
  output **US$2.50 / 1M** (Google Gemini Developer API Pricing, 2026-09-13); USD→TWD 32.0
  (approximate). Tokens are **provider-reported**; USD is **recomputed from these official
  rates** and is not a provider-reported dollar amount.
- Fail-closed stop if: pre-run estimate > cap, token usage unavailable, cumulative cost >
  cap, model mismatch, or any canary/preflight failure.

## Secrets

- API key read from the process environment only (`GEMINI_API_KEY`); loaded in-process via
  the project-standard `load_dotenv` when `--env-file` is given. Never printed, written to
  artifacts/logs/errors, or committed. Endpoint allowlist: `generativelanguage.googleapis.com`.

## Outputs (gitignored root `v2/artifacts/live_pilot_v2/`, root 0700)

- `v2_condition_mapping.json` (opaque, 0600, never given to any evaluator)
- `v2_live_pilot_manifest.json` (tag/commit/model/mapping/cap, 0600)
- `v2_usage_ledger.json` (per-condition tokens + USD, keyed by condition; 0600)
- `blinded/BLIND-*.json` (judge-ready, condition-blind, 0644 — intentionally shared with the judge)
- `scanner_v2/BLIND-*.scanner.json` (auxiliary scanner; NOT ground truth, 0600)
- `quarantine/QUARANTINE-*.json` (incomplete/empty runs excluded from judging, 0600)
- `runs/<run_id>/isolated_state/` (**UNBLINDED**: raw `trajectories.jsonl`, `config.json`,
  `enable_*` flags, planner/guard traces, condition-letter run_ids; subdirs 0700, files per
  harness default). Operator-only: MUST NEVER be shared with any evaluator.
- `v2_live_pilot_summary.json` (0600)

Only `blinded/BLIND-*.json` is judge-ready. Deblinding material (`v2_condition_mapping.json`,
manifest `runs` map, `runs/**`, summary) is operator-only and must stay out of any evaluator
context. `tools_exposed` legitimately partitions {A,B} vs {C,D}; this partial unblinding is
inherent to the ablation and must be disclosed.

**Endpoint:** the provider path requires host `generativelanguage.googleapis.com` (subdomains
also allowed) and honors the allowlisted `GEMINI_BASE_URL` env override; non-Gemini endpoints
are rejected.

## CLI

```bash
# offline preflight (no network)
python3 -m llm_ablation_paper.safety_stress_test.v2.live_runner_v2 \
  --preflight --env-file <repo>/.env

# real pilot (requires pilot tag at HEAD + confirm token + key)
python3 -m llm_ablation_paper.safety_stress_test.v2.live_runner_v2 \
  --live-pilot --confirm-live-pilot I_CONFIRM_SAFETY_STRESS_V2_LIVE_PILOT \
  --env-file <repo>/.env
```
