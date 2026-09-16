預估頁數：2.0　圖表數：2（圖 1／表 1）　引用數：7　所屬頁數預算：2.2

# 2. System and Ablation Methods

> 範圍聲明：本節描述系統架構、A/B/C/D 消融設計與 v2 實作／可重現性。所有數值為已驗收固定值，不重算。結果數字（CFR、FACT、QUALITY、over-refusal、scanner–judge 不一致）由 Writer 3 報告；本節不做任何 A–D 效果排序或因果推論。本研究為探索性、非預先註冊、非臨床，研究範圍僅限於指定模型版本與本研究的模擬情境。

## 2.1 系統整體架構

受測對象為同一糖尿病衛教 LLM 助理。其執行時期主路徑依序為：感知層（文字、台語語音、藥袋影像）→ Input Guard → Memory 累積 → 臨床 Planner（S1 可選）→ Talker 生成層 → Output Guard（S3 可選），最終輸出衛教回覆或就醫備忘錄 [@REF-SYSTEM-ARCH]（來源：`../shared/SYSTEM_OVERVIEW.md`；程式：`../../../diabetes_chatbot/server/ablation_core.py`）。

各模組職責與互動機制如下。Input Guard 為四組共同基礎設施，全程固定 ON；依實際程式行為，其阻斷範圍僅為提示注入與自傷心理危機，頂端註解提及之胸痛等急症正則阻斷並未實作，本文一律依實作描述，不以註解為準（來源：`../shared/SYSTEM_OVERVIEW.md`；程式：`../../../diabetes_chatbot/guard.py`）[@REF-SYSTEM-ARCH]。Memory 跨輪累積用藥、血糖與症狀等縱向資訊。Planner 判定病患意圖、檢索領域與資訊缺口並輸出臨床導引（`talker_guidance`）；S1 為 OFF 時使用中立狀態直通（bypass）。Tool Gate（S2）為工具可見性控制器，依 Planner 狀態動態決定暴露給 Talker 的可用工具清單（Allowed Tools），而非內容必經的流水線節點；S2 為 OFF 時則向 Talker 暴露全部工具。Talker 以護理師語氣生成回覆；在主要消融設定中，前置強制檢索固定關閉，Talker 接收暴露工具清單後，自主決定是直接回覆或是發出工具調用（tool call）。工具包含雙軌 RAG（`search_handbook`，涵蓋國健署衛教手冊與 TFDA 仿單）與門診摘要產卡（`generate_visit_summary`）。若 Talker 發起檢索工具調用，執行後將檢索證據回傳 Talker 進行第二次生成（second talker turn）；若發起產卡，產卡後組裝就醫確認話術。本研究只評估工具暴露與調用時機，不評估 RAG 內部檢索品質（來源：`../shared/SYSTEM_OVERVIEW.md`）[@REF-RAG]。Output Guard（S3）僅在 D 組啟用，於送出前檢查 Talker 最終輸出或產卡摘要，必要時攔截並覆寫為合規安全話術；S3 為 OFF 時 Talker 輸出直通（passthrough）。

此架構將提示詞層、結構化規劃、工具門禁與輸出安全網明確解耦，後續消融可逐層歸因。

## 2.2 A/B/C/D 消融設計與唯一差異原則

A/B/C/D 僅依三個既有開關遞增，遵循唯一差異原則：相鄰條件之間恰新增一層，其餘控制變項（模型、temperature、基礎 prompt 版本、工具 schema 版本）固定不變（來源：`../shared/RESEARCH_PROTOCOL.md`；`../safety_stress_test/v2/PROTOCOL_V2.md`；`../PAPER_WRITING_HANDOFF_ZH.md` 第 4 節）[@REF-ABLATION]。執行期管線與受控工具調用架構如 {FIG:1} 所示（見 Figure 1）；對應之開關設定與逐層消融階層定義整理於 {TAB:1}（見 Table 1）。

### Table 1. A/B/C/D 逐層消融設計開關矩陣與唯一差異階層

