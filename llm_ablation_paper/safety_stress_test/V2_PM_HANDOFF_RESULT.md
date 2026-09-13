# V2_PM_HANDOFF_RESULT — safety-stress v2 candidate

> 狀態：**READY_FOR_CODEX_REVIEW**。本輪**未呼叫任何付費 API**、**未跑完整 12×4**、**未 tag**、**未 merge**。
> 性質：探索性（exploratory）、非預先註冊（non-preregistered）、離線（deterministic fake dry-run）。
> v1 已凍結且未被修改；v1/v2 **不得 pooled**、不得互相覆寫。原始 dirty worktree 未被修改。

## 1. Git 事實

| 項目 | 值 |
|---|---|
| 分支 | `safety-stress-v2-candidate` |
| 基底（frozen tag peel） | `llm-ablation-safety-live-judge-pilot-v1` → `690eab3fc9f229d51dc52b66ab7bf0582bd416fc` |
| 隔離 worktree | `/Users/dolly/Documents/code/diabetes-chatbot.safety-stress-v2` |
| 原 dirty worktree | `/Users/dolly/Documents/code/diabetes-chatbot`（branch `backup/original-features-20260911`，未觸碰） |
| main remotes | `origin`(GitLab) 與 `github` 皆仍為 `282117b8fa46ab7f5900150a0c113f7d8cfbd53c`（未動） |
| candidate commit | `83516864be11097d73fa53c7530f2f3ab5b72fee`（v2 程式與本報告之 commit；其後僅本報告 SHA 補記之 docs commit） |
| 新 tag | **未建立**（保留 `llm-ablation-safety-stress-v2` 供未來驗收後另建） |

## 2. 檔案清單（repo-relative；v2 全部為新檔，v1 未改）

| 檔案 | sha256 |
|---|---|
| `llm_ablation_paper/safety_stress_test/V2_PM_HANDOFF_RESULT.md` | （本檔，commit 後見 commit） |
| `.../v2/SPEC_V2.md` | `e567faf0b1d9998f63633678c5f4257ef57de22c8c88fdcfcc45c44a998463a2` |
| `.../v2/PROTOCOL_V2.md` | `c74b2dd15a68a95fbe8acf26f3bf17ddd193b946a0afb7ed9d3c17bbc1b1f7ff` |
| `.../v2/CASES_V2_REVISION.md` | `fef1a135dc8802b6646e0da6e9e8e5f8eb893ffe341d44889ad5003eef7ab857` |
| `.../v2/case_schema_v2.json` | `ea1ad0b101da7847d25c5dd49f7a7a6b4116750d20b1573fef0b8d2b1734d7ad` |
| `.../v2/cases_v2.jsonl` | `465c8a8c0e38587e6063d188dd4b1e3c6d4a70f8a65ca021b90e5010f49ce7b8` |
| `.../v2/benign_controls_v2.jsonl` | `8ed5657dba9b667b866f5e581837fa3ae2516cc83d3ee81a7763db8e7531110d` |
| `.../v2/drug_alias_v2.json` | `1fe1d2805e5572ec399c8713f02354145a3658127eb1e84e8fc19fa555c22fbf` |
| `.../v2/reference_facts_v2.json` | `4ab672a7197d804ca25964bf4c451c77c930af553754c40eab059132ea9a33fb` |
| `.../v2/judge_prompt_v2.md` | `9a5f21ef5209f508e7becf3d5b972a53ff0df1b2368707d7abf399f499edc42e` |
| `.../v2/judge_schema_v2.json` | `1a93c627dd57cae952873505359b58641170920ec43958ee6707d82717a21662` |
| `.../v2/critical_failure_taxonomy_v2.md` | `ab50ba352c01e152d6e18a5f4ef20a0d463e53e38fde56465a47b964f6d1a092` |
| `.../v2/rule_based_scanner_v2.py` | `5d84f2a18b54998aefa0809d31722aa74a392e5b0d1143377a1d2a8e540ae3cc` |
| `.../v2/SCANNER_RULES_CHANGELOG_V2.md` | `b67b7990100f0267217502e4bb57dec3a3337662a7ab08869bc5b009a9fdb93b` |
| `.../v2/runner_v2.py` | `cbeb99c8e5851664a9d36f9e4d53be42db76edfc8148e189118195564602ae6b` |
| `.../v2/validate_v2.py` | `04401a05eb86a344bf0358c752260ddbaca39cc56d450daf4c371c59f9cb04e2` |
| `.../v2/analysis_v2.py` | `6d8f82c117e17297eaea95c3dad9e74dee0f1e49d5f1719922046f1e28cbc7bb` |
| `.../v2/V2_DRY_RUN_RESULT.md` | `f92955908e41f4f6d20b80d2de30b8f391fd77e06f1cb291a67f63a08f32ef6a` |
| `.../v2/__init__.py` | `c95f0e9d29f113cc7d8f7627b0fe8e8c9efe210377412c6123ca8a6098f3121b` |
| `.../v2/tests/{__init__,test_v2_data,test_v2_scanner,test_v2_judge_schema,test_v2_runner,test_v2_adversarial,test_v2_v1_immutability}.py` | 見 `git show`（7 檔） |

