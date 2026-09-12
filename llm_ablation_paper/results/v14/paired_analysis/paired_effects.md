# 糖尿病衛教大型語言模型消融實驗事後探索性配對統計報告 (v14)

> [!IMPORTANT]
> **研究性質聲明**：本統計分析為評審評判完成後之**事後探索性配對分析 (Post-hoc Exploratory Paired Analysis)**，**非預先註冊 (Not Preregistered)**；每位病患每條件僅一條隨機軌跡 (one stochastic trajectory per patient-condition)。
> 實驗嚴格以**病患為配對封閉單元 (Block/Pairing: 12 位病患 × 4 條件；48 條軌跡為 12 個配對病患區集，絕非 48 筆獨立樣本)**。
> 所有統計檢定皆採用非參數配對檢定（Friedman、Wilcoxon 雙尾、Cochran's Q、Exact McNemar），並施加 Holm-Bonferroni 多重比較校正。

## 1. 描述性統計摘要 (N=12 病患 / 組)

| 指標 | 條件 A (Baseline) | 條件 B (Planner) | 條件 C (Planner+Gate) | 條件 D (Full) | 單位/範圍 |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **安全性 (Safety；LLM-judge 共識觀察，非臨床事實)** | 2.00 (中位 2.00, IQR 0.00) | 2.00 (中位 2.00, IQR 0.00) | 2.00 (中位 2.00, IQR 0.00) | 2.00 (中位 2.00, IQR 0.00) | 0.0 - 2.0 |
| **工具使用 (Tool Use)** | 1.92 (中位 2.00, IQR 0.00) | 1.92 (中位 2.00, IQR 0.00) | 1.75 (中位 2.00, IQR 0.50) | 1.92 (中位 2.00, IQR 0.00) | 0.0 - 2.0 |
| **狀態一致性 (State Cons.)** | 2.00 (中位 2.00, IQR 0.00) | 2.00 (中位 2.00, IQR 0.00) | 1.92 (中位 2.00, IQR 0.00) | 2.00 (中位 2.00, IQR 0.00) | 0.0 - 2.0 |
| **對話規劃 (Dialogue Plan.)** | 1.96 (中位 2.00, IQR 0.00) | 1.79 (中位 2.00, IQR 0.12) | 1.75 (中位 2.00, IQR 0.25) | 2.00 (中位 2.00, IQR 0.00) | 0.0 - 2.0 |
| **實用性 (Helpfulness)** | 2.00 (中位 2.00, IQR 0.00) | 1.92 (中位 2.00, IQR 0.00) | 2.00 (中位 2.00, IQR 0.00) | 2.00 (中位 2.00, IQR 0.00) | 0.0 - 2.0 |
| **每輪平均提問數** | 0.84 (中位 0.90, IQR 0.25) | 1.39 (中位 1.45, IQR 0.39) | 1.19 (中位 1.10, IQR 0.32) | 1.09 (中位 1.00, IQR 0.10) | 客觀測量 |
| **每輪平均延遲 (ms)** | 1528.51 (中位 1442.50, IQR 428.45) | 3888.50 (中位 3839.60, IQR 444.95) | 4151.57 (中位 4058.70, IQR 800.88) | 3727.18 (中位 3774.30, IQR 1007.82) | 客觀測量 |
| **對話總 Tokens** | 17045.83 (中位 17834.00, IQR 4025.50) | 9515.08 (中位 9247.50, IQR 2506.75) | 9984.83 (中位 10631.00, IQR 6711.75) | 8278.67 (中位 6780.50, IQR 6416.75) | 客觀測量 |
| **模型呼叫次數** | 5.25 (中位 5.00, IQR 1.00) | 5.33 (中位 5.00, IQR 0.25) | 5.17 (中位 5.50, IQR 1.00) | 5.42 (中位 5.00, IQR 1.00) | 客觀測量 |
| **終止對話輪數** | 4.17 (中位 4.00, IQR 1.00) | 3.92 (中位 4.00, IQR 0.25) | 4.33 (中位 5.00, IQR 1.00) | 4.58 (中位 5.00, IQR 0.25) | 客觀測量 |

## 2. 配對 Omnibus 檢定 (Friedman & Cochran's Q)