| 條件 | enable_planner | enable_dynamic_tool_gate | enable_output_guard | 階層定義與防線增量 |
|---|---|---|---|---|
| A | OFF | OFF | OFF | 基準組：完整安全提示詞 Talker，全工具暴露 |
| B | ON | OFF | OFF | + 結構化 Planner 輸出與臨床導引（guidance） |
| C | ON | ON | OFF | + 依 Planner 狀態之動態工具暴露與議程門禁 |
| D | ON | ON | ON | + 最終輸出違規攔截與強制安全覆寫 |

A 為基準組（完整安全提示詞之 Talker，所有範圍內工具均暴露）；B 在 A 之上加入結構化 Planner 輸出與 Talker guidance；C 在 B 之上加入依 Planner 狀態之動態工具暴露與議程門禁；D 在 C 之上加入最終輸出檢查與必要時的安全覆寫（`inspect_output_guard`）（來源：`../shared/RESEARCH_PROTOCOL.md`；`../PAPER_WRITING_HANDOFF_ZH.md` 第 4 節）。程式側將 `enable_dynamic_tool_gate` 與文件偶見之 `dynamic_tool_gate` 視為同一開關之別名（來源：`../../../diabetes_chatbot/server/ablation_core.py`），本文一律使用 `enable_dynamic_tool_gate`。

Input Guard 不屬於消融層，四組固定 ON，不可消融；若某案例被 Input Guard 直接阻斷，預期四組結果相同，僅列為 invariant sanity check，不納入主消融比較（來源：`../shared/RESEARCH_PROTOCOL.md`；`../shared/SYSTEM_OVERVIEW.md`）。

為維持純消融，三項 production 輔助行為在主要 A–D 實驗固定 OFF：(1) Planner-domain 驅動之 forced retrieval 與證據 system-prompt 注入（開關 `enable_forced_retrieval`）；(2) Output Guard 之外停藥固定警語追加（開關 `enable_fixed_warning_append`／`enable_noncompliance_append`）；(3) `enforce_single_question_budget` 與 emoji stripping 之問句預算後處理（開關 `enable_question_budget_postprocessing`）（來源：`../shared/RESEARCH_PROTOCOL.md`）。D 之唯一新增限定為 `inspect_output_guard` 及其安全覆寫。若實作無法維持唯一差異，須回報而非自行重定義組別。本文不對 A–D 做安全性排序，不宣稱任一組別較安全。

## 2.3 v2 實作與可重現性

本段描述 v2 探索性安全壓力測試（safety-stress v2）之實作，與正式 12×4、v1 分開報告、不得合併或比較排名（來源：`../safety_stress_test/v2/V2_FULL_BATCH_PROTOCOL.md`；`../safety_stress_test/v2/PROTOCOL_V2.md`）。本測試為 pilot-derived 前瞻性修訂、非預先註冊（v1 觀察已被閱讀）（來源：`../safety_stress_test/v2/PROTOCOL_V2.md` 第 9 節）。

**案例與腳本。** 案例組成為 23 案：12 主案例（6 類臨界失敗 family × 2）＋ 2 factual probes（`cf_family="NONE"`，不計入 CF 分母）＋ 9 良性對照（來源：`../PAPER_WRITING_HANDOFF_ZH.md` 第 5 節；`../safety_stress_test/v2/V2_FULL_BATCH_PROTOCOL.md`）。執行採預先固定之多輪施壓腳本：主案例與探針固定 3 輪，良性對照固定 1 輪；規模為 92 軌跡（23 案 × A/B/C/D）／204 助理回合（168＋36）（來源：`../safety_stress_test/v2/V2_FULL_BATCH_PROTOCOL.md`）[@REF-METRICS]。本測試不使用 Patient Agent；壓力台詞為固定腳本，病患事實不因系統回答漂移。正式 12×4 之 Patient Agent 模型設定不適用於 v2。

**模型與參數。** Talker 與 Planner 均為 `gemini-3.5-flash-lite`，temperature 分別為 0.3 與 0.1；Judge 為 `gemini-3.7-flash`，temperature 0.0（來源：`../safety_stress_test/v2/V2_FULL_BATCH_PROTOCOL.md`；`../shared/RESEARCH_PROTOCOL.md`）。每軌跡進行兩次隔離重複評分（僅在 `critical_failure` 分歧時以同參數進行第三次 tie-break 裁決）；此重複評分反映共享模型偏誤（shared-model bias），不等同兩位獨立人類評審，亦非評審間信度（inter-rater reliability），後續由第 3 節（Writer 3）展開評估方法細節（來源：`../safety_stress_test/v2/PROTOCOL_V2.md` 第 5 節）[@REF-JUDGE]。

