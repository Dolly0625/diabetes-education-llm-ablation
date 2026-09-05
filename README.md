# 糖尿病衛教助理（Diabetes Chatbot：日常陪伴與就醫備忘錄）

> 結合大型語言模型臨床規劃、雙軌實證 RAG 檢索、台語語音辨識與藥袋影像解析的糖尿病智慧健康助理。
> 平時陪伴長輩日常對話與記錄生理數據，看診前彙整為標準就醫備忘錄（附 QR Code），協助醫護於 30 秒內掌握最新病況與用藥變化。

---

## 核心功能特色

### 1. 日常衛教陪伴（雙軌臨床大腦）
* 臨床規劃與護理師回覆雙軌解耦：先由規劃器判定病患意圖（飲食、用藥、血糖、看診需求），再以溫和護理師語氣給予回應。
* 衛教問答遵循常識：日常飲食與生活關懷直接回應，單輪僅追問一個問題，不無謂觸發後端檢索。
* 嚴謹檢索機制：成因機制、藥物安全、臨床數值標準強制檢索官方指引，資料來源小字註記於備忘錄中，不干擾聊天閱讀體驗。

### 2. 雙軌 RAG 實證檢索（整合 diabetes-rag）
* 雲端向量檢索：結合國健署糖尿病衛教手冊（172 筆）與 TFDA 藥品仿單（85 筆），精準對齊衛福部指引。
* 知識圖譜關聯：建立 TFDA 藥品三元組關聯，飲食查詢自動過濾無關之藥理雜訊。
* 跨領域防污染：生活飲食諮詢時自源頭隱藏檢索工具，防範跨領域資訊混淆。

### 3. 雙向安全守護（輸入阻斷與輸出熔斷）
* 輸入安全閘：及時攔截提示詞注入（Prompt Injection）與自傷危險意圖。
* 輸出熔斷器：任何涉及調藥、確診、斷言根治之內容即時覆寫為安全警示話術；擅自停藥意圖強制啟動衛教提醒。
* 認知負擔控管：單輪對話最多提出一個問句，降低高齡長輩認知過載。
* 零符號規範：輸出全面過濾表情符號與特殊圖標，保持專業醫療視覺風格。

### 4. 多模態感知能力（藥袋與台語語音）
* 藥袋 QR 碼優先、OCR 文字辨識備援：拍照上傳自動擷取藥品資訊，影像於記憶體解析完成即銷毀不留存。
* 台語語音辨識：整合在地化語音辨識模型，支援長輩母語輸入。

### 5. 就醫備忘錄（Pre-visit Memo）
* 標準交班單格式：包含本次就醫主訴、用藥現況、血糖監測趨勢、待確認方向（警示標註）、病患口語陳述、指引出處小字與醫師勾選欄位。
* LINE Flex 訊息卡片與 15 分鐘動態 QR Code：具備時效保護機制，調閱動作留存於審計日誌。

### 6. 長期病歷記憶（Longitudinal Memory）
* 個人化縱向檔案：跨輪次持續累積用藥紀錄、血糖數值、症狀變化與低血糖史。
* 回診變化比對：備忘錄自動加註「與上次比對」，突顯數值變化趨勢。

---

## 系統架構

```text
[病患文字 / 台語語音 / 藥袋照片]
           │
           ▼
   【感知層：ASR / QR-OCR】
           │
           ▼
 【輸入警衛：提示注入 / 自傷阻斷】
           │
           ▼
 【臨床規劃：槽位收集 / 意圖判定 / 檢索決策】
           │
           ├─► 【雙軌 RAG：向量檢索 + 知識圖譜（成因/用藥強制查詢）】
           │
           ▼
   【生成層：臨床護理師同理回覆】
           │
           ▼
 【輸出熔斷：調藥/確診覆寫 + 問句上限 + 零符號過濾】
           │
           ▼
   【LINE Flex 訊息 / 就醫備忘錄】
```

---

## 專案目錄結構

