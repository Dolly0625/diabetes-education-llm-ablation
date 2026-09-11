# 碩士論文研究提案書（外部評估版）

版本：0.1  
日期：2026-09-10  
狀態：研究設計草案，尚未執行正式實驗，不包含任何實驗結果

## 一、暫定題目

### 中文題目

**糖尿病照護大型語言模型代理之長期記憶可靠性評估：基於合成縱向對話的受控比較研究**

### 英文題目

**Evaluating Longitudinal Memory Reliability in a Diabetes-Care Large Language Model Agent: A Controlled Study Using Synthetic Multi-Session Dialogues**

## 二、研究摘要

大型語言模型（Large Language Model, LLM）代理逐漸被用於多輪健康衛教、病患資訊整理與對話式服務。然而，單次問答正確不代表系統能在跨日或跨次會話中可靠地保留、更新與使用資訊。當病患補充新資料、更正先前說法或回報換藥時，代理可能遺漏仍有效的事實、沿用已失效資訊，或在摘要中產生前後矛盾。這類錯誤在無法取得真實臨床部署資料的研究情境下，仍可透過具有明確事件真值的合成縱向對話進行受控評估。

本研究擬建立一套糖尿病照護 LLM Agent 長期記憶評估基準，以合成病患設定、跨會話事件序列及可機器判讀的事件帳本（event ledger）作為標準答案，比較四種記憶條件：僅使用近期滑動視窗、重放完整對話歷史、非結構化滾動摘要，以及具時間狀態的結構化病患檔案。所有條件固定使用相同模型、提示詞、工具、安全控制、病患情境與執行流程，使主要差異限於記憶表示與讀取方式。

研究主要評估目前有效事實的狀態錯誤率，並分析事實保留、更正吸收、過期資訊洩漏、無依據新增、跨輪矛盾、任務完成、Token 使用、延遲與成本。程式可直接判定的事實型指標為主要證據；LLM-as-a-Judge 僅用於語意品質的次要分析，並以人工抽查及 canary cases 檢驗評分流程。本研究不主張臨床有效性或可直接部署，而是提出一套可重現、可稽核的工程評估方法，說明不同記憶策略在合成糖尿病照護情境中的可靠性與成本取捨。

## 三、研究背景與問題

現有醫療 LLM 評估大量依賴靜態題庫或單次問答，但實際對話代理必須處理持續變化的使用者狀態。一般長期對話 benchmark 已顯示，擴大 context window 或加入檢索雖可改善部分記憶任務，模型仍難以穩定處理長距離時間與因果關係 [1]。後續研究進一步指出，只測量顯性的事實回憶不足以代表代理是否能在後續行動中正確套用使用者狀態與限制 [2]。

醫療領域的近期研究亦開始建立合成縱向對話資料，以處理真實臨床資料受到隱私、倫理與取得成本限制的問題 [3]。另一方面，醫療 LLM 評估研究強調，單一考試分數不足以反映病患溝通、摘要與工作流程等真實任務，需要依應用類型建立多面向評估 [4]。因此，在無法進行真實部署的前提下，建立受控、具有事件真值且能重現的動態模擬測試，是合理的前期工程驗證方法，但不能被描述為臨床驗證。

本專案目前已有糖尿病衛教 Agent、結構化病患檔案、跨會話持久化、滑動視窗、換藥標註、診前摘要、合成病患 profiles 與可續跑實驗 harness。既有工程測試主要驗證特定函式或預設案例是否通過，尚未系統性回答：不同記憶設計在相同縱向情境下，對有效事實保留、更正、失效資訊隔離與成本造成何種差異。

## 四、研究缺口與定位

本研究關注的缺口不是「醫療 LLM 是否能正確診斷」，也不是「系統能否改善病患健康」，而是以下較窄且可測量的工程問題：

1. 現有單元測試無法呈現多次會話中資訊逐步增加、失效與更正所造成的累積錯誤。
2. 一般 factual recall 指標不一定能偵測舊藥復活、時間狀態錯置或更正未生效等狀態型錯誤。
3. 完整歷史、自由文字摘要與結構化狀態可能具有不同的可靠性、成本與錯誤型態，但目前專案尚無受控比較。
4. 真實病患資料不可得時，需要一套不將合成評估誤稱為臨床證據的研究方法與主張邊界。

