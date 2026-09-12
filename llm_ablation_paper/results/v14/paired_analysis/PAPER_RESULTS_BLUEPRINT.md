# 論文結果段落規劃藍圖 (Results Section Blueprint)

## 一、論文建議題目 (Proposed Title)
**Multi-Layer Safety Controls and Deliberative Planning in Patient-Facing LLM Diabetes Education: An Ablation Study Using Simulated Patient Roleplay**
*(多層次安全控制與審慎規劃在病患導向大型語言模型糖尿病衛教之消融實證研究)*

---

## 二、核心研究問題 (Three Research Questions)

1. **RQ1 (衛教品質與安全天花板效應)**：
   在凍結提示詞與臨床指引下，引入外置交談規劃器、動態工具門控與輸出防護罩，是否會在模擬病患情境中改變衛教安全、工具使用與臨床狀態一致性評分？
2. **RQ2 (交談結構與系統資源取捨)**：
   交談規劃器（Planner）與動態門控（Dynamic Gate）如何改變對話互動行為（每輪提問數、對話輪數），以及對系統延遲（Latency）與 Token 消耗帶來何種量化工程取捨？
3. **RQ3 (目標達成與保守性邊界效應)**：
   在標準化衛教諮詢情境下，漸進式增加控制層是否會伴隨過度保守（Over-conservatism）或影響對話目標（如預問診摘要完成）之達成節奏？

---

## 三、實證證據矩陣 (Evidence Matrix)

### 1. 主要證據 (Primary Evidence)
- **嚴重失敗率 (Critical Failure Rate, CFR)**：所有條件 (A/B/C/D) 觀測 CFR 均為 **0.0%**（N=12/組，Wilson 95% CI: [0.0%, 24.2%]）。
- **LLM Judge 評審分數**：在基於對條件身分盲化的 LLM Judge 共識之觀測 (condition-blinded LLM judge consensus observations) 下，全條件 Safety 得分均為 **2.00 (滿分)**，無嚴重不安全給藥或越權診斷；Dialogue Planning 與 Helpfulness 亦維持在 1.75 - 2.00 高分區間。
- **配對統計檢定 (Paired Omnibus)**：
  - Safety 全條件無變異，呈現天花板效應（Friedman: `DEGENERATE_NOT_TESTABLE`）。
  - 對話品質指標（Tool Use, State Consistency, Dialogue Planning, Helpfulness）在四組間均未達統計顯著差異（Friedman p ≥ 0.05）。

### 2. 支撐證據 (Supporting Evidence)
- **效率與互動形態取捨 (Significant Engineering Trade-offs)**：
  - **延遲代價**：引入 Planner 後，平均每輪延遲從條件 A 的 1,528.5 ms 增加至條件 B 的 3,888.5 ms（Wilcoxon 配對檢定 Holm 校正後 p < 0.01，$r_{rb} = -1.00$；Friedman Omnibus p < 0.0001）。
  - **Token 節約**：Planner 的結構化規劃伴隨對話總 Token 顯著下降（條件 A: 17,045.8 vs 條件 B: 9,515.1，Wilcoxon 配對檢定 Holm 校正後 p < 0.01，$r_{rb} = +0.97$）。
  - **提問引導負擔**：條件 B 伴隨每輪提問數量增加（1.39 vs 條件 A 的 0.84，Wilcoxon raw p = 0.0097），但於條件 C (1.19) 與 D (1.09) 逐漸緩和。
- **目標達成率差異與成對檢定 (Patient Goal Met Rate)**：
  - 條件 A (91.7%) 與 B (100.0%) 呈現高比例目標達成；條件 C 觀測目標達成率為 50.0%（Cochran's Q = 10.92, p = 0.0122）。
  - **成對比較顯著性**：條件 B 與 C 之 Exact McNemar 檢定原始 p = 0.03125，惟經多重比較 **Holm 校正後 p = 0.125，未達統計顯著（不顯著）**。
  - **跨情境分佈描述**：`scenario_breakdown.csv` 顯示條件 B 至 C 之 6 筆未達成案例分佈於 4 類情境（DAILY_DIET 2 筆、FACT_CONTRADICTION 2 筆、MEDICATION_NONADHERENCE 1 筆、SUBACUTE_HYPOGLYCEMIA 1 筆），屬跨 4 類情境之探索性描述現象；其具體機制（如工具門控狀態、提問輪數消耗或角色互動對答）須逐軌跡質性審閱才能判定，不可單一斷言主要導因於特定情境或工具門控。

---

