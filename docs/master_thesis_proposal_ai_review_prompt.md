# 給其他 AI 的碩士論文提案審查指令

請先完整閱讀同目錄的 `master_thesis_proposal_longitudinal_memory.md`，再依下列規則審查。這是一份兩個月內必須完成、以順利畢業與 AI／LLM Engineer 求職作品為目標的碩士論文提案。研究無法進行真實臨床部署，僅能使用合成病患、受控 LLM 對話、程式評分與有限人工抽查。

## 審查任務

請不要重寫整份提案，也不要只給鼓勵。請判斷此研究是否具備清楚、可測量、可在兩個月內完成且能通過碩士口試的方法設計。

依序檢查：

1. **研究問題**：是否單一、可回答，且沒有偷偷混入臨床有效性？
2. **新穎性與定位**：相較 LoCoMo、LoCoMo-Plus、MediLongChat 等工作，本研究的貢獻是否足以作為碩士論文？若不足，缺的是 benchmark、metric、domain adaptation 還是實驗比較？
3. **內部效度**：M0–M3 是否真的只差記憶機制？有哪些 confounds 會使結果無法歸因？
4. **Ground truth**：event ledger 是否足以判定 active、stale、correction 與 unsupported facts？哪些輸出無法確定性評分？
5. **評估指標**：CSER 的分母、錯誤互斥性與加總方式是否合理？是否有 double counting 或可被模型投機的問題？
6. **統計設計**：24 profiles × 4 conditions × 3 repetitions 是否足夠且可行？paired tests、cluster bootstrap 與多重比較是否適當？
7. **LLM Judge**：Judge 的角色是否被限制在合理範圍？人工抽查是否足以發現系統性評分偏差？
8. **合成資料效度**：哪些結論能由合成資料支持，哪些不能？是否需要額外的內容效度或 sensitivity analysis？
9. **兩個月可行性**：找出最可能拖延的三項工作，並提出不改變核心 RQ 的最小縮減方案。
10. **研討會重疊**：本碩論與既有 Planner／dynamic tool gate／Output Guard A–D 安全消融是否有實質重疊或 salami slicing 風險？
11. **口試風險**：列出委員最可能提出的五個尖銳問題，以及提案目前是否答得出來。
12. **求職價值**：這份研究能否展示 AI／LLM Engineer 所需的實驗控制、evaluation、observability 與 reproducibility 能力？

## 固定輸出格式

### 目前判定

只能選一項：

- 通過：研究問題與核心方法可凍結。
- 部分通過：保留核心方向，但必須完成指定的小幅修改。
- 不通過：存在無法以局部修改解決的研究設計問題。

### Blocking issues

只列會使研究無法回答 RQ、無法歸因、無法重現或無法在兩個月完成的問題。每項須引用提案的確切章節。

### 可保留內容

列出不需重寫的研究問題、設計、指標或主張邊界。

### 最小修正行動

依優先順序提供最多五項修正。每項說明要改哪一節、改什麼，以及修正後解決哪個風險。

### 建議凍結版本

提供：

- 一個修訂後的主 RQ。
- 一個主要 outcome。
- 最多三個 planned comparisons。
- 最低可行實驗規模。
- 一句允許的最終 contribution claim。
- 一句禁止使用的過度主張。

### 委員可能提問

以表格列出五個問題、風險等級，以及提案可採用的回答方向。不得捏造尚未取得的結果或專家背書。

