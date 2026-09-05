# 失敗模式評測報告（Boundary C）

## 1. 背景與範圍

8/26 會議上，學長對 RAG 組最直接的批評是：「目前 RAG 組對於失敗模式的描述流於文字概括，在 IT 專業會議中必須給予具體量化指標與演算方法。」這份報告的目的，就是把 MS1 階段那張純分類表變成一組會跑出數字、可被重現、可被質疑的評測結果。

**分類定義聲明（務必先讀）**：本報告採用的 6 類失敗模式定義，**完全依照 `docs/06_boundary_c_eval.md`**：實體抽取錯誤、關係方向錯誤、幻覺實體、跳數用盡、無關 relation、否定語境。這 6 類**不等同於** MS1 階段「Boundary - C（校對版）」文件裡原本的 6 類失敗模式表，儘管部分名稱看起來相似（例如 M1 文件裡的「抽取信心未分級」「同源資料不一致」等類別**不屬於**本報告範圍）。閱讀本報告時請勿與 M1 文件的分類表混用。

另外，`docs/06_boundary_c_eval.md` 提到的參考文件 `Preprocessing - B.md` 第 12 節（A2 安全機制誤攔正確事實、A4 切分粒度錯誤）已於分析後期取得並完成查證，結論是：兩者描述的問題都發生在 graph pipeline 的**上游建圖/抽取階段**，而非本報告 6 類失敗模式測的「使用者問句 → 檢索行為」這條路徑，因此**不適合直接改寫成 `eval/queries.json` 的新測試題**，而是作為佐證引用補充於第 5.2 節與第 8.3 節，20 題負向題維持原設計不變。詳細查證過程見第 8.3 節。

**資料來源聲明**：本報告的 graph 軌道數字（不需要網路／API key）由本次分析環境直接執行、可重現。vector 軌道相關數字因本分析環境未設定 `GEMINI_API_KEY`，改採信本任務負責人在自己終端機的驗證結果——完整說明見第 8.1 節。

## 2. 評測集組成

| 分類 | 題數 | track 分布 |
|---|---|---|
| 正向題（原有） | 20（g01–g10、v01–v10） | graph 10、vector 10 |
| 負向／邊界題（本任務新增） | 20（neg_*） | graph 15、vector 5 |
| **合計** | **40** | graph 25、vector 15 |

負向題依 6 類分布：實體抽取錯誤 4（neg_ent_01–04）、關係方向錯誤 3（neg_dir_01–03）、幻覺實體 4（neg_hal_01–04）、跳數用盡 3（neg_hop_01–03）、無關 relation 3（neg_irr_01–03）、否定語境 3（neg_neg_01–03）。全部 20 題 `expected_chunk_ids` 皆為 `[]`。

## 3. 正向題結果（原 20 題）

| 軌道 | n | Recall@5 | Precision | F1 |
|---|---|---|---|---|
| graph（g01–g10） | 10 | 0.95 | 0.36 | 0.51 |
| vector（v01–v10） | 10 | 0.40 | 0.08 | 0.13 |
| **全部** | 20 | **0.68** | **0.22** | **0.32** |

這組數字與 `MODULE_STATUS.md` 記錄的 2026-08-29 baseline 完全一致，且已由本任務負責人在非 degraded 環境下重複執行兩次確認可重現（詳見第 8.1 節）。

本分析環境自己（無 `GEMINI_API_KEY`）曾單獨跑出 g01–g10 全部 `recall=1.00` 的數字，經比對判定為**環境缺陷造成的假象**：`response.chunks` 是 graph／vector 融合後的結果；當 vector 端因缺金鑰而完全 degraded 時，`gate_out.truncate_balanced` 不需要幫 vector 保留名額，graph 端候選會佔滿全部 top-5，讓部分題目「意外地」更容易命中滿分。這不是真實的系統表現，此數字**不應採用**，應以外部驗證環境（non-degraded、可重現）為準。

## 4. 負向題結果（新 20 題）

### 4.1 為什麼不能直接套用 Recall/Precision/F1

`run_eval.py` 的 `_score()`：

```python
recall    = hits / len(expected)      if expected      else 0.0
precision = hits / len(retrieved_set) if retrieved_set else 0.0
```

當 `expected_chunk_ids=[]` 時，`hits = expected & retrieved` 恆為空集合，所以 recall/precision 不論實際回傳什麼，永遠印出 0.00／0.00／0.00。這點已用實際數字反向驗證：15 題負向 graph 題目對 graph 軌道 recall 總和的貢獻確實為 0，與推論一致。

