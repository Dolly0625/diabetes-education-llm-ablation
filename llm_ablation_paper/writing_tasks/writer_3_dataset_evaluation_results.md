# Writer 3 — 資料來源、23 案例、Judge 方法、指標、完整結果、圖表與 Error Analysis

> 路徑以 `llm_ablation_paper/writing_tasks/` 為基準；`../` = `llm_ablation_paper/`。

## 1. 負責與不負責範圍

**負責**
- 資料來源（`../safety_stress_test/v2/cases_v2.jsonl`、`../safety_stress_test/v2/benign_controls_v2.jsonl`、`../safety_stress_test/v2/reference_facts_v2.json`）。
- 23 案例（12 main／2 探針／9 良性）與 6 類 CF 對應。
- Judge 方法（盲測、同模型 2 次、tie-break、canary、schema/taxonomy）。
- 指標定義（CFR_strict／CFR_composite、FACT、QUALITY、over-refusal、scanner–judge 不一致、Wilson CI）。
- 完整結果與 Error Analysis。
- Table 1、Table 2、Figure 2／3／4。

**不負責**
- Introduction／Related Work（Writer 1）；A–D 架構與 Figure 1（Writer 2）；Discussion／Limitations／Conclusion／Abstract（Writer 4）。

## 1a. 頁數預算（3.3 頁，含主要表格與圖）

- Dataset / Evaluation / Results / Error Analysis，共 **3.3 頁**（Table 1／Table 2 與 Figure 2–4 占頁計入）。
- 交稿首行須填 metadata：`預估頁數：<x.x>　圖表數：<n>（圖 a／表 b）　引用數：<m>　所屬頁數預算：3.3`。

## 2. 必讀相對路徑

- `../PAPER_WRITING_HANDOFF_ZH.md`（第 5–8、11、13 節）
- `../safety_stress_test/v2/V2_FULL_RESULT.md`
- `../safety_stress_test/v2/V2_FULL_METRICS.json`（唯一 committed 數字來源）
- `../safety_stress_test/v2/judge_prompt_v2.md`、`../safety_stress_test/v2/judge_schema_v2.json`
- `../safety_stress_test/v2/critical_failure_taxonomy_v2.md`
- `../safety_stress_test/v2/cases_v2.jsonl`、`../safety_stress_test/v2/benign_controls_v2.jsonl`
- `../PAPER_NARRATIVE_BLUEPRINT_ZH.md`（統一敘事藍圖，**必讀**；Results 敘事順序與圖表論點見第 4 節）

## 3. 固定數字（全表照抄，不得重算）

| 指標 | A | B | C | D |
|---|---|---|---|---|
| CFR_strict（N=12） | 0/12 | 0/12 | 0/12 | 0/12 |
| CFR_composite（N=12） | 0/12 | 0/12 | 0/12 | 0/12 |
| FACT main（N=12） | 2 | 4 | 0 | 0 |
| FACT probe（N=2） | 1 | 1 | 2 | 2 |
| QUALITY（N=12） | 0 | 1 | 0 | 1 |
| over-refusal（N=9） | 0 | 0 | 0 | 0 |
| scanner–judge 不一致（N=14） | 2 | 3 | 2 | 2 |

- Wilson 95% 上限：CFR main **24.25%**、family N=2 **65.76%**、over-refusal **29.91%**（四組同）。
- 規模：**92/92** 軌跡、**204** 回合、排除 **0**、完整區塊 **23/23**；FACT 代碼合計 11／2／1（NEGH／POSITIVE_ADDITION／RESEARCH_GT）；escalations **0**。
- Judge：**190** 呼叫（184＋6 canary）、canary **6/6**、tie-break **0**。
- 模型：Talker/Planner `gemini-3.5-flash-lite`（0.3／0.1）；Judge `gemini-3.7-flash`（0.0）。
- 成本：talker **US$0.2157378** ＋ judge **US$0.674631** = **US$0.8903688 ≈ TWD 28.49**（匯率 32.0）。
- 抽樣建議（描述性，非效果結論）：A 的 research-GT 不一致、NEGH 探針（合計 11 次）。

## 4. 禁止主張

禁止：臨床／醫師驗證、降低住院、100% 安全；Judge 等同醫師；scanner 等同 ground truth；同模型重複＝人類一致性；把 FACT 升格 critical；只報 strict 或只報 composite；把任一單一指標稱「the safety result」；zero observed 寫成零風險；**合併統計**（12×4／v1／v2 不得 pooled）。必須強調：zero observed ≠ 零風險、family N=2 區間寬、N=12 不得過度推論。

## 5. 交付檔名

`drafts/writer_3_dataset_evaluation_results.md`（＋「待補引用清單」）。

## 6. 引用占位規則

內文 `[@REF-KEY]`；圖 `{FIG:n}`、表 `{TAB:n}`；數字直接寫出並標來源相對路徑；不得虛構文獻。

## 7. 圖表責任

- **Table 1**：23 案例與 6 類 CF（12 main＋2 探針＋9 良性）。
- **Table 2**：完整結果表（上表 7 指標 × 4 組，附 Wilson）。
- **Figure 2**：CFR_strict 與 CFR_composite（含 Wilson 95% CI）。
- **Figure 3**：FACT main vs probe 分組長條。
- **Figure 4**：scanner–judge 不一致（方向：scanner_only 9／judge_only 0／both 0）。

## 8. 完成定義

交付檔名正確；表格數字與 `V2_FULL_METRICS.json` 完全一致並標來源；無禁止主張、含限定語；Table 1／2 與 Figure 2–4 圖說齊備；引用用佔位並附清單；不含他章內容；通過連結與數字測試。

## 9. 可直接貼給 AI 的 prompt

```
你協助撰寫論文「資料來源、案例、Judge 方法、指標、完整結果、圖表與 Error Analysis」。我不寫程式。
先讀 llm_ablation_paper/writing_tasks/writer_3_dataset_evaluation_results.md、
llm_ablation_paper/PAPER_WRITING_HANDOFF_ZH.md（第 5-8、11、13 節）、
llm_ablation_paper/safety_stress_test/v2/V2_FULL_RESULT.md 與 V2_FULL_METRICS.json。

規則：
1. 所有數字照抄任務檔「固定數字」，不得重算或更改；每個數字標來源相對路徑。
2. 一律同時報 CFR_strict 與 CFR_composite；FACT 不得升格 critical；scanner 非 ground truth。
3. 必加限定語：模擬情境、指定模型版本、exploratory、非預先註冊、非臨床；
   強調 zero observed ≠ 零風險、family N=2 區間寬。
4. 禁止臨床/醫師驗證、Judge 等同醫師、同模型重複=人類一致性、把 12×4／v1／v2 合併統計。
5. 引用用 [@REF-KEY] 佔位，末尾附「待補引用清單」。
6. 不要寫 Introduction、A-D 架構與 Discussion。

交付：drafts/writer_3_dataset_evaluation_results.md，含 Table 1、Table 2、Figure 2/3/4 的圖說與資料來源。
先給我大綱與每張圖表的草稿，我確認後再寫全文。
```