| 指標名稱 | 檢定方法 | 狀態 (Status) | 檢定量 | 自由度 df | 原始 P 值 (Raw P) | 統計意涵與註記 |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| 安全性 (Safety；LLM-judge 共識觀察，非臨床事實) | Friedman | `DEGENERATE_NOT_TESTABLE` | - | 3 | - | 退化 (無變異，不可檢定)；全條件觀測值皆為常數，無變異可檢定 (不可標記為 p=0) |
| 工具使用 (Tool Use) | Friedman | `TESTED` | 3.0000 | 3 | 0.3916 | 未達顯著 (p ≥ 0.05)；檢驗通過 |
| 狀態一致性 (State Cons.) | Friedman | `TESTED` | 3.0000 | 3 | 0.3916 | 未達顯著 (p ≥ 0.05)；檢驗通過 |
| 對話規劃 (Dialogue Plan.) | Friedman | `TESTED` | 4.2308 | 3 | 0.2376 | 未達顯著 (p ≥ 0.05)；檢驗通過 |
| 實用性 (Helpfulness) | Friedman | `TESTED` | 3.0000 | 3 | 0.3916 | 未達顯著 (p ≥ 0.05)；檢驗通過 |
| 每輪平均提問數 | Friedman | `TESTED` | 11.3304 | 3 | 0.0101 | **顯著差異 (p=0.0101)**；檢驗通過 |
| 每輪平均延遲 (ms) | Friedman | `TESTED` | 25.9000 | 3 | <0.0001 | **顯著差異 (p<0.0001)**；檢驗通過 |
| 對話總 Tokens | Friedman | `TESTED` | 17.6000 | 3 | 0.0005 | **顯著差異 (p=0.0005)**；檢驗通過 |
| 模型呼叫次數 | Friedman | `TESTED` | 0.4021 | 3 | 0.9398 | 未達顯著 (p ≥ 0.05)；檢驗通過 |
| 終止對話輪數 | Friedman | `TESTED` | 5.2597 | 3 | 0.1537 | 未達顯著 (p ≥ 0.05)；檢驗通過 |
| **病患目標達成率 (Goal Met)** | Cochran's Q | `TESTED` | 10.9200 | 3 | 0.0122 | **顯著條件間差異 (p=0.0122)** |

## 3. 指定成對比較與效果量 (A-B / B-C / C-D / A-D)

採用配對 Wilcoxon Signed-Rank 雙尾檢定，並以 **Matched-Pairs Rank-Biserial Correlation ($r_{rb}$)** 衡量效果量（$[-1, 1]$）；多重比較施加 **Holm-Bonferroni** 校正。

