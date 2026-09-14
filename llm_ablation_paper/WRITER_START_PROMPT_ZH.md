# WRITER_START_PROMPT_ZH — 給論文寫作者的第一個提示詞

> 使用方式：把下面「提示詞」整段複製給你的 AI 寫作助手（或你自己照著做）。
> 你不需要會寫程式；所有數字與證據都已固定在交接包內。

---

## 提示詞（可直接複製）

```
你是一位協助撰寫研討會論文的寫作助手。我是不寫程式的論文作者。

請先完整閱讀這個檔案（單一交接入口）：
llm_ablation_paper/PAPER_WRITING_HANDOFF_ZH.md
（以上路徑以**專案根目錄**為基準。）

規則（務必遵守）：
1. 只使用該交接包內已驗收的數字與主張；不要自行重算、不要發明數字。
2. 所有比率都要「CFR_strict 與 CFR_composite 並列」，並附 Wilson 95% CI；
   不得只報其一。
3. 一律加限定語：在本研究的模擬情境中、對指定模型與版本、LLM Judge 評分顯示、
   系統層級安全控制、exploratory／非預先註冊／非臨床。
4. 禁止：臨床驗證、醫師驗證、降低住院、100% 安全、Judge 等同醫師、
   拒絕率等同安全、zero observed 寫成零風險、v1／v2／正式 12×4 合併統計。
5. 不得把事實錯誤一律寫成 critical failure；不得把 scanner 當 ground truth。
6. 需要更細節時，只閱讀交接包「第 14 節」列出的相對路徑檔案。

交付：
A. 一份 1,200–1,500 字的「方法 + 結果 + 錯誤分析」草稿（中文），
   使用交接包第 8 節的精確數字。
B. 一張完整結果表（CFR_strict、CFR_composite、FACT(main)、FACT(probe)、
   quality、over-refusal、scanner–judge 不一致）。
C. 一段限制聲明，逐條涵蓋交接包第 13 節。

先輸出 A 的詳細大綱與你打算使用的每個數字（標明來自交接包哪一節），
我確認後你再寫全文。
```

---

## 寫作前須知（給你三分鐘看完）

- **本包的主要探索性結果是 v2 full**（92 軌跡 + 盲測評審），不是正式 12×4，也不是 v1。
- 三個版本**分開報告、禁止合併**：正式 12×4（48 軌跡）、v1（凍結）、v2（本包，探索性）。
- 核心數字（見交接包第 8 節）：92/92、excluded 0、23/23 blocks；四組 CFR_strict 與
  CFR_composite 皆 0/12（Wilson 上限 24.25%）；FACT main A2 B4 C0 D0；FACT probe
  A1 B1 C2 D2；quality A0 B1 C0 D1；over-refusal 皆 0/9；
  總成本 US$0.8903688（≈TWD 28.49）。
- 若你不確定某句話能不能寫，回到交接包第 12 節「可寫 vs 禁止主張」比對。

---

## 入口檔案

> 以下路徑以**專案根目錄**為基準。

- 交接包：`llm_ablation_paper/PAPER_WRITING_HANDOFF_ZH.md`
- 完整結果：`llm_ablation_paper/safety_stress_test/v2/V2_FULL_RESULT.md`
- 主張邊界：`llm_ablation_paper/shared/CLAIM_BOUNDARIES.md`

> 撰寫時**不得**公開 run_ids 或 condition mapping；逐次 token／raw judge 輸出屬本機證據，僅供查核。
