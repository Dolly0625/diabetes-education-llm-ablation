# Writer 2 — 系統架構、A/B/C/D、實作與可重現性

> 路徑以 `llm_ablation_paper/writing_tasks/` 為基準；`../` = `llm_ablation_paper/`。

## 1. 負責與不負責範圍

**負責**
- 系統架構（感知層、Input Guard、臨床規劃、雙軌 RAG、生成層、Output Guard 的概念圖述）。
- A/B/C/D 定義與**唯一差異原則**（三開關；Input Guard 固定 ON；三輔助行為固定 OFF）。
- 實作與可重現性（模型、temperature、固定腳本、無 Patient Agent、blinded 匯出、fail-closed 閘門）。
- Figure 1（A–D 架構與唯一差異開關）。

**不負責**
- Introduction／Related Work（Writer 1）；資料與結果數字（Writer 3）；Discussion／Limitations（Writer 4）。

## 1a. 頁數預算（2.2 頁，含 Figure 1）

- System Architecture + A/B/C/D + Implementation / Reproducibility，共 **2.2 頁**（Figure 1 占頁計入）。
- 交稿首行須填 metadata：`預估頁數：<x.x>　圖表數：<n>　引用數：<m>　所屬頁數預算：2.2`。

## 2. 必讀相對路徑

- `../PAPER_WRITING_HANDOFF_ZH.md`（第 4 節 A–D 定義）
- `../shared/SYSTEM_OVERVIEW.md`、`../shared/RESEARCH_PROTOCOL.md`
- `../safety_stress_test/v2/V2_FULL_BATCH_PROTOCOL.md`（fail-closed／模型參數）
- `../safety_stress_test/v2/PROTOCOL_V2.md`（唯一差異、非可比性）
- `../PAPER_NARRATIVE_BLUEPRINT_ZH.md`（統一敘事藍圖，**必讀**；Methods 敘事見第 3 節）

## 3. 固定數字（引用即可，不得重算）

- 模型：Talker/Planner `gemini-3.5-flash-lite`（temp **0.3／0.1**）；Judge `gemini-3.7-flash`（temp **0.0**）。
- A/B/C/D 三開關：A OFF-OFF-OFF、B ON-OFF-OFF、C ON-ON-OFF、D ON-ON-ON。
- 規模：**92 軌跡 / 204 回合**、固定 3 輪（benign 1 輪）、**不使用 Patient Agent**。
- 來源：`../safety_stress_test/v2/V2_FULL_BATCH_PROTOCOL.md`、`../safety_stress_test/v2/PROTOCOL_V2.md`。

## 4. 禁止主張

禁止把 A–D 寫成「D 最安全」或任何**效果結論**；禁止臨床／部署主張；禁止把 canary／guard-reachability 當安全效果；禁止合併統計。必須加限定語：探索性、非預先註冊、非臨床、指定模型版本。

## 5. 交付檔名

`drafts/writer_2_system_ablation_method.md`（＋「待補引用清單」）。

## 6. 引用占位規則

內文 `[@REF-KEY]`；圖 `{FIG:n}`、表 `{TAB:n}`；數字標來源相對路徑；不得虛構文獻。

## 7. 圖表責任

**Figure 1**（A–D 架構與唯一差異開關）：提供圖說、三開關表、並標明「其餘固定不變」。可用 `{TAB:1}` 引出（若需與 Writer 3 的 Table 1 區隔，改用 `{FIG:1}` 自帶小表）。

## 8. 完成定義

交付檔名正確；A–D 與唯一差異正確；只用固定數字且標來源；無效果／臨床主張；Figure 1 圖說與資料來源齊備；引用用佔位並附清單；不含他章內容；通過連結與數字測試。

## 9. 可直接貼給 AI 的 prompt

```
你協助撰寫論文「系統架構、A/B/C/D 消融、實作與可重現性」章節。我不寫程式。
先讀 llm_ablation_paper/writing_tasks/writer_2_system_ablation_method.md、
llm_ablation_paper/PAPER_WRITING_HANDOFF_ZH.md（第 4 節）、
llm_ablation_paper/shared/SYSTEM_OVERVIEW.md、
llm_ablation_paper/safety_stress_test/v2/V2_FULL_BATCH_PROTOCOL.md。

規則：
1. A/B/C/D 三開關照抄：A OFF-OFF-OFF、B ON-OFF-OFF、C ON-ON-OFF、D ON-ON-ON；
   Input Guard 固定 ON；三輔助行為固定 OFF；強調唯一差異原則。
2. 只用任務檔固定數字，標來源相對路徑；不得重算或發明。
3. 禁止任何「哪一組更安全」的效果結論、臨床或部署主張、canary/guard 當安全效果、合併統計。
4. 引用用 [@REF-KEY] 佔位，末尾附「待補引用清單」。
5. 不要寫 Introduction、結果數字與 Discussion。

交付：drafts/writer_2_system_ablation_method.md，並附 Figure 1 的圖說與資料來源。
先給我大綱與 Figure 1 草圖描述，我確認後再寫全文。
```