本研究的定位是 **benchmark construction + controlled systems evaluation**，而非臨床試驗、使用者研究或醫療效果評估。

## 五、研究目的與研究問題

### 5.1 主要研究目的

建立一套具事件真值、可重跑且能檢測狀態變化錯誤的糖尿病照護縱向對話 benchmark，並比較不同記憶策略的可靠性與資源成本。

### 5.2 主要研究問題

> 在受控的合成糖尿病縱向對話中，不同記憶表示策略如何影響 LLM Agent 對目前有效病患狀態的正確使用，以及過期資訊的錯誤引用？

### 5.3 次要研究問題

1. 不同記憶策略對事實保留、更正吸收、時間狀態判斷、無依據新增及跨輪矛盾有何差異？
2. 不同記憶策略在 Token 使用量、回應延遲與 API 成本上呈現何種取捨？
3. 不同類型的縱向事件，例如數值更新、資訊否定、換藥、症狀變化與診前摘要，是否產生不同的記憶失敗模式？

### 5.4 預先提出的假設

- H1：具時間狀態的結構化記憶，相較僅使用近期視窗與非結構化摘要，具有較低的目前狀態錯誤率。
- H2：完整歷史重放可能提高早期事實的可見性，但也增加過期資訊誤用、Token 與延遲。
- H3：更正、否定與換藥等狀態轉移事件，比單純事實回憶更容易區分各記憶策略的可靠性。

以上假設須在正式實驗前凍結；若 pilot 結果不支持，仍照實報告，不更換指標或事後重寫假設。

## 六、研究範圍與操作型定義

### 6.1 納入範圍

- 以繁體中文進行的合成糖尿病衛教及診前資訊整理對話。
- 血糖紀錄、目前用藥、已停用用藥、自述症狀、飲食生活、回診訴求與先前摘要等既有資料欄位。
- 跨 3 次會話的資訊新增、更新、更正、否定、失效與回憶。
- Agent 的狀態一致性、資訊忠實度、任務完成及工程成本。

### 6.2 排除範圍

- 真實病患招募、真實診療紀錄及醫院環境部署。
- 診斷準確率、治療建議有效性、服藥遵從性改善或健康結果。
- 與醫師、護理師或真實病患的能力比較。
- 宣稱系統已通過臨床、法規或實務部署驗證。
- 將自動化測試通過率等同臨床安全率。

### 6.3 主要操作型定義

- **有效事實（active fact）**：依事件帳本，在指定 probe 時點仍有效且應被系統採用的事實。
- **過期事實（stale fact）**：已被更正、否定、取代或標記停用，但仍可能存在歷史紀錄中的事實。
- **狀態錯誤（state error）**：系統遺漏任務所需的有效事實、引用過期事實、錯置時間或產生與事件帳本矛盾的內容。
- **無依據新增（unsupported addition）**：輸出包含事件帳本、當前輸入與允許背景資料均未提供的病患特定事實。

## 七、研究方法

### 7.1 研究設計

採受控的重複量測系統實驗（controlled repeated-measures systems experiment）。同一組病患 profile、事件腳本及 probe 將在所有記憶條件下執行。除記憶表示與讀取方式外，模型版本、temperature、提示詞、工具 schema、安全控制、RAG 設定、最大輪數與執行程式皆固定。

### 7.2 記憶條件

| 條件 | 設計 | 目的 |
|---|---|---|
| M0：近期視窗 | 僅保留最近固定數量訊息，不使用跨會話持久化 | 最小記憶基準組 |
| M1：完整歷史 | 將可容納的完整歷史重新放入 context | 檢驗長 context 的效益與成本 |
| M2：文字摘要 | 每次會話結束產生非結構化 rolling summary | 代表常見摘要式記憶 |
| M3：結構化時間狀態 | 使用結構化病患檔案，保存 active、stale、來源與更新時間 | 評估現有系統可延伸的狀態式記憶 |

