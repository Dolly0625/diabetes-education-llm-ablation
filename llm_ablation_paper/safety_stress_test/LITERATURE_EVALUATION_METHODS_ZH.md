# 醫療對話 LLM、模擬病患、LLM 安全防護、工具使用與 LLM-as-a-Judge：文獻評估方法盤點

> 文件用途：回答「與本研究相近的醫療對話 LLM、模擬病患、LLM 安全防護、工具使用與 LLM-as-a-Judge 研究，實際都如何測試安全或失敗？」本文件為**文獻蒐集與方法盤點**，不是論文全文，也不修改既有大綱、實驗程式或 git。
> 檢索與查證日期：**2026-09-12**。所有條目均以官方論文頁、DOI 頁或官方 preprint 頁查證；找不到的欄位一律標 **NR**（Not Reported），不臆測。
> 語言：繁體中文敘述；模型名、benchmark 名、統計方法名與固定術語保留英文。

---

## 0. 方法與證據強度聲明

### 0.1 來源優先序（本文件遵循）

1. 同儕審查期刊／會議論文（Nature、Nature Medicine、npj Digital Medicine、JAMA Internal Medicine、NeurIPS、ICLR、ACL、EMNLP、JMIR、Diabetes Care）。
2. 正式 preprint（arXiv、medRxiv）與官方 benchmark 頁面（OpenAI、GitHub 官方 repo、計畫官網）。
3. 本文件**不使用**部落格、新聞摘要或搜尋引擎摘要作為核心方法證據。

### 0.2 三項硬性禁止（已在各節落實）

- **不得把 AMIE 等同本研究的臨床驗證**：AMIE 為 Google 之診斷對話系統，其驗證規格（OSCE、真人病人演員、專科醫師評分）與本研究之合成病患、LLM Judge 設計**不同**；本研究僅能自稱「受 AMIE 啟發之 in-silico 模擬對話評估」。
- **不得宣稱 LLM Judge 等同醫師**：文獻一致顯示 LLM Judge 與臨床醫師存在系統性落差（見 §2.6、§4）。
- **不得杜撰引用**：所有編號來源 [S1]–[S29] 均為 2026-09-12 查證存在之官方條目，URL 見 §5。

### 0.3 統計單位用語校正

文獻中 "N" 常指「對話數／題數／案例數」，與「獨立受試者數」不同。本文件一律標示 N 之**實際單位**；涉及配對或重複時另註明。

---

## 1. 文獻比較表

> 每篇以欄位表列出。欄位對應使用者要求：題名、作者、年份、venue/preprint、DOI/URL、研究任務、資料來源、樣數、單/多輪、模型、baseline/ablation、重複與 temperature、安全定義、失敗定義、評審者、是否盲評、評分尺度、統計方法、主要限制。

### 群組 A：醫療多輪對話 LLM 評估

#### A1. HealthBench [S1]

| 欄位 | 內容 |
|---|---|
| 完整題名 | HealthBench: Evaluating Large Language Models Towards Improved Human Health |
| 作者 | Rahul K. Arora, Jason Wei, Rebecca Soskin Hicks, Preston Bowman, Joaquin Quiñonero-Candela, Foivos Tsimpourlas, et al.（OpenAI） |
| 年份 | 2025 |
| venue/preprint | 官方 benchmark 論文；arXiv:2505.08775（cs.CL） |
| DOI/URL | https://doi.org/10.48550/arXiv.2505.08775 ；官方頁 https://openai.com/index/healthbench/ |
| 研究任務 | 對真實健康對話的「最後一則使用者訊息」產生最佳回覆 |
| 資料/案例來源 | 合成生成 + 醫師 red-teaming；262 位醫師（60 國、26 專科）撰寫對話專屬 rubric |
| 樣數 | N=5,000 對話；48,562 條 rubric 準則；Consensus 子集 3,671 例；Hard 子集 1,000 例 |
| 單/多輪 | 多輪（平均 2.6 輪，範圍 1–19） |
| 模型 | GPT-3.5 Turbo、GPT-4o、GPT-4.1（含 nano/mini）、o1、o3、o4-mini、Claude 3.7 Sonnet、Gemini 2.5 Pro、Grok 3、Llama 4 Maverick |
| baseline/ablation | 醫師撰寫基準（有/無模型輔助）；成本–效能前緣；Consensus／Hard 子集；worst-of-n 可靠度 |
| 重複與 temperature | OpenAI 模型 temperature 1.0；其他模型依附錄 H（欄位值 NR）；主要分數之重複次數 NR；另做 worst-of-n |
| 安全定義 | 無單一安全定義；以負向 rubric 準則、急症轉介主題、Consensus 錯誤率、worst-of-n 可靠度綜合衡量 |
| 失敗定義 | 未達正向準則，或觸發負向準則 |
| 評審者 | LLM grader（GPT-4.1）+ 醫師 meta-evaluation 校驗 grader |
| 是否盲評 | NR |
| 評分尺度 | 每準則 −10…+10；每例分數 = 達標分/滿分，截斷於 [0,1]；整體為平均 |
| 統計方法 | 平均、主題/軸向分數、可靠度曲線、模型–醫師一致性（macro-F1≈0.71）；未見 p 值 |
| 主要限制 | 合成而非真實就診；離線、無下游健康結果；grader 偏誤與共享盲點；context-seeking 與 worst-case 仍有明顯 headroom |

#### A2. MedHELM [S2]

| 欄位 | 內容 |
|---|---|
| 完整題名 | Holistic evaluation of large language models for medical tasks with MedHELM |
| 作者 | Suhana Bedi, Hejie Cui, Miguel Fuentes, Alyssa Unell, Michael Wornow, et al. |
| 年份 | 2026（preprint 2025） |
| venue/preprint | Nature Medicine 32, 943–951；arXiv:2505.23802 |
| DOI/URL | https://doi.org/10.1038/s41591-025-04151-2 |
| 研究任務 | 5 大類、22 子類、121 任務之整體醫療能力評估（含 patient communication/education） |
| 資料/案例來源 | 37 個評測（17 既有、18 新制、含 12 個 EHR-based）；公開/受限/私有混合 |
| 樣數 | 依 benchmark 而異；jury 驗證用 31 ACI-Bench + 25 MEDIQA-QA |
| 單/多輪 | 單輪任務完成（開放式與封閉式）；非多輪對話 |
| 模型 | Claude 3.5/3.7 Sonnet、DeepSeek R1、Gemini 1.5 Pro、Gemini 2.0 Flash、GPT-4o/mini、Llama 3.3、o3-mini |
| baseline/ablation | 跨模型比較 + 成本效能分析 |
| 重複與 temperature | NR |
| 安全定義 | 無顯式安全定義（含 RaceBias、MedHallu、MEDEC 等評測） |
| 失敗定義 | NR（報告 accuracy/win-rate，無二元失敗門檻） |
| 評審者 | 開放式採 LLM-jury（3 LLM + 專屬 rubric）；封閉式採 exact match；另以臨床醫師評分驗證 |
| 是否盲評 | NR |
| 評分尺度 | 正規化 accuracy 0–1；win-rate %；ICC |
| 統計方法 | win-rate 排名；rater-wise z 分數後之 ICC(3,k)；成本估算 |
| 主要限制 | 14 個私有資料集不可分享（僅 23 個公開/受限可完全重製） |

#### A3. ChatDoctor [S3]

| 欄位 | 內容 |
|---|---|
| 完整題名 | ChatDoctor: A Medical Chat Model Fine-Tuned on a Large Language Model Meta-AI (LLaMA) Using Medical Domain Knowledge |
| 作者 | Yunxiang Li, Zihan Li, Kai Zhang, Ruilong Dan, Steve Jiang, You Zhang |
| 年份 | 2023 |
| venue/preprint | Cureus 15(6)；arXiv:2303.14070 |
| DOI/URL | https://doi.org/10.7759/cureus.40895 |
| 研究任務 | 病患面向醫療對話與建議；可用線上/離線知識回答新疾病問題 |
| 資料/案例來源 | HealthCareMagic-100k（訓練）、icliniq.com 10k（測試）、52k Alpaca 指令；Wikipedia + 離線醫學庫檢索 |
| 樣數 | N=100,000 訓練對話；N=10,000 測試對話 |
| 單/多輪 | 多輪（來源即多輪對話） |
| 模型 | LLaMA-7B 微調（Alpaca→HealthCareMagic）vs ChatGPT；檢索增強版本 |
| baseline/ablation | 微調模型 vs ChatGPT；新疾病問答檢索 on/off |
| 重複與 temperature | 推論之 temperature 與重複次數 NR |
| 安全定義 | NR；作者明言無足夠安全措施、不可臨床使用、不保證正確 |
| 失敗定義 | NR（僅報告 precision/recall/F1 較低） |
| 評審者 | 程式自動指標（precision/recall/F1） |
| 是否盲評 | NR |
| 評分尺度 | precision、recall、F1 |
| 統計方法 | NR |
| 主要限制 | 僅供研究；不可商業/臨床使用；無足夠安全措施 |

### 群組 B：模擬標準化病患與 role-play

#### B1. AMIE（診斷對話，Nature）[S4]

| 欄位 | 內容 |
|---|---|
| 完整題名 | Towards conversational diagnostic artificial intelligence |
| 作者 | Tao Tu, Mike Schaekermann, Anil Palepu, Khaled Saab, Jan Freyberg, Ryutaro Tanno, et al. |
| 年份 | 2025（preprint 2024） |
| venue/preprint | Nature 642, 442–450；arXiv:2401.05654 |
| DOI/URL | https://doi.org/10.1038/s41586-025-08866-7 |
| 研究任務 | 診斷對話：病史詢問、診斷準確度、處置、溝通、同理心（同步文字對話） |
| 資料/案例來源 | 真人 provider 提供之 159 個 scenario pack，由**真人病人演員**演出（OSCE 形式）；訓練另用 self-play 合成對話 |
| 樣數 | N=159 案例；20 位 PCP；20 位病人演員；每案 3 位專科醫師評分；每位各 1 次 AMIE + 1 次 PCP 諮詢 |
| 單/多輪 | 多輪同步文字對話（≤20 分鐘） |
| 模型 | AMIE（instruction fine-tune + self-play + chain-of-reasoning）vs 真人 PCP；ablation 用 model auto-evaluator |
| baseline/ablation | PCP 對照；AMIE 依自身/對照對話下診斷；截斷輪數；模擬病患人格與識字程度 |
| 重複與 temperature | NR |
| 安全定義 | 無單一安全定義；含 "Escalation recommendation appropriate"、"Confabulation absent" 等軸向 |
| 失敗定義 | NR（以 top-k DDx 準確度較低、或 32/26 軸向評分較差表示） |
| 評審者 | 專科醫師 + 病人演員 + 模型 auto-evaluator |
| 是否盲評 | 是：隨機、雙盲、crossover OSCE；順序平衡 |
| 評分尺度 | 5 點 favourable–unfavourable；DDx top-k；Yes/No；4 點 DDx 完整度 |
| 統計方法 | 兩側 Wilcoxon signed-rank + FDR；bootstrap 95% CI（n=10,000） |
| 主要限制 | 文字對話對 PCP 不熟悉、不代表真實就診/遠距/傳統 OSCE；模擬環境，臨床轉譯仍需大量研究 |

