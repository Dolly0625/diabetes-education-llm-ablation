# Writer 1 文獻引用第一手查核報告（複審與修正版）

**查核日期：** 2026-09-18（第 2 輪嚴格複審與元數據對齊）  
**查核標準：** 嚴格以官方出版社（Nature Portfolio, ADA Diabetes Care, Springer/BMC, JMIR, NEJM AI）、學會 Anthology（ACL Anthology, NeurIPS, ICLR via OpenReview）及官方 arXiv 第一手 metadata 為準。禁止使用「and others」隱匿作者名單，逐項核驗作者全名、標題、年份、卷期、頁碼、DOI/arXiv 及官方網址。

---

## 總結摘要表

| # | BibTeX Key | 第一作者與年份 | 出版類型 | 狀態 | 官方連結 | 備註說明 |
|---|---|---|---|---|---|---|
| 1 | `Sng2023-diabetes-pitfalls` | Sng et al. (2023) | 期刊通信 (Diabetes Care) | **CORRECTED** | [DOI: 10.2337/dc23-0197](https://doi.org/10.2337/dc23-0197) | 依刊物補齊 4 位作者全名與正式大小寫 |
| 2 | `Huang2023-diabetes-accuracy` | Huang et al. (2023) | 期刊論文 (J Transl Med) | **CORRECTED** | [DOI: 10.1186/s12967-023-04354-6](https://doi.org/10.1186/s12967-023-04354-6) | 展開全部 8 位作者，移除 and others |
| 3 | `MedSafetyBench2024` | Han et al. (2024) | 會議論文 (NeurIPS 2024) | **CORRECTED** | [OpenReview](https://openreview.net/forum?id=7P0eFmS3dZ) | **重大修正**：首位作者為 Tessa Han，第二作者為 Aounon Kumar |
| 4 | `WildGuard2024` | Han et al. (2024) | 會議論文 (NeurIPS 2024) | **CORRECTED** | [OpenReview](https://openreview.net/forum?id=6aQ62Yl9a6) | 展開全部 8 位作者，移除 and others |
| 5 | `HealthBench2025` | Arora et al. (2025) | 預印本 (arXiv) | **CORRECTED** | [arXiv:2505.08775](https://arxiv.org/abs/2505.08775) | 展開全部 12 位作者，移除 and others |
| 6 | `AgentClinic2026` | Schmidgall et al. (2026) | 期刊論文 (npj Digital Med) | **CORRECTED** | [DOI: 10.1038/s41746-026-02674-7](https://doi.org/10.1038/s41746-026-02674-7) | 展開全部 7 位作者，移除 and others |
| 7 | `AMIE2025` | Tu et al. (2025) | 期刊論文 (Nature) | **CORRECTED** | [DOI: 10.1038/s41586-025-08866-7](https://doi.org/10.1038/s41586-025-08866-7) | 展開全部 26 位作者，移除 and others |
| 8 | `MultimodalAMIE2026` | Saab et al. (2026) | 期刊論文 (Nature Med) | **CORRECTED** | [DOI: 10.1038/s41591-026-04371-0](https://doi.org/10.1038/s41591-026-04371-0) | 展開全部 13 位作者，移除 and others |
| 9 | `CRAFT-MD2025` | Johri et al. (2025) | 期刊論文 (Nature Med) | **CORRECTED** | [DOI: 10.1038/s41591-024-03328-5](https://doi.org/10.1038/s41591-024-03328-5) | 展開全部 12 位作者，移除 and others |
| 10 | `AgentHarm2025` | Andriushchenko et al. (2025) | 會議論文 (ICLR 2025) | **CORRECTED** | [OpenReview](https://openreview.net/forum?id=eI0zI3gX2Y) | 展開全部 14 位作者，移除 and others |
| 11 | `ToolEmu2024` | Ruan et al. (2024) | 會議論文 (ICLR 2024) | **CORRECTED** | [OpenReview](https://openreview.net/forum?id=HO3-sHi7So) | **重大修正**：補齊 Chris J. Maddison 與 Tatsunori Hashimoto，共 9 位 |
| 12 | `MedAgentBench2025` | Jiang et al. (2025) | 期刊論文 (NEJM AI) | **CORRECTED** | [DOI: 10.1056/AIdbp2500144](https://doi.org/10.1056/AIdbp2500144) | 展開全部 7 位作者，移除 and others |
| 13 | `RISE2024` | Wang et al. (2024) | 期刊論文 (JMIR) | **CORRECTED** | [DOI: 10.2196/58041](https://doi.org/10.2196/58041) | 展開全部 15 位作者，移除 and others |
| 14 | `MTBench2023` | Zheng et al. (2023) | 會議論文 (NeurIPS 2023) | **CORRECTED** | [OpenReview](https://openreview.net/forum?id=9H1AgcSnZ7) | 展開全部 13 位作者，移除 and others |
| 15 | `FairEval2024` | Wang et al. (2024) | 會議論文 (ACL 2024) | **CORRECTED** | [ACL Anthology](https://aclanthology.org/2024.acl-long.511/) | **重大修正**：補齊 Zefan Cai 與 Lingpeng Kong，依官方調整順序與 DOI |
| 16 | `PDSQI2025` | Croxford et al. (2025) | 期刊論文 (npj Digital Med) | **CORRECTED** | [DOI: 10.1038/s41746-025-02005-2](https://doi.org/10.1038/s41746-025-02005-2) | 展開全部 17 位作者，移除 and others |
| 17 | `MedJUDGE2026` | Li et al. (2026) | 預印本 (arXiv) | **CORRECTED** | [arXiv:2604.25933](https://arxiv.org/abs/2604.25933) | **重大修正**：首位作者為 Chenyu Li，第二為 Zohaib Akhtar，第三為 Mingu Kwak，展開全體 16 位作者 |
| 18 | `SameVerdict2026` | DeLucia et al. (2026) | 預印本 (arXiv) | **VERIFIED** | [arXiv:2604.16383](https://arxiv.org/abs/2604.16383) | 6 位作者名單與 metadata 完全吻合 |
| 19 | `Wilson1927` | Wilson (1927) | 期刊論文 (JASA) | **VERIFIED** | [DOI: 10.1080/01621459.1927.10502953](https://doi.org/10.1080/01621459.1927.10502953) | 古典統計方法文獻，metadata 完全吻合 |

---

## 逐筆詳細核驗與修訂對照

### 1. `Sng2023-diabetes-pitfalls`
- **官方 URL：** [https://doi.org/10.2337/dc23-0197](https://doi.org/10.2337/dc23-0197)
- **修正前：** 僅簡寫 `Sng GGR, Tung JYM, Lim DYZ, Bee YM`
- **修正後（完整作者）：** `Gerald Gui Ren Sng and Joshua Yi Min Tung and Daniel Yan Zheng Lim and Yong Mong Bee`
- **題名：** Potential and Pitfalls of ChatGPT and Natural-Language Artificial Intelligence Models for Diabetes Education
- **期刊卷期：** *Diabetes Care*, 46(5): e103–e105 (2023)
- **判定：** `CORRECTED`（展開完整作者姓名與補足大小寫保護）

### 2. `Huang2023-diabetes-accuracy`
- **官方 URL：** [https://doi.org/10.1186/s12967-023-04354-6](https://doi.org/10.1186/s12967-023-04354-6)
- **修正前：** 使用 `et al.` / `and others` 簡略
- **修正後（完整作者）：** `Chunling Huang and Lijun Chen and Huibin Huang and Qingyan Cai and Ruhai Lin and Xiaohong Wu and Yong Zhuang and Zhengrong Jiang`
- **題名：** Evaluate the accuracy of ChatGPT's responses to diabetes questions and misconceptions
- **期刊卷期：** *Journal of Translational Medicine*, 21(1): 502 (2023)
- **判定：** `CORRECTED`（補全全部 8 位作者名單）

### 3. `MedSafetyBench2024`
- **官方 URL：** [https://openreview.net/forum?id=7P0eFmS3dZ](https://openreview.net/forum?id=7P0eFmS3dZ) / [https://arxiv.org/abs/2403.03744](https://arxiv.org/abs/2403.03744)
- **修正前：** `Tianyue Han and Anand Kumar and Chirag Agarwal and Himabindu Lakkaraju`（作者名字拼寫錯誤）
- **修正後（官方作者）：** `Tessa Han and Aounon Kumar and Chirag Agarwal and Himabindu Lakkaraju`
- **題名：** MedSafetyBench: Evaluating and Improving the Medical Safety of Large Language Models
- **會議：** Advances in Neural Information Processing Systems (NeurIPS 2024) Datasets and Benchmarks Track
- **判定：** `CORRECTED`（重大修正：更正第一作者與第二作者英文原名）

### 4. `WildGuard2024`
- **官方 URL：** [https://openreview.net/forum?id=6aQ62Yl9a6](https://openreview.net/forum?id=6aQ62Yl9a6) / [https://arxiv.org/abs/2406.18495](https://arxiv.org/abs/2406.18495)
- **修正前：** 使用 `and others` 遮蓋
- **修正後（完整作者）：** `Seungju Han and Kavel Rao and Allyson Ettinger and Liwei Jiang and Bill Yuchen Lin and Nathan Lambert and Yejin Choi and Nouha Dziri`
- **題名：** WildGuard: Open One-Stop Moderation Tools for Safety Risks, Jailbreaks, and Refusals of LLMs
- **會議：** Advances in Neural Information Processing Systems (NeurIPS 2024) Datasets and Benchmarks Track
- **判定：** `CORRECTED`（展開全體 8 位作者名單）

### 5. `HealthBench2025`
- **官方 URL：** [https://arxiv.org/abs/2505.08775](https://arxiv.org/abs/2505.08775)
- **修正前：** 使用 `and others` 遮蓋
- **修正後（完整作者）：** `Rahul K. Arora and Jason Wei and Rebecca Soskin Hicks and Preston Bowman and Joaquin Qui{\~n}onero-Candela and Foivos Tsimpourlas and Michael Sharman and Meghan Shah and Andrea Vallone and Alex Beutel and Johannes Heidecke and Karan Singhal`
- **題名：** HealthBench: Evaluating Large Language Models Towards Improved Human Health
- **發表平台：** arXiv:2505.08775 (2025)
- **判定：** `CORRECTED`（展開全體 12 位作者名單）

### 6. `AgentClinic2026`
- **官方 URL：** [https://doi.org/10.1038/s41746-026-02674-7](https://doi.org/10.1038/s41746-026-02674-7)
- **修正前：** 使用 `and others` 遮蓋
- **修正後（完整作者）：** `Samuel Schmidgall and Rojin Ziaei and Carl Harris and Ji Woong Kim and Eduardo Pontes Reis and Jeffrey Jopling and Michael Moor`
- **題名：** AgentClinic: a multimodal benchmark for tool-using clinical AI agents
- **期刊：** *npj Digital Medicine* (2026)
- **判定：** `CORRECTED`（展開全體 7 位作者名單）

### 7. `AMIE2025`
- **官方 URL：** [https://doi.org/10.1038/s41586-025-08866-7](https://doi.org/10.1038/s41586-025-08866-7)
- **修正前：** 使用 `and others` 遮蓋
- **修正後（完整作者）：** `Tao Tu and Mike Schaekermann and Anil Palepu and Khaled Saab and Jan Freyberg and Ryutaro Tanno and Amy Wang and Brenna Li and Mohamed Amin and Yong Cheng and Elahe Vedadi and Nenad Tomasev and Shekoofeh Azizi and Karan Singhal and Le Hou and Albert Webson and Kavita Kulkarni and S. Sara Mahdavi and Christopher Semturs and Juraj Gottweis and Joelle Barral and Katherine Chou and Greg S. Corrado and Yossi Matias and Alan Karthikesalingam and Vivek Natarajan`
- **題名：** Towards conversational diagnostic artificial intelligence
- **期刊卷期：** *Nature*, 642: 442–450 (2025)
- **判定：** `CORRECTED`（展開全體 26 位作者名單）

### 8. `MultimodalAMIE2026`
- **官方 URL：** [https://doi.org/10.1038/s41591-026-04371-0](https://doi.org/10.1038/s41591-026-04371-0)
- **修正前：** 使用 `and others` 遮蓋
- **修正後（完整作者）：** `Khaled Saab and Chunjong Park and Tim Strother and Jan Freyberg and David G. T. Barrett and Yong Cheng and Wei-Hung Weng and David Stutz and Nenad Tomasev and Anil Palepu and Tao Tu and Vivek Natarajan and Alan Karthikesalingam`
- **題名：** Advancing conversational diagnostic AI with multimodal reasoning
- **期刊卷期：** *Nature Medicine*, 32: 1726–1736 (2026)
- **判定：** `CORRECTED`（展開全體 13 位作者名單）

### 9. `CRAFT-MD2025`
- **官方 URL：** [https://doi.org/10.1038/s41591-024-03328-5](https://doi.org/10.1038/s41591-024-03328-5)
- **修正前：** 使用 `and others` 遮蓋
- **修正後（完整作者）：** `Shreya Johri and Jaehwan Jeong and Benjamin A. Tran and Daniel I. Schlessinger and Shannon Wongvibulsin and Leandra A. Barnes and Hong-Yu Zhou and Zhuo Ran Cai and David Kim and Roxana Daneshjou and Eliezer M. Van Allen and Pranav Rajpurkar`
- **題名：** An evaluation framework for clinical use of large language models in patient interaction tasks
- **期刊卷期：** *Nature Medicine*, 31: 77–86 (2025)
- **判定：** `CORRECTED`（展開全體 12 位作者名單）

### 10. `AgentHarm2025`
- **官方 URL：** [https://openreview.net/forum?id=eI0zI3gX2Y](https://openreview.net/forum?id=eI0zI3gX2Y) / [https://arxiv.org/abs/2410.09024](https://arxiv.org/abs/2410.09024)
- **修正前：** 使用 `and others` 遮蓋
- **修正後（完整作者）：** `Maksym Andriushchenko and Alexandra Souly and Mateusz Dziemian and Derek Duenas and Maxwell Lin and Justin Wang and Dan Hendrycks and Andy Zou and Zico Kolter and Matt Fredrikson and Eric Winsor and Jerome Wynne and Yarin Gal and Xander Davies`
- **題名：** AgentHarm: A Benchmark for Measuring Harmfulness of LLM Agents
- **會議：** The Thirteenth International Conference on Learning Representations (ICLR 2025)
- **判定：** `CORRECTED`（展開全體 14 位作者名單）

### 11. `ToolEmu2024`
- **官方 URL：** [https://openreview.net/forum?id=HO3-sHi7So](https://openreview.net/forum?id=HO3-sHi7So) / [https://arxiv.org/abs/2309.15817](https://arxiv.org/abs/2309.15817)
- **修正前：** 遺漏最後兩位作者 Chris J. Maddison 與 Tatsunori Hashimoto
- **修正後（完整作者）：** `Yangjun Ruan and Honghua Dong and Andrew Wang and Silviu Pitis and Yongchao Zhou and Jimmy Ba and Yann Dubois and Chris J. Maddison and Tatsunori Hashimoto`
- **題名：** Identifying the Risks of LM Agents with an LM-Emulated Sandbox
- **會議：** The Twelfth International Conference on Learning Representations (ICLR 2024)
- **判定：** `CORRECTED`（重大修正：依 OpenReview 官方 BibTeX 補齊全體 9 位作者）

### 12. `MedAgentBench2025`
- **官方 URL：** [https://doi.org/10.1056/AIdbp2500144](https://doi.org/10.1056/AIdbp2500144)
- **修正前：** 使用 `and others` 遮蓋
- **修正後（完整作者）：** `Yixing Jiang and Kameron C. Black and Gloria Geng and Danny Park and James Zou and Andrew Y. Ng and Jonathan H. Chen`
- **題名：** MedAgentBench: A Realistic Virtual EHR Environment to Benchmark Medical LLM Agents
- **期刊卷期：** *NEJM AI*, 2(9) (2025)
- **判定：** `CORRECTED`（展開全體 7 位作者名單）

### 13. `RISE2024`
- **官方 URL：** [https://doi.org/10.2196/58041](https://doi.org/10.2196/58041)
- **修正前：** 使用 `and others` 遮蓋
- **修正後（完整作者）：** `Dingqiao Wang and Jiangbo Liang and Jinguo Ye and Jingni Li and Jingpeng Li and Qikai Zhang and Qiuling Hu and Caineng Pan and Dongliang Wang and Zhong Liu and Wen Shi and Danli Shi and Fei Li and Bo Qu and Yingfeng Zheng`
- **題名：** Enhancement of the Performance of Large Language Models in Diabetes Education Through Retrieval-Augmented Generation: Comparative Study
- **期刊卷期：** *Journal of Medical Internet Research*, 26: e58041 (2024)
- **判定：** `CORRECTED`（展開全體 15 位作者名單）

### 14. `MTBench2023`
- **官方 URL：** [https://openreview.net/forum?id=9H1AgcSnZ7](https://openreview.net/forum?id=9H1AgcSnZ7) / [https://arxiv.org/abs/2306.05685](https://arxiv.org/abs/2306.05685)
- **修正前：** 使用 `and others` 遮蓋
- **修正後（完整作者）：** `Lianmin Zheng and Wei-Lin Chiang and Ying Sheng and Siyuan Zhuang and Zhanghao Wu and Yonghao Zhuang and Zi Lin and Zhuohan Li and Dacheng Li and Eric P. Xing and Hao Zhang and Joseph E. Gonzalez and Ion Stoica`
- **題名：** Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena
- **會議：** Advances in Neural Information Processing Systems (NeurIPS 2023) Datasets and Benchmarks Track
- **判定：** `CORRECTED`（展開全體 13 位作者名單）

### 15. `FairEval2024`
- **官方 URL：** [https://aclanthology.org/2024.acl-long.511/](https://aclanthology.org/2024.acl-long.511/)
- **修正前：** 遺漏 Zefan Cai 與 Lingpeng Kong，且作者排序不合官方出版
- **修正後（官方 ACL Anthology）：** `Peiyi Wang and Lei Li and Liang Chen and Zefan Cai and Dawei Zhu and Binghuai Lin and Yunbo Cao and Lingpeng Kong and Qi Liu and Tianyu Liu and Zhifang Sui`
- **題名：** Large Language Models are not Fair Evaluators
- **會議：** Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (ACL 2024), pp. 9440–9450
- **DOI：** `10.18653/v1/2024.acl-long.511`
- **判定：** `CORRECTED`（重大修正：依 ACL Anthology 官方 BibTeX 補齊全部 11 位作者及正式 DOI）

### 16. `PDSQI2025`
- **官方 URL：** [https://doi.org/10.1038/s41746-025-02005-2](https://doi.org/10.1038/s41746-025-02005-2)
- **修正前：** 使用 `and others` 遮蓋
- **修正後（完整作者）：** `Emma Croxford and Yanjun Gao and Elliot First and Nicholas Pellegrino and Miranda Schnier and John R. Caskey and Madeline K. Oguss and Graham Wills and Guanhua Chen and Dmitriy Dligach and Matthew M. Churpek and Anoop M. Mayampurath and Frank J. Liao and Cherodeep Goswami and Karen K. Wong and Brian W. Patterson and Majid Afshar`
- **題名：** Evaluating clinical AI summaries with large language models as judges
- **期刊卷期：** *npj Digital Medicine*, 8: 65 (2025)
- **判定：** `CORRECTED`（展開全體 17 位作者名單）

### 17. `MedJUDGE2026`
- **官方 URL：** [https://arxiv.org/abs/2604.25933](https://arxiv.org/abs/2604.25933)
- **修正前：** `Chaoyi Li and Zeeshan Akhtar and Minjeong Kwak and others`（前三作者姓名拼寫錯誤，其餘遮蔽）
- **修正後（官方 arXiv 完整名單）：** `Chenyu Li and Zohaib Akhtar and Mingu Kwak and Yuelyu Ji and Hang Zhang and Tracey Obi and Yufan Ren and Xizhi Wu and Sonish Sivarajkumar and Harold P. Lehmann and Shyam Visweswaran and Michael J. Becich and Danielle L. Mowery and Renxuan Liu and Haoyang Sun and Yanshan Wang`
- **題名：** A Scoping Review of LLM-as-a-Judge in Healthcare and the MedJUDGE Framework
- **發表平台：** arXiv:2604.25933 (2026)
- **判定：** `CORRECTED`（重大修正：更正前三作者姓名，並補齊全體 16 位作者名單）

### 18. `SameVerdict2026`
- **官方 URL：** [https://arxiv.org/abs/2604.16383](https://arxiv.org/abs/2604.16383)
- **官方作者：** `Alexandra DeLucia and Heyuan Huang and Sonal Joshi and Mahsa Yarmohammadi and Ahmed Hassoon and Mark Dredze`
- **題名：** Same Verdict, Different Reasons: LLM-as-a-Judge and Clinician Disagreement on Medical Chatbot Completeness
- **發表平台：** arXiv:2604.16383 (2026)
- **判定：** `VERIFIED`（作者名單與 metadata 100% 精確吻合）

### 19. `Wilson1927`
- **官方 URL：** [https://doi.org/10.1080/01621459.1927.10502953](https://doi.org/10.1080/01621459.1927.10502953)
- **官方作者：** `Edwin B. Wilson`
- **題名：** Probable Inference, the Law of Succession, and Statistical Inference
- **期刊卷期：** *Journal of the American Statistical Association*, 22(158): 209–212 (1927)
- **判定：** `VERIFIED`（古典統計學歷史文獻，metadata 100% 精確吻合）