| 指標 | 成對比較 | 非零 Pair 數 | Rank-Biserial $r_{rb}$ | 原始 P 值 (Raw P) | 校正後 P 值 (Holm Adj P) | 檢定結論 |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| 安全性 (Safety；LLM-judge 共識觀察，非臨床事實) | A-B | 0 | 0.00 | - | - | `NOT_TESTABLE` (差值全為 0) |
| 安全性 (Safety；LLM-judge 共識觀察，非臨床事實) | B-C | 0 | 0.00 | - | - | `NOT_TESTABLE` (差值全為 0) |
| 安全性 (Safety；LLM-judge 共識觀察，非臨床事實) | C-D | 0 | 0.00 | - | - | `NOT_TESTABLE` (差值全為 0) |
| 安全性 (Safety；LLM-judge 共識觀察，非臨床事實) | A-D | 0 | 0.00 | - | - | `NOT_TESTABLE` (差值全為 0) |
| 工具使用 (Tool Use) | A-B | 3 | +0.00 | 1.0000 | 1.0000 | 未達顯著 (Adj p ≥ 0.05) |
| 工具使用 (Tool Use) | B-C | 5 | +0.47 | 0.3340 | 1.0000 | 未達顯著 (Adj p ≥ 0.05) |
| 工具使用 (Tool Use) | C-D | 5 | -0.47 | 0.3340 | 1.0000 | 未達顯著 (Adj p ≥ 0.05) |
| 工具使用 (Tool Use) | A-D | 3 | +0.00 | 1.0000 | 1.0000 | 未達顯著 (Adj p ≥ 0.05) |
| 狀態一致性 (State Cons.) | A-B | 0 | 0.00 | - | - | `NOT_TESTABLE` (差值全為 0) |
| 狀態一致性 (State Cons.) | B-C | 1 | +1.00 | 0.3173 | 0.6346 | 未達顯著 (Adj p ≥ 0.05) |
| 狀態一致性 (State Cons.) | C-D | 1 | -1.00 | 0.3173 | 0.6346 | 未達顯著 (Adj p ≥ 0.05) |
| 狀態一致性 (State Cons.) | A-D | 0 | 0.00 | - | - | `NOT_TESTABLE` (差值全為 0) |
| 對話規劃 (Dialogue Plan.) | A-B | 4 | +0.70 | 0.1936 | 0.5809 | 未達顯著 (Adj p ≥ 0.05) |
| 對話規劃 (Dialogue Plan.) | B-C | 5 | +0.07 | 0.8875 | 0.8875 | 未達顯著 (Adj p ≥ 0.05) |
| 對話規劃 (Dialogue Plan.) | C-D | 3 | -1.00 | 0.0833 | 0.3331 | 未達顯著 (Adj p ≥ 0.05) |
| 對話規劃 (Dialogue Plan.) | A-D | 1 | -1.00 | 0.3173 | 0.6346 | 未達顯著 (Adj p ≥ 0.05) |
| 實用性 (Helpfulness) | A-B | 1 | +1.00 | 0.3173 | 0.6346 | 未達顯著 (Adj p ≥ 0.05) |
| 實用性 (Helpfulness) | B-C | 1 | -1.00 | 0.3173 | 0.6346 | 未達顯著 (Adj p ≥ 0.05) |
| 實用性 (Helpfulness) | C-D | 0 | 0.00 | - | - | `NOT_TESTABLE` (差值全為 0) |
| 實用性 (Helpfulness) | A-D | 0 | 0.00 | - | - | `NOT_TESTABLE` (差值全為 0) |
| 每輪平均提問數 | A-B | 11 | -0.88 | 0.0097 | 0.0388 | **顯著 (p=0.0388 Holm-adjusted)** |
| 每輪平均提問數 | B-C | 11 | +0.44 | 0.1949 | 0.3898 | 未達顯著 (Adj p ≥ 0.05) |
| 每輪平均提問數 | C-D | 12 | -0.03 | 0.9697 | 0.9697 | 未達顯著 (Adj p ≥ 0.05) |
| 每輪平均提問數 | A-D | 10 | -0.60 | 0.0920 | 0.2759 | 未達顯著 (Adj p ≥ 0.05) |
| 每輪平均延遲 (ms) | A-B | 12 | -1.00 | 0.0005 | 0.0020 | **顯著 (p=0.0020 Holm-adjusted)** |
| 每輪平均延遲 (ms) | B-C | 12 | -0.46 | 0.1763 | 0.1763 | 未達顯著 (Adj p ≥ 0.05) |
| 每輪平均延遲 (ms) | C-D | 12 | +0.62 | 0.0640 | 0.1279 | 未達顯著 (Adj p ≥ 0.05) |
| 每輪平均延遲 (ms) | A-D | 12 | -1.00 | 0.0005 | 0.0020 | **顯著 (p=0.0020 Holm-adjusted)** |
| 對話總 Tokens | A-B | 12 | +0.97 | 0.0010 | 0.0039 | **顯著 (p=0.0039 Holm-adjusted)** |
| 對話總 Tokens | B-C | 12 | -0.18 | 0.6221 | 0.7607 | 未達顯著 (Adj p ≥ 0.05) |
| 對話總 Tokens | C-D | 12 | +0.31 | 0.3804 | 0.7607 | 未達顯著 (Adj p ≥ 0.05) |
| 對話總 Tokens | A-D | 12 | +0.87 | 0.0049 | 0.0146 | **顯著 (p=0.0146 Holm-adjusted)** |
| 模型呼叫次數 | A-B | 10 | -0.09 | 0.7907 | 1.0000 | 未達顯著 (Adj p ≥ 0.05) |
| 模型呼叫次數 | B-C | 10 | +0.09 | 0.7940 | 1.0000 | 未達顯著 (Adj p ≥ 0.05) |
| 模型呼叫次數 | C-D | 7 | -0.18 | 0.6709 | 1.0000 | 未達顯著 (Adj p ≥ 0.05) |
| 模型呼叫次數 | A-D | 8 | -0.08 | 0.8314 | 1.0000 | 未達顯著 (Adj p ≥ 0.05) |
| 終止對話輪數 | A-B | 6 | +0.43 | 0.3173 | 0.9929 | 未達顯著 (Adj p ≥ 0.05) |
| 終止對話輪數 | B-C | 8 | -0.44 | 0.2482 | 0.9929 | 未達顯著 (Adj p ≥ 0.05) |
| 終止對話輪數 | C-D | 6 | -0.24 | 0.5951 | 0.9929 | 未達顯著 (Adj p ≥ 0.05) |
| 終止對話輪數 | A-D | 7 | -0.43 | 0.3008 | 0.9929 | 未達顯著 (Adj p ≥ 0.05) |
| **病患目標達成率 (Goal Met)** | A-B | 1 (b=0, c=1) | - | 1.0000 | 1.0000 | 未達顯著 (Adj p ≥ 0.05) |
| **病患目標達成率 (Goal Met)** | B-C | 6 (b=6, c=0) | - | 0.0312 | 0.1250 | 未達顯著 (Adj p ≥ 0.05) |
| **病患目標達成率 (Goal Met)** | C-D | 4 (b=1, c=3) | - | 0.6250 | 1.0000 | 未達顯著 (Adj p ≥ 0.05) |
| **病患目標達成率 (Goal Met)** | A-D | 5 (b=4, c=1) | - | 0.3750 | 1.0000 | 未達顯著 (Adj p ≥ 0.05) |

