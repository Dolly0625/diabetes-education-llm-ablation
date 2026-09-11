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

# 驗證兩者控制旗標唯一差異（排除 condition 標籤本身）
diff = config_diff(cfg_c, cfg_d)
flags_diff = {k: v for k, v in diff.items() if k != "condition"}
assert flags_diff == {"enable_output_guard": {"from": False, "to": True}}
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
    model_client=fake_client,       # 注入 FakeClient，零外部 API 呼叫
    turn_index=0,
    run_id="RUN-TEST-001",
    artifacts_dir=temp_state_dir,   # 隔離寫入專屬目錄，避免污染正式 artifacts
)
```

### 2.3 Harness 真實回傳欄位與下游契約映射

WS1 `run_ablation_turn` 回傳字典之**真實欄位鍵值**如下，右側對應下游 `EXPERIMENT_CONTRACT.md` 軌跡最低 Schema 轉換欄位名稱：

| Harness 真實回傳鍵值（Python Dict Key） | 欄位資料型態 | 下游 Contract 對應名稱 | 語意說明 |
|---|---|---|---|
| `turn_result["planner_result_or_neutral"]` | `dict` | `planner_state` | 結構化規劃大腦狀態快照（B/C/D 組為評估字典；A 組為中立 neutral 字典） |
| `turn_result["exposed_tools"]` | `list[str]` | `tools_exposed` | 當輪模型視野中暴露之工具名稱清單（如 `["search_handbook"]`） |
| `turn_result["called_tools"]` | `list[str]` | `tools_called` | 當輪模型實際發起調用之工具名稱清單 |
| `turn_result["tool_rejections"]` | `list[dict]` | （稽核欄位） | 未暴露工具調用被拒記錄清單（含 `tool`, `reason`, `id`） |
| `turn_result["raw_talker_output"]` | `str` | `raw_talker_output` | 輸出端熔斷前，Talker 模型之原始生成文字（C 與 D 均完整保留） |
| `turn_result["output_guard_result"]` | `dict` | `guard_action` | 輸出端熔斷評估字典（含 `is_blocked`, `risk_category`, `blocked_message`） |
| `turn_result["assistant_response"]` | `str` | `final_output` | 呈送病患端之最終文字（未熔斷為 raw；熔斷時為安全覆寫文字） |
| `turn_result["latency_ms"]` | `int` | `latency_ms` | 該輪對話端到端執行延遲毫秒數 |
| `turn_result["token_usage"]` | `dict \| None`| `token_usage` | Token 消耗統計字典（含 prompt, completion, total） |

> **說明**：`planner`、`exposed_tool_names`、`guard_action`、`final_output` 僅為研究契約 `EXPERIMENT_CONTRACT.md` 匯總時的轉換命名；WS1 Harness 原生回傳鍵值一律為上述表格第一欄所示之真實名稱。

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
  4. 輸出資料結構可完整對齊 `EXPERIMENT_CONTRACT.md` 要求。
- **因此，Workstream 3 無需向 Workstream 1 提出任何介面調整或 PR 需求，可直接使用既有 Harness 達成全部驗收目標。**