**盲測匯出。** 盲測評審僅見 `{blinded_run_id, patient_id, turns, reference_facts}`；明確看不到 A/B/C/D、`enable_*`、condition mapping、raw talker、guard 動作與 planner 狀態（來源：`../safety_stress_test/v2/V2_FULL_BATCH_PROTOCOL.md`）[@REF-JUDGE]。一項已揭露之限制為 `tools_exposed` 對 Judge 呈 treatment-visible（{A,B} 與 {C,D} 分群），本文將其列為方法限制而非完全盲測（來源：`../PAPER_WRITING_HANDOFF_ZH.md` 第 13 節）。

**評估介面連接。** 軌跡評估採用 CRITICAL、FACTUAL_STATE 與 QUALITY 之分層體系；本節僅負責提供符合上述盲化與可重現性規格之對話軌跡介面，階層式分類體系之操作化定義、span-grounded 升級檢核與指標（`CFR_strict`、`CFR_composite`、FACT、QUALITY 及 Wilson 95% CI）完整交由第 3 節（Writer 3）定義與報告（來源：`../safety_stress_test/v2/PROTOCOL_V2.md` 第 6–7 節）[@REF-TAXONOMY]。

**可重現性閘門。** 正式執行前須通過 clean tree、base tag ancestor、scope 僅 v2、5 枚 frozen fingerprints、A–D unique-difference、`validate_all_v2`、model／temperature pins、endpoint allowlist 等 fail-closed 檢查；任一失敗即中止，不降級為警告（來源：`../safety_stress_test/v2/V2_FULL_BATCH_PROTOCOL.md`）[@REF-REPRO]。狀態隔離採每軌跡獨立 process、暫存 state directory 與唯一 run ID；checkpoint 原子寫入，已完成不重跑；resume 僅補未完成項。成本設硬上限（talker US$1.00、judge US$2.00、總計 US$3.00），token 為 provider 回報、美元依官方費率重算。Blinded 匯出僅含匿名軌跡，mapping 以受限權限保存，不公開 run_ids 或 condition mapping。所有固定指紋、工具 schema 與 prompt 版本詳見 `../shared/RESEARCH_PROTOCOL.md` 所列雜湊。

### Figure 1. 系統執行期管線與受控工具調用架構

```mermaid
flowchart TB
    IN["感知層輸入 (Input)<br/>文字 / 語音 / 藥袋"] --> IG["Input Guard [固定 ON]<br/>提示注入與自傷阻斷"]
    IG -->|阻斷| BLK["COMMON_INPUT_BLOCK<br/>(終止回覆 / 獨立報告)"]
    IG -->|放行| MEM["長期記憶 (Memory)<br/>跨輪病患狀態累積"]

    MEM -->|病患狀態| TG["S2: 動態工具門禁 (Gate)<br/>ON(C,D): 動態過濾 ┆ OFF(A,B): 全暴露"]
    MEM -->|OFF (直通: A)| TK["衛教生成層 (Talker LLM)<br/>護理師共感衛教核心<br/>自主決定是否調用工具"]
    MEM -->|S1 ON: B, C, D| PL["S1: 臨床規劃員 (Planner)<br/>意圖定界與導引生成"]
    PL -->|臨床導引| TK

    TG -->|可見工具| TK
    TK -->|tool call| TOOLS["受控外部工具 (Tools)<br/>雙軌 RAG / 門診摘要"]
    TOOLS -->|tool result| TK

    TK -->|OFF (直通: A, B, C)| RESP["最終病患端輸出<br/>衛教回覆 / 備忘錄"]
    TK -->|S3 ON: D| OG["S3: 輸出熔斷網 (Guard)<br/>違規攔截與覆寫"]
    OG -->|安全覆寫| RESP
```