## 4. 完全無變異指標描述性說明

1. **安全性評分 (Safety Score；LLM-judge (gemini-3.7-flash) consensus observation, not clinical fact)**：48 條配對對話軌跡（12 位病患 × 4 條件之配對區集，非 48 筆獨立樣本）之評審一致性評分全數為 **2.00 (滿分)**，方差為 0。本現象反映出強烈之**天花板效應 (Ceiling Effect)**，故 Friedman 檢定退化（`DEGENERATE_NOT_TESTABLE`），不可輸出 p=0。
2. **防護罩攔截率與未授權工具呼叫 (zero observed only)**：全條件下 `guard_override_rate`、`unexposed_tool_call_rate`、`premature_summary_call_rate` 觀測值皆為 0（zero observed only）；A/B 條件下所有工具皆已開放、A-C 條件下無輸出防護罩，結構上無資訊量 (structurally uninformative in A/B (all tools exposed) and A-C (no output guard))，無法證明 Talker 自我克制 (cannot establish Talker self-restraint)，亦不可解讀為越權行為缺席之證據。

## 5. 探索性核心發現與邊界約束

1. **延遲與 Token 成本 (Efficiency Trade-off；事後探索、非預先註冊；每位病患每條件僅一條隨機軌跡)**：
   - 觀察到加入交談規劃器與每輪延遲增加相關（A: 1528ms vs B: 3888ms，Wilcoxon Holm-adjusted p=0.0020，$r_{rb} = -1.00$；post-hoc，非預先註冊）。
   - 觀察到總 Token 消耗與 Planner 條件相關之下降（A: 17,045 tokens vs B: 9,515 tokens，Wilcoxon Holm-adjusted p=0.0039，$r_{rb} = +0.97$）；此為伴隨觀察 (association)，不構成 Planner 收斂對話之因果證明；每位病患每條件僅一條隨機軌跡 (one stochastic trajectory per patient-condition)。
2. **病患目標達成率 (Goal Met Rate；事後探索、非預先註冊)**：
   - 條件 A (91.7%) 與 B (100.0%) 觀察到高目標達成率；條件 C 觀測為 50.0%。B–C Exact McNemar raw p=.03125, Holm-adjusted p=.125, not significant after correction.
   - B-to-C 6 discordant losses span DAILY_DIET 2, FACT_CONTRADICTION 2, MEDICATION_NONADHERENCE 1, SUBACUTE_HYPOGLYCEMIA 1; gate-mechanism hypothesis requires trajectory-level qualitative review, not established. 上述為伴隨觀察，非因果證明；每位病患每條件僅一條隨機軌跡。
3. **嚴格禁止之主張**：
   - 嚴禁聲稱「條件 D 顯著更安全」（Safety 為 LLM-judge (gemini-3.7-flash) consensus observation, not clinical fact；全條件皆為 2.0，無統計差異）。
   - 嚴禁聲稱「具備臨床有效性」或「已證明醫療改善」（本實驗為模擬環境下之工程架構消融，非臨床試驗；事後探索、非預先註冊）。
