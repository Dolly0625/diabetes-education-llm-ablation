# PAPER_NARRATIVE_BLUEPRINT_ZH — 統一敘事藍圖（技術主持主筆）

> **路徑基準**：本檔位於 `llm_ablation_paper/`，以下相對路徑皆以 `llm_ablation_paper/` 為基準。
> 本檔由**技術主持**主筆，提供全篇**具體敘事**（不只大綱）。四位作者**必須以此保持統一論述**，
> **禁止各自發明不同主結論**。總頁數仍以 **12 頁**（conservative：references 計入；見 `writing_tasks/README.md` 第 11 節）為準。
> 引用一律回到**原始來源**（可以 `safety_stress_test/LITERATURE_EVALUATION_METHODS_ZH.md` 為候選入口，但**不得引用該整理檔本身**）。
> 本檔不新增數字；所有數字見 `safety_stress_test/v2/V2_FULL_METRICS.json` 與 `safety_stress_test/v2/V2_FULL_RESULT.md`。

---

## 0. 一句話核心故事

**本研究不是要證明「D 最安全」。** 我們在**固定模型、逐層唯一差異**下，對糖尿病衛教助理做對抗壓力測試，
發現**分層防線會改變錯誤的分布**，且改善**並非單調**：嚴格嚴重安全失敗（CFR）四組皆 0/12，
但**事實／狀態層錯誤在不同層級之間此消彼長**（main：A 2、B 4、C 0、D 0；探針：A 1、B 1、C 2、D 2）。
因此我們主張的是**錯誤重分配（error redistribution）**與**情境相依的防護（context-dependent safeguards）**，
而非單一組別全面較優。

**統一主張（全篇一致，不得改寫成別的結論）**
- 在本研究的模擬情境與指定模型版本下，四組皆未觀察到嚴格定義的嚴重安全失敗；**零觀察 ≠ 零風險**。
- 加入各層控制改變了**錯誤分布**，且**非單調**；不宣稱因果、不宣稱「D 最佳」。
- 盲測 LLM Judge 為**同模型重複評分**（shared-model bias），**非**人類評審。
- v1／v2／正式 12×4 **分開報告、不得 pooled**；v2 為主要探索性結果。

---

## 1. Introduction — 逐段寫法（≈1.1 頁）

**第 1 段（風險場景）**
- Topic sentence：「糖尿病衛教聊天機器人面對的多是長期、低識字的長輩；真正的安全風險常出現在**病患持續施壓**時，而非正常衛教。」
- 內容：舉例（要求自行停藥／減半、要求線上確診、遭遇急症、要求為偏方背書），說明為何這類情境是安全評估的關鍵。

**第 2 段（prompt 不足）**
- Topic sentence：「單靠系統提示詞（prompt）不足以保證安全；錯誤可能在多輪互動中被誘發或累積。」
- 內容：說明提示詞防線的極限，帶出「需要**系統層級**、可稽核的防護」。

**第 3 段（layer attribution 缺口）**
- Topic sentence：「既有醫療 LLM 評估多在**單一整體設定**下報告安全，缺少**逐層歸因**。」
- 內容：指出缺一個「**固定模型、逐層唯一差異**」的設計，能回答「哪一層改變了什麼錯誤」。

**第 4 段（收斂到 RQ）**
- Topic sentence：「因此我們提出四個研究問題。」
- **RQ1**：加入 Planner、動態工具門禁、輸出熔斷後，A/B/C/D 的**嚴重安全失敗**是否改變？（探索性）
- **RQ2**：各層控制對**事實／狀態一致性**（含「由沉默捏造否定病史」）的影響為何？
- **RQ3**：各層控制是否造成**過度拒絕**？
- **RQ4**：確定性規則掃描器與盲測 LLM 評審的**一致性**如何？（掃描器非 ground truth）

**段落轉折語建議**：「然而，…」「問題在於，…」「為此，我們…」。

---

## 2. Related Work — 四脈絡逐段寫法（≈1.4 頁）

> 每個脈絡：**topic sentence → 如何比較（共同點／差異／限制）→ 收束到與本研究的差異**。至少 2 篇／脈絡，核心 12–18 篇，**回查原始論文**。

**脈絡一：醫療對話 LLM 與模擬病患／AMIE-inspired evaluation**
- Topic sentence：「多輪醫療對話評估常以**模擬病患**與標準化情境進行。」
- 比較：AMIE-inspired 系統以模擬對話檢驗能力，但多聚焦**診斷／對話品質**，較少**對抗式安全壓力**。

