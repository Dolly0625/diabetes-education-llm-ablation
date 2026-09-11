# 五人協作狀態板

更新規則：每位成員至少在每日結束前更新一次。狀態只能使用 `NOT_STARTED`、`IN_PROGRESS`、`REVIEW`、`APPROVED`、`BLOCKED`。

| 工作流 | 負責人 | 狀態 | 當前交付 | 下一步 | Blocker |
|---|---|---|---|---|---|
| 1 技術主持 | 待指派 | REVIEW | Harness、A–D config 與 formal-readiness 已通過；P0-1 Stage 2 freeze candidate（`ws1-freeze-candidate`）已備：核心實驗功能、share-free、prompt／tool fingerprint 已計算，待審 | 完成 candidate 審核與 final freeze（prompt／tool schema／commit／timeout／opaque mapping） | 正式指紋尚未 final freeze；WS2/WS3/WS5 尚未完成 |
| 2 A／B | 待指派 | NOT_STARTED | 直接接入已核准 Harness，建立 A/B config 與事件驗收 | 依 `member_prompts/member_2_ablation_ab.md` 開工 | 無 |
| 3 C／D | 待指派 | NOT_STARTED | 直接接入已核准 Harness，建立 C/D logging 與 fault injection | 依 `member_prompts/member_3_ablation_cd.md` 開工 | 無 |
| 4 模擬病患 | 待指派 | APPROVED | WS4-A profiles/schema/驗證已通過；WS4-B runner、checkpoint/resume/retry、逐輪正式路徑 fake dry-run 與 Input Guard canary 已完成並經 WS1 驗收合併（WS4 目錄 139 passed） | 待整體實驗指紋凍結後由 WS1 執行正式 12×4 批次 | P0-1 核心 production 髒檔未審核；正式指紋尚未凍結；WS2/WS3/WS5 尚未完成 |
| 5 Judge／分析 | 待指派 | NOT_STARTED | Judge rubric、schema、canary、統計程式與結果樣板 | 依 `member_prompts/member_5_judge_analysis.md` 開工 | 正式 transcripts 尚未產生 |

> 本輪 WS1／WS4 技術判定：`APPROVED`（formal-readiness 修復已驗收並合併）。P0-1 Stage 2：freeze candidate `REVIEW`（待審，不得宣稱 final frozen）。正式 12×4 實驗狀態：`BLOCKED`（1. candidate 尚未 final freeze；2. 正式 prompt／tool schema／commit／timeout／opaque mapping 指紋尚未凍結；3. WS2、WS3、WS5 尚未完成）。

## 里程碑

| 里程碑 | 截止 | 狀態 | 驗收人 |
|---|---|---|---|
| M1 A–D 規格凍結 | Day 1 中午 | REVIEW | 技術主持人 |
| M2 工程管線 dry run | Day 1 晚上 | APPROVED | 技術主持人 |
| M3 raw transcripts 凍結 | Day 2 晚上 | NOT_STARTED | 技術主持人 |
| M4 Judge 與統計凍結 | Day 3 中午 | NOT_STARTED | 技術主持人＋分析負責人 |
| M5 各節初稿完成 | Day 3 晚上 | NOT_STARTED | 論文整合者 |
| M6 投稿 QA | Day 4 | NOT_STARTED | 全體 |

## 決策紀錄

