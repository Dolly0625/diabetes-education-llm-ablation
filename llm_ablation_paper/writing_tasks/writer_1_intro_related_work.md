# Writer 1 — Introduction、Related Work、Research Questions

> 路徑以 `llm_ablation_paper/writing_tasks/` 為基準；`../` = `llm_ablation_paper/`。

## 1. 負責與不負責範圍

**負責**
- Introduction（動機、缺口、貢獻一段話）。
- Related Work（醫療對話 LLM 評估、模擬病患／角色扮演、LLM-as-a-Judge、系統層護欄）。
- Research Questions（RQ1 嚴重安全失敗；RQ2 事實／狀態一致性；RQ3 過度拒絕；RQ4 scanner–judge 一致性）。

**不負責**
- A–D 與系統架構細節（Writer 2）。
- 資料、Judge 方法、指標與結果數字（Writer 3）。
- Discussion／Limitations／Conclusion／Abstract（Writer 4）。

## 1a. 頁數預算（合計 2.5 頁）

- **Introduction：約 1.1 頁**（動機、缺口、貢獻一段話、RQ1–RQ4 精簡列出）。
- **Related Work：約 1.4 頁**。
- 交稿首行須填 metadata：`預估頁數：<x.x>　圖表數：<n>　引用數：<m>　所屬頁數預算：2.5`。

## 1b. Related Work 結構（至少四個脈絡，每脈絡至少 2 篇）

1. **醫療對話 LLM 與模擬病患／AMIE-inspired evaluation**（多輪對話評估、標準化病人、模擬環境）。
2. **醫療安全 benchmark 與 adversarial stress／red teaming**（越獄、紅隊、風險行為 benchmark）。
3. **分層／程式化防線與消融研究**（Planner、tool gating／動態工具暴露、output guard／熔斷等「由提示詞到程式防線」）。
4. **LLM-as-a-Judge 的可擴展性、偏誤、與人類／臨床評審落差**（位置偏誤、同模型偏誤、judge–human 一致度上限）。

**文獻規則**
- 以 `../safety_stress_test/LITERATURE_EVALUATION_METHODS_ZH.md` 為**候選來源入口**；**必須回查原始論文**後再引用。
- **不可引用該整理檔本身**（不得把彙整文件當文獻）。
- **不可發明 DOI／年份／期刊**；查不到就標 `[@REF-KEY, 待查證]` 並列入清單。
- 核心文獻 **須 12–18 篇**，每個脈絡至少 2 篇。
- Related Work **結尾必須明確指出研究缺口**：缺少在**固定模型與逐層唯一差異**下，**同時量測** critical safety、factual state、over-refusal 與 scanner–judge disagreement 的**糖尿病衛教系統**研究。

## 2. 必讀相對路徑

- `../PAPER_WRITING_HANDOFF_ZH.md`（第 1–3、12 節）
- `../shared/CLAIM_BOUNDARIES.md`
- `../shared/RESEARCH_PROTOCOL.md`
- `../safety_stress_test/v2/PROTOCOL_V2.md`（第 13 節非可比性）
- `../safety_stress_test/v2/V2_FULL_BATCH_PROTOCOL.md`（範圍一句話）
- `../PAPER_NARRATIVE_BLUEPRINT_ZH.md`（統一敘事藍圖，**必讀**；四脈絡與研究缺口寫法見第 1–2 節）

## 3. 固定數字（引用即可，不得重算）

- **92/92** 軌跡、**204** 回合、排除 **0**、完整區塊 **23/23**。
- 四組 **CFR_strict = 0/12**、**CFR_composite = 0/12**（Wilson 上限 **24.25%**）。
- 成本 **US$0.8903688 ≈ TWD 28.49**。
- 來源：`../safety_stress_test/v2/V2_FULL_METRICS.json`、`../safety_stress_test/v2/V2_FULL_RESULT.md`。

## 4. 禁止主張

臨床驗證／醫師驗證／降低住院／100% 安全；Judge 等同醫師；scanner 等同評審；拒絕率等同安全；zero observed 寫成零風險；**合併統計**（12×4／v1／v2 不得 pooled）；把 FACT 一律升格 critical。必須加限定語：模擬情境、指定模型版本、exploratory、非預先註冊、非臨床。

