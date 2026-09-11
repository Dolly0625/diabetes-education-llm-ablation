# Workstream 3：WS1 Harness 接入與整合說明

- **基準 Tag**：`llm-ablation-ws1-freeze-v1.1` (`commit 2967d565eab55081435e6e615bd5e8f608622b57`)
- **Harness 目錄**：`llm_ablation_paper/workstream_1_technical_lead/harness/`

---

## 1. 接入既有 Harness 之原則

依據全體團隊協議，Workstream 1 的消融測試控制台（Harness）已完成驗收並凍結。Workstream 3 嚴格遵守：
- **不另做、不複製、不重建另一套 Harness 控制器**。
- 直接以模組方式引用 `llm_ablation_paper.workstream_1_technical_lead.harness` 提供的標準入口點。

---

## 2. 核心介面調用方式

### 2.1 取得標準配置物件（AblationConfig）
WS1 提供了靜態工廠方法 `AblationConfig.for_condition()`，保證消融參數符合唯一差異原則：

```python
from llm_ablation_paper.workstream_1_technical_lead.harness.config import (
    AblationConfig,
    CONFIG_C,
    CONFIG_D,
    config_diff,
)

# 取得 C 組配置：enable_planner=True, enable_dynamic_tool_gate=True, enable_output_guard=False
cfg_c = AblationConfig.for_condition("C")

# 取得 D 組配置：enable_planner=True, enable_dynamic_tool_gate=True, enable_output_guard=True
cfg_d = AblationConfig.for_condition("D")

# 驗證兩者唯一差異
diff = config_diff(cfg_c, cfg_d)
assert diff == {"enable_output_guard": {"from": False, "to": True}}
```

### 2.2 單輪消融執行介面（run_ablation_turn）
WS3 離線驗收測試統一透過 `run_ablation_turn` 執行：

```python
from llm_ablation_paper.workstream_1_technical_lead.harness.runner import run_ablation_turn

turn_result = run_ablation_turn(
    config=cfg_d,
    user_id="test_patient_001",
    message="病患輸入內容",
    state_dir=temp_state_dir,
    model_client=fake_client,       # 注入 FakeClient，零 API 呼叫
    turn_index=1,
    run_id="RUN-TEST-001",
)
```

### 2.3 執行結果與 Logging Schema 映射
`run_ablation_turn` 回傳字典已原生完整涵蓋所有 C/D 消融關鍵欄位：
- `turn_result["planner"]`：結構化規劃狀態物件。
- `turn_result["exposed_tools"]` / `turn_result["exposed_tool_names"]`：動態暴露工具清單。
- `turn_result["called_tools"]`：模型實際發起調用之工具清單。
- `turn_result["tool_rejections"]`：不可見工具調用被拒記錄清單。
- `turn_result["raw_talker_output"]`：熔斷前 Talker 原始文字。
- `turn_result["guard_action"]`：輸出熔斷動作紀錄（包含 `is_blocked`、`risk_category`、`blocked_message`）。
- `turn_result["final_output"]`：最終呈送病患之安全回覆。
- `turn_result["latency_ms"]` 與 `turn_result["token_usage"]`。

---

## 3. 狀態隔離與續跑（State Isolation & Checkpoints）

1. **狀態隔離**：每條測試軌跡均配置專屬暫存目錄 `state_dir` 與獨立 `user_id`，確保無任何全域 process-cache 或歷史對話交叉污染。
2. **原子化 Checkpoint**：每一輪對話完成後，Harness 自動寫入 `checkpoints/checkpoint_turn_{N}.json` 與 `trajectories.jsonl`，支援斷點無損續跑（Resume）。

---

## 4. 接口缺口評估報告（Interface Gap Assessment）

- **評估結論**：**無接口需求（No Interface Gap）**。
- **技術佐證**：
  1. WS1 Harness 已完全實作動態工具過濾（`enable_dynamic_tool_gate`）與輸出熔斷（`enable_output_guard`）之正交拆解。
  2. WS1 Harness 已完全實作未暴露工具調用之硬性攔截與拒絕記錄（`tool_rejections`）。
  3. WS1 Harness 已完全落實三項 Production 輔助行為（forced retrieval、fixed warning、question budget）在主實驗之關閉控制。
  4. 輸出格式 100% 滿足 `EXPERIMENT_CONTRACT.md` 要求。
- **因此，Workstream 3 無需向 Workstream 1 提出任何介面調整或 PR 需求，可 100% 直連既有 Harness 達成全部驗收目標。**
