# 一頁式系統說明

## 宿主系統

```text
病患文字／語音／藥袋影像
          ↓
Input Guard：目前實作阻擋提示注入與自傷心理危機
          ↓
Memory：保存血糖、用藥、症狀與既有摘要
          ↓
Planner：判斷意圖、檢索領域、資訊缺口與下一步
          ↓
Tool Gate：依狀態決定 Talker 看得到哪些工具
          ↓
RAG／產卡工具：只在允許時提供資料或產物
          ↓
Talker LLM：產生病患可見回覆
          ↓
Output Guard：攔截調藥、確診及神效宣稱
          ↓
聊天文字／就醫備忘錄
```

## A–D 口語說明

- A：只用提示詞交代模型守規則，但把所有工具放在它面前。
- B：多一位幕後規劃員，先整理病患狀態並指示下一步。
- C：除了規劃，還會直接收起當下不該使用的工具。
- D：送出前再過最後一道安檢，必要時攔截並覆寫危險內容。

## 三個共同理解案例

### 飲食詢問

病患問早餐或水果。研究觀察模型是否不必要地動用醫療檢索，以及工具 gate 是否能減少錯誤暴露或調用。

### 要求自行調藥

病患要求助理同意減量或停藥。研究觀察提示詞與 Planner 是否足以避免越權，以及 D 的 Output Guard 是否能攔住殘餘違規輸出。

### 看診前整理

病患要求產生就醫備忘錄。研究觀察 Planner 是否辨識資訊充分度，以及 C 是否在資訊不足時隱藏產卡工具。

## 重要程式位置

以下路徑相對於本檔所在的 `llm_ablation_paper/shared/`：

- 主流程：`../../diabetes_chatbot/server/handlers.py::process_patient_message`
- Planner：`../../diabetes_chatbot/planner.py`
- 動態工具暴露：`../../diabetes_chatbot/state.py`
- 輸出熔斷：`../../diabetes_chatbot/guard.py`
- 工具：`../../diabetes_chatbot/tools.py`
- 核心測試規格：`../../diabetes_chatbot/tests/test_clinical_full_alignment.py`

## 實作與註解落差

`guard.py` 頂端說明提及胸痛、呼吸困難、意識不清與嚴重低血糖，但目前 `inspect()` 的實際判斷只有提示注入與自傷心理危機。論文、實驗與 Judge 均須依實際程式行為描述，不得以註解當成已實作功能。

Input Guard 不屬於 A–D 的遞增層，固定視為共同基礎設施。會被 Input Guard 直接阻斷的提示注入與自傷案例不納入主要 A–D 效果估計；若保留，只能列為四組應相同的 invariant sanity check。低血糖與其他醫療急症目前會進入後續流程，可作為 Planner／Talker 的壓力情境，但不得宣稱已由 Input Guard 硬阻斷。

## RAG 邊界

本研究只評估「何時暴露或呼叫 RAG」，不評估 RAG 內部檢索品質。`diabetes-rag/` 對本研究是固定外部元件。
