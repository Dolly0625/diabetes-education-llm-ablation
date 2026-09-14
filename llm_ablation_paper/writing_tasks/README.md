# 論文寫作分工（writing_tasks）— 四人平行協作

> 給**不寫程式**的論文作者四人小組。所有數字皆已驗收、**不需重算**、**不得修改**。
> 本目錄路徑以 `llm_ablation_paper/writing_tasks/` 為基準；文中的 `../` 指 `llm_ablation_paper/`。
> 主交接包：`../PAPER_WRITING_HANDOFF_ZH.md`；提示詞：`../WRITER_START_PROMPT_ZH.md`。

---

## 1. 四人分工總表

| 成員 | 任務檔 | 負責章節 | 可立即開始 | 交付檔名（建立於 `drafts/`） |
|---|---|---|---|---|
| Writer 1 | `writer_1_intro_related_work.md` | Introduction、Related Work、Research Questions | ✅ 可平行 | `drafts/writer_1_intro_related_work.md` |
| Writer 2 | `writer_2_system_ablation_method.md` | 系統架構、A/B/C/D、實作與可重現性 | ✅ 可平行 | `drafts/writer_2_system_ablation_method.md` |
| Writer 3 | `writer_3_dataset_evaluation_results.md` | 資料來源、23 案例、Judge 方法、指標、完整結果、圖表、Error Analysis | ✅ 可平行 | `drafts/writer_3_dataset_evaluation_results.md` |
| Writer 4 | `writer_4_discussion_integration.md` | Discussion、Limitations、Conclusion、Abstract、**全文整合** | ⚠️ 可先寫 Discussion/Limitations/Conclusion 初稿；**全文整合須等 1–3 完成** | `drafts/writer_4_discussion_integration.md` |

---

## 2. 認領機制（避免重複）

1. 四人各自挑選**尚未被認領**的任務（上方總表）。
2. 在下方「認領表」新增一列，填入**姓名**與**branch 名稱**；未回報前不算認領，先回報者先得。
3. 若兩人同時想要同一任務，以**較早回報**者為準，另一人改挑其他任務。
4. branch 命名建議：`writing/w1-intro`、`writing/w2-method`、`writing/w3-results`、`writing/w4-integration`。

### 認領表（請自行新增列）

| 任務 | 姓名 | branch | 認領時間 |
|---|---|---|---|
| Writer 1 |  |  |  |
| Writer 2 |  |  |  |
| Writer 3 |  |  |  |
| Writer 4 |  |  |  |

---

## 3. 依賴順序

- **W1、W2、W3 可立即平行**（互不阻塞）。
- **W4**：可先寫 Discussion／Limitations／Conclusion 初稿；**Abstract 與全文整合必須等 W1–W3 交付後**才進行。
- W3 的結果（第 8 節）是 W4 Discussion 的輸入；W2 的 A–D 定義是 W1／W3 的引用依據。

---

## 4. 回傳方式

> `drafts/` 目錄**目前不存在**，請在**自己的 branch** 建立後放入草稿（例如 `drafts/writer_1_intro_related_work.md`）。

1. 依各自任務檔的「交付檔名」建立草稿檔（`drafts/…md`）。
2. 在自己的 branch commit，開 PR（或依小組約定）並在 `README.md` 認領表回報。
3. 回報格式（貼在 PR 描述或群組）：
   ```
   成員：Writer N
   branch：<branch 名稱>
   交付檔：<檔名>
   狀態：初稿 / 修訂 / 完成
   使用數字來源：<引用的相對路徑>
   未解問題：<列出或寫「無」>
   ```
4. **回傳方式不含原始逐次 token／run_ids／condition mapping**；這些屬本機證據，僅供查核。
5. **交稿須附 page metadata**（預估頁數／圖表數／引用數；格式見第 11 節），並對照第 11 節頁數預算。

---

## 5. 固定數字（所有成員共用；不得重算或更改）

