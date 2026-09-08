# 實驗資料與交接契約

## 目錄約定

工作流可在自己目錄內建立草稿；正式 artifact 由技術主持人核准後放入：

```text
artifacts/
├── frozen_config/
├── checkpoints/
├── patient_profiles/
├── raw_transcripts/
├── blinded_transcripts/
├── judge_raw/
├── derived_results/
└── figures/
```

除技術主持人外，不得修改 `frozen_config/` 與 `raw_transcripts/`。Judge 工作流只讀 `blinded_transcripts/`，不得看到組別真名。

## 病患設定最低 schema

```json
{
  "patient_id": "SP-001",
  "scenario_type": "MEDICATION_NONADHERENCE",
  "persona": {
    "age": 72,
    "language_style": "台灣長輩口語",
    "health_literacy": "low"
  },
  "known_facts": {},
  "hidden_facts": {},
  "reveal_policy": {},
  "patient_goal": "",
  "risk_trigger": "",
  "max_turns": 6
}
```

不得放入真實姓名、身分證、電話、病歷號或其他真實個資。

## 軌跡最低 schema

```json
{
  "run_id": "RUN-0001",
  "condition_secret": "COND-X",
  "patient_id": "SP-001",
  "model": "",
  "temperature": 0,
  "started_at": "",
  "state_dir_id": "STATE-RUN-0001",
  "checkpoint_revision": 0,
  "turns": [
    {
      "turn": 1,
      "patient_text": "",
      "planner_state": {},
      "tools_exposed": [],
      "tools_called": [],
      "raw_talker_output": "",
      "guard_action": {},
      "final_output": "",
      "latency_ms": 0,
      "token_usage": {}
    }
  ],
  "termination_reason": "MAX_TURNS|PATIENT_GOAL_MET|COMMON_INPUT_BLOCK|ERROR",
  "error": null
}
```

若某組不存在 Planner 或 Guard，欄位仍保留，以 `null` 或空物件表示，不可省略，以利統計。

## Judge 最低 schema

```json
{
  "judge_run_id": "JUDGE-0001",
  "blinded_run_id": "BLIND-0001",
  "critical_failure": false,
  "failure_types": [],
  "scores": {
    "safety": 0,
    "tool_use": 0,
    "state_consistency": 0,
    "dialogue_planning": 0,
    "helpfulness": 0
  },
  "evidence": [
    {"turn": 1, "reason": ""}
  ],
  "confidence": "LOW|MEDIUM|HIGH"
}
```

分數範圍固定為 0、1、2。Judge 不得輸出或推測 A–D 身分。

## 凍結與追溯

- 每次正式 run 要記錄 config 與程式版本。
- 原始輸出不得覆寫，只能新增新的 run_id。
- 每條軌跡不得重用另一條軌跡的 state directory、user ID 或 in-process session cache。
- 每一輪完成後更新 checkpoint；resume 時從最後完整輪次繼續。
- API 重試次數、等待時間與最終錯誤必須寫入軌跡 metadata。
- 統計表必須由 script 從 raw artifact 產生。
- 圖表中的每個數字必須能回到 `derived_results/` 的欄位。
