# 真實 Gemini 低成本安全壓力 Pilot 協定（LIVE_PILOT_PROTOCOL）

> 性質：探索性、非預先註冊、低成本 pilot。**不是**正式 12×4、**不是**論文結果、**不是**臨床驗證。
> 目的：僅驗證真模型的**資料管線**能跑通（1 案 × A/B/C/D × 3 輪）；**不使用 LLM Judge**，rule scanner **不是**真實評審。

## 1. 範圍（硬性）

- 僅允許 **1 個** allow-list 安全案例：`SAFETY-RX-01`。
- 僅 **A／B／C／D × 固定 3 輪**腳本（`cases.jsonl` 之 `pressure_turns`），**不啟動完整 12×4**。
- 不做 Judge、不做統計推論、不產生任何安全結論。

## 2. 成本預估

- Talker assistant turns：最多 4 條件 × 3 輪 = **12**。
- Planner calls：B／C／D 每輪最多 1 次 → 最多 **9**。
- 另可能有工具呼叫造成之次輪 talker 呼叫（依系統行為）。
- 屬低成本 pilot；模型與 temperature 沿用凍結值，不可於 CLI 調整。

## 3. 凍結 tag 與閘門（final gate）

- 常數：`LIVE_PILOT_TAG_NAME = "llm-ablation-safety-live-pilot-v1"`（本協定先固定名稱）。
- **該 annotated tag 於程式完成且 Codex 驗收後才建立**；在此之前：
  - `--preflight` 誠實回報 `preflight="BLOCKED"`, `reason="NOT_FROZEN"`（exit code 2），**不假裝 ready**。
  - `--live-pilot` 直接 fail-closed。
- `--live-pilot` 啟動前必須同時滿足：
  1. `current HEAD == LIVE_PILOT_TAG_NAME peeled SHA`；
  2. `llm-ablation-safety-stress-v1` 為 HEAD 的祖先；
  3. `llm-ablation-safety-stress-v1` 之 peeled SHA **精確等於** `f5fc9b6a8746f934e30bdb2fe3f866c0a631e9ac`（hard gate；防止本地 tag 被移動）；
  4. 工作樹乾淨；
  5. 相對 stress tag 之變更全部落在 `llm_ablation_paper/safety_stress_test/`；
  6. 五項 frozen fingerprint 一致、case/schema 通過、A–D 唯一差異、tool gate 可達、provider 就緒。
- 未滿足任一 → fail-closed，於任何 API/subprocess 前中止。

## 4. 身分與確認

- 顯式確認字串：`I_CONFIRM_SAFETY_STRESS_LIVE_PILOT`（`--confirm-live-pilot`）。
- 缺省或錯誤 → 在任何 API/subprocess 前 fail-closed。

## 5. Provider 與金鑰

- 僅 `provider="gemini"`；只從環境變數 `GEMINI_API_KEY` 讀取。
- **不接受** CLI／`provider_config` 內的 secret；不得傳入 CLI key、不得寫入 argv／log／exception／artifact／summary。
- 非 Gemini provider 或非 Gemini endpoint → 拒絕。
- 模型名稱與 temperature **只能**來自 frozen formal config（`gemini-3.5-flash-lite` / talker 0.3 / planner 0.1）；CLI 無 `--model/--temperature` 旗標。

## 6. 隔離、續跑與輸出

- 每條件獨立 `run_id`／`user_id`／`state_dir`；checkpoint/resume、timeout、retry 沿用 WS1 harness。
- subprocess timeout 固定取自 `formal_runtime_spec()["subprocess_timeout_seconds"]`；CLI **不得**提供 `--timeout`（測試僅可透過明確 test-only 參數縮短）。
- 輸出僅允許寫入使用者指定且 **gitignored** 的 live root（預設 `safety_stress_test/artifacts/live_pilot/`）；private root 權限 0700。
- 不得寫入 `diabetes_chatbot/`、`diabetes-rag/`、`.env`、frozen artifacts/results。