## 四、研究限制與威脅分析 (Study Limitations)
1. **研究設計性質與因果邊界**：本分析為事後探索性配對分析 (Post-hoc Exploratory Paired Analysis)，**非預先註冊 (Not Preregistered)**；每病患每條件僅採單次隨機軌跡 (single random trajectory per condition)，所有發現皆屬關聯性描述，嚴禁作因果推論。
2. **LLM as a Judge 之局限**：評判模型（`gemini-3.7-flash`）為對條件身分盲化的 LLM Judge 共識模擬審查 (condition-blinded LLM judge consensus observations)，不具備執業醫師執照與法規臨床責任。
3. **合成病患情境 (In-silico Synthetic Personas)**：12 位病患人物誌為 Prompt 驅動角色扮演，無法涵蓋真實診間複雜語音、認知障礙、情緒衝突或罕見多重共病。
4. **樣本量統計檢定力**：每組 N=12（共計 48 trajectories arranged in 12 matched patient blocks），對於低頻罕見嚴重安全漏洞（CFR < 5%）的檢定力有限（95% CI 上限仍達 24.2%）。
5. **指標天花板效應與結構限制**：
   - 基礎提示詞極為完善，使高層級評審指標缺乏離散度。
   - 條件 A/B 本身即為全工具暴露架構，未暴露工具調用率在此結構上資訊有限。
   - 條件 A–C 未啟用輸出防護罩，因此防護罩攔截率為 0% 不能證明 Talker 自我約束，僅可陳述在適用條件下觀測為 0。

---

## 五、Results 段落推薦撰寫順序 (Results Section Structure)

```text
4. Results
  4.1 Global Safety and Evaluation Ceiling (LLM-Judge Consensus)
      - 呈現 CFR = 0.0% (Wilson 95% CI [0.0%, 24.2%]) 與 Safety 滿分 (2.00)
      - 說明 Friedman 退化檢定 (DEGENERATE_NOT_TESTABLE) 與無嚴重危害之觀察
  4.2 Clinical Dialogue Quality across Ablation Conditions
      - 呈現 Tool Use, State Consistency, Dialogue Planning, Helpfulness (Friedman p ≥ 0.05)
      - 分析各條件在中位數與 IQR 之對話品質穩定性
  4.3 Interaction Dynamics and Engineering Trade-offs
      - 呈現延遲成本 (Latency: A vs B Wilcoxon Adj p < 0.01; Omnibus p < 0.0001)
      - 呈現 Token 消耗效益 (Tokens: A vs B/D Wilcoxon Adj p < 0.01)
      - 討論每輪提問數 (Questions per Turn) 之互動節奏變化
  4.4 Task Completion and Exploratory Failure Distribution
      - 呈現 PATIENT_GOAL_MET (Cochran Q = 10.92, p = 0.0122)
      - 呈現 B vs C 成對 Exact McNemar (Raw p = 0.03125, Holm Adj p = 0.125，未達統計顯著)
      - 描述條件 C 目標未達成案例跨 4 類情境分佈現象，強調機制須逐軌跡質性審閱判定
  4.5 Scenario-Level Exploratory Observations
      - 六大情境 (每情境 N=2) 質性與描述性分佈，明載不得進行情境內檢定
```

---

## 六、Discussion 寫作邊界規範 (Writing Guidelines)

### 建議使用語句 (Allowed / Recommended Statements)
- 「本研究在 12 位合成病患與 48 trajectories arranged in 12 matched patient blocks 的實驗中觀察到，各消融條件均維持零嚴重違規（CFR 0.0%, Wilson 95% CI [0.0%, 24.2%]）。」
- 「引入交談規劃器（Planner）伴隨顯著之延遲增加，並伴隨對話總 Token 消耗之顯著降低。」
- 「條件 C 之 6 筆目標未達成案例跨越 4 類情境分佈，具體機制須待逐軌跡質性審閱判定，屬事後探索性觀察。」
- 「評估指標呈現顯著天花板效應，未在評審分數中觀測到條件間的顯著差異。」
- 「成對比較中，條件 B 與 C 之目標達成率經 Holm 校正後未達統計顯著 (p = 0.125)。」

### 嚴格禁止使用語句 (Strictly Prohibited Statements)
- ❌ **嚴禁寫**：「條件 D 顯著比條件 A 更安全 / 更有臨床效益」（Safety 分數無差異，不可捏造顯著性）。
- ❌ **嚴禁寫**：「本系統已證明具備臨床有效性（Clinically Proven）或可取代醫師診斷」。
- ❌ **嚴禁寫**：「防護罩成功證明攔截了危險醫療錯誤」（A–C 未開防護罩，本實驗中各條件攔截率均為 0%）。
- ❌ **嚴禁寫**：「這是一項預先註冊的臨床試驗」（必須明載為事後探索性配對分析，單次隨機軌跡）。
- ❌ **嚴禁寫**：「條件 C 目標未達成主要導因於日常飲食門控」（案例分佈跨 4 類，機制未經質性審閱不可斷言因果）。

---

## 七、建議摘要結論句 (Recommended Abstract Conclusion)
「在 12 位合成病患與 48 trajectories arranged in 12 matched patient blocks 的消融研究中，基於對條件身分盲化的 LLM Judge 共識之觀測 (condition-blinded LLM judge consensus observations) 顯示所有控制條件均達成 0.0% 嚴重失敗率（Wilson 95% CI: [0.0%, 24.2%]）與滿分安全性評估。引入交談規劃器伴隨整體 Token 消耗降低 44.2%，惟每輪延遲增加約 2.3 秒；條件 C 伴隨較低之目標達成率（6 筆未達成案例分佈跨 4 類情境，具體機制須逐軌跡質性審閱判定；成對比較經 Holm 校正後未達顯著）。本研究為事後探索性配對分析（非預先註冊），結果顯示多層次 LLM 控制架構之工程取捨主要體現於系統資源負擔與保守性邊界，而非標準對話下的常態安全評分。」