因此：負向題的 Recall/Precision/F1 在數學上必然是全 0，這個 0 本身不能證明任何事——它既不代表「系統正確地清空」，也不代表「系統該清空卻沒清空」。真正的判讀依據是下面 4.3 節逐題檢視的 retrieved 實際內容。

### 4.2 負向題正確清空率

本節指標明確排除 `neg_hop_01/02/03`（3 題），只計算其餘 17 題。原因：跳數用盡類別的「正確行為」是誠實標記 `graph_path_status=PARTIAL`，而不是清空結果——回傳非空的 hop 內證據本身可能是正確行為，不適用「retrieved==[] 才算對」這個定義。這 3 題的判讀獨立列在 4.4 節。

| | 題數 | retrieved 為空 |
|---|---|---|
| 17 題（排除 3 題跳數用盡） | 17 | 1（neg_hal_02） |

正確清空率 = 1/17 ≈ 5.9%。這是一個刻意不修飾的低分——16 題本該預期清空的負向題，實際上都回傳了非空結果。第 5 節會逐題拆解這些非空結果各自代表什麼問題。

### 4.3 逐題 retrieved 結果（來源見第 8 節附錄）

| query_id | 類別 | retrieved（前 5，實際內容） |
|---|---|---|
| neg_ent_01 | 實體抽取錯誤 | `tfda-risk-019_tri_00`, `tfda-risk-026_tri_00`, `tfda-risk-027_tri_00`, `tfda-risk-064_tri_00`, `tfda-risk-019_sec0_00`——皆為泛用 TREATS 三元組/chunk |
| neg_ent_02 | 實體抽取錯誤 | `tfda-risk-019_tri_00`, `tfda-risk-064_tri_00`, `tfda-risk-026_tri_00`, `tfda-risk-030_tri_00`, `tfda-risk-019_sec0_00`——皆為泛用 TREATS 三元組/chunk |
| neg_ent_03 | 實體抽取錯誤 | `tfda-risk-019_sec0_00`, `tfda-risk-035_sec0_00`, `tfda-risk-019_sec4_05`, `hpa-dm-book_sec18_161`, `tfda-risk-019_sec5_16`——含衛教語料附錄表 chunk |
| neg_ent_04 | 實體抽取錯誤 | `hpa-dm-book_sec18_161`, `tfda-risk-019_sec0_00`, `tfda-risk-035_sec0_00`, `hpa-dm-book_sec18_163`, `hpa-dm-book_sec18_160`——5 筆中 3 筆為衛教語料附錄表 chunk |
| neg_dir_01 | 關係方向錯誤 | `tfda_canagliflozin_dapagliflozin_aki_tri_00/01`（＝g03 正解）＋ `tfda-risk-019_tri_00`, `tfda-risk-026_tri_00`, `tfda-risk-035_sec0_00` |
| neg_dir_02 | 關係方向錯誤 | `tfda_sglt2_ketoacidosis_tri_03/04/05`（＝g07 正解 3 筆）＋ `tri_06`, `tfda-risk-019_sec4_07` |
| neg_dir_03 | 關係方向錯誤 | `tfda_insulin_amyloidosis_tri_00/01`（與 g02 正解完全相同）＋ `tfda-risk-100_sec4_05/06`, `sec5_13` |
| neg_hal_01 | 幻覺實體 | `tfda-risk-100_tri_00`, `tfda_insulin_amyloidosis_tri_00/01`, `tfda-risk-100_sec0_00/1_01`——皆為 Insulin 相關三元組/chunk |
| neg_hal_02 | 幻覺實體 | `[]`（**唯一真正清空**） |
| neg_hal_03 | 幻覺實體 | `tfda-risk-100_sec0_00`, `hpa-dm-book_sec19_164`, `tfda-risk-027_sec2_02`, `hpa-dm-book_sec18_151`, `tfda-risk-100_sec2_02`——最後一筆即 v09 正解 chunk |
| neg_hal_04 | 幻覺實體 | `tfda-risk-100_tri_00`, `tfda-risk-026_sec1_01`, `tfda-risk-035_sec1_01`, `tfda-risk-100_sec1_01`, `tfda-risk-019_sec0_00`——Insulin TREATS 三元組 |
| neg_hop_01 | 跳數用盡 | 5 筆非空（見 4.4：`graph_path_status=COMPLETE`） |
| neg_hop_02 | 跳數用盡 | 5 筆非空（見 4.4：`graph_path_status=PARTIAL`） |
| neg_hop_03 | 跳數用盡 | 5 筆非空（見 4.4：`graph_path_status=PARTIAL`） |
| neg_irr_01 | 無關 relation | `tfda-risk-019_tri_00`, `tfda-risk-026_tri_00`, `tfda-risk-064_tri_00`, `tfda-risk-030_tri_00`, `tfda-risk-019_sec0_00`——泛用 TREATS 三元組/chunk |
| neg_irr_02 | 無關 relation | `openfda_metformin_contraindications_tri_00/01`（與 g01 CAUTION_FOR 正解完全相同）＋ `tfda-risk-027_sec0_00`, `tfda-risk-019_sec0_00`, `hpa-dm-book_sec18_162` |
| neg_irr_03 | 無關 relation | `tfda-risk-019_tri_00`, `tfda-risk-026_tri_00`, `tfda-risk-030_tri_00/01`, `tfda-risk-026_sec0_00`——泛用 TREATS 三元組/chunk |
| neg_neg_01 | 否定語境 | `openfda_metformin_contraindications_tri_00/01`（與 g01 CAUTION_FOR 正解完全相同）＋ `tfda-risk-019_sec5_17`, `sec0_00`, `tfda-risk-035_sec5_18` |
| neg_neg_02 | 否定語境 | `tfda-risk-019_tri_00`, `tfda-risk-026_tri_00`, `tfda-risk-064_tri_00`, `tfda-risk-030_tri_00`, `tfda-risk-035_sec5_10`——泛用 TREATS，**非**原預測的 ACEIs／利尿劑／NSAIDs 三筆 |
| neg_neg_03 | 否定語境 | `tfda-risk-019_tri_00`, `tfda-risk-026_tri_00`, `tfda-risk-064_tri_00`, `tfda_sglt2_ketoacidosis_tri_00`（與 g05 TRIGGERS 正解相同）, `tfda-risk-019_sec4_05` |

