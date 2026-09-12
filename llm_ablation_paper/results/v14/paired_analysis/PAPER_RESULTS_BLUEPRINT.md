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
   在標準化衛教諮詢情境下，漸進式增加控制層是否會引發過度保守（Over-conservatism）或阻礙對話目標（如預問診摘要完成）之自然達成？

---

## 三、實證證據矩陣 (Evidence Matrix)

### 1. 主要證據 (Primary Evidence)
- **嚴重失敗率 (Critical Failure Rate, CFR；LLM-judge 共識觀察，非臨床事實)**：所有條件 (A/B/C/D) 觀測 CFR 均為 **0.0%**（N=12/組，Wilson 95% CI: [0.0%, 24.2%]）；48 條軌跡為 12 個配對病患區集 (12 matched patient blocks)，非 48 筆獨立樣本。
- **LLM Judge 評審分數 (LLM-judge (gemini-3.7-flash) consensus observation, not clinical fact)**：全條件 Safety 得分均為 **2.00 (滿分)**，未觀察到嚴重不安全給藥或越權診斷之評審紀錄；Dialogue Planning 與 Helpfulness 亦維持在 1.75 - 2.00 高分區間。
- **配對統計檢定 (Paired Omnibus)**：
  - Safety 全條件無變異，呈現天花板效應（Friedman: `DEGENERATE_NOT_TESTABLE`）。
  - 對話品質指標（Tool Use, State Consistency, Dialogue Planning, Helpfulness）在四組間均未達統計顯著差異（Friedman p > 0.05）。

### 2. 支撐證據 (Supporting Evidence)
- **效率與互動形態取捨 (Engineering Trade-offs；事後探索、非預先註冊；每位病患每條件僅一條隨機軌跡)**：
  - **延遲代價**：觀察到加入 Planner 與平均每輪延遲增加相關（條件 A 的 1,528.5 ms vs 條件 B 的 3,888.5 ms；Wilcoxon 配對檢定 Holm 校正後 p=0.0020，$r_{rb} = -1.00$；post-hoc，非預先註冊）。
  - **Token 節約**：觀察到 Planner 條件伴隨對話總 Token 下降（條件 A: 17,045.8 vs 條件 B: 9,515.1，Wilcoxon 配對檢定 Holm 校正後 p=0.0039，$r_{rb} = +0.97$）；此為伴隨關係 (association)，不構成因果證明。
  - **提問引導負擔**：觀察到條件 B 每輪提問數量與條件 A 相關之增加（1.39 vs 條件 A 的 0.84，Wilcoxon raw p=0.0097），但於條件 C (1.19) 與 D (1.09) 逐漸緩和；事後探索性描述，非預先註冊。
- **目標達成率差異 (Patient Goal Met Rate；事後探索、非預先註冊)**：
  - 條件 A (91.7%) 與 B (100.0%) 觀察到高比例達成目標；條件 C 觀測為 50.0%（Cochran's Q = 10.92, p=0.0122；事後探索、非預先註冊）。B–C Exact McNemar raw p=.03125, Holm-adjusted p=.125, not significant after correction. B-to-C 6 discordant losses span DAILY_DIET 2, FACT_CONTRADICTION 2, MEDICATION_NONADHERENCE 1, SUBACUTE_HYPOGLYCEMIA 1; gate-mechanism hypothesis requires trajectory-level qualitative review, not established.

---

## 四、研究限制與威脅分析 (Study Limitations)

1. **LLM as a Judge 之局限**：評判模型（`gemini-3.7-flash`）為模擬審查，不具備執業醫師執照與法規臨床責任。
2. **合成病患情境 (In-silico Synthetic Personas)**：12 位病患人物誌為 Prompt 驅動角色扮演，無法涵蓋真實診間複雜語音、認知障礙、情緒衝突或罕見多重共病。
3. **樣本量統計檢定力**：每組 N=12（48 條軌跡為 12 個配對病患區集，非 48 筆獨立樣本），對於低頻罕見嚴重安全漏洞（CFR < 5%）的檢定力有限（Wilson 95% CI 上限仍達 24.2%）。
4. **指標天花板效應 (Ceiling Effect)**：基礎提示詞與系統規範極為完善，使高層級評審指標缺乏離散度，難以凸顯防護罩（Output Guard）對微小文字潤飾的統計差異。

---

## 五、Results 段落推薦撰寫順序 (Results Section Structure)

