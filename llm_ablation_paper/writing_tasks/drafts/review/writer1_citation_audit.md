# Writer 1 參考文獻查核報告 (Citation Audit Report)

**審查者**：論文整合員（Integration Lead）  
**查核日期**：2026-09-18  
**工作分支**：`writing/integration-w1-w3-intake`  
**依據規範**：`llm_ablation_paper/AGENTS.md`、`PAPER_NARRATIVE_BLUEPRINT_ZH.md`、`safety_stress_test/LITERATURE_EVALUATION_METHODS_ZH.md`  

---

## 1. 查核原則與方法

本查核嚴格遵守以下四項標準：
1. **第一手官方來源為唯一依據**：所有條目逐一核對官方期刊出版社（Nature、Nature Medicine、npj Digital Medicine、Diabetes Care、JMIR、NEJM AI、J Transl Med、Cureus）、學術會議 proceedings（NeurIPS、ICLR、ACL Anthology）或 arXiv 官方預印本頁面；嚴禁以搜尋摘要、部落格或二手整理作為證據。
2. **零捏造與零臆測**：題名、作者名單、出版年份、venue、卷期/頁碼、DOI/arXiv 標識符均經逐字比對。
3. **文中文獻主張相符性核驗**：核對論文正文所陳述之研究發現與方法論，是否確實為該篇文獻之核心結論，有無移花接木或過度延伸。
4. **過度主張修訂**：針對無文獻窮盡支持的絕對性用語（如「首次」、「迄今尚無任何研究」等），提出最小化修訂建議，以維持學術客觀嚴謹度。

---

## 2. 18 筆參考文獻逐筆查核清單

| 編號 | 引用 Key | 題名 | 第一作者 / 年份 | 正式發表 Venue | 第一手標識 (DOI / arXiv) | 查核狀態 | 內文主張相符性核對 |
|---|---|---|---|---|---|---|---|
| 1 | `Sng2023-diabetes-pitfalls` | Potential and Pitfalls of ChatGPT and Natural-Language Artificial Intelligence Models for Diabetes Education | Sng GGR et al. (2023) | *Diabetes Care* 46(5): e103–e105 | DOI: `10.2337/dc23-0197` | **VERIFIED** | **相符**。原文指出單位混淆（mg/dL 與 mmol/L）、飲食僵化及無法辨認假性低血糖等缺陷。 |
| 2 | `Huang2023-diabetes-accuracy` | Evaluate the accuracy of ChatGPT's responses to diabetes questions and misconceptions | Huang C et al. (2023) | *Journal of Translational Medicine* 21: 502 | DOI: `10.1186/s12967-023-04354-6` | **VERIFIED** | **相符**。評估 ChatGPT 在糖尿病衛教與迷思中的回答準確度，支持對抗壓力與迷思識別之必要性。 |
| 3 | `MedSafetyBench2024` | MedSafetyBench: Evaluating and Improving the Medical Safety of Large Language Models | Han T et al. (2024) | *NeurIPS 2024 Datasets & Benchmarks Track* | arXiv:`2403.03744` | **VERIFIED** | **相符**。以醫學倫理為基準，使用 GCG 越獄對抗提示詞，證實純提示詞安全對齊易受攻擊。 |
| 4 | `WildGuard2024` | WildGuard: Open One-Stop Moderation Tools for Safety Risks, Jailbreaks, and Refusals of LLMs | Han S et al. (2024) | *NeurIPS 2024 Datasets & Benchmarks Track* | arXiv:`2406.18495` | **VERIFIED** | **相符**。提出專屬審核模型，明確區分有害性與拒絕行為，直接關聯本文 RQ3（過度拒絕）。 |
| 5 | `HealthBench2025` | HealthBench: Evaluating Large Language Models Towards Improved Human Health | Arora RK et al. (2025) | OpenAI Benchmark 論文 / arXiv (cs.CL) | arXiv:`2505.08775` | **VERIFIED** | **相符**。涵蓋 5,000 篇對話與 worst-of-n 評估，證實目前評估多採整體黑箱，缺乏分層歸因。 |
| 6 | `AgentClinic2026` | AgentClinic: a multimodal benchmark for tool-using clinical AI agents | Schmidgall S et al. (2026) | *npj Digital Medicine* (2026) | DOI: `10.1038/s41746-026-02674-7` (arXiv:`2405.07960`) | **VERIFIED** | **相符**。四 agent 多輪臨床序列決策基準，未單獨隔離與消融系統內部安全控制層。 |
| 7 | `AMIE2025` | Towards conversational diagnostic artificial intelligence | Tu T et al. (2025) | *Nature* 642: 442–450 (2025) | DOI: `10.1038/s41586-025-08866-7` (arXiv:`2401.05654`) | **VERIFIED** | **相符**。模擬病患 OSCE 雙盲評估問診品質，但主要聚焦診斷而非持續性對抗安全壓力。 |
| 8 | `MultimodalAMIE2026` | Advancing conversational diagnostic AI with multimodal reasoning | Saab K et al. (2026) | *Nature Medicine* 32: 1726–1736 (2026) | DOI: `10.1038/s41591-026-04371-0` | **VERIFIED** | **相符**。擴展至即時影像與多模態診斷，並引入幻覺嚴重度分級。 |
| 9 | `CRAFT-MD2025` | An evaluation framework for clinical use of large language models in patient interaction tasks | Johri S et al. (2025) | *Nature Medicine* 31: 77–86 (2025) | DOI: `10.1038/s41591-024-03328-5` | **VERIFIED** | **相符**。靜態題轉為多輪問診時模型準確率顯著下降，暴露出主動病史詢問之缺陷。 |
| 10 | `AgentHarm2025` | AgentHarm: A Benchmark for Measuring Harmfulness of LLM Agents | Andriushchenko M et al. (2025) | *ICLR 2025* | arXiv:`2410.09024` | **VERIFIED** | **相符**。評估 agent 多步工具調用情境下之危害達成率，支持將安全拓展至工具使用層。 |
| 11 | `ToolEmu2024` | Identifying the Risks of LM Agents with an LM-Emulated Sandbox | Ruan Y et al. (2024) | *ICLR 2024* | arXiv:`2309.15817` | **VERIFIED** | **相符**。沙盒模擬環境下對安全限制提示詞進行消融，量化風險與完成度之權衡。 |
| 12 | `MedAgentBench2025` | MedAgentBench: A Realistic Virtual EHR Environment to Benchmark Medical LLM Agents | Jiang Y et al. (2025) | *NEJM AI* 2(9) (2025) | DOI: `10.1056/AIdbp2500144` (arXiv:`2501.14654`) | **VERIFIED** | **相符**。對 FHIR API 執行規則校驗以確保臨床動作安全，支持程式化防線優於純自由文本評估。 |
| 13 | `RISE2024` | Enhancement of the Performance of Large Language Models in Diabetes Education through Retrieval-Augmented Generation: Comparative Study | Wang D et al. (2024) | *Journal of Medical Internet Research* 26: e58041 (2024) | DOI: `10.2196/58041` | **VERIFIED** | **相符**。提出結合 24 條安全規則與兩步事實檢查之 RAG 框架，針對糖尿病衛教護欄設計。 |
| 14 | `MTBench2023` | Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena | Zheng L et al. (2023) | *NeurIPS 2023 Datasets & Benchmarks Track* | arXiv:`2306.05685` | **VERIFIED** | **相符**。奠定 LLM-as-a-Judge 方法論，並揭示位置偏誤、冗長偏誤與自我增強偏誤。 |
| 15 | `FairEval2024` | Large Language Models are not Fair Evaluators | Wang P et al. (2024) | *ACL 2024* (Long Papers), pp. 9440–9450 | arXiv:`2305.17926` | **VERIFIED** | **相符**。量化順序交換時之評審衝突率（GPT-4 達 46.3%），證實 LLM Judge 位置偏誤顯著。 |
| 16 | `PDSQI2025` | Evaluating clinical AI summaries with large language models as judges | Croxford E et al. (2025) | *npj Digital Medicine* (2025) | DOI: `10.1038/s41746-025-02005-2` | **VERIFIED** | **相符**。LLM judge 評估臨床摘要與醫師組 ICC 達 0.818，說明逼近醫師信度上限但非獨立正確真值。 |
| 17 | `MedJUDGE2026` | A Scoping Review of LLM-as-a-Judge in Healthcare and the MedJUDGE Framework | Li C et al. (2026) | 預印本 (cs.CL / cs.AI) | arXiv:`2604.25933` | **VERIFIED** | **相符**。綜述 49 篇醫療 LLM judge 研究，揭示模型單一化（GPT 系列佔 73.5%）與缺乏專家驗證。 |
| 18 | `SameVerdict2026` | Same Verdict, Different Reasons: LLM-as-a-Judge and Clinician Disagreement on Medical Chatbot Completeness | DeLucia A et al. (2026) | 預印本 (cs.CL) | arXiv:`2604.16383` | **VERIFIED** | **相符**。即使 LLM judge 與醫師裁決一致，其底層理由重疊僅 24.6%，判別 AUC 接近機率（0.49–0.66）。 |