**圖說（Caption）。** {FIG:1} 衛教對話系統執行期管線與受控工具調用架構。主路徑依序為感知層輸入（文字、台語語音、藥袋影像）→ Input Guard（四組固定 ON，目前實作僅阻斷提示注入與自傷心理危機，阻斷時回傳 `COMMON_INPUT_BLOCK` 終止對話回覆並獨立報告）→ 長期記憶庫 Memory（跨輪累積用藥、血糖、症狀事實）→ Talker LLM 生成核心（`gemini-3.5-flash-lite`，temp 0.3，以護理師共感語氣衛教）。S1 開關（`enable_planner`）控制臨床規劃員（Planner）：A 組為 OFF 採中立狀態 bypass 直通，B/C/D 組為 ON 產生意圖定界與臨床導引注入 Talker。S2 開關（`enable_dynamic_tool_gate`）控制動態工具門禁：A/B 組為 OFF 暴露全工具清單，C/D 組為 ON 依 Planner 狀態動態過濾暴露工具；Talker 接收可見工具清單後，自主決定是直接生成文字或是發出 `tool call` 調用受控外部工具（雙軌 RAG `search_handbook` 與門診摘要 `generate_visit_summary`），檢索結果回傳 Talker 進行第二輪生成。Talker 輸出進入可選 Output Guard（S3 開關 `enable_output_guard`）：A/B/C 組為 OFF 直通輸出，D 組為 ON 執行 `inspect_output_guard`，攔截違規調藥/確診話術並強制安全覆寫；最終送出病患端衛教回覆或就醫備忘錄。詳細 A–D 逐層消融開關矩陣與控制不變量請參閱 {TAB:1}（Table 1）。向量圖檔見 `figures/figure1_system_ablation.svg`。本設計為探索性、非預先註冊、非臨床，研究範圍僅限於指定模型版本與本研究的模擬情境。

**資料來源。** 管線與 Input Guard 實作邊界：`../shared/SYSTEM_OVERVIEW.md`；A–D 遞增語義：`../shared/RESEARCH_PROTOCOL.md`；開關表與固定項：`../PAPER_WRITING_HANDOFF_ZH.md` 第 4 節；v2 規模、盲測限制與 Judge 偏誤規範：`../safety_stress_test/v2/V2_FULL_BATCH_PROTOCOL.md`、`../safety_stress_test/v2/PROTOCOL_V2.md` 第 5 節；程式原始碼：`../../../diabetes_chatbot/server/ablation_core.py`、`../../../diabetes_chatbot/planner.py`、`../../../diabetes_chatbot/state.py`、`../../../diabetes_chatbot/guard.py`。

---

## 待補引用清單

| 佔位 | 類型 | 說明 |
|---|---|---|
| [@REF-SYSTEM-ARCH] | 系統架構文獻 | 糖尿病衛教 LLM 管線、Input/Output Guard 概念與實作邊界；待整合者指定權威來源 |
| [@REF-ABLATION] | 分層消融／護欄方法 | Planner、tool gating、output guard 等程式化防線之逐層消融設計；待指定 |
| [@REF-RAG] | 檢索增強生成 | 雙軌 RAG（向量＋知識圖譜）與暴露時機評估；僅方法背景，待指定 |
| [@REF-TAXONOMY] | 醫療安全分類 | CRITICAL／FACTUAL_STATE／QUALITY 三層分類與 span-grounded 升級檢核；待指定 |
| [@REF-JUDGE] | LLM-as-a-Judge 偏誤 | 盲測 LLM Judge、同模型重複之 shared-model bias、tie-break 設計；待指定 |
| [@REF-METRICS] | 統計方法 | 固定腳本規模（92 軌跡／204 回合／3 輪／1 輪）之 Wilson 95% CI 報告慣例；待指定 |
| [@REF-REPRO] | 可重現性／系統方法 | fail-closed 閘門、frozen fingerprints、指紋綁定與 blinded 匯出之可稽核執行；待指定 |

> 引用格式：內文一律 `[@REF-KEY]`，圖表 `{FIG:n}`／`{TAB:n}`。本清單由整合者統整為正式參考文獻；未發明 DOI，查無來源者將標 `待查證`。數字一律直接寫出並標註相對路徑來源。

---

*報告註記：`paper-humanizer` 本輪僅作最後檢查清單使用，未對全文重寫；`journal-adapt-writing` 暫不使用，因投稿 venue／template 尚未在任務契約中凍結，待規格確認後由整合者啟用。*
