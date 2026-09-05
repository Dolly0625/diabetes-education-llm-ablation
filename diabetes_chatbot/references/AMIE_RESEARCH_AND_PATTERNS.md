# Google AMIE 核心架構與技術控制模式 (2024–2026)

本文件整理 Google Research 與 Google DeepMind 針對臨床對話 AI 系統 **AMIE (Articulate Medical Intelligence Explorer)** 的系列核心論文、工程架構、RAG 與回覆控制機制，作為 TFDA 糖尿病衛教 Agent（v2）系統架構演進之長期技術參考。

---

## 一、文獻索引與發展里程碑

1. **基礎奠基（2024 年 1 月）**
   - **論文名稱**：*Towards Conversational Diagnostic AI*
   - **出處**：arXiv:2401.05654 (Google Research & Google DeepMind, Tu et al.)
   - **核心成果**：提出 AMIE 初版文字對話系統，透過自博弈（Self-play）模擬環境訓練，在模擬客觀結構化臨床考試（OSCE）中，於病史採集（History-taking）、診斷準確度、共情溝通與清晰度上首次達到或超越基層主治醫師水準。

2. **臨床專科深化（2025 年）**
   - **出處**：*Nature Medicine*
   - **核心成果**：評估跨專科（內科、心臟科、皮膚科）複雜臨床諮詢，確立了「三階段推理鏈（Chain-of-Reasoning）」在消除幻覺與維護醫學嚴謹度上的有效性。

3. **長期慢性病管理突破（2026 年 6 月）**
   - **論文名稱**：*AI for Longitudinal Disease Management across Multiple Clinical Consultations*
   - **出處**：*Nature* (2026)
   - **核心成果**：跨越「單次就醫診斷」限制，進入「跨診次長期疾病管理（Longitudinal Management）」。利用 Gemini 長上下文處理數月累積的病歷、飲食、血糖數值，動態調整個人化衛教與處置計畫。

4. **多模態視訊即時問診（2026 年 8 月）**
   - **核心技術**：結合 Project Astra 與 Gemini 多模態能力，發表非同步多代理人架構（Asynchronous Multi-Agent），即時分析病患呼吸、步態、皮膚狀況與面部表情。

5. **真實世界臨床試驗（Beth Israel Deaconess Medical Center / Included Health）**
   - **落地核心**：看診前病史採集（Pre-visit History Taking），證實 AI 預問診摘要可大幅提升醫師看診效率且無安全事故。

---

## 二、AMIE 核心系統架構

```
                                [ 病患輸入 / 生活對話 ]
                                          │
                                          ▼
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                        Talker Agent (發言代理人)                             │
   │  - 毫秒級低延遲、自然口語溝通                                                │
   │  - 維持溫暖共情 (Empathy)、控制對話節奏                                      │
   │  - 避免長篇大論教科書式說教 (Anti-Info Dumping)                              │
   └──────────────────────────────────────┬──────────────────────────────────────┘
                                          │ 非同步事件流 (Asynchronous Event)
                                          ▼
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                        Planner Agent (臨床規劃大腦)                          │
   │  - 背景非同步運轉，維持「動態臨床狀態清單」                                   │
   │  - 辨識資訊缺口 (Information Gaps)，避免過早閉合 (Premature Closure)         │
   │  - 指示 Talker 下一步行動：【同理】/【追問缺口】/【精準衛教】                │
   └───────────────────┬─────────────────────────────────────┬───────────────────┘
                       │                                     │
                       ▼                                     ▼
        ┌─────────────────────────────┐       ┌─────────────────────────────┐
        │  Perception Agent (多模態)   │       │ Management Reasoning Agent  │
        │  - 呼吸、步態、皮膚、影像分析 │       │ (RAG 臨床指引檢索管理)       │
        └─────────────────────────────┘       └──────────────┬──────────────┘
                                                             │
                                                             ▼
                                              ┌─────────────────────────────┐
                                              │  權威指引庫 / 藥物仿單手冊  │
                                              └─────────────────────────────┘
```

---

## 三、AMIE 的 RAG 檢索控制機制

在醫療領域，隨意檢索容易造成嚴重假陽性（如用「澱粉」命中「類澱粉病理沉積」）。AMIE 採取以下嚴格控制：

### 1. 檢索發起權限隔離（Management Reasoning Agent）
- **前端對話模型無權直接發起全文檢索**。
- 檢索統一由後台的 Management Reasoning Agent 決定，僅在確認臨床有具體知識依據需求時才觸發。

### 2. 本體範圍定界（Scope-Constrained Query Formulation）
- AMIE 嚴禁直接將病患的自然語言切詞拿去 RAG 資料庫做子字串比對。
- 檢索查詢必須被形式化為帶有**領域邊界標籤**的結構體：
  ```json
  {
    "clinical_intent": "DIET_CARB_CONTROL",
    "target_domain": "LIFESTYLE_NUTRITION_GUIDELINE",
    "forbidden_domains": ["ADR_BLACK_BOX_WARNINGS", "ONCOLOGY_PATHOLOGY"],
    "retrieval_concepts": ["fried_noodles_glycemic_impact", "tofu_skin_oil_content"]
  }
  ```