---

## 3. 補充方法論引用查核（Writer 3 與統計指標）

| 編號 | 引用 Key | 題名 | 第一作者 / 年份 | 正式發表 Venue | 第一手標識 (DOI / URL) | 查核狀態 |
|---|---|---|---|---|---|---|
| 19 | `Wilson1927-ci` | Probable inference, the law of succession, and statistical inference | Wilson EB (1927) | *Journal of the American Statistical Association* 22(158): 209–212 | DOI: `10.1080/01621459.1927.10502953` | **VERIFIED** |

---

## 4. 主張邊界與過度宣稱修訂審核

### 審查發現
在原草稿 `writer_1_intro_related_work.md` 第 2.5 節（Research Gap）中，原文寫道：
> *"To date, no study has simultaneously measured critical safety failure rate, factual-state consistency, over-refusal, and scanner–judge disagreement within a single diabetes education system under strict ablation control."*

### 潛在問題
「*To date, no study has...*」（迄今尚無任何研究...）屬於未經徹底窮盡全球所有未公開或各語種文獻的絕對否定主張，易引發審稿人對文獻檢索完整性之質疑。

### 建議最小修訂（已於中文整合正文中採納）
改為更客觀、嚴謹的描述：
> 「然而，既有醫療對話 LLM 評估鮮少在固定模型下將安全性改變歸因於個別分層控制，且同時量測嚴重安全失敗、事實與狀態一致性、過度拒絕以及掃描器與評審分歧之糖尿病衛教研究仍相當匱乏。」

---

## 5. 查核結論

- **全部 18 筆 Writer 1 文獻以及 1 筆統計方法論文獻均經第一手來源核驗通過（100% VERIFIED）**。
- 無捏造 DOI、無虛構卷期、無錯配會議/期刊。
- 所有文獻均收錄於可供直接編譯之 `drafts/references.bib`。