```text
diabetes-chatbot/
├── diabetes_chatbot/        # 主服務核心模組
│   ├── server/              # FastAPI 伺服器與 Webhook 處理 (app.py, handlers.py)
│   ├── vendor/              # 藥袋 QR 與 OCR 解析服務 (qr_ocr_service.py)
│   ├── planner.py           # 臨床規劃大腦（意圖識別、槽位追蹤、工具調用決策）
│   ├── state.py             # 動態工具狀態閘門（飲食隱藏、備忘錄啟動門檻）
│   ├── tools.py             # 外部工具實作（官方手冊檢索、就醫備忘錄生成）
│   ├── guard.py             # 雙向安全防護閘（注入防護、醫療風險熔斷、符號清理）
│   ├── memory.py            # 病患個人化縱向記憶體（SQLite 儲存）
│   ├── perception.py        # 多模態感知介面（語音辨識、影像特徵萃取）
│   ├── prompts.py           # 臨床角色設定與系統提示詞
│   ├── chat.py              # CLI 終端互動測試介面
│   ├── logger.py            # AMIE 臨床審計日誌
│   └── tests/               # 臨床整合與全鏈路回歸測試套件
├── diabetes-rag/            # 雙軌 RAG 知識檢索子系統
│   ├── src/rag_retrieval/   # 檢索器實作（向量、圖譜、融合校準）
│   ├── data/                # 內建衛教手冊與仿單嵌入向量
│   └── tests/               # 檢索模組專用測試
├── fixtures/                # 測試用音訊與藥袋影像素材
├── docs/                    # 檢索觸發策略與架構規範說明
├── requirements.txt         # 專案 Python 相依套件清單
└── .env.example             # 環境變數設定範例
```

---

## 安裝與快速啟動

### 步驟一：環境建置

建議使用 Python 3.11 環境：

```bash
git clone <本專案網址>
cd diabetes-chatbot
pip install -r requirements.txt
cp .env.example .env
```

請編輯 `.env`，填入模型 API 金鑰：
* `GEMINI_API_KEY`: Google Gemini API 金鑰（必填其一）
* `OPENCODE_API_KEY`: 或相容之 API 金鑰

### 步驟二：啟動服務

啟動本機 FastAPI 伺服器（預設連接埠 8000）：

```bash
python3 -m uvicorn diabetes_chatbot.server.app:app --host 0.0.0.0 --port 8000
```

### 步驟三：本機功能測試（Mock 模式，免 LINE 帳號）

服務內建 Mock 測試端點，便於本機直接進行功能驗證：

```bash
# 1. 健康檢查（回傳狀態 healthy）
curl http://localhost:8000/

# 2. 一般對話測試（固定 user_id 以維持長期記憶）
curl -X POST http://localhost:8000/mock/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test_patient","text":"護理師您好，我今天中午吃糙米飯配煎魚"}'

# 3. 就醫備忘錄產出測試
curl -X POST http://localhost:8000/mock/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test_patient","text":"我下週二要回診，請幫我整理就醫備忘錄"}'
```

---

## LINE 官方帳號上線串接

如需與 LINE 官方帳號對接，請依循下列程序：

1. **外網穿透**：使用 ngrok 或類似工具建立安全通道：
   ```bash
   ngrok http 8000
   ```
   複製對應之 HTTPS 網址（例如 `https://xxxx.ngrok-free.dev`）。

2. **設定環境變數**：在 `.env` 中設定 LINE 憑證並重啟服務：
   ```env
   LINE_CHANNEL_SECRET=您的頻道金鑰
   LINE_CHANNEL_ACCESS_TOKEN=您的存取權杖
   ```

3. **LINE Developers Console 設定**：
   - 進入 Messaging API 設定頁面。
   - 將 Webhook URL 設定為 `https://xxxx.ngrok-free.dev/callback`。
   - 點擊「Verify」確認驗證成功，並開啟「Use webhook」。
   - 在 LINE Official Account Manager 後台關閉「自動回應訊息」，開啟「Webhook」。

---

## 執行自動化測試

專案附帶完整臨床與系統回歸測試：

```bash
# 執行核心臨床大腦與回歸測試套件
python3 -m pytest diabetes_chatbot/tests/test_clinical_full_alignment.py -k "not live" \
  diabetes_chatbot/tests/test_planner.py \
  diabetes_chatbot/tests/test_diet_rag_filter.py \
  diabetes_chatbot/tests/test_memory_integration.py -q
```

---

## 醫療免責聲明

本系統為健康衛教諮詢與就醫資料預整理之研究原型系統，所提供之資訊均依據主管機關公開指引彙整，僅供衛教參考，絕不可取代合格醫療專業人員之正式診斷、評估與治療。藥物處方調整與醫療決策一律應由主治醫師判定。若病患自覺嚴重身體不適或突發急性症狀，應立即前往醫療院所急診就醫。