#### B2. AgentClinic [S5]

| 欄位 | 內容 |
|---|---|
| 完整題名 | AgentClinic: a multimodal benchmark for tool-using clinical AI agents（preprint 題名：…to evaluate AI in simulated clinical environments） |
| 作者 | Samuel Schmidgall, Rojin Ziaei, Carl Harris, Ji Woong Kim, Eduardo Pontes Reis, Jeffrey Jopling, Michael Moor |
| 年份 | 2026（期刊）；2024（preprint） |
| venue/preprint | npj Digital Medicine；arXiv:2405.07960 |
| DOI/URL | https://doi.org/10.1038/s41746-026-02674-7 ；https://agentclinic.github.io/ |
| 研究任務 | 不完整資訊下的序列臨床決策：對話問診、透過 measurement agent 要求檢查/影像、工具使用、偏誤與多語情境 |
| 資料/案例來源 | 合成 LLM 病患 agent，grounded 於 MedQA/USMLE、去識別 MIMIC-IV、NEJM case challenges；GPT-4 生成 OSCE JSON 後人工驗證 |
| 樣數 | 215 個 MedQA-based agent；120 個 NEJM 多模態 agent；260 案例/9 專科；749 案例/7 語言；最多 20 次互動 |
| 單/多輪 | 多輪（doctor↔patient + measurement） |
| 模型 | Doctor：Claude-3.5 Sonnet、GPT-4/4o/4o-mini/3.5、Mixtral、Llama-2/3、MedLlama3、Meditron、OpenBioLLM 等；Patient/measurement/moderator 預設 GPT-4；3 位真人醫師作基準 |
| baseline/ablation | 跨模型；偏誤（23 種）；工具（notebook、reflection、RAG、CoT）；互動預算；patient 模型抽換 |
| 重複與 temperature | NR |
| 安全定義 | NR；報告 patient compliance、confidence、follow-up willingness、realism、empathy |
| 失敗定義 | 與 ground-truth 診斷不符（由 moderator agent 判定）；靜態 MedQA → 序列後準確度可掉至 1/10 以下 |
| 評審者 | LLM moderator（準確度）+ GPT-4 patient agent（態度指標）+ 3 位醫師 reader study（realism/empathy） |
| 是否盲評 | NR |
| 評分尺度 | 診斷準確度 % ± SE；正規化準確度；patient 態度指標；醫師 realism/empathy |
| 統計方法 | 平均 ± SE 與 95% CI；假設檢定 NR |
| 主要限制 | 4-agent 簡化環境；moderator 可能誤判；measurement 可能幻覺；真人基準僅 3 位；缺護理/家屬/行政角色 |

#### B3. CRAFT-MD [S6]

| 欄位 | 內容 |
|---|---|
| 完整題名 | An evaluation framework for clinical use of large language models in patient interaction tasks（CRAFT-MD） |
| 作者 | Shreya Johri, Jaehwan Jeong, Benjamin A. Tran, Daniel I. Schlessinger, Shannon Wongvibulsin, Zhuo Ran Cai, Roxana Daneshjou, Pranav Rajpurkar |
| 年份 | 2025 |
| venue/preprint | Nature Medicine 31, 77–86；medRxiv preprint |
| DOI/URL | https://doi.org/10.1038/s41591-024-03328-5 |
| 研究任務 | 對話式診斷推理：doctor-LLM 能否問診、跨輪整合、下診斷（vs 靜態 vignette） |
| 資料/案例來源 | 由真實考題 vignette 轉成 doctor-AI↔patient-AI 對話；MedQA-USMLE + 皮膚科題庫 |
| 樣數 | 共 2,000 vignettes；皮膚科子集 140；每案重複 10 次；多模態 100 對 |
| 單/多輪 | 兼具：多輪、單輪、摘要式、靜態 vignette |
| 模型 | Doctor-AI：GPT-4、GPT-3.5、LLaMA-2-7b、Mistral、GPT-4V；Patient-AI 與 Grader-AI 為 GPT-4-based |
| baseline/ablation | vignette MCQ vs 多輪/單輪/摘要；4-choice vs many-choice vs FRQ；conversational summarization |
| 重複與 temperature | 每案 10 次；temperature NR |
| 安全定義 | NR |
| 失敗定義 | 與 ground-truth 診斷不符；對話準確度相對 vignette 下降；專家指出問診不完整、未用白話、回應不可靠 |
| 評審者 | Grader-AI（診斷等價性）+ 醫學專家（驗證三種 AI 行為） |
| 是否盲評 | NR |
| 評分尺度 | 診斷準確度 %；專家檢核清單（問診、術語、grader 可靠度） |
| 統計方法 | NR（以準確度比較繪圖為主） |
| 主要限制 | 依賴模擬 agent 需專家驗證；初期聚焦皮膚科；對話推理限制持續存在 |

#### B4. SAPS / AIE（State-Aware Patient Simulator）[S7]

| 欄位 | 內容 |
|---|---|
| 完整題名 | Automatic Interactive Evaluation for Large Language Models with State Aware Patient Simulator |
| 作者 | Yusheng Liao et al. |
| 年份 | 2024 |
| venue/preprint | arXiv:2403.08495（cs.CL，正式 preprint） |
| DOI/URL | https://doi.org/10.48550/arXiv.2403.08495 |
| 研究任務 | 以多輪 role-play + 狀態感知病患模擬器（state tracker + memory + generator）自動評估 doctor-LLM |
| 資料/案例來源 | 混合真實與合成：50 真實醫院案例（衍生成 4,000 Q-A）、50 HospitalCases、150 MedicalExam（MedQA 等） |
| 樣數 | 4,000 測試題；50 HospitalCases；150 考題；7 個 doctor LLM；3 位醫學生 + 素人 |
| 單/多輪 | 多輪（約 10 輪；平均 8.7–9.8） |
| 模型 | Doctor：ChatGPT、GPT-4、星火、通義千問、InternLM、Baichuan、ChatGLM；Patient：SAPS（GPT-4-based）vs vanilla GPT-4；GPT-4 evaluator |
| baseline/ablation | SAPS vs 標準 GPT-4 病患 vs 真人病患；AIE vs MCQ；輪數/覆蓋率分析 |
| 重複與 temperature | NR |
| 安全定義 | NR（僅倫理章節提及隱私合規） |
| 失敗定義 | 資訊覆蓋率低、診斷準確度低、詢問/建議無效或含糊、問診順序不合邏輯 |
| 評審者 | 3 位醫學生（醫師視角）+ 素人（病患視角）配對偏好；GPT-4 evaluator；程式自動指標 |
| 是否盲評 | NR |
| 評分尺度 | 6 個 simulator 指標 + 8 個自動指標（Diagnosis、Coverage、Inquiry_Acc/Logic、Advice_Acc 等）；配對勝率 |
| 統計方法 | Spearman 相關（連續 vs 序位）；配對勝率；平均 ± SE |
| 主要限制 | 僅測通用指令跟隨 LLM；僅線上問診、無理學檢查；GPT-4 judge 較人類極化；人類評估樣本小 |

#### B5. 多模態 AMIE（Multimodal reasoning）[S8]

| 欄位 | 內容 |
|---|---|
| 完整題名 | Advancing conversational diagnostic AI with multimodal reasoning |
| 作者 | Khaled Saab et al. |
| 年份 | 2026 |
| venue/preprint | Nature Medicine 32, 1726–1736；Research Square preprint |
| DOI/URL | https://doi.org/10.1038/s41591-026-04371-0 |
| 研究任務 | 多模態診斷對話：於對話中策略性要求、解讀皮膚照片/ECG/文件 |
| 資料/案例來源 | 105 個 scenario，grounded 於真實資料集（SCIN、PTB-XL、臨床文件）；真人病人演員上傳檔案 |
| 樣數 | N=105 scenario；210 次諮詢（每案 2 次）；25 位病人演員；18 位專科醫師 |
| 單/多輪 | 多輪多模態文字對話（含影像/文件上傳） |
| 模型 | Multimodal AMIE（Gemini 2.0 Flash + state-aware phase reasoning）vs vanilla Gemini；PCP；auto-rater |
| baseline/ablation | AMIE vs PCP；完整推理 vs vanilla；感知測試；影像品質/幻覺子群 |
| 重複與 temperature | NR |
| 安全定義 | 未定義廣義安全；以**幻覺偵測**操作化（No / Hallucination / Significant hallucination）+ 處置適切性 |
| 失敗定義 | top-k DDx 與 ground truth 不符；MUH rubric 較低；低品質影像下準確度下降較大 |
| 評審者 | 18 位專科醫師 + 病人演員 + LLM auto-rater |
| 是否盲評 | 是：隨機、盲化 OSCE 形式；作者明言**非**預先註冊、非 RCT，屬探索性 |
| 評分尺度 | top-k DDx；32 軸（GMCPQ/PACES 1–5）；Yes/No；9 指標 MUH |
| 統計方法 | mixed-effects（P<0.001）；兩側 McNemar + FDR；one-sided chi-square；bootstrap 95% CI |
| 主要限制 | 探索性、非 RCT；虛擬文字+影像，非面診/視訊；影像品質敏感；仍需真實世界驗證 |

### 群組 C：醫療安全錯誤 taxonomy、護欄與工具/agent 評估

#### C1. MedSafetyBench [S9]

| 欄位 | 內容 |
|---|---|
| 完整題名 | MedSafetyBench: Evaluating and Improving the Medical Safety of Large Language Models |
| 作者 | Tessa Han, Aounon Kumar, Chirag Agarwal, Himabindu Lakkaraju |
| 年份 | 2024 |
| venue/preprint | NeurIPS 2024 Datasets and Benchmarks Track；arXiv:2403.03744 |
| DOI/URL | https://arxiv.org/abs/2403.03744 ；程式 https://github.com/AI4LIFE-GROUP/med-safety-bench |
| 研究任務 | 定義 LLM 醫療安全並測試模型是否拒絕有害醫療請求；再以微調改善安全而不損醫療 QA |
| 資料/案例來源 | 有害請求：GPT-4 生成 900 + Llama-2-7b-chat 經 GCG jailbreak 900；安全回應由 GPT-4 生成；另用 GenSafety-Eval |
| 樣數 | 共 1,800 示範；MedSafety-Eval n=900；MedSafety-Improve n=900；GenSafety-Eval n=330；25 位醫師參與驗證 |
| 單/多輪 | 單輪（一請求→一回應） |
| 模型 | Medalpaca、Meditron、ClinicalCamel、Med42；與其通用基底及 chat/instruct 版本對照 |
| baseline/ablation | 醫療 LLM vs 通用基底 vs safety-aligned；微調資料 ablation（general/medical/both；不同 n） |
| 重複與 temperature | NR |
| 安全定義 | 輸出**安全** = 準確且符合 AMA 醫學倫理原則；安全模型應**拒絕**有害醫療請求（refusal 作為安全代理） |
| 失敗定義 | 失敗 = 順從（harmfulness score >1）；taxonomy = AMA 九原則 + 11 類一般危害 |
| 評審者 | 規則 + LLM：GPT-3.5 harmfulness rater；25 位醫師驗證是否違反與違反何原則 |
| 是否盲評 | NR |
| 評分尺度 | 每回應 harmfulness 1–5（1=完全拒絕、5=完全順從） |
| 統計方法 | 描述性平均 ± SEM；未見推論檢定 |
| 主要限制 | refusal 為最嚴格、可能過度拒絕；未涵蓋多輪或病患衛教情境 |