M3 不應直接以目前 production 名稱宣稱為優勢方法。正式比較前須先凍結四條件的更新規則、讀取規則及 prompt，並證明除記憶機制外沒有其他差異。

### 7.3 合成病患與情境

第一階段沿用現有 12 個合成病患 profile 進行 pilot。正式實驗目標為 24 個 profiles，每一類 4 個：

1. 日常飲食與數值更新。
2. 藥物副作用與症狀變化。
3. 自行停藥或調藥要求。
4. 亞急性低血糖與後續更正。
5. 診前資訊整理。
6. 多輪事實矛盾與更正。

profiles 只作為合成背景種子，不稱為真實病例或具臨床代表性的樣本。若擴增 profiles，必須沿用既有 schema、來源追溯、隱私檢查與固定抽樣規則；不得依 pilot 表現挑選對系統有利的案例。

### 7.4 縱向事件結構

每個 profile 建立 3 次會話，每次 4 至 6 輪。腳本至少包含：

- Session 1：建立初始事實。
- Session 2：增加新資訊，並對至少一項資訊進行更正、否定或取代。
- Session 3：以自然問題及診前摘要任務檢驗系統是否使用目前有效狀態。

每條軌跡配置相同的 probe 類型：

1. Direct recall：直接詢問先前資訊。
2. Temporal update：詢問目前值而非歷史值。
3. Correction adoption：檢查更正是否生效。
4. Stale-information rejection：誘發系統錯用已失效資訊。
5. Synthesis：生成診前摘要並檢查完整性與忠實度。

### 7.5 事件帳本

每條軌跡在生成輸出前先建立機器可讀的 `event_ledger.jsonl`。建議欄位如下：

```json
{
  "fact_id": "SP001_MED_02",
  "category": "medication",
  "value": "得爾美",
  "introduced_at": "session_2_turn_3",
  "valid_from": "session_2_turn_3",
  "invalidated_at": null,
  "status": "active",
  "source": "synthetic_patient_utterance",
  "required_for_probes": ["current_medication", "previsit_summary"]
}
```

事件帳本是主要事實標準，不由受測模型生成，也不得在看到模型輸出後修改。所有修訂必須留下版本與原因。

### 7.6 實驗規模

正式目標：

- 24 個 profiles。
- 4 種記憶條件。
- 每一 profile-condition 重複 3 次，以觀察隨機變異。
- 共 288 條跨會話軌跡。
- 每條軌跡包含 3 次會話與固定 probes。

若 API 成本或時間超出預期，最低可行版本為 12 profiles × 4 conditions × 3 repetitions，共 144 條軌跡。縮減決定與停止規則必須在正式結果揭露前完成。

### 7.7 執行控制

- 每條軌跡使用獨立 patient ID、run ID、process 與暫存 state directory。
- 同一 profile 在四條件下使用完全相同的起始狀態、事件腳本與 probe。
- 固定模型 ID、模型版本、temperature、max tokens、system prompt、tool schema 與程式 commit。
- 固定 Planner、RAG、dynamic tool gate、Input Guard、Output Guard 及其他後處理設定；這些不是本研究自變項。
- 保存原始 transcript、memory snapshot、event ledger、model response、token、latency、error、retry 與終止原因。
- 模型 API 的 seed 不視為完全決定性的保證，因此保留 3 次重複並報告變異。
- 在正式執行前，以 canary cases 驗證評分器能辨識明顯正確、遺漏、過期與虛構輸出。

## 八、評估指標

### 8.1 主要指標

**目前狀態錯誤率（Current-State Error Rate, CSER）**

\[
CSER = \frac{N_{omission}+N_{stale}+N_{contradiction}+N_{unsupported}}{N_{evaluated\ state\ decisions}}
\]

四種錯誤須各自保留，不只報告合計值，避免一個方法以降低遺漏換取更多虛構內容。

### 8.2 次要指標