- 軌跡 **92/92**；助理回合 **204**；排除 **0**；完整區塊 **23/23**。
- 四組 **CFR_strict 皆 0/12**、**CFR_composite 皆 0/12**（Wilson 95% 上限 **24.25%**；family N=2 上限 **65.76%**）。
- FACT（main，N=12）：A **2**、B **4**、C **0**、D **0**；FACT（probe，N=2）：A **1**、B **1**、C **2**、D **2**。
- QUALITY（N=12）：A **0**、B **1**、C **0**、D **1**；over-refusal（N=9）：皆 **0**。
- scanner–judge 不一致（N=14）：A **2**、B **3**、C **2**、D **2**（方向 scanner_only 9／judge_only 0／both 0）。
- Judge：**190** 次呼叫（184＋6 canary）、canary **6/6**、tie-break **0**。
- 成本：talker **US$0.2157378** ＋ judge **US$0.674631** = **US$0.8903688 ≈ TWD 28.49**（匯率 32.0）。
- 唯一 committed 數字來源：`../safety_stress_test/v2/V2_FULL_METRICS.json` 與 `../safety_stress_test/v2/V2_FULL_RESULT.md`。

---

## 6. 禁止主張（所有成員共用）

- 禁止：臨床驗證、醫師／病患驗證、降低住院／停藥／低血糖、100% 安全、完全無幻覺、可直接部署。
- 禁止：把 LLM Judge 寫成醫師；把掃描器寫成 ground truth／評審；把同模型重複評分寫成人類一致性。
- 禁止：把 FACT 一律升格為 critical failure；只報 CFR_strict 或只報 CFR_composite；把任單一指標稱為「the safety result」。
- 禁止：**合併統計**（正式 12×4、v1、v2 三者不得 pooled／相加／互相覆寫）；v2 為主要探索性結果。
- 禁止：把 zero observed 寫成零風險；把 canary 或 guard-reachability 當安全效果。
- 必須加限定語：在本研究的模擬情境中、對指定模型與版本、LLM Judge 評分顯示、exploratory／非預先註冊／非臨床。

---

## 7. 引用占位規則（所有人一致）

- 本文引用一律用佔位符，**不要**自行發明條目：內文用 `[@REF-KEY]`，圖表用 `{FIG:n}`、表格用 `{TAB:n}`。
- 每份草稿末尾附「待補引用清單」，逐條列出 `REF-KEY` 與你要引用的類型（例：`藥品仿單`、`系統性回顧`），由整合者統整。
- **數字禁止放在引用佔位符內**；數字一律直接寫出並標註來源相對路徑。

---

## 8. 圖表責任

| 圖表 | 內容 | 負責人 |
|---|---|---|
| Figure 1 | A–D 架構與唯一差異開關 | Writer 2 |
| Figure 2 | CFR_strict 與 CFR_composite（含 Wilson CI） | Writer 3 |
| Figure 3 | FACT（main vs probe）分組 | Writer 3 |
| Figure 4 | scanner–judge 不一致（方向） | Writer 3 |
| Table 1 | 23 案例與 6 類 CF | Writer 3 |
| Table 2 | 完整結果表 | Writer 3 |

---

## 9. 完成定義（共通 gate）

一份草稿算「完成」需全部滿足：
1. 交付檔名正確、位於 `drafts/`。
2. 只使用第 5 節固定數字，且每個數字標註來源相對路徑。
3. 無第 6 節禁止主張；含必要限定語。
4. 引用使用 `[@REF-KEY]` 佔位並附「待補引用清單」。
5. 負責章節齊備、不含「不負責範圍」內容。
6. 圖表責任清楚（交付含圖說與資料來源）。
7. **附 page metadata 且不超過第 11 節該章節頁數預算**（超出須說明並優先精簡重複背景，不得刪限制段落）。
8. 通過連結與數字測試（見 `../safety_stress_test/v2/tests/test_writing_tasks_docs.py`）。