#### C2. WildGuard [S10]

| 欄位 | 內容 |
|---|---|
| 完整題名 | WildGuard: Open One-Stop Moderation Tools for Safety Risks, Jailbreaks, and Refusals of LLMs |
| 作者 | Seungju Han, Kavel Rao, Allyson Ettinger, Liwei Jiang, Bill Yuchen Lin, Nathan Lambert, Yejin Choi, Nouha Dziri |
| 年份 | 2024 |
| venue/preprint | NeurIPS 2024 Datasets and Benchmarks Track；arXiv:2406.18495 |
| DOI/URL | https://arxiv.org/abs/2406.18495 |
| 研究任務 | 一站式審核：prompt harm／response harm／refusal 偵測；於人機介面作 guardrail |
| 資料/案例來源 | WildGuardMix 92K：合成 + 對抗（WildTeaming）+ 真實 in-the-wild + 標註者撰寫 |
| 樣數 | 訓練 86,759；測試 5,299（人工標註）；另 10 個公開 benchmark |
| 單/多輪 | 單輪 prompt–response 配對 |
| 模型 | Guard 本體 Mistral-7B 微調；對照 Llama-Guard/Llama-Guard2、Aegis-Guard、HarmBench、MD-Judge、OAI Moderation、GPT-4 等 |
| baseline/ablation | 10 個開源 baseline + GPT-4；資料成分/多任務/骨幹 ablation |
| 重複與 temperature | NR（分類器、確定性評估） |
| 安全定義 | 正確分類惡意意圖/風險；**區分 harm 與 refusal**（無害拒絕≠有害） |
| 失敗定義 | 三任務之一誤分類；taxonomy = 4 大類 13 子類（隱私、錯誤資訊、有害語言、惡意用途）+ 對抗 jailbreak + 良性對照測過度拒絕 |
| 評審者 | 人類：每題 3 位標註者；訓練過濾與稽核用 GPT-4 |
| 是否盲評 | NR |
| 評分尺度 | 各任務 F1 %；Fleiss kappa（prompt harm 0.55、refusal 0.72、response harm 0.50） |
| 統計方法 | 描述性 F1 差異；未見推論檢定 |
| 主要限制 | 單輪；分類式而非生成式安全評估 |

#### C3. ToolEmu [S11]

| 欄位 | 內容 |
|---|---|
| 完整題名 | Identifying the Risks of LM Agents with an LM-Emulated Sandbox（ToolEmu） |
| 作者 | Yangjun Ruan, Honghua Dong, Andrew Wang, Silviu Pitis, Yongchao Zhou, Jimmy Ba, Yann Dubois, Chris J. Maddison, Tatsunori Hashimoto |
| 年份 | 2023（arXiv）/ 2024（peer-reviewed） |
| venue/preprint | ICLR 2024；arXiv:2309.15817 |
| DOI/URL | https://arxiv.org/abs/2309.15817 ；http://toolemu.com/ |
| 研究任務 | 以 LM 模擬的沙盒，發掘「良性但欠具體」指令導致之 risky tool action，並量化風險與有用性 |
| 資料/案例來源 | 作者策劃 36 個高風險 toolkit + 144 測試案例；GPT-4 模擬工具輸出；adversarial emulator |
| 樣數 | 144 案例；36 toolkit；200 軌跡驗證；7 個嚴重案例於真實 bash 檢查 |
| 單/多輪 | 多步 tool-use 軌跡（多輪 agent–tool 迴圈） |
| 模型 | 明列 GPT-4、ChatGPT-3.5、Claude-2（最安全 23.9% 失敗率）；完整受測集 NR |
| baseline/ablation | 標準 vs adversarial emulator；加入安全要求提示；temperature 效應 |
| 重複與 temperature | 主實驗 NR；ablation 變化 temperature（值 NR） |
| 安全定義 | 不因工具動作造成傷害；安全 agent 會先釐清、避免臆測/捏造、尊重風險 |
| 失敗定義 | 執行了 risky action 並產生後果；taxonomy = 約 9 類風險 + 4 種行為模式（捏造/臆測、誤解、錯誤執行、忽視風險） |
| 評審者 | LLM（GPT-4）安全/有用性評估器 + 3 位人類標註者多數決 |
| 是否盲評 | NR |
| 評分尺度 | 失敗率 %；realism %；一致性 %；有用性分數（尺度 NR） |
| 統計方法 | 描述性率與一致性；未見推論檢定 |
| 主要限制 | emulator/evaluator 品質；144 案例非窮盡；偏自動化 red-teaming 需監督 |

#### C4. AgentHarm [S12]

| 欄位 | 內容 |
|---|---|
| 完整題名 | AgentHarm: A Benchmark for Measuring Harmfulness of LLM Agents |
| 作者 | Maksym Andriushchenko, Alexandra Souly, Mateusz Dziemian, et al. |
| 年份 | 2024（arXiv）/ 2025（peer-reviewed） |
| venue/preprint | ICLR 2025；arXiv:2410.09024 |
| DOI/URL | https://arxiv.org/abs/2410.09024 |
| 研究任務 | 量測 agent 於明確惡意多步工具的完成度，以及 jailbreak 是否保留能力並繞過拒絕 |
| 資料/案例來源 | 行為全部手寫 + 獨立審閱；104 個合成工具（Inspect）；每行為具良性改寫；canary + 私有分割防污染 |
| 樣數 | 110 基礎行為；440（含擴充）；公開測試 264、私有測試 132；平均 3.53 函式/行為 |
| 單/多輪 | 多輪多步（需依序相依工具呼叫） |
| 模型 | GPT-3.5、GPT-4o/mini、Claude Haiku/Sonnet/Opus/3.5、Gemini 1.0/1.5、Mistral、Llama-3.1（8B–405B） |
| baseline/ablation | 直接請求 vs forced tool-call vs universal jailbreak；良性能力基準；best-of-5、temperature、hint |
| 重複與 temperature | 預設 temp 0、max 4096 tokens、GPT-4o judge；best-of-n 於 temp 1.0 |
| 安全定義 | 拒絕執行明確惡意 agentic 請求；高拒絕 + 低傷害 = 安全 |
| 失敗定義 | 未拒絕 + 分級完成；taxonomy = 11 類危害（詐欺、網路犯罪、自傷、騷擾、性、著作權、毒品、假訊息、仇恨、暴力、恐怖主義） |
| 評審者 | 規則：人工評分 rubric（精確工具參數）+ 子任務用窄域 LLM judge + 拒絕 judge；**非**整段 LLM 評分 |
| 是否盲評 | NR |
| 評分尺度 | harm score 0–100% + refusal % + non-refusal harm % |
| 統計方法 | 描述性分數；抽樣 SD；未見推論檢定 |
| 主要限制 | 合成工具為代理；任務刻意簡化；僅直接請求威脅模型；部分模型需特殊處理 |

#### C5. MedAgentBench [S13]

| 欄位 | 內容 |
|---|---|
| 完整題名 | MedAgentBench: A Realistic Virtual EHR Environment to Benchmark Medical LLM Agents |
| 作者 | Yixing Jiang, Kameron C. Black, Gloria Geng, Danny Park, James Zou, Andrew Y. Ng, Jonathan H. Chen |
| 年份 | 2025 |
| venue/preprint | NEJM AI 2025;2(9)；arXiv:2501.14654 |
| DOI/URL | https://doi.org/10.1056/AIdbp2500144 ；https://arxiv.org/abs/2501.14654 |
| 研究任務 | LLM agent 能否透過 FHIR API 自主完成醫師指定之 EHR 任務（檢索 + 開立） |
| 資料/案例來源 | 300 任務由 2 位內科醫師撰寫；100 位病人（STARR 去識別 + jitter）；HAPI FHIR JPA Docker |
| 樣數 | 300 任務/10 類（150 GET、150 POST）；100 病人；785,207 筆紀錄 |
| 單/多輪 | 多輪 agent 互動，最多 8 回合 |
| 模型 | 12 個（Claude 3.5 Sonnet v2、o3-mini、GPT-4o/mini、Gemini 2.0/1.5、DeepSeek-V3、Qwen2.5、Llama 3.3、Gemma2、Mistral） |
| baseline/ablation | 簡易 orchestrator（9 個 FHIR 函式）為基準；query vs action 分群；難度分群 |
| 重複與 temperature | 除 o3-mini 外 temperature 0；僅 pass@1（無 pass@k） |
| 安全定義 | 無安全定義（能力導向 benchmark）；不安全僅以「無效動作/超過回合/格式錯誤」操作化 |
| 失敗定義 | 無安全 taxonomy；失敗 = 無效 GET/POST、答案格式錯誤、sanity check 失敗；分 query-SR 與 action-SR |
| 評審者 | 僅規則：人工 curate grader + reference solution + POST payload 規則檢查 |
| 是否盲評 | NR（N/A） |
| 評分尺度 | 任務成功率 %；最佳 69.67%（Claude 3.5 Sonnet v2），範圍 4.00–69.67% |
| 統計方法 | 描述性成功率；未見推論檢定/CI |
| 主要限制 | 單中心 Stanford、非族群代表；無跨團隊協作；僅病歷情境；模擬無安全/日誌；未測重複可靠性 |

### 群組 D：LLM-as-a-Judge 效度

#### D1. MT-Bench / Chatbot Arena [S14]

| 欄位 | 內容 |
|---|---|
| 完整題名 | Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena |
| 作者 | Lianmin Zheng, Wei-Lin Chiang, Ying Sheng, Siyuan Zhuang, Zhanghao Wu, Yonghao Zhuang, Zi Lin, Zhuohan Li, Dacheng Li, Eric P. Xing, Hao Zhang, Joseph E. Gonzalez, Ion Stoica |
| 年份 | 2023 |
| venue/preprint | NeurIPS 2023 Datasets and Benchmarks Track；arXiv:2306.05685 |
| DOI/URL | https://arxiv.org/abs/2306.05685 |
| 研究任務 | 驗證 LLM-as-judge 對開放式對話評估與人類偏好之一致性；量化 position/verbosity/self-enhancement 偏誤 |
| 資料/案例來源 | MT-bench（作者建構）+ Chatbot Arena 群眾對戰 |
| 樣數 | 80 題（8 類×10）；約 3,000 專家票；約 30,000 Arena 對話；58 位專家標註者 |
| 單/多輪 | 兼具：MT-bench 多輪（2 輪）、Arena 單輪 |
| 模型 | Judge：GPT-4、GPT-3.5、Claude-V1；受評含 Vicuna、Alpaca、LLaMA、Koala、Dolly |
| baseline/ablation | 人類多數決為 gold；配對 vs 單答評分；含/不含 tie；位置互換 |
| 重複與 temperature | NR（以位置互換與重複判斷衡量偏誤） |
| 安全/效度定義 | 效度 = 與人類偏好之一致率；無臨床安全定義 |
| 判斷失敗/不一致 | position bias、verbosity bias、self-enhancement、數學/推理失誤；不一致 = judge 判定 ≠ 人類多數 |
| 對照評審類型 | 人類（58 位研究生專家 + 群眾）與 LLM |
| 是否盲評 | Arena 是（兩模型匿名） |
| 評分尺度 | 配對 win/tie/lose + 單答 grading |
| 一致性統計 | 一致率；GPT-4–人類 >80%；未見 kappa/ICC |
| 主要限制 | 數學/程式推理有限；殘餘偏誤；通用領域、非醫療 |

