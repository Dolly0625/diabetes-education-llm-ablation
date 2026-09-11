# 研討會論文方法章素材：A／B Planner 消融實驗設計

> **標籤說明**：本段文字為研討會論文「方法學章節（Methodology: Planning Layer Ablation）」專用之學術素材，字數約 900 字，嚴格遵守研究邊界規範（`CLAIM_BOUNDARIES.md`）。本研究採用 AMIE 啟發之多輪模擬對話評估架構（AMIE-inspired simulated dialogue evaluation），不作任何未經人體試驗支持的臨床有效性主張。

---

### 3.1 規劃層消融設計：提示詞基準與結構化規劃員之解耦對比

為深入驗證「解耦式臨床認知規劃（Decoupled Clinical Cognitive Planning）」在病患端對話系統中對多輪決策穩定性與臨床焦點維持的具體貢獻，本研究在受控模擬情境下，設計了嚴格的逐層消融對照組：**Condition A（Prompt-only 基準組）** 與 **Condition B（A ＋ Planner 實驗組）**。兩者探索的核心假設為：在維持相同對話模型與完全相同之全暴露工具集合下，引入結構化規劃員能否顯著改善多輪資訊收集之完整性，並在不依賴硬性工具門禁的情況下引導更符合衛教常規之應答。

#### Condition A（Prompt-only Baseline）之形式化定義
Condition A 模擬現行主流對話代理人設計：直接將完整臨床安全規範、溝通原則與全部候選工具 Schema 注入單一對話模型（Talker LLM）之系統提示詞中。在 Condition A 下，系統完全關閉結構化規劃模組（`enable_planner = False`）。在此條件中，系統既不呼叫 Planner 模型，亦不執行任何規則式規劃備援。為滿足評估管線之資料契約完整性，Condition A 採用預先定義之**中立規劃狀態（Neutral Planner State）**填補軌跡紀錄，其所有臨床槽位狀態皆標記為缺失（`MISSING`），且導引字串為空（`talker_guidance = ""`）。值得特別精確釐清的是，Condition A 並非完全不持久化任何狀態：系統底層的基礎事實抽取模組仍照常自病患自然語言中提取關鍵數據（如血糖量測值），對話歷史亦如實維護；Condition A 的本質在於**完全不執行臨床槽位推論、不產生 Talker 導引，且不持久化任何 Planner Assessment 結構化槽位**。

#### Condition B（A ＋ Planner）之決策與導引機制
Condition B 在 Condition A 之基礎上，於 Talker 生成回覆前引入一個輕量且低溫（`temperature = 0.1`）之結構化規劃員（`enable_planner = True`）。Planner 依據病患歷史上下文與病患檔案，評估包含看診主訴、用藥歷程、血糖指標、低血糖史及病患疑慮等五項臨床核心槽位（Clinical Slots），並判定當前對話意圖與衛教需求。若 Planner 評估需引導溝通方向，其產出之自然語言臨床導引（`talker_guidance`）將動態以系統角色（`{"role": "system"}`）注入至 Talker 的推論上下文中，直接提示模型當前優先釐清之臨床缺口或衛教重點，並將推論槽位持久化於病患紀錄。為保障執行穩健性，Planner 具備四次指數退避重試機制，遇不可抗之暫態故障時自動平滑降級為確定性規則規劃器，確保消融軌跡之完整性。

#### 控制變項與無偏消融保證（Controlled Invariants）
為確保觀察到之差異純粹源自結構化規劃能力，本研究建立嚴格的控制變項隔離規範：
1. **模型與提示詞凍結**：A 與 B 均採用相同之 Talker 模型（`gemini-3.5-flash-lite`）、相同採樣溫度（`0.3`）以及經 SHA-256 雜湊鎖定之護理師基礎提示詞。
2. **工具全暴露等價性**：A 與 B 的動態工具閘門均固定關閉（`enable_dynamic_tool_gate = False`）。兩者向模型暴露之工具集合均嚴格等於標準工具快照（Canonical Tool Snapshot，包含衛教手冊檢索與就醫備忘錄產出），徹底排除因工具可見性差異引起之混淆。
3. **生產端干擾項排除**：為杜絕未建模的額外資訊優勢，A 與 B 固定關閉強制檢索（`enable_forced_retrieval = False`）。即使 Condition B 之 Planner 判定出特定檢索領域，系統亦嚴格禁止自動抓取手冊片段注入 Prompt，保證 B 相對於 A 絕不具備額外外部實證資訊。同時，兩組均關閉輸出熔斷（`enable_output_guard = False`）與後處理問句截斷。

本消融設計確保了從 Condition A 到 Condition B 的過渡中，唯一的自變項僅為**結構化規劃員及其導引注入機制**，為後續多輪一致性與對話策略評估奠定堅實的因果對照基礎。