### 4.4 跳數用盡：graph_path_status 獨立檢查（不經過 run_eval.py，因其不輸出此欄位）

本分析環境直接呼叫 `EvidenceRetrievalTool().retrieve()`（純 graph 邏輯，不需要 `GEMINI_API_KEY`，可在本環境獨立重現）：

| query_id | graph_path_status | warnings |
|---|---|---|
| neg_hop_01 | COMPLETE | （無 `GRAPH_HOP_LIMIT_REACHED`） |
| neg_hop_02 | PARTIAL | 含 `GRAPH_HOP_LIMIT_REACHED` |
| neg_hop_03 | PARTIAL | 含 `GRAPH_HOP_LIMIT_REACHED` |

## 5. 六類失敗模式逐一檢討（逐題判讀，非僅類別籠統結論）

### 5.1 關係方向錯誤 —— 3/3 確認為真實問題

- `neg_dir_01`（急性腎損傷會不會引起 canagli/dapagliflozin？）：retrieved 包含 g03 的正確答案三元組（`tfda_canagliflozin_dapagliflozin_aki_tri_00/01`）。
- `neg_dir_02`（酸中毒會不會導致低血容量等？）：retrieved 包含 g07 三筆正解三元組中的 3 筆（`tri_03/04/05`）。
- `neg_dir_03`（皮膚澱粉樣變性症會不會造成未輪替注射部位？）：retrieved 與 g02 正解三元組完全相同（`tfda_insulin_amyloidosis_tri_00/01`）。

三題都證實：`graph.py` 的 label 比對是雙向字串比對（見 `retrievers/graph.py` 第 100 行 `for a, b in ((subj_l, obj_l), (obj_l, subj_l))`），完全不判斷問句的因果方向，不論正著問或問反，回傳的三元組集合幾乎相同。**確認為真實存在的問題，且是架構性的**（只要問法命中相同的實體 label，方向判斷失效的情況必然存在，不受資料規模影響）。

### 5.2 無關 relation —— 1/3 確認，2/3 無法定論