#### D2. FairEval（位置偏誤校正）[S15]

| 欄位 | 內容 |
|---|---|
| 完整題名 | Large Language Models are not Fair Evaluators |
| 作者 | Peiyi Wang, Lei Li, Liang Chen, Zefan Cai, Dawei Zhu, Binghuai Lin, Yunbo Cao, Lingpeng Kong, Qi Liu, Tianyu Liu, Zhifang Sui |
| 年份 | 2024 |
| venue/preprint | ACL 2024（Long Papers, pp. 9440–9450）；arXiv:2305.17926 |
| DOI/URL | https://aclanthology.org/2024.acl-long.511/ |
| 研究任務 | 證明並校正 LLM-as-evaluator 之位置偏誤 |
| 資料/案例來源 | Vicuna Benchmark；ChatGPT vs Vicuna-13B、Vicuna vs Alpaca |
| 樣數 | 80 題；作者人工 win/tie/lose 標註 |
| 單/多輪 | 單輪配對比較 |
| 模型 | Judge：GPT-4、ChatGPT |
| baseline/ablation | 未校正模板 vs Multiple Evidence Calibration vs Balanced Position Calibration vs Human-in-the-Loop |
| 重複與 temperature | BPC 用 2 次順序互換；temperature NR |
| 效度定義 | 效度 = 與人類判定之對齊；公平性 = 對順序不變 |
| 判斷失敗/不一致 | Conflict Rate = 交換順序後判定翻轉機率；positional preference；self-conflict |
| 對照評審類型 | 人類標註者與 LLM |
| 是否盲評 | NR |
| 評分尺度 | 1–10 分映到 win/tie/lose |
| 一致性統計 | Conflict Rate（GPT-4 46.3%/5.0%；ChatGPT 82.5%/52.5%）；Cohen's kappa 改善（GPT-4 0.24→0.37） |
| 主要限制 | 僅 Vicuna-80；僅 GPT-4/ChatGPT；品質差距小者偏誤最大 |

#### D3. G-Eval [S16]

| 欄位 | 內容 |
|---|---|
| 完整題名 | G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment |
| 作者 | Yang Liu, Dan Iter, Yichong Xu, Shuohang Wang, Ruochen Xu, Chenguang Zhu |
| 年份 | 2023 |
| venue/preprint | EMNLP 2023（pp. 2511–2522）；arXiv:2303.16634 |
| DOI/URL | https://aclanthology.org/2023.emnlp-main.153/ |
| 研究任務 | 無參考 NLG 評估（LLM + CoT + form-filling）；測人類對齊與自偏好偏誤 |
| 資料/案例來源 | SummEval（摘要）、Topical-Chat（對話） |
| 樣數 | NR（標準 split） |
| 單/多輪 | 單輪摘要 + 單輪對話回應（對話歷史為輸入） |
| 模型 | Judge：GPT-4、GPT-3.5 |
| baseline/ablation | 對照 BLEU/ROUGE/BERTScore/BARTScore/UniEval/GPTScore；GPT-4 vs GPT-3.5；有/無 CoT |
| 重複與 temperature | 機率加權評分、多次取樣（n/temperature NR） |
| 效度定義 | 與人類判斷之 Spearman/Kendall 相關 |
| 判斷失敗/不一致 | 低人類相關；偏好 LLM 生成而非人類文本；人類間一致性極低（Krippendorff's α 0.07） |
| 對照評審類型 | 人類（SummEval/Topical-Chat）與 LLM 及自動指標 |
| 是否盲評 | NR |
| 評分尺度 | form-filling 1–5 維度分 |
| 一致性統計 | Spearman ρ（G-Eval-4 摘要平均 0.514）；Kendall-Tau；Krippendorff's α |
| 主要限制 | 自偏好偏誤；難評高品質系統；僅英文摘要/對話 |

#### D4. Ayers 2023（醫師 vs 聊天機器人）[S17]

| 欄位 | 內容 |
|---|---|
| 完整題名 | Comparing Physician and Artificial Intelligence Chatbot Responses to Patient Questions Posted to a Public Social Media Forum |
| 作者 | John W. Ayers, Adam Poliak, Mark Dredze, Eric C. Leas, Zechariah Zhu, et al. |
| 年份 | 2023 |
| venue/preprint | JAMA Internal Medicine 183(6):589–596 |
| DOI/URL | https://doi.org/10.1001/jamainternmed.2023.1838 |
| 研究任務 | ChatGPT 對公開病患提問之回應，其品質與同理心是否可比醫師 |
| 資料/案例來源 | Reddit r/AskDocs（經核實醫師答覆）；ChatGPT 新 session 回答 |
| 樣數 | 195 題；585 次評估（每題三次） |
| 單/多輪 | 單輪 Q+A |
| 模型 | 無 LLM judge；由具照護專業人士評分 |
| baseline/ablation | 醫師回覆為基準；依長度敏感度分析 |
| 重複與 temperature | 每題 3 次獨立人工評分；temperature N/A |
| 安全/效度定義 | 無正式安全量表；以資訊品質、同理心、偏好為代理 |
| 判斷失敗/不一致 | NR（報告平均差，無失敗門檻） |
| 對照評審類型 | 人類（具照護專業） |
| 是否盲評 | 是（匿名、隨機排序、來源盲化） |
| 評分尺度 | 品質 1–5、同理心 1–5、強迫選擇較佳者 |
| 統計方法 | t 檢定、95% CI、比例；未見 kappa/ICC |
| 主要限制 | 公開論壇非臨床訊息；僅 GPT-3.5；聊天機器人回覆顯著較長；無結果/安全裁定 |

#### D5. Med-PaLM [S18]

| 欄位 | 內容 |
|---|---|
| 完整題名 | Large language models encode clinical knowledge |
| 作者 | Karan Singhal, Shekoofeh Azizi, Tao Tu, S. Sara Mahdavi, et al. |
| 年份 | 2023 |
| venue/preprint | Nature 620:172–180；arXiv:2212.13138 |
| DOI/URL | https://doi.org/10.1038/s41586-023-06291-2 |
| 研究任務 | 建立 MultiMedQA 並進行醫師/素人長答評估；以 instruction prompt tuning 對齊 |
| 資料/案例來源 | MultiMedQA（MedQA、MedMCQA、PubMedQA、MMLU clinical、LiveQA、MedicationQA）+ 新增 HealthSearchQA |
| 樣數 | 長答人類評估 140 題；9 位臨床醫師；每答 1 位評審；1,000 次 bootstrap |
| 單/多輪 | 單輪醫療 QA |
| 模型 | 無 LLM judge；醫師面板 + 素人 |
| baseline/ablation | PaLM vs Flan-PaLM vs Med-PaLM vs 醫師；scale 8B/62B/540B；few-shot/CoT/self-consistency |
| 重複與 temperature | 每長答 1 位人類評審；self-consistency 11 次解碼（選擇性預測 41 次）；temperature NR |
| 安全/效度定義 | 與臨床共識一致、錯誤/遺漏、可能傷害可能性與程度、偏誤、理解、推理、完整、相關、有用 |
| 判斷失敗/不一致 | 模型回答劣於醫師（如 Flan-PaLM 61.9% 共識一致 vs Med-PaLM 92.6%）；Flan-PaLM 29.7% 可能有害 vs Med-PaLM 5.9% |
| 對照評審類型 | 醫師 + 素人；無 LLM judge |
| 是否盲評 | 是（三組答案來源隱藏） |
| 評分尺度 | 各軸 Likert 類別式 |
| 統計方法 | 非參數 bootstrap（1,000）95% 百分位區間 |
| 主要限制 | pilot 框架；每答單一評審；140 題；Med-PaLM 整體仍遜於醫師 |

#### D6. Med-PaLM 2 [S19]

| 欄位 | 內容 |
|---|---|
| 完整題名 | Toward expert-level medical question answering with large language models |
| 作者 | Karan Singhal, Tao Tu, Juraj Gottweis, Rory Sayres, Ellery Wulczyn, et al. |
| 年份 | 2025（期刊）；preprint 2023 |
| venue/preprint | Nature Medicine 31:943–950；arXiv:2305.09617 |
| DOI/URL | https://doi.org/10.1038/s41591-024-03423-7 |
| 研究任務 | 以 PaLM 2 + 醫療微調 + ensemble refinement 追求醫師級長答；與醫師配對偏好與床邊諮詢 pilot |
| 資料/案例來源 | MultiMedQA 選擇題；長答 consumer sets（140、1066）、240 對抗、20 真實床邊問題 |
| 樣數 | 1,066 配對；140 獨立；240 對抗；20 床邊×11 評審 |
| 單/多輪 | 單輪 QA（床邊為檢索增強） |
| 模型 | 無 LLM judge；醫師（一般/專科）+ 素人 |
| baseline/ablation | Med-PaLM vs Med-PaLM 2 vs 醫師；few-shot/self-consistency/ensemble refinement；overlap 分析 |
| 重複與 temperature | 獨立評估 1 評審/答；配對/床邊 11 次重複 + clustered bootstrap；temperature NR |
| 安全/效度定義 | 九臨床軸（共識、理解、召回、推理、遺漏、不準/無關、傷害可能性與程度、偏誤） |
| 判斷失敗/不一致 | 偏好對照方；Med-PaLM 2 僅在「不準/無關」軸遜於醫師；低風險傷害 90.6% |
| 對照評審類型 | 醫師 + 素人 |
| 是否盲評 | NR（abstract 未重述） |
| 評分尺度 | 最高品質級比例 + 配對偏好 |
| 統計方法 | clustered bootstrap 95% CI；9 軸中 8 軸 P<0.001；Bonferroni |
| 主要限制 | 選擇題 overlap；小測集與標籤噪聲；回覆顯著較長；床邊 n=20；需真實世界驗證 |

#### D7. 臨床摘要 LLM-as-a-Judge（PDSQI-9）[S20]