- **核心價值**：從源頭隔絕「飲食生活」與「TFDA 藥品 ADR 警訊」，避免跨領域污染。

### 3. 證據風險評級與門檻過濾（Evidence Risk Leveling）
- 檢索召回的候選段落需經由可信度與相關度門檻過濾，若無高信心條目則明確回傳 `EMPTY`，絕不將低相關性的雜訊硬塞給生成端。

---

## 四、AMIE 的回覆生成控制：三階段推理鏈 (Inference-Time CoR)

AMIE 在生成任何給病患的回覆前，嚴格在推理空間（CoT）內部走完三步驟：

```
[病患發言]
   │
   ▼
Step 1: 臨床資訊深度解構 (Analyzing Patient Information)
   ├─ 萃取陽性與陰性表徵 (Positive/Negative Findings)
   ├─ 更新既往史、用藥史、生活紀錄
   ├─ 產出鑑別診斷假說與潛在風險
   └─ ★ 明確列出「資訊缺口 (Information Gaps)」與當前信心度
   │
   ▼
Step 2: 處置與對話行動擬定 (Formulating Response and Action)
   ├─ 決定本次回覆的主目標：【主動追問補齊缺口】或【給予具體衛教】
   ├─ 若遇急性危急表徵 (Red Flags)，優先強制插入安全網 (Safety Netting)
   └─ 結合 RAG 檢索到的官方臨床指引形成對策
   │
   ▼
Step 3: 回覆精煉與自我批判審查 (Refining the Response / Critic Pass)
   ├─ [真實性檢核]：回覆中的每一個論點是否有檢索指引支持？
   ├─ [語言去黑話]：是否將艱澀病理學術語轉化為口語白話？
   ├─ [共情度確認]：口吻是否具備同理心？
   └─ [防資訊傾倒]：是否控制單次訊息量？避免一次塞滿 300 字衛教？
   │
   ▼
[輸出自然口語回覆]
```

---

## 五、狀態感知推理（State-Aware Reasoning：諮詢四階段）

2026 年 AMIE 確立了「看診階段狀態機」，嚴格約束各階段合法行為：

| 諮詢階段 (Phase) | 核心目標 | 允許的系統行為 | 嚴格禁止的行為 |
| :--- | :--- | :--- | :--- |
| **Phase 1: 建立關係與主訴** | 傾聽病患核心抱怨與飲食生活動態 | 溫暖同理、簡短覆誦、引導病患多說 | 禁止檢索藥品庫、禁止下診斷、禁止說教 |
| **Phase 2: 針對性細節採集** | 釐清資訊缺口 (份量、頻率、伴隨症狀) | 封閉式或引導式提問 (每次 1~2 個問題) | 禁止一次性傾倒大量衛教文字 |
| **Phase 3: 指引對齊與衛教** | 針對已確認之生活事實給予具體改善建議 | 觸發 Nutrition RAG，提供生活替代方案 | 禁止提及未確認之罕見藥品不良反應 |
| **Phase 4: 門診摘要與安全網** | 產出就醫備忘錄，提示異常危險訊號 | 產出 Pre-visit Card，叮嚀就醫時機 | 禁止取代專科醫師進行最終處方決策 |

---

## 六、對 TFDA 糖尿病 v2 系統的直接改造對照表

| AMIE 核心模式 | TFDA 糖尿病 v2 目前現況 | 建議改進方案 (對應檔案) |
| :--- | :--- | :--- |
| **Talker / Planner 解耦** | `handlers.py` 採雙階段模型，但 Planner 僅輸出關鍵字。 | 讓 `v2/planner.py` 輸出結構化狀態（包含 `Information Gaps` 與 `Target Domain`）。 |
| **Scope-Constrained RAG** | `v2/tools.py` 固定傳入 `GENERAL_EDUCATION`，無腦走 `HYBRID`。 | 修改 `v2/tools.py` 與 `v2/server/handlers.py`，飲食意圖只走 `VECTOR`，停用 `GRAPH`。 |
| **三階段推理鏈 (Critic Pass)** | 第二階段 LLM 一步到位輸出回答，偶爾長篇大論。 | 在 `v2/prompts.py` 引入 CoT 標籤：先思辨缺口與同理點，再輸出對話。 |
| **縱向狀態管理 (Longitudinal)** | 依賴平鋪直敘的線性歷史文字，長對話容易失焦。 | 在 `v2/state.py` 建立常駐結構體：記錄血糖歷程、固定用藥、飲食偏好。 |
| **Pre-visit History Taking** | 具備 `generate_previsit_intake_summary`（此點完全契合 2026 AMIE 趨勢）。 | 維持並強化！使門診備忘卡能自動從多輪對話中動態填入未解決問題。 |