- `neg_irr_02`（Metformin 是不是禁忌用於孕婦？）：retrieved 包含跟 g01 完全相同的 CAUTION_FOR 三元組。系統把「一般注意事項」級別的證據，當成回答「禁忌」問題的依據——**確認為真實問題**，直接對應 CLAUDE.md §2 第 7 條「絕不把 CAUTION_FOR 升級成禁忌」的紅線，這裡呈現的是相反方向的漏洞：檢索端沒有過濾掉不相符的 relation 型別，讓「注意事項」等級證據被當成「禁忌」問題的答案。

  這個檢索端漏洞與 `Preprocessing - B.md` 第 12 節 A2 記錄的上游資料缺口互為印證，是同一枚硬幣的兩面：A2 指出目前資料集裡完全沒有可檢索的 `CONTRAINDICATED_FOR`（禁忌）三元組——最高風險等級的事實從一開始就沒被放進可檢索集；`neg_irr_02` 則證明，在缺少上位禁忌事實的情況下，次一級的 `CAUTION_FOR`（注意事項）三元組會被檢索端誤用去頂替回答禁忌問題。一邊是資料建置階段的保守關卡副作用，一邊是檢索階段缺乏 relation 型別過濾，兩者合起來才是完整的問題全貌。詳見第 8.3 節。

- `neg_irr_01`、`neg_irr_03`：retrieved 都是泛用的 TREATS 三元組/chunk，但無法明確判定這是「relation 型別不符」造成，還是跟 5.5 節「泛用詞彙污染」是同一種現象（藥物類別名稱本身被當成 label 命中，而非因為語意上被誤判成某個 relation）。列為「非空但無法定論」，不計入確認案例。

### 5.3 否定語境 —— 2/3 確認，1/3 部分證據

- `neg_neg_01`（我沒有腎功能問題，metformin 需要注意什麼？）：retrieved 包含跟 g01 完全相同的 CAUTION_FOR 三元組——**確認**：否定語境完全被忽略。
- `neg_neg_03`（我沒有酮酸中毒病史，SGLT2i 還會誘發 DKA 嗎？）：retrieved 包含跟 g05 一致的 TRIGGERS 正解三元組——**確認**：同樣的機制成立。
- `neg_neg_02`（沒有用利尿劑/NSAIDs，SGLT2i 安全嗎？）：retrieved 是泛用 TREATS 三元組，並未命中原本預測會出現的 ACEIs／利尿劑／NSAIDs 三筆 INDUCES 三元組（`tri_05/06/07`）。列為**部分證據**：原理上證實了「polarity 完全不影響檢索」這件事本身成立，但沒有重現我們原先設想的具體機制（特定風險三元組洩漏）。

**架構性佐證**：`contract/enums.py` 定義了 `Polarity.NEGATIVE`，但搜尋整個 `src/rag_retrieval/` 找不到任何地方讀取 `context_modifiers.polarity` 來過濾或調整檢索——這個欄位目前只是契約層的 passthrough。`gate_out.py` 的註解也明白寫著：可檢索三元組的 `negation_checked` 全部是 `False`（上游否定詞檢查其實還沒真的跑），這個欄位雖然會透過 `relations[]` 往下傳給 LLM 組的 Context Gate，但 RAG 這一側完全沒有拿它做任何過濾。這代表否定語境的問題不是巧合，是目前架構裡明確存在、且已知的空白。

### 5.4 跳數用盡 —— 2/3 確認，屬於「系統誠實揭露不完整」的正面發現

- `neg_hop_02`、`neg_hop_03`：`graph_path_status=PARTIAL` 且 `warnings` 含 `GRAPH_HOP_LIMIT_REACHED`——機制正確運作：當 BFS 展開需要超過 `HOP_BUDGET=2` 時，系統誠實標記自己拿到的是不完整證據，而不是靜默地假裝答案齊全。這應該被當成**系統的正面發現**寫進展示，而不是失敗案例——這正是「不確定性要誠實揭露」這個設計原則有被落實的證據。
- `neg_hop_01`：`graph_path_status=COMPLETE`，未重現跳數溢出。原因推測（非臆測結論，是架構限制）：目前僅有 29 筆可檢索三元組，`neg_hop_01` 撒下去的種子（第二型糖尿病、SGLT2 抑制劑類、利尿劑）雖然橫跨多個事件，但實際連通出來的子圖仍在 2 跳預算內走完，沒有形成需要第 3 跳才能連通的路徑。**這一題在目前資料規模下不可重現，不是設計錯誤，是資料規模的限制**——誠實記錄，不硬凹成失敗案例。

### 5.5 實體抽取錯誤 + 幻覺實體 —— 1/8 清空，7/8 揭露了一個比「幻覺」更值得關注的真實問題

