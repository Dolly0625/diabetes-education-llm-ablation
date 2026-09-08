# 可攜式任務包清單

## 放置位置

解壓或下載後，專案應維持以下相對結構：

```text
diabetes-chatbot/
├── diabetes_chatbot/
├── diabetes-rag/
├── scripts/
└── llm_ablation_paper/
```

任務包不包含 `.env`、API key、真實病患資料、正式實驗輸出、`.git`、本機模型、cache 或其他敏感檔案。包內的 `patient_profiles.jsonl` 為合成 profiles。

## 2026-09-08 最低必要內容

- 完整 `diabetes_chatbot/`，包含 WS1 向後相容注入點與 `ablation_core.py`。
- 完整 `llm_ablation_paper/`，保留 WS1 Harness/tests 與 WS4-A profiles/tests。
- `scripts/`、`requirements.txt`、`.env.example` 與必要的專案說明。
- `diabetes-rag/` 保留供程式依賴與專案結構參照，但本論文不評估其 RAG 效果。

## 共同文件

- `README.md`：五份工作的入口與啟動方式。
- `GROUP_HANDOFF_GUIDE.md`：可直接傳到大群的完整實驗、資料集、分工、操作與回傳說明。
- `TEAM_START_HERE.md`：給全體成員的白話研究說明、交付方式與共同執行流程。
- `AGENTS.md`：所有 AI 共同遵守的上層規則。
- `STATUS.md`：負責人、狀態、里程碑與決策紀錄。
- `shared/RESEARCH_PROTOCOL.md`：A–D、控制變項、指標與停止規則。
- `shared/SYSTEM_OVERVIEW.md`：一頁式架構與重要程式位置。
- `shared/EXPERIMENT_CONTRACT.md`：profiles、transcripts 與 Judge 的資料格式。
- `shared/CLAIM_BOUNDARIES.md`：可用主張、禁用主張及 RAG 邊界。
- `shared/FEASIBILITY_AUDIT.md`：以現有程式碼驗證的工程缺漏、修正決策與 Day 1 阻塞條件。

## 五份工作單

- `workstream_1_technical_lead/AGENTS.md`
- `workstream_2_ablation_ab/AGENTS.md`
- `workstream_3_ablation_cd/AGENTS.md`
- `workstream_4_patient_simulation/AGENTS.md`
- `workstream_5_judge_analysis/AGENTS.md`

## 五份 AI 啟動指令

- `member_prompts/member_1_technical_lead.md`
- `member_prompts/member_2_ablation_ab.md`
- `member_prompts/member_3_ablation_cd.md`
- `member_prompts/member_4_patient_simulation.md`
- `member_prompts/member_5_judge_analysis.md`

## 可攜性規則

- 文件內不得出現任何個人家目錄或作業系統專屬的絕對路徑。
- 跨目錄引用須使用相對路徑。
- 各工作流的 `../../` 會回到專案根目錄。
- 移動單一工作流而不攜帶完整專案，會使程式參考路徑失效；應下載完整 repository。