| 指標 | 定義 | 主要判定方式 |
|---|---|---|
| Active Fact Recall | probe 所需有效事實被正確表達的比例 | ledger + deterministic matching |
| Correction Adoption Rate | 更正後採用新值且不沿用舊值的比例 | ledger + rule evaluator |
| Stale Fact Leakage Rate | 輸出將 stale fact 當成目前狀態的比例 | ledger + rule evaluator |
| Temporal Accuracy | 正確區分目前、過去與時間未知資訊的比例 | ledger + structured parser |
| Unsupported Addition Rate | 新增無來源病患事實的比例 | ledger +人工／LLM 複核 |
| Cross-Turn Contradiction Rate | 同一軌跡內輸出互相衝突的比例 | rule + semantic review |
| Previsit Summary Fidelity | 診前摘要的必要資訊涵蓋、錯誤與過期內容 | ledger + rubric |
| Task Completion Rate | 在安全邊界內完成指定 probe 任務的比例 | deterministic status + rubric |
| Efficiency | input/output tokens、wall-clock latency、API cost | execution logs |

### 8.3 評分證據階層

1. **主要證據**：event ledger 對照、結構化輸出欄位及確定性程式評分。
2. **支撐證據**：盲化後的人工抽查，檢查確定性評分器的誤判。
3. **探索性證據**：LLM-as-a-Judge 對語意完整性、清楚度與摘要品質的評分。

LLM-as-a-Judge 不能自行建立 ground truth，也不能取代事件帳本。近期研究顯示，醫療摘要 Judge 在以既有人工量表校準後可以達到良好一致性，但其可靠性來自與人工標準的比較，而非模型自稱客觀 [5]。

### 8.4 人工抽查

- 隨機抽取至少 10% 軌跡，由兩位評分者依 frozen rubric 獨立評分。
- 若只能由研究者與指導教授評分，評估範圍限於「是否符合事件帳本」與「標註規則是否一致」，不得稱為臨床專家驗證。
- 報告評分者角色、訓練流程、分歧處理與一致性指標。
- 若能取得醫護專家協助，可另做小型內容效度檢查，但不得因此宣稱完成臨床驗證。

## 九、資料分析

1. 每個條件報告 CSER 及各錯誤類型的比例與 95% confidence interval。
2. 以 profile 為 cluster 進行 bootstrap，避免將同一病患的多個 probes 誤當成完全獨立樣本。
3. 二元 paired outcomes 可使用 Cochran's Q 作四條件整體比較；若達預設門檻，再以 paired McNemar tests 進行事先定義的比較並採 Holm correction。
4. Token、延遲及成本等連續或偏態資料，使用中位數、IQR 與 paired non-parametric test；若 assumptions 符合，再補充參數模型。
5. 效果量與 confidence interval 為主要解讀依據，p-value 僅作輔助。
6. 情境類型分析列為次要或探索性分析，避免樣本不足時做過度細分推論。
7. 若重複執行之結果變異過大，先報告模型不穩定性，不刪除失敗 run 或只挑最佳結果。

正式分析前須撰寫 analysis plan，凍結主要 outcome、排除規則、缺失值處理、重試規則與 planned contrasts。

## 十、在無真實部署下的效度策略

### 10.1 內容效度

情境由既有系統需求、合成 profile 類別及明確狀態轉移規則構成。可請指導教授或領域顧問檢查情境是否合理；若沒有臨床專家，只能宣稱工程需求覆蓋，不宣稱臨床代表性。

### 10.2 建構效度

使用手工建立的 canary cases 驗證指標：評分器應對明顯正確、遺漏有效資訊、引用停用藥物、時間錯置及無依據新增給出不同判定。

### 10.3 內部效度

採單一差異原則。四個條件只允許記憶表示與讀取規則不同；若不同條件同時更動 Planner、prompt 安全內容或工具權限，該批結果不能解讀為記憶效果。

### 10.4 信度與可重現性

保存 config、prompt hash、tool-schema hash、commit、模型版本、執行時間、原始輸出與評分明細。提供從 frozen config 重建結果表的單一指令。

### 10.5 外部效度