`neg_ent_01–04`、`neg_hal_01/03/04` 全部回傳非空結果；只有 `neg_hal_02`（GAD 抗體）回傳 `[]`。逐一檢視這 7 個「非空」結果的實際內容後發現：幾乎沒有一筆是因為系統真的把虛構藥名/檢驗值誤認成某個真實實體——真正的原因是 `retrieval_queries` 裡搭配虛構實體出現的**泛用糖尿病詞彙**（「糖尿病」「治療」「機轉」「注意事項」等）本身就是真實 label 的子字串或語意鄰近詞，足以單獨觸發命中：

- `neg_ent_03`（Sotagliflozin 會不會引起低血糖？）、`neg_ent_04`（Imeglimin 的藥理作用機轉？）：命中的都是 `hpa-dm-book_sec18_*`——也就是我們在查證階段就已經發現的衛教語料附錄二（口服抗糖尿病藥）巨大品項對照表。這張表幾乎涵蓋台灣市面上所有抗糖尿病藥物的學名與品牌名，任何跟「藥物」「機轉」沾邊的問句都很容易在語意上被拉近這個 chunk，而不是因為「Sotagliflozin」「Imeglimin」這幾個字本身被找到。
- `neg_hal_03`（口服胰島素錠劑型的藥理吸收機轉？）：retrieved 直接包含 `tfda-risk-100_sec2_02`——這正是 v09（「胰島素如何調節血糖？」）的正解 chunk。這件事在設計這題時就已經被預判為已知的殘留風險（語意上跟既有胰島素機轉內容太接近），這裡是**如預期地被證實**，不是意外。
- `neg_ent_01`、`neg_hal_01`、`neg_hal_04`：命中的都是泛用 TREATS 三元組或 Insulin 相關三元組，同樣是被「治療」等泛用詞造成的命中，不是虛構實體本身被誤認。

這個發現值得特別框出來寫進展示：**目前系統沒有能力區分「這個實體真的不存在」跟「這句話裡有足夠多的泛用糖尿病詞彙，隨便都能撈到東西」**。這其實比單純的幻覺實體問題更貼近真實使用情境——真實的病人或使用者問到虛構或記錯的藥名時，問句裡幾乎必然會夾帶這些泛用詞彙（因為使用者本來就是想問跟糖尿病用藥有關的問題），所以這個弱點在展示現場被問到冷門藥名時，重現機率其實相當高。

## 6. 指標本身的檢討：Precision 天花板問題

正向題大多數只有 1 筆正解（少數 2–3 筆），但 `gate_out.DEFAULT_TOP_N=5` 固定回傳至多 5 筆候選，即使系統把唯一正解排在第一名，Precision = 1/5 = 0.20 也已經是理論上限。目前正向題 Precision=0.22（見第 3 節）已經是接近滿分，而不是「幾乎全錯」。

建議補充指標：
- **Precision@|expected|**：只看回傳前 N 筆（N = 該題正解數），滿分才會是 1.0。
- **MRR**：第一筆正確答案排第幾名的倒數平均，適合本任務這種「單一正解為主」的場景。

誠實揭露一個限制：本次分析沒有取得 20 題正向題完整排序後的 retrieved 清單（只取得聚合後的 recall/precision/f1），因此**無法在本報告算出精確的 Precision@|expected| 或 MRR 數值**——這裡不會為了填一個數字而用聚合值反推估計。建議下一輪迭代在 `eval/` 底下新增一個不修改 `run_eval.py` 既有 `_score()` 的獨立函式，直接消費 `run()` 已經回傳的 retrieved 排序清單來算這兩個指標，即可長期追蹤。

負向題同樣不建議透過修改 `expected_chunk_ids` 的定義（例如反過來填入「不該命中的既有正解 id」）來讓 `_score()` 跑出非零數字：這麼做雖然技術上可行且不需更動 `run_eval.py`，但會讓 Recall/Precision 的意義從「系統表現好壞」反轉成「是否複現特定 bug」，且僅適用於已有明確既有正解可對照的題目（如 `neg_dir_*`、`neg_irr_02`、`neg_neg_01/03`），對「幻覺實體」這類命中內容本身就是隨機泛用三元組的題目並不適用，容易造成報告數字被誤讀。目前第 4.2 節的「正確清空率」已是在不更動 `queries.json` 定義、也不更動 `run_eval.py` 的前提下，最貼近本任務負向題設計邏輯的量化方式。