## 5. 交付檔名

`drafts/writer_1_intro_related_work.md`（＋「待補引用清單」於檔末）。

## 6. 引用占位規則

內文用 `[@REF-KEY]`；圖表用 `{FIG:n}`／`{TAB:n}`；數字直接寫出並標來源路徑；**不得**發明文獻條目，末尾列「待補引用清單」。

## 7. 圖表責任

不負責任何圖表；可在 Introduction 以文字引用 Figure 1（Writer 2）與 Figure 2（Writer 3），格式 `{FIG:1}`、`{FIG:2}`。

## 7a. 章節完成清單（本檔）

- [ ] Introduction 約 1.1 頁；Related Work 約 1.4 頁（合計 2.5 頁）。
- [ ] Related Work 四脈絡齊備，每脈絡 ≥2 篇；核心文獻 12–18 篇。
- [ ] 以 `LITERATURE_EVALUATION_METHODS_ZH.md` 為入口並回查原始論文；**未引用該整理檔本身**。
- [ ] 無發明 DOI；查不到者標 `[@REF-KEY, 待查證]`。
- [ ] 結尾點名研究缺口（固定模型＋逐層唯一差異＋同時量測四類指標的糖尿病衛教研究）。
- [ ] 首行 page metadata。

## 8. 完成定義

交付檔名正確；只用固定數字且標來源；無禁止主張、含限定語；RQ1–RQ4 齊備；引用用佔位並附清單；不含他章內容；通過連結與數字測試。

## 9. 可直接貼給 AI 的 prompt

```
你協助撰寫研討會論文的 Introduction、Related Work 與 Research Questions。我不寫程式。
先讀 llm_ablation_paper/writing_tasks/writer_1_intro_related_work.md 與 llm_ablation_paper/PAPER_WRITING_HANDOFF_ZH.md（第 1-3、12 節）及 llm_ablation_paper/shared/CLAIM_BOUNDARIES.md。

篇幅：Introduction 約 1.1 頁；Related Work 約 1.4 頁（合計 2.5 頁）。首行填：預估頁數／圖表數／引用數。

Related Work 至少四脈絡，每脈絡 ≥2 篇，核心文獻 12-18 篇：
1) 醫療對話 LLM 與模擬病患／AMIE-inspired evaluation；
2) 醫療安全 benchmark 與 adversarial stress／red teaming；
3) 分層／程式化防線與消融（Planner、tool gating、output guard）；
4) LLM-as-a-Judge 的可擴展性、偏誤、與人類／臨床評審落差。
以 llm_ablation_paper/safety_stress_test/LITERATURE_EVALUATION_METHODS_ZH.md 為「候選來源入口」，
  但必須回查原始論文後才引用；不可引用該整理檔本身；不可發明 DOI／年份／期刊，
  查不到就標 [@REF-KEY, 待查證]。
Related Work 結尾明確指出缺口：缺少在固定模型與逐層唯一差異下，同時量測
  critical safety、factual state、over-refusal 與 scanner-judge disagreement 的糖尿病衛教系統研究。

規則：
1. 只使用任務檔「固定數字」；不得重算、不得發明數字；數字須標來源相對路徑。
2. 引用一律用 [@REF-KEY] 佔位，末尾附「待補引用清單」。
3. 必加限定語：在本研究的模擬情境中、對指定模型與版本、LLM Judge 評分顯示、
   exploratory／非預先註冊／非臨床。
4. 禁止：臨床驗證、醫師驗證、降低住院、100% 安全、Judge 等同醫師、scanner 等同評審、
   zero observed 寫成零風險、把 12×4／v1／v2 合併統計。
5. 不要寫 A–D 系統細節、資料/Judge 方法、結果數字與 Discussion。

交付：drafts/writer_1_intro_related_work.md。
先給我大綱（含四脈絡與每脈絡初始文獻清單）與每個要用的數字（標來源），我確認後再寫全文。
```
