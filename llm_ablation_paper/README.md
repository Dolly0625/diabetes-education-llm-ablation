# LLM 分層安全消融論文：五人協作入口

本目錄是四天版研討會論文的唯一協作入口。研究題目暫定為：

> 從提示詞到程式防線：糖尿病衛教 LLM 助理之分層安全控制消融研究

英文暫定題目：

> From Prompts to Programmatic Safeguards: An Ablation Study of Layered Safety Controls for a Diabetes Education LLM Assistant

整個目錄採用相對路徑，可以跟著 repository 一起 clone、下載或解壓到任何位置，不依賴原作者電腦的使用者名稱或絕對路徑。

第一次加入專案的成員，請先閱讀 `GROUP_HANDOFF_GUIDE.md`。這是群組共用的單一交接文件，包含實驗、資料集、進度、分工、AI 操作與回傳方式。`TEAM_START_HERE.md` 保留為簡版開始指南。

## 使用方式

每位成員只進入自己的工作目錄，先要求 AI 閱讀該目錄與上層的 `AGENTS.md`，再開始工作。

| 工作 | 目錄 | 主要責任 |
|---|---|---|
| 1 | `workstream_1_technical_lead/` | 技術主持、A–D 定義、正式實驗、整合與技術審核 |
| 2 | `workstream_2_ablation_ab/` | A／B 實驗設計與方法章素材 |
| 3 | `workstream_3_ablation_cd/` | C／D、安全事件紀錄與故障注入 |
| 4 | `workstream_4_patient_simulation/` | 模擬病患角色、病患設定與多輪角色扮演 |
| 5 | `workstream_5_judge_analysis/` | 盲測 LLM Judge、統計、結果圖表與結果章 |

所有人共同遵守：

- `shared/RESEARCH_PROTOCOL.md`
- `shared/SYSTEM_OVERVIEW.md`
- `shared/EXPERIMENT_CONTRACT.md`
- `shared/CLAIM_BOUNDARIES.md`
- `shared/FEASIBILITY_AUDIT.md`
- `STATUS.md`

完整套件內容列於 `PACKAGE_MANIFEST.md`。若取得的是壓縮包，請保留目錄結構並放在專案根目錄，使 `llm_ablation_paper/` 與 `diabetes_chatbot/`、`diabetes-rag/`、`scripts/` 位於同一層。

2026-09-08 狀態：WS1 已驗收；WS4-A profiles 與 schema 已完成；WS2、WS3、WS4-B、WS5 待執行。每位成員必須被指定一個成員編號，並將對應的 `member_prompts/` 檔案完整交給 AI；單純上傳整包不能取代成員指派。

## 四天節奏

| 時間 | 必須完成 |
|---|---|
| Day 1 | A–D 與評估規格凍結；一個病患完成全流程 dry run |
| Day 2 | 正式角色扮演完成；raw transcripts 凍結 |
| Day 3 | Judge、統計、圖表與各節初稿完成 |
| Day 4 | 全文整合、數字稽核、限制聲明與投稿格式 QA |

## 給組員的啟動指令

不要自行重寫指令。請依成員編號，直接使用 `member_prompts/` 中對應的啟動指令。