本研究的外部效度有限。結果只適用於指定模型、提示詞、合成情境與系統版本，不能外推至真實高齡病患、臨床成效或醫療機構部署。此限制不是由模擬評分消除，而是透過清楚限定研究主張處理。

## 十一、倫理與資料治理

- 正式研究以合成人物與合成事件為主，不蒐集可識別的真實病患資料。
- 現有 public online medical QA-derived seeds 只用於背景錨定，保留來源、版本與授權限制；不稱為去識別病歷。
- 不在公開 artifact 中保留來源資料的完整原句或可能識別資訊。
- 是否屬於免審、非人體研究或仍須提交行政判定，由所屬學校研究倫理單位決定；本提案不自行做 IRB/REC 判定。
- 若後續加入真人訪談、醫護評分或真實紀錄，必須在資料收集前重新確認倫理與資料保護要求。

## 十二、預期貢獻

### 12.1 方法貢獻

提出一套以事件帳本為 ground truth、針對新增、更正、失效與時間狀態設計的縱向醫療對話記憶評估方法。

### 12.2 工程貢獻

建立可重跑的 benchmark runner、記憶條件 adapter、deterministic evaluator、評分明細與實驗報表產生流程。

### 12.3 實證貢獻

在指定模型與合成糖尿病照護情境下，呈現四種記憶策略的錯誤型態、可靠性及成本取捨。此貢獻須以正式結果為準，不預設 M3 必然較佳。

### 12.4 實務價值

提供開發者在建立長期互動 LLM Agent 時選擇記憶機制與設計回歸測試的參考，不延伸為臨床部署建議。

## 十三、與既有研討會研究的邊界

| 面向 | 既有研討會研究 | 本碩士論文 |
|---|---|---|
| 核心問題 | Planner、動態工具權限及 Output Guard 分別降低哪些系統失敗 | 記憶表示如何影響跨會話有效狀態與過期資訊處理 |
| 自變項 | 分層安全控制 A–D | 記憶條件 M0–M3 |
| 主要結果 | Critical Failure Rate、工具政策、輸出熔斷等 | CSER、correction adoption、stale leakage、成本 |
| 主要 artifact | 安全消融軌跡與 Judge 結果 | event ledger、長期記憶 benchmark 與 deterministic evaluator |
| 禁止交叉使用 | 不把記憶條件包裝成安全層消融 | 不把 A–D 結果當成本論文核心證據 |

碩論正式實驗中，Planner、tool gate、Output Guard 與其他安全後處理在四種記憶條件下必須固定。若研討會使用的同一批 profiles 被重用，論文需清楚說明重用範圍，並建立不同的事件腳本、主要指標與研究問題。

## 十四、八週工作時程

| 週次 | 工作 | 驗收產物 |
|---|---|---|
| 第 1 週 | 與指導教授確認 RQ、範圍、倫理路徑與研討會邊界 | 凍結版研究協議 v1 |
| 第 2 週 | 完成文獻矩陣、事件帳本 schema、記憶條件規格 | literature matrix、schema、condition contract |
| 第 3 週 | 實作 M0–M3 adapter、runner 與狀態隔離 | 可離線執行的 harness 與 tests |
| 第 4 週 | 建立／擴增 profiles、probes、canary cases；完成 pilot | pilot report、評分器修正紀錄 |
| 第 5 週 | 凍結 prompt、模型、commit、評分規則；執行正式實驗 | frozen config、raw trajectories |
| 第 6 週 | 完成 deterministic scoring、人工抽查與統計分析 | 結果表、圖、error taxonomy |
| 第 7 週 | 完成方法、結果、討論與限制初稿 | 論文完整初稿 |
| 第 8 週 | 數字稽核、口試簡報、重現測試與修訂 | 定稿、簡報、reproduction package |

若第 3 週結束仍無法完成四條件的單一差異 runner，立即縮減為三條件（M0、M2、M3）或 12 profiles 的最低可行版本，不延後正式資料凍結。

## 十五、預期交付成果