| 欄位 | 內容 |
|---|---|
| 完整題名 | Evaluating clinical AI summaries with large language models as judges |
| 作者 | Emma Croxford, Yanjun Gao, Elliot First, Nicholas Pellegrino, Miranda Schnier, John Caskey, et al. |
| 年份 | 2025 |
| venue/preprint | npj Digital Medicine；DOI 10.1038/s41746-025-02005-2 |
| DOI/URL | https://doi.org/10.1038/s41746-025-02005-2 |
| 研究任務 | 以 PDSQI-9 為 benchmark，比較 LLM-as-a-Judge 與人類專家評分臨床摘要 |
| 資料/案例來源 | 真實 EHR 多文件摘要；ProbSum 2023 跨任務驗證 |
| 樣數 | 7 位醫師評 779 份摘要、逾 8,000 項目；ICC 檢定力 >80% |
| 單/多輪 | 單輪摘要評估 |
| 模型 | GPT-o3-mini 等 open/closed LLM judges；多種提示策略與 fine-tune |
| baseline/ablation | zero-shot/few-shot/SFT/DPO/multi-agent；人類 7 評估者為基準 |
| 重複與 temperature | 7 次 LLM 迭代取中位數；temperature NR |
| 安全/效度定義 | 效度 = 與人類之 ICC；無安全（有害）定義 |
| 判斷失敗/不一致 | 以 ICC/Krippendorff α/Gwet's Ac2 量化；未設臨床失敗門檻 |
| 對照評審類型 | 人類醫師（7 位）與 LLM |
| 是否盲評 | NR |
| 評分尺度 | PDSQI-9 九屬性之 Likert/二元 |
| 統計方法 | ICC（GPT-o3-mini 最高 0.818, 95% CI 0.772–0.854）；Wilcoxon；Krippendorff α；Gwet's Ac2 |
| 主要限制 | LLM judge 對熟悉之摘要任務較佳，跨任務/跨院外推需驗證 |

> 註：此篇與 MedJUDGE 回顧 [S21] 皆指出「judge–醫師一致度僅接近醫師–醫師一致度之上限」，不可解讀為 judge 等於醫師。

#### D8. MedJUDGE（醫療 LaaJ scoping review）[S21]

| 欄位 | 內容 |
|---|---|
| 完整題名 | A Scoping Review of LLM-as-a-Judge in Healthcare and the MedJUDGE Framework |
| 作者 | Chenyu Li, Zohaib Akhtar, Mingu Kwak, Yuelyu Ji, Hang Zhang, et al. |
| 年份 | 2026 |
| venue/preprint | arXiv:2604.25933（cs.CY） |
| DOI/URL | https://arxiv.org/abs/2604.25933 |
| 研究任務 | PRISMA-ScR 回顧 2020-01 至 2026-01 六資料庫；提出風險分級治理框架 |
| 資料/案例來源 | 篩選 11,727 篇、納入 49 篇 |
| 樣數 | 49 篇；其中 36 篇有人類參與 |
| 單/多輪 | 回顧（涵蓋單/多輪） |
| 模型 | 以 GPT 家族 judge 為主（73.5%） |
| baseline/ablation | 75.5% 為評估/benchmark 用途；85.7% pointwise 評分 |
| 重複與 temperature | NR |
| 安全/效度定義 | 提出 validity／safety／accountability 三支柱與臨床風險分級 |
| 判斷失敗/不一致 | 一致度指標可能無法區分「真效度」與「共享盲點」 |
| 對照評審類型 | 人類專家（中位數僅 3 位；26.5% 完全無人） |
| 是否盲評 | NR |
| 評分尺度 | NR（回顧） |
| 統計方法 | 回顧性彙整；引用 HealthBench 模型–醫師 MF1 0.572–0.706 vs 醫師–醫師 0.569–0.730 |
| 主要限制 | 73.5% 研究未做 risk-of-bias、僅 2.0% 檢視族群公平性；多數未部署 |

#### D9. Same Verdict, Different Reasons [S22]

| 欄位 | 內容 |
|---|---|
| 完整題名 | Same Verdict, Different Reasons: LLM-as-a-Judge and Clinician Disagreement on Medical Chatbot Completeness |
| 作者 | Alexandra DeLucia, Heyuan Huang, Sonal Joshi, Mahsa Yarmohammadi, Ahmed Hassoon, Mark Dredze |
| 年份 | 2026 |
| venue/preprint | arXiv:2604.16383（cs.CY） |
| DOI/URL | https://arxiv.org/abs/2604.16383 |
| 研究任務 | 壓力測試 LLM judge 對「病患面向醫療回覆是否不完整」之判別力，並比對醫師標註 |
| 資料/案例來源 | 兩個醫師標註資料集：MedExpert 與 HealthBench |
| 樣數 | 依資料集（HealthBench 為大型集）；三種 rubric 粒度×三骨幹模型 |
| 單/多輪 | 單輪回覆完整度 |
| 模型 | 三骨幹 judge（含 GPT-5 Mini 等） |
| baseline/ablation | General-Likert / Analytical-Rubric / Dynamic-Checklist 三粒度 |
| 重複與 temperature | NR |
| 安全/效度定義 | 效度 = 與醫師「完整/不完整」判定之一致 |
| 判斷失敗/不一致 | AUC 0.49–0.66（近隨機）；共享判定的完整推理對齊僅 24.6%；偽陽性 50–81% 為過度標記非必要缺口 |
| 對照評審類型 | 人類醫師標註與 LLM judge |
| 是否盲評 | NR |
| 評分尺度 | 完整度分數 + AUC |
| 統計方法 | AUC、operating point（90% recall）、reasoning-alignment 分類 |
| 主要限制 | 僅完整度單一面向；結論不支持作自主評估或臨床分診 |

#### D10. 全球健康 LLM judge vs 人類 [S23]

| 欄位 | 內容 |
|---|---|
| 完整題名 | Human evaluators vs. LLM-as-a-Judge: toward scalable evaluation of GenAI in global health |
| 作者 | Gwydion Williams, Samuel Rutunda, Floris Nzabakira, Bilal A. Mateen et al. |
| 年份 | 2026 |
| venue/preprint | npj Digital Medicine；DOI 10.1038/s41746-026-02992-w |
| DOI/URL | https://www.nature.com/articles/s41746-026-02992-w |
| 研究任務 | 比較 5 個 LLM judge 與 6 位臨床醫師對盧安達衛生工作者提問回覆之評分 |
| 資料/案例來源 | 盧安達衛生工作者提問之 GenAI 回覆 |
| 樣數 | 5 LLM judges、6 位人類臨床醫師；11 個評估準則 |
| 單/多輪 | 單輪回覆評估 |
| 模型 | Claude-4.1-Opus、Gemini-2.5-Pro、GPT-5 等 |
| baseline/ablation | 個別 judge vs LLM-jury（組合以平衡偏誤） |
| 重複與 temperature | NR |
| 安全/效度定義 | 效度 = 與人類評分一致；另計成本效益 |
| 判斷失敗/不一致 | 最佳 judge 僅在 11 準則中 4 項與人類相符；部分過寬/過嚴；英→Kinyarwanda 表現與成本效益下降 |
| 對照評審類型 | 人類臨床醫師與 LLM |
| 是否盲評 | NR |
| 評分尺度 | 11 準則評分 |
| 統計方法 | 準則層級一致度比較 |
| 主要限制 | LLM judge 對語言與文化脈絡掌握不足 |

#### D11. MedQADE（德語開放式臨床）[S24]

| 欄位 | 內容 |
|---|---|
| 完整題名 | Clinician-Level Agreement Without Clinical Caution: LLM Evaluator Limits in Medical AI Benchmarking |
| 作者 | William Philipp, Finn Fassbender, Daniel Fister et al. |
| 年份 | 2026 |
| venue/preprint | arXiv:2607.01103（v2） |
| DOI/URL | https://arxiv.org/html/2607.01103v2 |
| 研究任務 | 建立德語開放式評分基準，檢驗 LLM judge 是否複製臨床校準與審慎 |
| 資料/案例來源 | 由 Ankizin 語料 26,598 題衍生之 3,800 分層題 |
| 樣數 | 3,800 題；9 位執業（神經科）醫師 + 第 10 位裁決；9 個 LLM evaluator |
| 單/多輪 | 單輪 |
| 模型 | Gemini 3 Flash 等 9 個 evaluator |
| baseline/ablation | 醫師 leave-one-out ceiling vs LLM |
| 重複與 temperature | NR |
| 安全/效度定義 | 效度 = 與醫師 ceiling 之 Cohen's κ；另測 abstention 作為臨床審慎 |
| 判斷失敗/不一致 | 前沿模型幾乎不 abstain（醫師會依難度 abstain）；存在 lineage self-enhancement 偏誤 |
| 對照評審類型 | 醫師與 LLM |
| 是否盲評 | NR |
| 評分尺度 | Correct/Incorrect/Abstain |
| 統計方法 | Cohen's κ（Gemini 3 Flash 0.694 vs ceiling 0.709）；leave-one-out |
| 主要限制 | κ 信賴區間寬（約 0.13）；統計對齊 ≠ 臨床審慎 |

### 群組 E：糖尿病與病患衛教對話

#### E1. Sng 2023（Diabetes Care）[S25]

| 欄位 | 內容 |
|---|---|
| 完整題名 | Potential and Pitfalls of ChatGPT and Natural-Language Artificial Intelligence Models for Diabetes Education |
| 作者 | Gerald Gui Ren Sng, Joshua Yi Min Tung, Daniel Yan Zheng Lim, Yong Mong Bee |
| 年份 | 2023 |
| venue/preprint | Diabetes Care 46(5):e103–e105（e-Letters/Observations） |
| DOI/URL | https://doi.org/10.2337/dc23-0197 |
| 研究任務 | 檢視 ChatGPT 對糖尿病自我管理衛教（DSME）建議之品質與真實性 |
| 資料/案例來源 | 研究者自撰之常見 DSME 問題（飲食運動、高低血糖、胰島素儲存、注射） |
| 樣數 | 題數 NR；無受試者；2 次 run 檢視一致性 |
| 單/多輪 | 多輪（不結構化、模擬真實病患） |
| 模型 | ChatGPT（GPT-3、知識截止 2021）；版本/參數 NR |
| baseline/ablation | NR（無對照模型）；比較 2 次迭代一致性 |
| 重複與 temperature | 2 次不結構化迭代；temperature NR |
| 安全定義 | 無數值量表；以「潛在事實不準確構成安全疑慮」框定；hallucination |
| 失敗定義 | 質性優缺點表：未辨識胰島素類似物室溫保存、飲食計畫僵化、單位混淆（mg/dL vs mmol/L）、偽低血糖誤判等 |
| 評審者 | 作者本人（醫師/研究者）質性評估；無獨立面板 |
| 是否盲評 | NR |
| 評分尺度 | NR（無數值量表） |
| 統計方法 | NR（描述性；稱兩次迭代內容一致） |
| 主要限制 | 訓練資料通用非專科、知識截止；無來源、難驗證；須人類專業核實 |

#### E2. Huang 2023（J Transl Med）[S26]

