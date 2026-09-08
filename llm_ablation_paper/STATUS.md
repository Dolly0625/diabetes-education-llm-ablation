# 五人協作狀態板

更新規則：每位成員至少在每日結束前更新一次。狀態只能使用 `NOT_STARTED`、`IN_PROGRESS`、`REVIEW`、`APPROVED`、`BLOCKED`。

| 工作流 | 負責人 | 狀態 | 當前交付 | 下一步 | Blocker |
|---|---|---|---|---|---|
| 1 技術主持 | 待指派 | APPROVED | Harness、A–D config、狀態隔離、checkpoint/resume、盲測匯出與離線 dry-run 已通過 | 凍結正式模型與版本；整合審核各 WS | 正式模型設定尚未凍結 |
| 2 A／B | 待指派 | NOT_STARTED | 直接接入已核准 Harness，建立 A/B config 與事件驗收 | 依 `member_prompts/member_2_ablation_ab.md` 開工 | 無 |
| 3 C／D | 待指派 | NOT_STARTED | 直接接入已核准 Harness，建立 C/D logging 與 fault injection | 依 `member_prompts/member_3_ablation_cd.md` 開工 | 無 |
| 4 模擬病患 | 待指派 | IN_PROGRESS | WS4-A：Patient prompt、12 profiles、schema 與 72 項測試已通過 | WS4-B：只建 roleplay runner、checkpoint/resume/retry 與 dry-run | 正式模型尚未凍結，不影響離線開發 |
| 5 Judge／分析 | 待指派 | NOT_STARTED | Judge rubric、schema、canary、統計程式與結果樣板 | 依 `member_prompts/member_5_judge_analysis.md` 開工 | 正式 transcripts 尚未產生 |

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
- `RESEARCH_PROTOCOL.md` 的 Talker、Patient Agent、Judge 模型、temperature、prompt 版本、tool schema 版本與正式 commit 尚未凍結。
- 在上述設定凍結前，各組可建立程式、測試與 fake-data dry-run，但禁止啟動正式 12×4 批次或宣稱模型實驗結果。
