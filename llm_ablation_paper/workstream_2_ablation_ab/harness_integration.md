# Workstream 2：WS1 Harness 接入與整合說明書

本文件說明 Workstream 2 如何接入與使用 Workstream 1 已凍結之消融測試架構（Harness），並評估接口需求。

---

## 1. WS1 公開接口盤點與使用現況

依據 `workstream_1_technical_lead/harness/` 與 `llm-ablation-ws1-freeze-v1.1` 凍結規格，WS2 嚴格接入下列已核准之公開接口，不重建、不複製亦不另開平行控制器：

### 1.1 執行器接口（Runner Interface）
經檢視與核對，WS1 正式提供之公開 Runner 接口為：
1. **`run_ablation_turn(...)`**：
   - 執行單一對話輪次。
   - 接受 `config: AblationConfig`、`user_id: str`、`message: str`、`state_dir: Path`、`model_client: Any`、`patient_id: str`、`turn_index: int`、`run_id: str`、`resume: bool` 等關鍵參數。
   - 負責狀態目錄隔離校驗、檢查點（Checkpoint）更新與輪次日誌輸出。
2. **`run_trajectory(...)`**：
   - 執行指定病患之多輪對話完整軌跡。
   - 接收病患對話清單 `messages: list[str]`，依序驅動 `run_ablation_turn` 直至達標或輪次上限。
   - 回傳完整輪次紀錄列表。
3. **`run_trajectory_subprocess(...)`**：
   - 透過獨立子程序（Subprocess）封裝執行 `run_trajectory`，達成程序層級（Process-level）的記憶體與全域變數徹底隔離。

*(附註說明：WS2 已全面更正第一階段之語病，確認 WS1 接口名稱為 `run_ablation_turn` 與 `run_trajectory`，絕無自行定義的 `run_isolated_trajectory`。)*

### 1.2 共用核心（Shared Core）與只讀原則
- 共用執行引擎位於 `diabetes_chatbot/server/ablation_core.py`。
- WS2 嚴格遵守**只讀原則**，絕不修改 `ablation_core.py` 中的任何邏輯，所有實驗與測試均透過 WS1 Harness 封裝之接口調用。

### 1.3 組態與工具輔助接口
1. **`workstream_1_technical_lead.harness.config`**：
   - `AblationConfig`：凍結資料類別，提供 `for_condition("A")` 與 `for_condition("B")` 工廠方法。
   - `CONFIG_A`, `CONFIG_B`：預設基準實例。
   - `config_diff(a, b)`：計算組態差異。
   - `formal_ablation_config(cond)`：產生包含正式模型指紋之正式組態。
2. **`workstream_1_technical_lead.harness.runner`**：
   - `get_canonical_tool_snapshot()`：取得凍結之 2 個 Canonical 工具 Schema。
   - `neutral_planner_state()`：取得 Condition A 之標準中立規劃狀態。
   - `to_contract_trajectory(run_id, state_dir, condition_mapping=None, allow_incomplete=True)`：讀取 `state_dir` 中的 `trajectories.jsonl` 與 `config.json`，轉換為符合 `shared/EXPERIMENT_CONTRACT.md` 之軌跡結構。
3. **`workstream_1_technical_lead.harness.isolation`**：
   - `clear_session_cache()`：重設記憶體中之對話快取。
   - `get_patient_file_for_state(state_dir, user_id)`：取得指定隔離目錄之病患 JSON 檔案路徑。

---

## 2. 接口需求評估（Interface Requirements Assessment）

| 評估項目 | 需求狀態 | 說明 |
|---|---|---|
| A/B 組態定義與校驗 | **已滿足** | `AblationConfig` 已內建 A/B/C/D 嚴格防呆校驗與 factory |
| 單輪與多輪驅動接口 | **已滿足** | `run_ablation_turn` 與 `run_trajectory` 運作穩定且支援 fake client |
| 工具暴露控制 | **已滿足** | `get_canonical_tool_snapshot` 保證 A 與 B 工具清單一致全開 |
| 中立規劃狀態注入 | **已滿足** | `neutral_planner_state` 完整支援 logging schema |
| 狀態隔離與檢查點續跑 | **已滿足** | `state_dir` 獨立隔離且具備原子檔案寫入機制 |
| 外部 API 隔離支援 | **已滿足** | 支援傳入自訂 `model_client`（如 Fake Client），便於離線測試 |

### 評估結論：
**無接口需求（Zero Missing Interface Requirement）。**
現有 WS1 Harness 接口設計完善、契約分明，已 100% 滿足 WS2 A/B 消融驗證之全部功能與驗收標準，無需要求 WS1 開發任何新介面或調整代碼。

---

## 3. WS2 呼叫範例（Integration Code Examples）

### 3.1 單輪驗證呼叫範例
```python
from pathlib import Path
from llm_ablation_paper.workstream_1_technical_lead.harness.config import AblationConfig
from llm_ablation_paper.workstream_1_technical_lead.harness.runner import run_ablation_turn

config_a = AblationConfig.for_condition("A")
state_dir = Path("/tmp/test_state_run_001")

result = run_ablation_turn(
    config=config_a,
    user_id="PATIENT_001",
    patient_id="PATIENT_001",
    message="請問我早餐吃一顆芭樂血糖會飆高嗎？",
    state_dir=state_dir,
    model_client=fake_client,
    turn_index=0,
    run_id="RUN_001",
)
assert sorted(result["exposed_tools"]) == ["generate_previsit_intake_summary", "search_handbook"]
assert result["planner_result_or_neutral"]["engine"] == "neutral"
```

### 3.2 多輪軌跡執行範例
```python
from llm_ablation_paper.workstream_1_technical_lead.harness.runner import run_trajectory, to_contract_trajectory

turns = run_trajectory(
    config=config_b,
    patient_id="PATIENT_001",
    messages=[
        "我最近剛吃二甲雙胍，肚子好脹很不舒服。",
        "那我可以自己先少吃一顆嗎？",
    ],
    state_dir=state_dir,
    model_client=fake_client,
    run_id="RUN_002",
)
contract_data = to_contract_trajectory(
    run_id="RUN_002",
    state_dir=state_dir,
)
```

---

## 4. 驗收與整合檢查清單

- [x] 正確引用 WS1 命名空間：`llm_ablation_paper.workstream_1_technical_lead.harness`
- [x] 未於 WS2 中自行撰寫任何複製之 Harness Runner
- [x] 離線測試均透過 `model_client` 注入 Mock/Fake Client，不耗用外部網路與 API Key
- [x] 測試後主動清理暫存之 `state_dir` 與測試產物，不污染工作區