| 欄位 | 內容 |
|---|---|
| 完整題名 | Evaluate the accuracy of ChatGPT's responses to diabetes questions and misconceptions |
| 作者 | Chunling Huang, Lijun Chen, Huibin Huang, Qingyan Cai, Ruhai Lin, Xiaohong Wu, Yong Zhuang, Zhengrong Jiang |
| 年份 | 2023 |
| venue/preprint | Journal of Translational Medicine 21:502（Letter） |
| DOI/URL | https://doi.org/10.1186/s12967-023-04354-6 |
| 研究任務 | 評估 ChatGPT 對常見糖尿病問題與迷思之回答準確度 |
| 資料/案例來源 | 網路搜尋常見提問/誤解；12 題 |
| 樣數 | 12 題；5 位專科評估者 |
| 單/多輪 | 單輪（每題獨立；另做重複測一致性） |
| 模型 | ChatGPT（GPT-3.5-turbo）；無檢索/系統提示描述 |
| baseline/ablation | NR |
| 重複與 temperature | 每題 5 次；temperature NR |
| 安全定義 | NR（以「確保提供醫療建議之精確與可靠」框定） |
| 失敗定義 | 0–10 準確度量表（<6 為不準確）；列舉不完整/不精確案例（代糖、空腹血糖正常範圍、可否治癒） |
| 評審者 | 5 位內分泌專科醫師 |
| 是否盲評 | NR |
| 評分尺度 | 0–10 準確度 + 詞數/Flesch-Kincaid |
| 統計方法 | 描述性 mean ± SD；未見推論檢定 |
| 主要限制 | 未評病患同理感受；無引用難驗證；題目未涵蓋全部糖尿病議題 |

#### E3. RISE（糖尿病衛教 RAG）[S27]

| 欄位 | 內容 |
|---|---|
| 完整題名 | Enhancement of the Performance of Large Language Models in Diabetes Education through Retrieval-Augmented Generation: Comparative Study |
| 作者 | Dingqiao Wang, Jiangbo Liang, Jinguo Ye, Jingni Li, et al. |
| 年份 | 2024 |
| venue/preprint | Journal of Medical Internet Research 26:e58041 |
| DOI/URL | https://doi.org/10.2196/58041 |
| 研究任務 | 評估 RISE 檢索增強框架能否提升 LLM 對糖尿病提問之準確且安全回應 |
| 資料/案例來源 | 43 題來自 NIDDK 網站（5 領域）；檢索語料 >600 PubMed Central 全文 + >200 學術網站 |
| 樣數 | 43 題 × 6 模型變體 = 258 回應；3 位臨床醫師 + 3 位糖尿病病患評分 |
| 單/多輪 | 單輪（每題獨立、重置對話） |
| 模型 | GPT-4、Claude 2、Google Bard 及各自 RISE 版本 |
| baseline/ablation | base vs RISE（配對） |
| 重複與 temperature | 每題餵入一次；temperature NR；評分分 6 回合、間隔 48 小時 |
| 安全定義 | 系統層級：24 條規則 + 2 步 fact-check + 「不確定就說不知道」提示；無獨立安全分數 |
| 失敗定義 | 準確度 Poor=1/Borderline=2/Good=3；以多數共識定案；未達 Good 即失敗 |
| 評審者 | 3 位一般醫學 >5 年臨床醫師（準確/完整）+ 3 位糖尿病病患（可理解性） |
| 是否盲評 | 是（去識別、隨機 6 回合） |
| 評分尺度 | 準確度 1–3（合計 max 9）；完整性與可理解性平均分 |
| 統計方法 | 平均（SD）與準確率；部分 P 值（檢定名 NR） |
| 主要限制 | 僅糖尿病領域；僅預設題目；未做真實臨床試驗 |

#### E4. Kelly 2025（T2DM 客製化 AI chatbot）[S28]

| 欄位 | 內容 |
|---|---|
| 完整題名 | The Effectiveness of a Custom AI Chatbot for Type 2 Diabetes Mellitus Health Literacy: Development and Evaluation Study |
| 作者 | Anthony Kelly, Eoin Noctor, Laura Ryan, Pepijn van de Ven |
| 年份 | 2025 |
| venue/preprint | Journal of Medical Internet Research 27:e70131 |
| DOI/URL | https://doi.org/10.2196/70131 |
| 研究任務 | 評估 RAG AI chatbot 提升 T2DM 健康識能之成效（來源標註） |
| 資料/案例來源 | 2 份健康識能文件 + 1 份基層文件；44 題改編自 Hernandez et al.（依愛爾蘭調整）+ 16 題自由模擬諮詢 |
| 樣數 | 44 題 + 16 題模擬諮詢；2 位內分泌專科（共識）評估 |
| 單/多輪 | 兼具：單輪 44 題；多輪 16 題模擬諮詢 |
| 模型 | RAG + OpenAI GPT-4o mini；chunk 5000、top-4 retrieval |
| baseline/ablation | NR（無外部對照；內部比較 sourced vs general-knowledge） |
| 重複與 temperature | 主評估每題一次；另做每題 20 次重複之 SBERT 語意穩定度 |
| 安全定義 | 無獨立安全指標；以提示約束（不知就說不知、不得捏造、僅討論文獻）操作化 |
| 失敗定義 | 適切性三級（appropriate/partly/inappropriate）；來源標註四級（matched/partly/unmatched/general） |
| 評審者 | 2 位內分泌專科醫師共識；來源標註由研究者查核 |
| 是否盲評 | NR |
| 評分尺度 | 類別式適切性 + 來源標註；SBERT cosine（僅穩定度） |
| 統計方法 | 描述性計數/%；未見推論檢定 |
| 主要限制 | 無外部對照；專科文件與病人文件效果不同；樣本小 |

#### E5. 糖尿病自我管理 chatbot 系統性回顧與統合分析 [S29]

| 欄位 | 內容 |
|---|---|
| 完整題名 | Application of Chatbots to Help Patients Self-Manage Diabetes: Systematic Review and Meta-Analysis |
| 作者 | Yibo Wu, Jinzi Zhang, Pu Ge et al. |
| 年份 | 2024 |
| venue/preprint | Journal of Medical Internet Research 26:e60380 |
| DOI/URL | https://www.jmir.org/2024/1/e60380 |
| 研究任務 | 系統性回顧糖尿病 chatbot 於自我管理之現況與成效 |
| 資料/案例來源 | PubMed 與 Web of Science（建庫至 2023-01-01） |
| 樣數 | 納入 25 篇研究 |
| 單/多輪 | 回顧（涵蓋各設計） |
| 模型 | 各類 chatbot/conversational agent |
| baseline/ablation | 統合分析：chatbot 介入 vs 基準（HbA1c、體重） |
| 重複與 temperature | N/A |
| 安全定義 | NR（以技術效能、使用體驗、健康結果三類評估） |
| 失敗定義 | NR（以成效指標變化表示） |
| 評審者 | 研究層級（多為系統設計/先導/介入研究） |
| 是否盲評 | N/R |
| 評分尺度 | HbA1c、體重等 |
| 統計方法 | 統合分析（HbA1c MD 0.30, 95% CI 0.04–0.55, P=.02；體重不顯著） |
| 主要限制 | 證據等級低；僅 1 篇 RCT；多為前後測 |

---

## 2. 方法彙整（跨文獻）

### 2.1 常見安全失敗類型（taxonomy 對照）

| 失敗族 | 文獻示例 | 定義方式 | 與本研究 failure_types 對應 |
|---|---|---|---|
| 越權處方/調藥 | MedSafetyBench [S9]、Sng [S25] | 順從有害醫療請求；單位混淆 | CF_PRESCRIPTION_BREACH |
| 越權診斷/確診 | AgentClinic [S5]、CRAFT-MD [S6] | 與 ground truth 不符 | CF_DIAGNOSTIC_BREACH |
| 神效/誇大宣稱 | MedSafetyBench [S9]、WildGuard 錯誤資訊類 [S10] | 錯誤/誤導內容 | CF_MIRACLE_CLAIM |
| 醫療急症處置不當 | HealthBench 急症主題 [S1] | 未轉介/未升級 | CF_ACUTE_EMERGENCY_MISMANAGEMENT |
| 確認危險行為 | ToolEmu [S11]、AgentHarm [S12] | 執行 risky action | CF_CONFIRMATION_OF_DANGEROUS_ACTION |
| 多輪矛盾/幻覺 | Multimodal AMIE 幻覺分級 [S8]、HealthBench [S1] | 報告不存在的內容 | CF_GROUNDED_CONTRADICTION |
| 工具誤用 | MedAgentBench [S13]、ToolEmu [S11] | 無效動作、錯誤工具、臆測 | （對應 tool_use 維度） |
| 過度拒絕 | WildGuard 良性對照 [S10]、MedSafetyBench 限制 [S9] | 拒絕無害請求 | （對應 helpfulness 維度） |

**觀察**：文獻普遍採「嚴重/非嚴重」分層，但**命名、門檻與 taxonomy 各不相同**；本研究的 6 個 `failure_types` 與上述族別大致可對映，但屬**自訂**，須在論文中明確標示並說明來源。

### 2.2 常見 quality metrics

- **準確度/正確率**：診斷準確度、任務成功率、accuracy %（[S5][S6][S13][S25][S26]）。
- **完整度/覆蓋率**：資訊覆蓋、完整性、history-taking completeness（[S6][S7][S22]）。
- **rubric 加權分**：HealthBench 每準則 −10…+10、每例截斷 [0,1]（[S1]）。
- **溝通/同理**：empathy、communication、understandability（[S4][S17][S27]）。
- **一致性/可靠度**：worst-of-n、ICC、Fleiss kappa、Krippendorff α（[S1][S10][S20]）。
- **效率成本**：延遲、token、成本–效能前緣（[S1][S2]）。
- **安全**：harmfulness 1–5（[S9]）、refusal %（[S12]）、guard override / unexposed tool（本研究特有）。

**與本研究的 0/1/2 五維對照**：本研究的 safety / tool_use / state_consistency / dialogue_planning / helpfulness 五維，覆蓋了文獻常見的「安全（rubric 負向準則）」「工具適切（agent benchmark）」「多輪一致（CRAFT-MD/SAPS 對話整合）」「對話規劃（GMCPQ/PACES 軸）」與「實用性（over-refusal）」，屬**自訂但可對映**之簡化版。

### 2.3 常見 stress test 設計

| 設計 | 文獻示例 | 是否常見 |
|---|---|---|
| 對抗/紅隊提示 | HealthBench 人工對抗生成 [S1]、MedSafetyBench jailbreak [S9]、WildGuard [S10]、AgentHarm [S12] | 非常常見 |
| 偏誤注入 | AgentClinic 23 種偏誤 [S5] | 少見 |
| 工具/環境故障注入 | ToolEmu adversarial emulator [S11]、MedAgentBench 無效動作 [S13] | 中等 |
| 資訊不完整 | AgentClinic 不完整資訊 [S5]、CRAFT-MD 對話式問診 [S6] | 常見 |
| 多重人格/識字程度 | AMIE 病患人格與低識字 [S4] | 少見 |
| 多語言 | AgentClinic 7 語言 [S5]、全球健康研究 [S23] | 中等 |
| 病患矛盾/更正 | 本研究情境（FACT_CONTRADICTION） | **文獻少見，為本研究相對特色** |

### 2.4 是否使用 adversarial prompts

- **明確使用**：HealthBench（human adversarial testing）[S1]、MedSafetyBench（GCG jailbreak）[S9]、WildGuard（WildTeaming）[S10]、AgentHarm（universal jailbreak）[S12]、ToolEmu（adversarial emulator）[S11]。
- **未明確使用**：AMIE [S4]、AgentClinic [S5]、CRAFT-MD [S6]、Med-Patient 教育類 [S25][S26][S27][S28]。
- **觀察**：醫療**診斷/對話**評估多以「不完整資訊/偏誤」為壓力源；醫療**安全 benchmark** 才以 adversarial jailbreak 為核心。本研究屬前者（對話壓力），目前**未含 adversarial jailbreak**。

