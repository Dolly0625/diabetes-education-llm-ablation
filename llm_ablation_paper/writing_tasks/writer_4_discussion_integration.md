# Writer 4 — Discussion、Limitations、Conclusion、Abstract、全文整合

> 路徑以 `llm_ablation_paper/writing_tasks/` 為基準；`../` = `llm_ablation_paper/`。

## 1. 負責與不負責範圍

**負責**
- Discussion（探索性解讀、與文獻對話、機制假設——一律標為假設）。
- Limitations（逐條：小樣本、無人類評審、同模型偏誤、scanner 非 ground truth、部分解盲、單一模型/溫度、非預先註冊、別名未驗證）。
- Conclusion（保守、探索性）。
- Abstract（最後寫）。
- **全文整合**：串接 W1–W3、統一術語、統整引用佔位清單、檢查數字一致。

**不負責**
- 重寫 W1–W3 的專屬內容；重算數字；變更實驗結果。

## 1a. 頁數預算（2.6 頁）與整合規則

- Abstract + Discussion + Limitations + Conclusion + 全文整合，共 **2.6 頁**。
- **整合時不得靠刪除限制段落壓頁**；頁數超出時**優先精簡重複背景**（Introduction／Related Work 與 Discussion 的重述）。
- 交稿首行須填 metadata：`預估頁數：<x.x>　圖表數：<n>　引用數：<m>　所屬頁數預算：2.6`。
- **References 頁數**：本包採保守配置（references 計入 12 頁內、預留 1.4 頁）。**若會議正式規定 references 不計頁**，記為「**可擴充版本**」並由整合者依正式規格調整；**不得自行假設**。

## 2. 必讀相對路徑

- `../PAPER_WRITING_HANDOFF_ZH.md`（第 9、11、12、13 節）
- `../shared/CLAIM_BOUNDARIES.md`
- 全體交付：`drafts/writer_1_intro_related_work.md`、`drafts/writer_2_system_ablation_method.md`、`drafts/writer_3_dataset_evaluation_results.md`
- `../safety_stress_test/v2/V2_FULL_RESULT.md`、`../safety_stress_test/v2/V2_FULL_METRICS.json`
- `../PAPER_NARRATIVE_BLUEPRINT_ZH.md`（統一敘事藍圖，**必讀**；Discussion 解讀、Limitations、摘要骨架、三種禁止敘事見第 5–9 節）

## 3. 固定數字（引用即可，不得重算）

- **92/92** 軌跡、**204** 回合、排除 **0**、完整區塊 **23/23**。
- 四組 **CFR_strict = 0/12**、**CFR_composite = 0/12**（Wilson 上限 **24.25%**）。
- FACT main A2 B4 C0 D0；probe A1 B1 C2 D2；quality A0 B1 C0 D1；over-refusal 皆 0/9。
- 成本 **US$0.8903688 ≈ TWD 28.49**；judge 190 呼叫、canary 6/6、tie-break 0。
- 其他數字（family 65.76%、over-refusal 29.91%、scanner 方向 9/0/0、escalations 0、FACT 代碼 11/2/1）以 `README.md` 第 5 節與 `../safety_stress_test/v2/V2_FULL_RESULT.md` 為準，**不得重算**。

## 4. 禁止主張

禁止：臨床／醫師驗證、降低住院、100% 安全、可直接部署；Judge 等同醫師；把機制假設寫成因果；把 FACT 升格 critical；把 zero observed 寫成零風險；**合併統計**（12×4／v1／v2 不得 pooled）；把 A–D 寫成效果結論。必須加限定語：模擬情境、指定模型版本、exploratory、非預先註冊、非臨床。

## 5. 交付檔名

`drafts/writer_4_discussion_integration.md`（含 Discussion／Limitations／Conclusion／Abstract 與整併後全文；＋統整「待補引用清單」）。

## 6. 引用占位規則

內文 `[@REF-KEY]`；圖表 `{FIG:n}`／`{TAB:n}`；數字標來源相對路徑；統整 W1–W3 的佔位清單，**不得**虛構文獻。

## 7. 圖表責任

不新增圖表；負責確認 Figure 1（W2）、Figure 2–4 與 Table 1–2（W3）在全文被正確引用且編號一致。

## 8. 完成定義

交付檔名正確；Discussion／Limitations／Conclusion／Abstract 齊備；全文整合（W1–W3 串接、術語一致、引用清單統整、數字一致）；無禁止主張、含限定語；通過連結與數字測試。

## 9. 依賴與時序（重要）

- **可先做**：Discussion／Limitations／Conclusion 初稿（不需等其他成員）。
- **必須等 W1–W3 交付後**：Abstract 與**全文整合**。
- 整合前先確認認領表 W1–W3 狀態為「完成」。

## 10. 可直接貼給 AI 的 prompt

```
你協助撰寫論文 Discussion、Limitations、Conclusion、Abstract，並整合全文。我不寫程式。
先讀 llm_ablation_paper/writing_tasks/writer_4_discussion_integration.md、
llm_ablation_paper/PAPER_WRITING_HANDOFF_ZH.md（第 9、11-13 節）、
llm_ablation_paper/shared/CLAIM_BOUNDARIES.md 與
llm_ablation_paper/safety_stress_test/v2/V2_FULL_RESULT.md。

規則：
1. 只用任務檔固定數字，標來源相對路徑；不得重算。
2. 機制解讀一律標為「假設」；不得寫成因果或效果結論。
3. 必加限定語：模擬情境、指定模型版本、exploratory、非預先註冊、非臨床；
   強調 zero observed ≠ 零風險、同模型重複＝shared-model bias。
4. 禁止臨床/醫師驗證、降低住院、100% 安全、Judge 等同醫師、
   把 12×4／v1／v2 合併統計。
5. 引用用 [@REF-KEY] 佔位；整合時統整 W1-W3 的「待補引用清單」。
6. 若 W1-W3 尚未完成，只交付 Discussion/Limitations/Conclusion 初稿，Abstract 與全文整合留待其完成。
7. 頁數預算 2.6 頁；首行填 page metadata。整合時不得靠刪除限制段落壓頁，優先精簡重複背景。
   References 保守計入 12 頁（預留 1.4 頁）；若會議規定不計頁，記為「可擴充版本」，不得自行假設。

交付：drafts/writer_4_discussion_integration.md。
先給我 Discussion 大綱與 Limitations 清單，我確認後再寫全文。
```