---

## 10. 檔案索引

- `../PAPER_NARRATIVE_BLUEPRINT_ZH.md`（統一敘事藍圖，**全員必讀**）
- `writer_1_intro_related_work.md`
- `writer_2_system_ablation_method.md`
- `writer_3_dataset_evaluation_results.md`
- `writer_4_discussion_integration.md`

---

## 11. 頁數預算（目標約 12 頁；**保守配置：References 計入 12 頁內**）

| 成員 | 章節 | 頁數 |
|---|---|---|
| Writer 1 | Introduction + Related Work | **2.5** |
| Writer 2 | System Architecture + A/B/C/D + Implementation / Reproducibility | **2.2** |
| Writer 3 | Dataset / Evaluation / Results / Error Analysis（含主要表格與圖） | **3.3** |
| Writer 4 | Abstract + Discussion + Limitations + Conclusion + 全文整合 | **2.6** |
| References | 參考文獻 | **1.4** |
| **合計** | | **12.0** |

**規則**
1. **圖表占頁計入所屬章節頁數**（不另佔）；頁數估算須含圖表所佔空間。
2. 每位成員**交稿必須標示**：預估頁數、圖表數、引用數（見下方「交稿 metadata」）。
3. **Writer 4 整合時不得靠刪除限制段落壓頁**；頁數超出時**優先精簡重複背景**（Introduction／Related Work 與 Discussion 的重述）。
4. 上表為**保守配置**（假設 references 計入 12 頁）。**若會議正式規定 references 不計頁**，則記為「**可擴充版本**」（reallocate 1.4 頁），**由整合者於規格確認後調整；不得自行假設**。

### 交稿 metadata（每位成員在草稿首行填寫）

```
預估頁數：<x.x>　圖表數：<n>（圖 a／表 b）　引用數：<m>　所屬頁數預算：<章節預算頁數>
```

---

## 12. Review 檢查規則（兩位 reviewer 共用）

**工作量與頁數**
- 各章節頁數是否落在第 11 節預算內（W1 2.5／W2 2.2／W3 3.3／W4 2.6／Refs 1.4／合計 12.0）。
- Writer 1 是否明確拆為 **Introduction ≈1.1 頁**、**Related Work ≈1.4 頁**。
- 每份交稿是否附 page metadata（預估頁數／圖表數／引用數）。

**依賴與時序**
- W1–W3 是否可平行；W4 是否只在 W1–W3 完成後做 Abstract 與全文整合。
- 認領表是否填姓名與 branch、有無重複認領。

**文獻（Writer 1）**
- Related Work 四脈絡齊備、每脈絡 ≥2 篇、核心 12–18 篇。
- 以 `../safety_stress_test/LITERATURE_EVALUATION_METHODS_ZH.md` 為入口並回查原始論文；**未引用該整理檔本身**；無發明 DOI；查不到者標 `待查證`。
- 結尾有明確研究缺口句（固定模型＋逐層唯一差異＋同時量測四類指標的糖尿病衛教系統）。

**主張邊界（全員）**
- 同時報 CFR_strict 與 CFR_composite；FACT 不得升格 critical；scanner 非 ground truth；同模型重複非人類一致性；zero observed ≠ 零風險；12×4／v1／v2 不得 pooled；必要限定語齊備。

**統一敘事（全員）**
- 是否以 `../PAPER_NARRATIVE_BLUEPRINT_ZH.md` 為準；**有無各自發明不同主結論**。
- 核心故事是否為「錯誤分布改變且**非單調**」，而非「D 最安全」。
- 是否出現三種禁止敘事：`zero failure 等於安全`、`LLM judge 等於醫師`、`v1/v2/12×4 pooled`。

**整合規則（Writer 4）**
- **不得靠刪除限制段落壓頁**；優先精簡重複背景。
- References 若會議不計頁 → 記為「可擴充版本」，**不得自行假設**。