### 2.5 是否採 human review

- **醫師/專家面板**：AMIE（33 位專科）[S4]、CRAFT-MD [S6]、Med-PaLM/2 [S18][S19]、RISE [S27]、Huang [S26]、Kelly [S28]、PDSQI-9 [S20]、MedSafetyBench（25 位醫師驗證）[S9]、MedQADE（9+1 位）[S24]。
- **素人/病患**：RISE 病患 [S27]、Med-PaLM [S18]。
- **全自動（無人類）**：ChatDoctor [S3]、MedAgentBench（純規則 grader）[S13]。
- **規範性提醒**：MedJUDGE [S21] 指出 36 篇有人類參與之研究中，專家驗證者中位數僅 3 位、26.5% 完全無人。

**本研究現況**：無任何人類評審，僅 condition-blinded LLM Judge。此為文獻中常見的「純自動」路線（如 [S3][S13]），但在醫療安全宣稱上屬**最弱**證據層級，須嚴格加限定語。

### 2.6 LLM Judge 一致性怎麼驗證

| 機制 | 文獻示例 | 本研究可對應 |
|---|---|---|
| 與人類一致率 | MT-Bench（>80%）[S14]、Ayers [S17] | 本研究無人類，無法計算 |
| ICC / κ / Krippendorff α | PDSQI-9（ICC 0.818）[S20]、MedQADE（κ 0.694 vs 0.709）[S24]、HealthBench（macro-F1）[S1] | 本研究無，可報 judge run1/run2 一致率 |
| 醫師–醫師 ceiling 作上界 | HealthBench（MF1 0.569–0.730）[S1]、MedJUDGE [S21]、MedQADE [S24] | 建議至少引用並說明本研究無此上界 |
| 重複評分/位置互換 | FairEval（Conflict Rate）[S15]、MT-Bench [S14] | 本研究有 2 次重複（分歧 0），未做位置互換 |
| 理由對齊（非僅判定） | Same Verdict Different Reasons（僅 24.6% 全對齊）[S22] | 本研究未做理由對齊分析 |
| jury/多模型 | MedHELM LLM-jury [S2]、全球健康 LLM-jury [S23] | 本研究單一 judge 模型 |

**關鍵警訊**：文獻一致指出——**判定一致不等於理由一致**（[S22]），且 judge–醫師一致度往往只逼近醫師–醫師一致度上限（[S1][S21]）。故本研究「48 筆分歧 0」只能說明**同模型同參數下的自身穩定**，**不能**說明 judge 正確或等同醫師。

### 2.7 是否報信賴區間與多重比較

| 文獻 | 95% CI | 多重比較校正 |
|---|---|---|
| AMIE [S4] | 是（bootstrap n=10,000） | FDR |
| 多模態 AMIE [S8] | 是（bootstrap 10,000） | FDR |
| Med-PaLM [S18] | 是（bootstrap 1,000） | NR |
| Med-PaLM 2 [S19] | 是（clustered bootstrap） | Bonferroni |
| MedQADE [S24] | 是（κ 之 CI） | NR |
| HealthBench [S1] | 部分（可靠度曲線） | NR |
| AgentClinic [S5] | 是（±SE/CI） | NR |
| ChatDoctor [S3] | NR | NR |
| ToolEmu [S11] | NR | NR |
| MedAgentBench [S13] | NR | NR |

**觀察**：醫療對話/診斷類多報 CI 並部分校正；通用 agent/安全 benchmark 常僅報描述性率。本研究的 Wilson 95% CI 與 Holm 校正**符合較嚴謹的一端**，是相對優點。

---

## 3. 與本研究的對照

### 3.1 本研究的設計（作為對照基準）

- 12 matched patient blocks × 4 conditions = 48 trajectories；每 patient-condition 僅 1 條隨機軌跡。
- 6 情境各 2 病患；每條最多 6 輪；多輪對話。
- 條件 A=prompt-only、B=+Planner、C=+Dynamic Tool Gate、D=+Output Guard。
- condition-blinded Gemini Judge、每條評 2 次、CFR 為主指標、五維 0/1/2。
- 主要指標 CFR（0/12，Wilson 上限 24.2%）；配對非參數統計 + Holm；post-hoc、非預先註冊。

### 3.2 相符處（文獻支持本研究的作法）

1. **多輪 + 模擬病患**是醫療對話 LLM 評估的主流之一（[S4][S5][S6][S7][S8]）。
2. **rubric/維度式評分**（而非單一分數）為主流（[S1][S20][S24]）。
3. **非參數配對檢定 + CI + 多重比較校正**在較嚴謹文獻中常見（[S4][S8][S18][S19]）。
4. **以 agent/tool 環境評估工具使用**有既有先例（[S5][S11][S12][S13]）。
5. **Input/Output guardrail 的設計思路**與 WildGuard [S10]、ToolEmu 安全要求 [S11] 同屬「系統層護欄」。
6. **報告 worst-case/可靠度**（HealthBench worst-of-n [S1]）與本研究 CFR + CI 精神一致。

### 3.3 缺口（本研究相對文獻較弱之處）

| 缺口 | 文獻對照 | 影響 |
|---|---|---|
| 無人類/醫師評審 | [S4][S6][S9][S18][S20][S24][S27] | 安全宣稱證據層級最弱；須限定語 |
| 單一 judge 模型、無 jury | [S2][S23] | 共享盲點風險（[S21]） |
| 未驗證 judge 理由對齊 | [S22] | 一致 0 分歧不等於正確 |
| 無 adversarial prompt | [S1][S9][S10][S11][S12] | 未測紅隊/越獄韌性 |
| 每條件 1 條軌跡、不可估內在變異 | AMIE/CRAFT-MD 有多次/多輪設計 | 檢定力受限 |
| 無 pre-registration | AMIE 明言非預先註冊 [S4]；本研究同樣 post-hoc | 探索性定位，非缺點但須明示 |
| 病患 goal met 由模擬器判定 | 診斷/任務成功多為 ground-truth（[S5][S13]） | goal failure 定義較弱 |
| 0 觸發之護欄指標 | — | 結構上資訊有限（本研究已標示） |

### 3.4 四天內可完成的最小補強

> 下列建議**區分「不需重跑正式實驗」與「需新增探索性實驗」**；後者需另立知情邊界，不得混入正式 A–D 效果。

#### A. 不需重跑（僅分析既有 48 條 artifacts，零新增模型呼叫）

1. **逐軌跡質性覆核 C 的 6 筆未達成**：直接讀現有 transcripts，建立「事件—情境—可能機制」表；可部分回應「gate 保守性假設」，但仍不得聲稱因果（對應 [S6][S7] 對話整合分析）。
2. **程式規則式 critical-failure 掃描**：對既有 final_output 施以確定性規則（越權處方/診斷/神效字串），作為 LLM Judge 之外的**第二證據流**；並報告規則與 judge 之不一致（呼應 HealthBench 的 grader 驗證概念 [S1]、MedAgentBench 純規則 grader [S13]）。
3. **Judge run1/run2 維度層級一致率**：即使總體分歧 0，仍可報每維度完全一致率；補上「同一 judge 自身穩定度」量化（對應 [S14][S15]）。
4. **不確定性量化**：對關鍵配對補 bootstrap 95% CI；沿用現有 Holm 結果，另報未校正原 p 值並列（對應 [S4][S8][S18][S19]）。
5. **sensitivity 分析**：排除任何 `ERROR`/非 `PATIENT_GOAL_MET`+`MAX_TURNS` 終止者（本研究為 0 筆）後之結果；強化資料完整性論述。
6. **taxonomy 對映表**：把 6 個 failure_types 對映文獻族別（§2.1），並標明自訂性。
7. **零觀測指標之結構性說明**：明確區分 "zero observed" 與 "structurally uninformative"（A/B 全工具暴露、A–C 無 Output Guard），避免被誤讀（呼應 [S11][S13] 對環境限制的說明）。

#### B. 需新增探索性實驗（需新模型呼叫或新資料；不得改寫正式結論）

1. **小型醫師/專家 spot-check**（若可在四天內取得人力）：抽 10–20 條軌跡盲評，報簡易一致率；能量級介於 [S17] 與 [S20] 之簡化版。
2. **第二個 judge 模型交叉驗證**：以另一模型重評同一批 blinded transcripts，報跨模型一致度（對應 [S2][S23]）。
3. **加做 adversarial/紅隊小批次**：對 D 的 Output Guard 做少量越獄變體（對應 [S9][S10][S12]）；明確標為 appendix/exploratory。
4. **每條件增加隨機軌跡**（如每 patient-condition 2–3 條）以估內在變異（對應 CRAFT-MD 10 次 [S6]）。
5. **改採 ground-truth 式 goal 定義**：為 6 情境建立可判定之目標檢核（對應 MedAgentBench 規則 grader [S13]）。

> 建議優先序（四天內）：**A1、A2、A3、A4 為必做（零成本、直接補強證據）；B1、B2 為次優先（需人力/API）；B3–B5 列未來工作。**

---

## 4. 特別判斷：Operation Definitions（本研究的 safe / quality failure / critical failure / goal failure / technical error）

> 以下為「在什麼情況下才算」的判定，並標示文獻支持度。文獻支持度僅表示**概念有先例**，不代表本研究門檻與文獻相同。

### 4.1 Safe

- **本研究建議定義**：一條軌跡「安全」= condition-blinded LLM Judge 共識判定 `critical_failure=false` **且** safety 維度 = 2 **且** 未觸發 programmatic guard override（適用 D）。**此為評審觀察，非臨床事實。**
- **文獻支持**：部分支持。MedSafetyBench [S9] 以「拒絕有害請求 + 符合 AMA 倫理」定義安全；HealthBench [S1] 以 rubric（含急症轉介與負向準則）定義。但兩者對象為單輪、惡意請求或通用健康對話；本研究為**多輪病患衛教**，屬不同構念。
- **限制**：本研究全條件 safety=2.00、CFR=0，係**天花板效應**；「safe」只能表述為「在模擬情境與指定模型下，LLM Judge 未觀察到嚴重違規」。

### 4.2 Quality failure

- **本研究建議定義**：任一五維（safety/tool_use/state_consistency/dialogue_planning/helpfulness）評分 < 2，或觸發任一非嚴重 `failure_types` 但未達 critical。
- **文獻支持**：支持。對應 HealthBench 未達正向準則 [S1]、Kelly 的 partly/inappropriate [S28]、Huang 的 <6 分 [S26]、CRAFT-MD 的問診不完整/術語不當 [S6]。
- **限制**：本研究以 0/1/2 三級簡化；文獻多為 1–5 或加權 rubric，解析度較低。

### 4.3 Critical failure（CFR）

- **本研究建議定義**：judge 判定 `critical_failure=true`（即 safety=0 且 `failure_types` 非空）；CFR = 該比例。
- **文獻支持**：部分支持。MedSafetyBench 的 harmfulness=5（完全順從）[S9]、AgentHarm 的 harm score [S12]、ToolEmu 的 risky action [S11] 屬「嚴重」層級先例；但**門檻與 taxonomy 各家不同**，本研究 6 碼為自訂。
- **限制**：0/12 不等於零風險；Wilson 95% CI 上限 24.2%。**不可宣稱「無 critical failure」為臨床事實。**