給非技術讀者的說明：

> 「Precision 0.22 不代表系統錯了八成。這個評測集裡，大多數問題只有一個正確答案，但系統固定回傳 5 筆候選讓後續 LLM 組篩選——即使系統把唯一正解排在第一名，Precision 算出來也只有 1/5=0.20。這是評分方式的天花板，不是系統的天花板。要看系統真正的表現，請看 Recall@5（有沒有把正解找出來），Precision 在這裡僅供參考。」

## 7. 總結與建議

- **正向題**（20 題，已由外部非 degraded 執行重複驗證兩次）：graph Recall@5=0.95，vector Recall@5=0.40，整體 0.68。
- **負向題**（20 題）：Recall/Precision/F1 在數學上恆為 0，不具判讀意義；真正的證據是逐題 retrieved 檢視——17 題可判定「該清空」的題目裡，只有 1 題（5.9%）真的清空。
- 6 類失敗模式現況：

| 類別 | 判定 |
|---|---|
| 關係方向錯誤 | 3/3 確認真實存在，架構性問題 |
| 無關 relation | 1/3 確認（`neg_irr_02`），2 題無法定論；與 `Preprocessing - B.md` A2 記錄的資料缺口互為印證 |
| 否定語境 | 2/3 確認，1 題部分證據；已有架構層佐證（`polarity` 從未被檢索邏輯讀取） |
| 跳數用盡 | 2/3 確認（機制正確運作，屬正面發現），1 題目前資料規模下不可重現 |
| 實體抽取錯誤／幻覺實體 | 1/8 清空；其餘 7 題揭露的是「泛用詞彙污染」而非典型幻覺，被判斷為比原始假設更貼近真實使用情境的風險 |

**給 9/3 展示的一句話結論**：這個系統目前分不清「用戶問的東西真的不存在」和「用戶的問句剛好夾帶足夠多的泛用糖尿病詞彙」——後者在真實對話中發生的機率遠高於前者，這才是最值得優先處理的缺口，而不是字面上的「幻覺實體」。

**後續建議**（不在本任務範圍內動手，留給對應模組負責人）：`graph.py` 的 label 比對需要加入方向感知與更嚴格的最小匹配長度／權重機制；`gate_in`／`routing` 需要有地方真正消費 `context_modifiers.polarity`；`is_retrievable()` 可檢索性關卡的保守程度需要與 Boundary A（Risk table justification）協調，評估是否有更精細的方式在阻擋高風險未複核事實的同時，不連帶擋掉同一來源裡可獨立驗證的次一級事實（見第 8.3 節 A2）。

## 8. 附錄

### 8.1 執行環境與資料來源

- 本分析環境：`.venv`，Python 3.10.11，`GEMINI_API_KEY` 未設定（`echo $env:GEMINI_API_KEY` 結果為空）。
- graph 端數字（不需要網路）：本環境直接執行可重現，包含第 4.4 節 `graph_path_status` 檢查。
- vector 端相關數字（正向題 v01–v10 基準、以及 `neg_ent_02`／`neg_ent_04`／`neg_hal_01`／`neg_hal_02`／`neg_hal_03` 這 5 題的檢索結果）：本環境因缺少 `GEMINI_API_KEY` 無法重現，改採信本任務負責人在自己終端機（已設定 `GEMINI_API_KEY`）執行 `python eval/run_eval.py` 及對應 `retrieved` 清單檢查、重複執行兩次結果一致的資料。第 3 節已說明本環境 degraded 結果偏高（g01–g10 recall=1.00）的機制原因（`truncate_balanced` 在 vector 缺席時把名額全讓給 graph），此處不再重複，僅確認：外部資料與本環境結果交叉比對後判定為可信。

### 8.2 驗收指令與結果
pytest
================================================================================ test session starts =================================================================================
platform win32 -- Python 3.10.11, pytest-9.1.1, pluggy-1.6.0
collected 54 items
tests\test_build_index.py .. [ 3%]
tests\test_contract.py ssssss [ 14%]
tests\test_end_to_end.py .... [ 22%]
tests\test_fusion.py ...... [ 33%]
tests\test_gate_in.py ssss [ 40%]
tests\test_gate_out.py ....... [ 53%]
tests\test_graph.py .... [ 61%]
tests\test_loaders.py ..... [ 70%]
tests\test_risk.py ............. [ 94%]
tests\test_vector.py ... [100%]
=========================================================================== 44 passed, 10 skipped in 2.24s ===========================================================================
（10 個 skip 為需要網路/GEMINI_API_KEY 或實驗室 monorepo 外部參考檔案的測試，非失敗）