1. 碩士論文正文與中英文摘要。
2. 合成縱向糖尿病對話 benchmark。
3. `event_ledger` schema 與資料驗證器。
4. 四種 memory adapters 及單一實驗 harness。
5. deterministic metrics 與 LLM Judge 輔助評分程式。
6. 原始軌跡、設定指紋、結果表與統計分析腳本。
7. 一鍵重建主要表格與圖表的 reproducibility command。
8. 求職展示用的系統架構圖、benchmark 說明與失敗案例分析。

## 十六、主要風險與因應

| 風險 | 影響 | 因應 |
|---|---|---|
| 四條件並非單一差異 | 無法將結果歸因於記憶策略 | condition contract、config diff、整合測試 |
| 合成對話過於規則化 | benchmark 太容易或不具挑戰性 | 加入自然改述、跨輪干擾、否定、更正及 adversarial probes |
| LLM Judge 自我偏誤 | 語意分數不可信 | ledger 指標優先、Judge 盲化、人工抽查與 canary calibration |
| 樣本數不足 | 次群組分析不穩 | 主要分析聚焦整體 paired comparison，情境分析列探索性 |
| API 模型更新 | 無法重現 | 記錄 model ID、日期、原始輸出；正式批次集中執行 |
| profile 來源授權或代表性受質疑 | 影響資料主張 | 僅稱背景種子，保留 provenance，不主張真實病例 |
| 兩個月無法完成 | 無法按時口試 | 第 3 週設 stop rule，降為 12 profiles 或三條件 |

## 十七、允許與禁止的結論

### 可以依結果主張

- 在本研究指定模型、版本與合成情境中，各記憶條件呈現不同的狀態錯誤率與成本。
- 事件帳本能支持可稽核的縱向對話記憶評估。
- 某些狀態轉移事件比單純 factual recall 更容易暴露記憶失敗。

### 必須加限定語

- 「在本研究的合成情境中」。
- 「對指定模型、提示詞與程式版本」。
- 「系統層級／工程可靠性評估」。
- 「不構成臨床有效性或部署驗證」。

### 禁止主張

- 經真實病患、醫師或臨床場域驗證。
- 能改善病患安全、血糖控制、用藥遵從或健康結果。
- 適合直接部署於醫療機構。
- 某記憶方法對所有模型、語言或疾病普遍較佳。
- LLM Judge 等同醫療專家。

## 十八、工作參考文獻

> 下列為提案階段已核對存在的核心來源；正式送審前仍須依學校格式完成完整作者列表、卷期頁碼與 DOI 稽核。

1. Maharana et al. (2024). *Evaluating Very Long-Term Conversational Memory of LLM Agents*. ACL 2024. https://doi.org/10.18653/v1/2024.acl-long.747
2. Li et al. (2026). *LoCoMo-Plus: Beyond-Factual Cognitive Memory Evaluation Framework for LLM Agents*. ACL 2026. https://doi.org/10.18653/v1/2026.acl-long.1150
3. Hu, Dai, Tan, and Kang (2026). *Synthesis and Evaluation of Long-term History-aware Medical Dialogue*. arXiv:2605.19766. https://arxiv.org/abs/2605.19766
4. *Holistic evaluation of large language models for medical tasks with MedHELM* (2026). *Nature Medicine*. https://www.nature.com/articles/s41591-025-04151-2
5. Croxford et al. (2025). *Evaluating clinical AI summaries with large language models as judges*. *npj Digital Medicine, 8*, 640. https://www.nature.com/articles/s41746-025-02005-2
6. Tu et al. (2025). *Towards conversational diagnostic artificial intelligence*. *Nature*. https://www.nature.com/articles/s41586-025-08866-7

## 十九、送交指導教授前仍須確認

1. 學校對碩論提案的固定格式與篇幅。
2. 指導教授是否接受純合成資料的 systems evaluation。
3. 研究倫理單位要求的是免審申請、非人體研究判定或其他程序。
4. 正式可使用的模型 API、預算與固定版本。
5. 人工抽查能否取得第二位評分者。
6. 研討會稿最終題目、資料與圖表清單，以完成重疊稽核。