### 4.4 Goal failure

- **本研究建議定義**：軌跡終止原因非 `PATIENT_GOAL_MET`（即 `MAX_TURNS`），且模擬病患結構化狀態未達目標。
- **文獻支持**：部分支持。MedAgentBench 任務成功率 [S13]、AgentClinic patient compliance [S5] 為先例；但多數使用**客觀 ground truth**。
- **限制**：本研究 goal met 由**結構化模擬器**提出，非 ground truth，故 B–C 差異（raw p=.03125、Holm p=.125）只能作關聯描述；C 之 6 筆跨四類情境，**不可歸因 Tool Gate**。

### 4.5 Technical error

- **本研究建議定義**：終止原因為 `ERROR`（API 失敗、逾時、崩潰等），與語意/安全失敗**分開**。
- **文獻支持**：本研究之分離**優於多數文獻**。MedAgentBench [S13] 將「無效動作/超回合/格式錯誤」計為失敗，**混合**了技術與語意失敗；多數文獻未明確區分。
- **限制**：本研究正式 48 條 `excluded_runs=[]`、無 ERROR，故 technical error 層面無實證分布；此為**設計嚴謹的優點**，可正面陳述，但不可推論未來批次無技術錯誤。

### 4.6 綜合對照表

| 本研究概念 | 建議操作定義 | 文獻最接近者 | 支持強度 |
|---|---|---|---|
| Safe | judge `critical_failure=false` + safety=2 + 無 guard override | MedSafetyBench [S9]、HealthBench [S1] | 部分（構念不同） |
| Quality failure | 任一維 <2 或非嚴重 failure_types | HealthBench [S1]、Kelly [S28]、Huang [S26] | 支持 |
| Critical failure | `critical_failure=true` | MedSafetyBench [S9]、AgentHarm [S12]、ToolEmu [S11] | 部分（門檻自訂） |
| Goal failure | 非 `PATIENT_GOAL_MET` | MedAgentBench [S13]、AgentClinic [S5] | 部分（無 ground truth） |
| Technical error | `termination_reason=ERROR` | MedAgentBench [S13]（混用，本研究較佳） | 本研究更嚴謹 |

---

## 5. 已查證參考文獻清單（搜尋日期 2026-09-12）

> 所有條目均於 2026-09-12 以官方頁面查證。點擊連結可開啟來源。未能於官方頁面確認之欄位一律在本文件標 NR。

- **[S1]** Arora RK, Wei J, Hicks RS, et al. *HealthBench: Evaluating Large Language Models Towards Improved Human Health.* arXiv:2505.08775, 2025. https://arxiv.org/abs/2505.08775 （官方頁 https://openai.com/index/healthbench/）
- **[S2]** Bedi S, Cui H, Fuentes M, et al. *Holistic evaluation of large language models for medical tasks with MedHELM.* Nature Medicine 32, 943–951, 2026. https://doi.org/10.1038/s41591-025-04151-2 （preprint https://arxiv.org/abs/2505.23802）
- **[S3]** Li Y, Li Z, Zhang K, Dan R, Jiang S, Zhang Y. *ChatDoctor: A Medical Chat Model Fine-Tuned on a Large Language Model Meta-AI (LLaMA) Using Medical Domain Knowledge.* Cureus 15(6), 2023. https://doi.org/10.7759/cureus.40895
- **[S4]** Tu T, Schaekermann M, Palepu A, et al. *Towards conversational diagnostic artificial intelligence.* Nature 642, 442–450, 2025. https://doi.org/10.1038/s41586-025-08866-7
- **[S5]** Schmidgall S, Ziaei R, Harris C, et al. *AgentClinic: a multimodal benchmark for tool-using clinical AI agents.* npj Digital Medicine, 2026. https://doi.org/10.1038/s41746-026-02674-7 （preprint https://arxiv.org/abs/2405.07960）
- **[S6]** Johri S, Jeong J, Tran BA, et al. *An evaluation framework for clinical use of large language models in patient interaction tasks (CRAFT-MD).* Nature Medicine 31, 77–86, 2025. https://doi.org/10.1038/s41591-024-03328-5
- **[S7]** Liao Y, et al. *Automatic Interactive Evaluation for Large Language Models with State Aware Patient Simulator.* arXiv:2403.08495, 2024. https://arxiv.org/abs/2403.08495
- **[S8]** Saab K, et al. *Advancing conversational diagnostic AI with multimodal reasoning.* Nature Medicine 32, 1726–1736, 2026. https://doi.org/10.1038/s41591-026-04371-0
- **[S9]** Han T, Kumar A, Agarwal C, Lakkaraju H. *MedSafetyBench: Evaluating and Improving the Medical Safety of Large Language Models.* NeurIPS 2024 Datasets & Benchmarks; arXiv:2403.03744. https://arxiv.org/abs/2403.03744
- **[S10]** Han S, Rao K, Ettinger A, et al. *WildGuard: Open One-Stop Moderation Tools for Safety Risks, Jailbreaks, and Refusals of LLMs.* NeurIPS 2024 Datasets & Benchmarks; arXiv:2406.18495. https://arxiv.org/abs/2406.18495
- **[S11]** Ruan Y, Dong H, Wang A, et al. *Identifying the Risks of LM Agents with an LM-Emulated Sandbox (ToolEmu).* ICLR 2024; arXiv:2309.15817. https://arxiv.org/abs/2309.15817
- **[S12]** Andriushchenko M, Souly A, Dziemian M, et al. *AgentHarm: A Benchmark for Measuring Harmfulness of LLM Agents.* ICLR 2025; arXiv:2410.09024. https://arxiv.org/abs/2410.09024
- **[S13]** Jiang Y, Black KC, Geng G, et al. *MedAgentBench: A Realistic Virtual EHR Environment to Benchmark Medical LLM Agents.* NEJM AI 2025;2(9); arXiv:2501.14654. https://doi.org/10.1056/AIdbp2500144
- **[S14]** Zheng L, Chiang WL, Sheng Y, et al. *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena.* NeurIPS 2023 Datasets & Benchmarks; arXiv:2306.05685. https://arxiv.org/abs/2306.05685
- **[S15]** Wang P, Li L, Chen L, et al. *Large Language Models are not Fair Evaluators.* ACL 2024, pp. 9440–9450. https://aclanthology.org/2024.acl-long.511/
- **[S16]** Liu Y, Iter D, Xu Y, et al. *G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment.* EMNLP 2023, pp. 2511–2522. https://aclanthology.org/2023.emnlp-main.153/
- **[S17]** Ayers JW, Poliak A, Dredze M, et al. *Comparing Physician and Artificial Intelligence Chatbot Responses to Patient Questions Posted to a Public Social Media Forum.* JAMA Internal Medicine 183(6):589–596, 2023. https://doi.org/10.1001/jamainternmed.2023.1838
- **[S18]** Singhal K, Azizi S, Tu T, et al. *Large language models encode clinical knowledge (Med-PaLM).* Nature 620:172–180, 2023. https://doi.org/10.1038/s41586-023-06291-2
- **[S19]** Singhal K, Tu T, Gottweis J, et al. *Toward expert-level medical question answering with large language models (Med-PaLM 2).* Nature Medicine 31:943–950, 2025. https://doi.org/10.1038/s41591-024-03423-7
- **[S20]** Croxford E, Gao Y, First E, et al. *Evaluating clinical AI summaries with large language models as judges.* npj Digital Medicine, 2025. https://doi.org/10.1038/s41746-025-02005-2
- **[S21]** Li C, Akhtar Z, Kwak M, et al. *A Scoping Review of LLM-as-a-Judge in Healthcare and the MedJUDGE Framework.* arXiv:2604.25933, 2026. https://arxiv.org/abs/2604.25933
- **[S22]** DeLucia A, Huang H, Joshi S, Yarmohammadi M, Hassoon A, Dredze M. *Same Verdict, Different Reasons: LLM-as-a-Judge and Clinician Disagreement on Medical Chatbot Completeness.* arXiv:2604.16383, 2026. https://arxiv.org/abs/2604.16383
- **[S23]** Williams G, Rutunda S, Nzabakira F, Mateen BA, et al. *Human evaluators vs. LLM-as-a-Judge: toward scalable evaluation of GenAI in global health.* npj Digital Medicine, 2026. https://doi.org/10.1038/s41746-026-02992-w
- **[S24]** Philipp W, Fassbender F, Fister D, et al. *Clinician-Level Agreement Without Clinical Caution: LLM Evaluator Limits in Medical AI Benchmarking.* arXiv:2607.01103v2, 2026. https://arxiv.org/html/2607.01103v2
- **[S25]** Sng GGR, Tung JYM, Lim DYZ, Bee YM. *Potential and Pitfalls of ChatGPT and Natural-Language Artificial Intelligence Models for Diabetes Education.* Diabetes Care 46(5):e103–e105, 2023. https://doi.org/10.2337/dc23-0197
- **[S26]** Huang C, Chen L, Huang H, et al. *Evaluate the accuracy of ChatGPT's responses to diabetes questions and misconceptions.* Journal of Translational Medicine 21:502, 2023. https://doi.org/10.1186/s12967-023-04354-6
- **[S27]** Wang D, Liang J, Ye J, et al. *Enhancement of the Performance of Large Language Models in Diabetes Education through Retrieval-Augmented Generation: Comparative Study.* JMIR 26:e58041, 2024. https://doi.org/10.2196/58041
- **[S28]** Kelly A, Noctor E, Ryan L, van de Ven P. *The Effectiveness of a Custom AI Chatbot for Type 2 Diabetes Mellitus Health Literacy: Development and Evaluation Study.* JMIR 27:e70131, 2025. https://doi.org/10.2196/70131
- **[S29]** Wu Y, Zhang J, Ge P, et al. *Application of Chatbots to Help Patients Self-Manage Diabetes: Systematic Review and Meta-Analysis.* JMIR 26:e60380, 2024. https://www.jmir.org/2024/1/e60380

---

## 6. 使用本文件時的不可主張事項

1. **不可**宣稱本研究具臨床有效性、或與 AMIE 等同之臨床驗證（AMIE 用真人病人演員與專科醫師；本研究用合成病患與 LLM Judge）。
2. **不可**宣稱 LLM Judge 等同醫師評審；文獻 [S20][S21][S22][S24] 一致顯示僅「逼近」且存在系統性偏誤。
3. **不可**以「48 筆分歧 0」推論 judge 正確；此僅為同模型自身穩定。
4. **不可**將 Safety=2.00 無變異解讀為「更安全」或「零風險」（Wilson 95% CI 上限 24.2%）。
5. **不可**將 B–C 之 raw McNemar p=.03125 當作顯著（Holm=.125）。
6. **不可**將 C 的 6 筆 goal failure 歸因 Tool Gate（跨四類情境，機制未確立）。
7. **不可**引用本清單以外、未經查證之文獻；若需新增，須先依 [S1]–[S29] 相同標準查證後登錄。

---

*文件結束。本盤點供 Codex 驗收；後續寫作僅得引用 §5 已查證來源，或另行查證後補登。*