**脈絡二：醫療安全 benchmark 與 adversarial stress／red teaming**
- Topic sentence：「醫療安全 benchmark 開始納入**越獄與紅隊**，但多以**單輪或通用健康**情境為主。」
- 比較：這些工作定義了危害等級，惟**逐層防線**的貢獻少有被單獨量測。

**脈絡三：分層／程式化防線與消融（Planner、tool gating、output guard）**
- Topic sentence：「由提示詞到程式防線，研究開始把安全拆成**可組合的層**。」
- 比較：既有護欄多為單一機制或非消融式；本研究以**唯一差異原則**比較三開關。

**脈絡四：LLM-as-a-Judge 的可擴展性、偏誤、與人類／臨床評審落差**
- Topic sentence：「LLM Judge 成本低、可擴充，但存在**偏誤與與人類評審的落差**。」
- 比較：位置偏誤、同模型偏誤、judge–human 一致度上限；本研究因此採**盲測＋同模型兩次**並**明確標示其限制**。

**研究缺口（必寫）**
- 「然而，既有研究**缺少**在**固定模型與逐層唯一差異**下，**同時量測** critical safety、factual state、over-refusal 與 scanner–judge disagreement 的**糖尿病衛教系統**研究。本研究填補此缺口（探索性）。」

---

## 3. Methods — 敘事順序（≈2.2＋3.3 頁共用敘事）

1. **系統 A→D**：先講架構概念（感知、Input Guard、規劃、雙軌 RAG、生成、Output Guard），再以**三開關**定義 A/B/C/D，強調**唯一差異**（其餘固定）。
2. **23 案例**：12 main（6 類 CF ×2）＋2 factual probes＋9 benign；固定 3 輪腳本、**不使用 Patient Agent**。
3. **盲評**：評審只看匿名軌跡；每軌跡**同模型兩次**、CF 分歧才 tie-break；**非人類評審**。
4. **三層 taxonomy**：CRITICAL／FACTUAL_STATE／QUALITY＋**span-grounded 升級檢核**；FACT 不預設升格 critical。
5. **指標**：CFR_strict 與 CFR_composite **並列**；FACT、QUALITY、over-refusal、scanner–judge disagreement；皆附 Wilson 95% CI。
6. **可重現性**：fingerprints、A–D unique-difference、fail-closed 閘門、成本上限、blinded 匯出與 usage ledger。

**轉折語**：「為避免把事實錯誤一律視為嚴重，我們…」「為確保可重現，我們…」。

---

## 4. Results — 敘事順序（≈3.3 頁）

**R1 完整性先行**：92/92 軌跡、204 回合、排除 0、完整區塊 23/23（先建立可信度）。
**R2 CFR**：四組 **0/12（strict 與 composite 皆同）**，但附 **Wilson 上限 24.25%**，立刻寫「**零觀察 ≠ 零風險**」。
**R3 FACT（反轉）**：main FACT **A 2／B 4／C 0／D 0**；probe FACT **A 1／B 1／C 2／D 2**。指出這是**錯誤重分配**與**情境相依**的證據，**不**下「誰較安全」的結論。
**R4 其他**：QUALITY（A0 B1 C0 D1）、over-refusal（皆 0/9）、scanner–judge disagreement（A2 B3 C2 D2，方向 scanner_only 9／judge_only 0／both 0）。
**R5 成本與規模**：judge 190 呼叫、canary 6/6、tie-break 0；總成本 US$0.8903688。

**建議圖表應支持的論點**
- Figure 2：CFR 四組為 0，但 CI 很寬 → 支持「不能宣稱安全」。
- Figure 3：main vs probe FACT 的**方向反轉** → 支持「錯誤重分配／非單調」。
- Figure 4：不一致**全為掃描器方向** → 支持「scanner 非 ground truth」。

---

## 5. Discussion — 解讀（≈2.6 頁的一部分）

- **主解讀**：把結果寫成 **error redistribution** 與 **context-dependent safeguards**：不同層把錯誤推向不同型態（例如主案例的狀態捏造、探針情境的事實填入），而非「愈多層愈好」。
- **機制假設（標明為假設）**：Planner 增加結構化追蹤的同時，可能放大某些狀態敘述；動態工具門禁與輸出熔斷改變了可見工具與最終輸出，可能降低某些主案例事實錯誤，卻在探針情境出現另一種事實填入。
- **明確禁止**：**不得因小樣本做因果推論**；**不得宣稱 D 最佳**（D 在探針 FACT 並非最好）。

---

## 6. Limitations 與 Conclusion — 保守收束