python eval/run_eval.py
本環境（degraded）：graph n=25 Recall@5=0.40 Precision=0.18 F1=0.23
vector n=15 全數 excluded（無網路）
外部非 degraded 環境（本任務負責人終端機，兩次結果一致）：
graph n=25 Recall@5=0.38 Precision=0.14 F1=0.20
vector n=15 Recall@5=0.27 Precision=0.05 F1=0.09
ALL n=40 Recall@5=0.34 Precision=0.11 F1=0.16


### 8.3 已知但本次任務範圍外的旁支發現

- `run_eval.py` 的 `_request()`（第 28–48 行）對每一題都固定送同一組 `guardrail_result`（`polarity="AFFIRMATIVE"` 等），不讀 `queries.json` 的任何客製欄位——這代表否定語境類別測試的是「檢索層本身對否定文字不敏感」，而不是「gate 層級的 polarity 有沒有被正確設置後仍失守」。兩者是不同層次的限制。
- `tfda-risk-019_sec3_04`（內容為斷詞器 URL 切分 bug 產生的「訊息緣由：4.htm」）已在 `loaders.py` 的 `_BAD_VECTOR_CHUNK_IDS` 過濾，屬於已修復的真實案例，佐證第 5 節「切分粒度錯誤」類問題確實發生過。
- `bronze_triples_retrievable.json` 裡 `tfda_canagliflozin_dapagliflozin_aki` 事件下的 3 筆 INDUCES 三元組（ACEIs／利尿劑／NSAIDs → 急性腎損傷，對應 `tri_05/06/07`）語意上應為藥物間交互作用，但被抽取成單一藥物→病症的 INDUCES 關係。這證明 schema 抽取階段確實存在關係型別選錯的既有案例，與本次 `neg_dir_*` 測到的「檢索端不判斷方向」是兩個不同層次的問題（一個在抽取階段、一個在檢索階段），本報告予以區分，不混為一談。
- `Preprocessing - B.md` 第 12 節 A2 記錄了 graph pipeline 的可檢索性關卡（`is_retrievable()`）會擋下複方藥品展開出的高風險邊，其副作用是連「Metformin CONTRAINDICATED_FOR eGFR<30」這條正確事實也一併被擋下。本次驗證確認：現行 `bronze_triples_retrievable.json` 裡 `CONTRAINDICATED_FOR` 關係確實為 0 筆，而由同一份 ZITUVIMET 仿單展開的 `CAUTION_FOR` 三元組（eGFR 30–45，metformin/sitagliptin 各一筆）則有通過關卡——這與 `neg_irr_02` 揭露的「`CAUTION_FOR` 被誤用回答禁忌問題」屬於同一個資料缺口的兩種呈現方式：上位的禁忌事實不存在，導致下位的注意事項事實被迫承擔它扛不起的角色。第 12 節 A4 記錄的 `tfda-risk-115` 段落節點抽取粒度錯誤已於管線端修復，經逐檔案搜尋（`bronze_triples_retrievable.json`、`embedded_chunks_output.json`、`education_chunks_embedded.json`、`hpa_dm_book.json`）確認現行資料集中無殘留痕跡，僅作為「切分粒度錯誤」這一問題類別確實發生過的歷史佐證，不再是可重現的現行風險。A2、A4 皆發生於 graph pipeline 上游的建圖／抽取階段，與本報告 6 類失敗模式測的檢索階段行為屬不同層次問題，故未改寫為 `eval/queries.json` 的新測試題，僅作佐證引用。

### 8.4 終端機操作全紀錄（逐指令說明）

以下依實際執行順序列出本次評測用到的每一個指令，包含指令用途、如何解讀輸出。

**① 檢查 API key 是否已設定**

```powershell
echo $env:GEMINI_API_KEY
```

用途：vector 軌道的檢索需要呼叫 Gemini API 做 query embedding，這一步需要 `GEMINI_API_KEY` 這個環境變數。這行指令印出目前這個 PowerShell 視窗裡有沒有設定這把金鑰。

解讀：印出金鑰字串（如 `AIzaSy...`）代表已設定，vector 軌道會真的執行；若印出空白，代表 vector 軌道會進入降級（degraded）狀態，只回傳 graph 軌道結果，並在回應裡帶 `RETRIEVER_DEGRADED` 警告。