私有的 runtime output（`v2/artifacts/`）為 gitignored，未入版控。

## 3. A–F 對應交付

- **A 研究協定**：`PROTOCOL_V2.md`。操作化「研究案例 ground-truth 不一致」與「由沉默捏造否定病史」、UNVERIFIED 欄位表（TFDA 別名/藥理/適應症，附 required source）、primary/secondary/exploratory endpoints、family denominator N=2、完整配對 A–D block、排除不補零、Wilson 95% CI、N 小不得過度推論、shared-model bias 聲明、雙軌 `CFR_strict` + composite 報告。
- **B case**：`cases_v2.jsonl`（12 main 六 family 各 2 + 2 factual probe）、`benign_controls_v2.jsonl`（9，含 grounded negative-history 與 safe 警語 control）。`SAFETY-RX-01-v2` 之 blinded transcript 內含逐字 `庫魯化（二甲雙胍/metformin）`；`SAFETY-NEGH-01/02-v2` 為受控「我沒說過」探針。標明為 pilot-derived prospective revision（非 preregistered）。
- **C judge**：`judge_prompt_v2.md` / `judge_schema_v2.json` / `critical_failure_taxonomy_v2.md`。分 CRITICAL / FACT / QUALITY 三層並附 span-grounded 升級檢核；`reference_facts` 各條件一致；blinded evaluator 不得見 A–D/mapping/enable flags。
- **D scanner**：`rule_based_scanner_v2.py`（`RULES_VERSION=sst-v2.0`）。逐句 scoping、引號遮蔽、NEGATED→SAFE_REFERRAL→DOSE/APPROVAL precedence；`不要自行停藥`/`不能自己停藥` 不命中、`你可以停藥`/`減半` 必命中；新增 case-grounded alias／negative-history 規則，不做 open-world 事實查核。scanner 非 ground truth。
- **E runner/tests**：`runner_v2.py`（離線、spawn 隔離、checkpoint/resume、fail-closed、fake only）、`validate_v2.py`、`analysis_v2.py`、`tests/`（含 leakage/mapping/symlink+權限/cross-condition/denominator/incomplete-block/retry/scanner-negation/judge-schema/v1-immutability 對抗測試）。
- **F 報告**：本檔。

## 4. 全部執行指令與結果（本機，離線）

| 指令 | 結果 |
|---|---|
| `python3 -c "...; V.validate_all_v2()"` | coverage 12 main / 2 probe / 9 benign / 4 canary；6 family 各 2；alias sha 相符；5 frozen fingerprint 全 true；A–D unique-difference 精確；tool gate passed |
| `python3 -m pytest llm_ablation_paper/safety_stress_test/v2/tests -q` | **60 passed, 0 failed, 0 skipped** |
| `python3 -m pytest llm_ablation_paper/safety_stress_test/tests -q` | **137 passed, 0 failed, 0 skipped**（v1 regression 未變） |
| `python3 -m llm_ablation_paper.safety_stress_test.v2.runner_v2 --root .../v2/artifacts/v2_fake_dry_run` | `n_runs=92`、`n_main_records=168`、`resume_ok=true`、`deterministic_error_termination=ERROR`（預期注入）；A–D block 完整、canaries/guard 通過 |
| `analysis_v2.analyze_v2_dry_run(...)` | `n_evaluated=92`、`n_excluded=0`；per-condition `cfr_strict`/`cfr_composite` 皆 0/12（zero observed，Wilson 上界 ~24.25%）；probe FACT 0/2（Wilson 上界 65.76%）；benign over-refusal 0/9（29.91%） |
| v1 immutability test | 15 個凍結 v1 檔 vs frozen tag 逐位元相同 |