| 時間 | 決策 | 原因 | 決策人 |
|---|---|---|---|
| 2026-09-07 | Stage 2 採用 deterministic fake model 完成離線測試與 dry run | 正式模型可設定不寫死，避免付費 API 阻塞 | 技術主持 |
| 2026-09-07 | AblationConfig 映射凍結：A OFF-OFF-OFF / B ON-OFF-OFF / C ON-ON-OFF / D ON-ON-ON，三輔助強制 OFF | 滿足唯一差異原則 | Sisyphus |
| 2026-09-07 | Harness 獨立於 `workstream_1_technical_lead/harness/`，production 僅加 optional `ablation_config` injection | 向後相容，不複製四份 handlers.py | Sisyphus |
| 2026-09-08 | 凍結模型：Talker/Planner=`gemini-3.5-flash-lite`、Patient Agent=`gemini-2.5-flash-lite`、Judge=`gemini-3.7-flash`；角色 temperature 分別為 0.3/0.1/0.3/0.0，max turns=6，seed=42 | 維持既有受測系統，同時以低成本模型生成病患對話並用不同、較強模型盲評 | 技術主持 |
| 2026-09-10 | 驗收並合併 `ws4-runner`（`e9d0ac7`）至 `main`：WS4-B runner、checkpoint/resume/retry、fake dry-run | 離線測試 84 passed（含來源追溯 test_01–test_04，以固定上游 CSV SHA-256 驗證）；無越界修改；獨立稽核判定部分通過且無硬性 blocker | 技術主持 |
| 2026-09-10 | 建立 `ws1-formal-readiness` 分支完成 WS1／WS4 正式就緒強化；判定 `READY_FOR_REVIEW` | 修正 provider 金鑰／endpoint 配對（Gemini-only）、統一 fake 與正式逐輪路徑、retry/timeout/research_patient_id/canary/CSV fail-closed，並重新產生 checked-in artifact；正式實驗維持 BLOCKED（P0-1） | Sisyphus |
| 2026-09-10 | 合併 `ws1-formal-readiness`（`a7f4b72`）至 `main`；WS1／WS4 formal-readiness 判定 `APPROVED` | 驗收實測 WS1 59 passed／WS4 139 passed／backward 5 passed／validator PASS；canary `COMMON_INPUT_BLOCK`；無越界修改；正式 12×4 維持 `BLOCKED` | 技術主持 |
| 2026-09-11 | 建立 `backup/original-features-20260911` 完整備份原功能（29 項），並自 `main@435c91f` 建立 `ws1-freeze-candidate`（僅核心實驗功能、排除 Demo／醫護／分享、share-free）；判定 `REVIEW` | 依 P0-1 Stage 2：先保護原功能再建可重現 freeze candidate；正式 12×4 維持 `BLOCKED` | 技術主持 |

## Workstream 1 交付清單（2026-09-07）

### 修改與新增檔案
- 新增 `llm_ablation_paper/workstream_1_technical_lead/harness/config.py` — frozen AblationConfig + for_condition(A-D) + SHA helper
- 新增 `llm_ablation_paper/workstream_1_technical_lead/harness/isolation.py` — make_isolated_state_dir / clear_session_cache / get_patient_file_for_state
- 新增 `llm_ablation_paper/workstream_1_technical_lead/harness/runner.py` — run_ablation_turn / run_trajectory / run_trajectory_subprocess / neutral_planner_state / get_canonical_tool_snapshot
- 新增 `llm_ablation_paper/workstream_1_technical_lead/harness/__init__.py` — 公開匯出
- 新增 `llm_ablation_paper/workstream_1_technical_lead/harness/dry_run.py` + `__main__.py` + `scripts/dry_run.py` — 離線 dry run
- 微改 `diabetes_chatbot/server/handlers.py` (+62/-25) — 加入 `ablation_config: Optional[AblationConfig]=None` 選擇性參數，預設行為不變
- 新增 `diabetes_chatbot/tests/test_ablation_backward_compat.py` — 5 測試證明向後相容
- 新增 `llm_ablation_paper/workstream_1_technical_lead/tests/test_ablation_harness.py` — 14 邏輯/27 參數化測試
- 產生 `llm_ablation_paper/artifacts/workstream_1/DRY-*/{config.json,tool_snapshot.json,trajectories.jsonl,checkpoints/,logs/,summary.json}` + `dry_run_summary.json`

### 測試指令與結果
- `python3 -m pytest llm_ablation_paper/workstream_1_technical_lead/tests/test_ablation_harness.py -v` — 27 passed
- `python3 -m pytest diabetes_chatbot/tests/test_ablation_backward_compat.py -v` — 5 passed
- `python3 -m pytest diabetes_chatbot/tests/test_clinical_full_alignment.py -k "not live" -q` — 13 passed
- 全部未呼叫付費 API，使用 MagicMock FakeClient

### Dry-run
- 指令：`python3 -m llm_ablation_paper.workstream_1_technical_lead.harness.dry_run`
- 病患：SP-DRY-001，Turn0「吃糙米飯配煎魚 血糖135」/ Turn1「庫魯化肚子脹想停藥」
- 輸出：`llm_ablation_paper/artifacts/workstream_1/DRY-{A,B,C,D}-20260907T155514-*/`
- 驗證：A planner False / BCD True；A/B 兩輪皆 full tools；C/D diet 首輪隱藏、藥物次輪僅 search；D 次輪 raw `少吃一顆庫魯化` 被 Output Guard 覆寫為 `【臨床安全提醒】`，C 不覆寫

### 尚未解決風險
- `RESEARCH_PROTOCOL.md` 的模型、各角色 temperature、max turns 與 seed 已凍結；Talker/Planner prompt 版本、tool schema 版本與正式 commit 尚未凍結。
- 在完整實驗指紋凍結前，各組可建立程式、測試與 fake-data dry-run，但禁止啟動正式 12×4 批次或宣稱模型實驗結果。