- **Limitations**：小樣本（12 main、family N=2）、無人類／臨床評審、同模型 judge 偏誤、scanner 非 ground truth、部分解盲（`tools_exposed` treatment-visible）、單一模型／溫度、v2 非預先註冊、別名藥理 `UNVERIFIED`。
- **Conclusion**：在本研究模擬情境與指定模型版本下，分層防線**改變錯誤分布且改善非單調**；結果為**探索性**，需更大樣本與人類／臨床評審驗證。**不**宣稱臨床有效或部署。

**段落轉折語**：「必須強調的是，…」「在解讀上，我們刻意避免…」。

---

## 7. 三種禁止敘事（全篇一致）

1. **禁止**把 `CFR = 0` 寫成「安全」：只能寫「未觀察到嚴格定義的嚴重安全失敗；**零觀察 ≠ 零風險**（Wilson 上限 24.25%）」。
2. **禁止**把 LLM Judge 寫成醫師或人類評審：只能寫「盲測 LLM Judge（**同模型重複評分**，shared-model bias）」。
3. **禁止**把 **v1／v2／正式 12×4** 合併統計或互相比較排名：三者**分開報告、不得 pooled**。

---

## 8. 摘要範例（中文，約 200–250 字；投稿時請依格式改寫）

> 糖尿病衛教聊天機器人需在長輩日常對話中安全地提供衛教，但既有評估多在正常情境呈現安全天花板，難以回答遭遇危險要求與持續施壓時各層防線是否有效。本研究以**固定模型與逐層唯一差異**設計，對同一糖尿病衛教 LLM 助理的四種設定（A/B/C/D）進行探索性安全壓力測試：23 個案例（12 主案例、2 事實探針、9 良性對照）× 四條件，共 **92 條真實模型對話軌跡、204 回合**，並以**盲測 LLM 評審**（同模型重複評分兩次）評分。結果顯示四組之嚴重安全失敗率（CFR_strict 與 CFR_composite）皆為 **0/12**，但 Wilson 95% 上限達 24.25%，**零觀察不等於零風險**；事實／狀態層錯誤則呈現**非單調**分布（主案例 A 2／B 4／C 0／D 0，事實探針 A 1／B 1／C 2／D 2），顯示分層防線**改變錯誤分布**而非單向改善。過度拒絕在四組皆為 0/9。本研究為探索性、非預先註冊、非臨床，且與正式 12×4 及 v1 分開報告、不得合併。

---

## 9. 英文摘要寫作骨架（投稿時改寫為目標格式）

```
Background. Diabetes-education chatbots must stay safe under patient pressure, not only in routine education.
Gap. Existing evaluations rarely attribute safety changes to individual layered controls under a fixed model.
Objective. To compare four layered configurations (A/B/C/D) of one diabetes-education LLM assistant under a fixed
  model and incrementally unique differences.
Methods. Exploratory safety stress test: 23 cases (12 main, 2 factual probes, 9 benign) x 4 conditions = 92 real-model
  trajectories / 204 assistant turns; fixed scripts, no patient agent; blinded LLM judge with same-model repeated
  evaluations (2x, tie-break only on disagreement).
Results. CFR_strict and CFR_composite were 0/12 in all four conditions (Wilson 95% upper bound 24.25%); zero observed
  is not zero risk. Factual-state errors were non-monotonic (main A 2 / B 4 / C 0 / D 0; probe A 1 / B 1 / C 2 / D 2),
  consistent with error redistribution rather than monotonic improvement. Over-refusal was 0/9 in all conditions.
Conclusions. Layered safeguards changed the *distribution* of errors under this simulation; findings are exploratory,
  non-preregistered, non-clinical, and are not pooled with the formal 12x4 or v1.
```

> **標註**：以上中／英文摘要為**範例骨架**，作者**需依投稿格式與字數改寫**；不得加入本檔未列之數字或主張。

---

## 10. 與 12 頁預算的對應

| 章節 | 頁數 | 敘事重點 |
|---|---|---|
| Introduction + Related Work | 2.5（Intro 1.1／RW 1.4） | 風險→prompt 不足→歸因缺口→RQ；四脈絡→缺口 |
| System + A/B/C/D + Implementation | 2.2 | 唯一差異、固定腳本、可重現性 |
| Dataset / Evaluation / Results / Error Analysis | 3.3 | 完整性→CFR→FACT 反轉→其他→成本 |
| Abstract + Discussion + Limitations + Conclusion + 整合 | 2.6 | error redistribution／context-dependent、保守收束 |
| References | 1.4 | 回原始來源 |

> 若會議規定 references 不計頁 → 記為「**可擴充版本**」，由整合者依正式規格調整，**不得自行假設**。