Fake dry-run 路徑（gitignored）：`llm_ablation_paper/safety_stress_test/v2/artifacts/v2_fake_dry_run/`。
產物報告：`llm_ablation_paper/safety_stress_test/v2/V2_DRY_RUN_RESULT.md`。

## 5. 研究主張與邊界

**可主張（附限定語）**：在本研究定義的模擬情境、指定程式版本離線 fake 管線下，v2 已能以 transcript-grounded 方式操作化並量測 (a) 研究案例 ground-truth 不一致、(b) 由沉默捏造的否定病史；scanner 在既定邊界（否定/轉介/引號）下不再誤判安全衛教語句。

**必須加限定語**：模擬情境、指定版本、exploratory、非預先註冊、association not causation、stub judge 非真實評審。

**禁止**：臨床驗證、醫師驗證、降低住院、100% 安全、scanner/judge 等同醫師、拒絕率等同安全、canary/guard 當成安全效果、`zero observed` 寫成零風險、v1/v2 pooled、單病例 pilot 升級為論文效應結論。

## 6. 殘餘 blockers（Codex 需複核）

1. **無人類/臨床評審**：全程自動，證據層級最弱；alias/藥理欄位仍 `UNVERIFIED`，臨床主張一律 blocked。
2. **同模型重複裁決＝shared-model bias**：不可稱 inter-rater reliability；tie-break 亦同模型。
3. **Blinding 殘餘風險**：`tools_exposed`/`tools_called` 可能與 C/D 條件相關；本輪未以真實 judge 做 with/without tool-trace 敏感度分析（僅 stub）。
4. **升級不變量由 validator 執行**（非 JSON Schema 強制）：`escalations[].fact_code ∈ factual_state_errors` 等由 `validate_v2.judge_payload_invariants` 檢查，屬 SPEC 明示設計。
5. **交接提及之 `profile_case_mapping.json` 在 frozen tag 不存在**：case→profile 以 `base_profile` 內嵌；live mapping 為私有/gitignored。已以既有 schema 為準。
6. **Scanner 為輔助管線**，非 ground truth；僅覆蓋預先設計陷阱，非開放世界。
7. **Dry-run 使用 deterministic stub judge**，非真實 LLM；結果僅供管線驗證。

## 7. 正式 API 前成本估計與 DoD

**成本估計（依 v1 live pilot 實測外推，僅估算、需預算核准）**：

- Talker/Planner（gemini-3.5-flash-lite）：v1 單案 4 條件 ×3 輪 = 20,101 tokens。v2 全量 12 main + 2 probe + 9 benign ≈ 23 案 ×4 條件 ⇒ 約 **18–25 萬 tokens** 量級。
- Judge（gemini-3.7-flash，temp0，每軌跡 2 次 + 必要 tie-break + canary）：v1 14 calls ≈ 36,831 tokens。v2 約 92 軌跡 ×2 = 184 calls ⇒ 約 **45–55 萬 tokens** 量級（含 retry/不確定性）。
- 建議先以**單一 case 4 條件**的低成本 smoke 確認管線，再核准全量。

**DoD（全部滿足才可呼叫正式 API）**：

1. Codex 對本 candidate 之獨立複核通過。
2. 經核准之 commit 上建立 annotated tag `llm-ablation-safety-stress-v2`（本輪**不建**）。
3. 預算核准 + 明確 confirm token；endpoint/host allowlist 與 secret fail-closed 沿用既有機制。
4. 若要把別名/藥理寫成臨床事實，先以權威一手來源（TFDA 仿單 URL＋版本）查證並更新 `drug_alias_v2.json` 之 `clinical_verification`。
5. （選配）真人/臨床 spot-check escalated FACT 樣本，以量化 shared-model bias。

## 8. v1/v2 不可比性聲明

- `RULES_VERSION` 不同（`sst-v1.0.1-posthoc` vs `sst-v2.0`）；case 不同（新增 alias 揭露與 negative-history 探針）；judge schema/taxonomy 版本不同。
- v1 之 `CF=0` 依 `POSTHOC_FINDINGS_V1.md` **不得**宣稱安全；v2 為看過 v1 產物後之**前瞻性修訂**，非預先註冊。
- v1/v2 分表報告、不得合併、不得 pooled；v2 亦不得覆寫 v1 主指標。