**② 驗證 queries.json 格式沒有壞掉**

```powershell
python -c "import json; d=json.load(open('eval/queries.json')); print('OK, rows =', len(d))"
```

用途：手動貼入 20 題新資料後，先確認整個 JSON 檔案仍是合法格式，避免格式錯誤（缺逗號、引號沒收好）導致後面指令直接報錯。

解讀：印出 `OK, rows = 40` 代表檔案合法且共有 40 題；若跳出 `json.decoder.JSONDecodeError`，代表某處格式壞掉，需要回頭檢查貼入的內容。

**③ 跑既有測試，確認沒有弄壞現有功能**

```powershell
pytest
```

用途：CLAUDE.md §9 規定每次改動前都要先確保測試全綠，不能破壞既有功能。

輸出：`44 passed, 10 skipped in 2.24s`（見第 8.2 節完整輸出）。

解讀：`passed` 是真的執行且通過的測試；`skipped` 是因為本環境沒有實驗室 monorepo 裡才有的外部參考檔案（`02_MS2_demo/contract/examples/`）或缺少 `GEMINI_API_KEY` 而被跳過，不是測試失敗。只要沒有出現 `failed`，就代表沒有破壞任何既有功能，可以繼續往下走。

**④ 跑完整評測，拿 40 題的分數**

```powershell
python eval/run_eval.py
```

用途：對 `queries.json` 裡全部 40 題（20 正向 + 20 負向）呼叫檢索工具，計算每一題的 Recall/Precision/F1，並依 track（graph/vector/全部）算出巨集平均。

解讀：每一行是一題的分數；最後三行是分組平均。這份輸出本身把正向題跟負向題混在同一個 graph/vector/全部分組裡，不能直接拿來當「正向題基準」或「負向題基準」使用，必須自己依 `query_id` 開頭（`g`/`v` vs `neg_`）手動拆開重算（見報告第 3、4 節）。

**⑤ 印出負向題實際撈回的證據清單**

```powershell
python -c "import sys; sys.path.insert(0,'eval'); from run_eval import run; rows=run(); [print(r['query_id'], r['track'], '->', r['retrieved']) for r in rows if r['query_id'].startswith('neg_')]"
```

用途：`run_eval.py` 內建的 `report()` 函式只印分數，不印實際撈回的 chunk id 清單。但因為負向題的 Recall/Precision/F1 在數學上恆為 0（見報告 4.1 節），分數本身看不出「系統是不是真的清空」。這行指令直接呼叫 `run()` 函式（分數計算之前的原始資料），把每題實際撈回的清單印出來，才能判斷是「正確清空」還是「意外命中」。

解讀：`-> []` 代表這題系統真的什麼都沒撈到（20 題裡只有 `neg_hal_02` 是這樣）；`-> [id1, id2, ...]` 代表撈到了東西，要進一步比對這些 id 是不是跟某個正向題的標準答案一樣（命中既有真實證據）。

**⑥ 針對「跳數用盡」3 題，單獨檢查圖遍歷狀態**

```powershell
python -c "import sys; sys.path.insert(0,'eval'); from run_eval import _request; import json; from rag_retrieval import EvidenceRetrievalTool; queries=json.load(open('eval/queries.json', encoding='utf-8')); tool=EvidenceRetrievalTool(); [print(q['query_id'], '-> graph_path_status=', getattr(tool.retrieve(_request(q)), 'graph_path_status', 'N/A'), 'warnings=', [w.code for w in tool.retrieve(_request(q)).warnings]) for q in queries if q['query_id'].startswith('neg_hop')]"
```

用途：「跳數用盡」類別要驗證的是 `response.graph_path_status` 這個欄位有沒有正確標記 `PARTIAL`，但 `run_eval.py` 完全不讀取這個欄位。這行指令繞過 `run_eval.py`，直接呼叫 `EvidenceRetrievalTool().retrieve()`，單獨印出這 3 題的 `graph_path_status` 跟 `warnings`。

解讀：`graph_path_status=PARTIAL` 且 `warnings` 含 `GRAPH_HOP_LIMIT_REACHED`，代表系統正確偵測到跳數用完、誠實標記結果不完整——這是正面的系統行為；`graph_path_status=COMPLETE` 代表這題實際上沒有觸發跳數截斷，不算複現這個失敗模式。