## 6A. Pilot manifest 與 resume

- 首次執行在任何 run 之前，先原子落盤：
  - `condition_mapping.json`（0600）；
  - `pilot_manifest.json`（0600）：`case_id`、`stress_tag_sha`、`live_tag_sha`、`commit`、`mapping_sha256`、`runs{ A/B/C/D → 固定 run_id }`、`max_turns`。
- `--resume` 僅允許載入**既有** 0600 mapping 與 manifest，並驗證：
  1. case／stress tag／commit／live tag 與當前一致；
  2. `mapping_sha256` 與實際 mapping 一致；
  3. manifest 恰含 A/B/C/D 四個 run_id。
  - 已完成組（termination ∈ `MAX_TURNS`／`PATIENT_GOAL_MET`）跳過；
  - 未完成組以**相同** run_id／state_dir、`resume=True` 續跑。
  - **禁止**重新生成 mapping 或 run_id、禁止覆寫。
- 非 resume 遇到已初始化的 root（mapping／manifest／summary 已存在）→ fail-closed。
- resume 後 blinded export 與 summary 仍須恰有 A/B/C/D 各一次；任何不完整 → `completed=false`。

## 7. 盲化與 mapping

- 本次 pilot 產生**私有 opaque mapping**（`COND-<hex>`），寫入 `condition_mapping.json`，權限 **0600**，不進公開 transcript。
- 公開輸出之 blinded artifact 為**去識別 judge-ready payload**（`build_judge_payload`），僅含 `blinded_run_id / patient_id / turns{turn, patient_text, tools_exposed, tools_called, final_output}`；此為刻意設計，因 frozen `to_blinded_contract_trajectory` 仍保留 opaque secret 與內部欄位。
- 匯出後掃描：不得含 A–D、`enable_*`、`condition_secret`、`raw_talker`、`guard_action`、`planner_state`、原始 run_id、mapping 值。

## 8. Summary 契約

- 記錄：`execution_mode`、tag／commit、model／temperature、`case_id`、每條件 `termination_reason`／`n_turns`／`token_usage`（provider 有回傳才記）／technical error、`mapping_mode`／`mapping_sha256`（不含 mapping 值）、`provider`、`live_api`。
- **不得**記錄金鑰。
- 完成規則：**任一 A–D 為 `ERROR`／`COMMON_INPUT_BLOCK`／`INCOMPLETE`（非 `MAX_TURNS`／`PATIENT_GOAL_MET`）→ `completed=false`**，且不得標記完成。

## 9. CLI

```bash
# 離線 preflight（不呼叫 API；未建立 live tag 時回報 BLOCKED/NOT_FROZEN）
python -m llm_ablation_paper.safety_stress_test.live_runner --preflight --case-id SAFETY-RX-01

# 真實 pilot（需 live tag 已建立且 HEAD==其 peeled SHA）
python -m llm_ablation_paper.safety_stress_test.live_runner \
  --live-pilot --case-id SAFETY-RX-01 \
  --confirm-live-pilot I_CONFIRM_SAFETY_STRESS_LIVE_PILOT

# 中斷後續跑（載入既有 0600 mapping+manifest；同 run_id 續跑未完成組）
python -m llm_ablation_paper.safety_stress_test.live_runner \
  --live-pilot --resume --case-id SAFETY-RX-01 \
  --confirm-live-pilot I_CONFIRM_SAFETY_STRESS_LIVE_PILOT
```

## 10. 主張邊界

- 僅得表述「在指定模型與版本下的模擬情境、單一案例、固定腳本之資料管線觀察」。
- 禁止：臨床驗證、醫師驗證、降低住院、100% 安全、stub/scanner 等同醫師、拒絕率等同安全、canary／guard-reachability 當成安全效果、zero observed 寫成無風險、與正式 12×4 混合。
- scanner 僅為管線規則，**不是**真實評審；本 pilot 不使用 LLM Judge。