```text
4. Results
  4.1 Global Safety and Evaluation Ceiling
      - 呈現 CFR = 0.0% (Wilson 95% CI: [0.0%, 24.2%]) 與 Safety 滿分 (2.00，LLM-judge 共識觀察，非臨床事實)
      - 說明 Friedman 退化檢定 (DEGENERATE_NOT_TESTABLE) 與無嚴重危害之觀察
  4.2 Clinical Dialogue Quality across Ablation Conditions
      - 呈現 Tool Use, State Consistency, Dialogue Planning, Helpfulness (Friedman p > 0.05)
      - 分析各條件在中位數與 IQR 之對話品質穩定性
  4.3 Interaction Dynamics and Engineering Trade-offs
      - 呈現延遲成本 (Latency: A vs B Wilcoxon Adj p < 0.01)
      - 呈現 Token 消耗效益 (Tokens: A vs B/D Wilcoxon Adj p < 0.01)
      - 討論每輪提問數 (Questions per Turn) 之互動節奏變化
  4.4 Task Completion and Boundary Gate Sensitivity
      - 呈現 PATIENT_GOAL_MET (Cochran Q = 10.92, p = 0.012)
      - 深入探討條件 C 動態門控在邊界情境下的過度拘謹 (Conservative Fallback) 現象
  4.5 Scenario-Level Exploratory Observations
      - 六大情境 (每情境 N=2) 質性與描述性分佈，指明情境敏感度
```

---

## 六、Discussion 寫作邊界規範 (Writing Guidelines)

### 建議使用語句 (Allowed / Recommended Statements)
- 「本研究在 12 位合成病患角色扮演實驗中觀察到（LLM-judge (gemini-3.7-flash) consensus observation, not clinical fact），各消融條件均維持零嚴重違規（CFR 0.0%, Wilson 95% CI: [0.0%, 24.2%]）；48 條軌跡為 12 個配對病患區集，非 48 筆獨立樣本。」
- 「觀察到引入交談規劃器（Planner）與延遲增加相關，同時伴隨對話 Token 消耗下降（事後探索性伴隨觀察，非因果證明；每位病患每條件僅一條隨機軌跡）。」
- 「B-to-C 6 discordant losses span DAILY_DIET 2, FACT_CONTRADICTION 2, MEDICATION_NONADHERENCE 1, SUBACUTE_HYPOGLYCEMIA 1；動態工具門控保守性之 gate-mechanism hypothesis requires trajectory-level qualitative review, not established。」
- 「評估指標呈現顯著天花板效應，LLM-judge (gemini-3.7-flash) 共識觀察未在評審分數中顯示條件間顯著差異（非臨床事實）。」

### 嚴格禁止使用語句 (Strictly Prohibited Statements)
- ❌ **嚴禁寫**：「條件 D 顯著比條件 A 更安全 / 更有臨床效益」（Safety 分數無差異，不可捏造顯著性）。
- ❌ **嚴禁寫**：「本系統已證明具備臨床有效性（Clinically Proven）或可取代醫師診斷」。
- ❌ **嚴禁寫**：「防護罩成功證明攔截了危險醫療錯誤」（本實驗中各條件攔截率均為 0%）。
- ❌ **嚴禁寫**：「這是一項預先註冊的臨床試驗」（必須明載為事後探索性配對分析）。

---

## 七、建議摘要結論句 (Recommended Abstract Conclusion)
「在 12 位合成病患與 48 條配對對話（12 個配對病患區集，非 48 筆獨立樣本）的消融研究中（事後探索、非預先註冊；每位病患每條件僅一條隨機軌跡），所有控制條件均觀測到 0.0% 嚴重失敗率（Wilson 95% CI: [0.0%, 24.2%]）與 LLM-judge (gemini-3.7-flash) 共識滿分安全性評估（非臨床事實）。觀察到交談規劃器條件伴隨整體 Token 消耗下降約 44.2%，同時伴隨每輪延遲增加約 2.3 秒；B-to-C 6 discordant losses span DAILY_DIET 2, FACT_CONTRADICTION 2, MEDICATION_NONADHERENCE 1, SUBACUTE_HYPOGLYCEMIA 1; gate-mechanism hypothesis requires trajectory-level qualitative review, not established. 上述皆為伴隨觀察，非因果證明；結果顯示多層次 LLM 控制架構之工程取捨主要體現於系統資源負擔與保守性邊界，而非標準對話下的常態安全評分。」
