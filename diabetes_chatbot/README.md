# 糖尿病衛教助理 v2（Diabetes Chatbot v2：日常陪伴與就醫備忘錄）

> 結合 LLM 臨床規劃、RAG 官方手冊檢索、台語語音與藥袋 QR 解析的糖尿病 LINE 智慧健康助理。
> 日常陪長輩聊天並記錄身體狀況，看診前整理成就醫備忘錄（附 QR Code）帶去診間，醫師 30 秒進入狀況。

---

## 核心功能特色

### 1. 日常衛教陪伴（雙軌臨床大腦）
* 臨床規劃＋護理師回話雙軌：先看懂病人在講什麼（吃／藥／糖／看診），再用護理師口氣回。
* 閒聊靠嘴：三餐、睡眠、心情靠常識回，只追問一個問題，不驚動檢索。
* 該查一定查：成因、藥物安全、數字標準強制先查官方手冊，出處印在備忘錄小字，不進聊天正文。

### 2. 雙軌 RAG 檢索（沿用 RAG 組 diabetes-rag）
* 雲端向量檢索：Google Gemini Embedding（國健署衛教專書 172 筆＋TFDA 仿單 85 筆），免裝本地模型。
* 知識圖譜：TFDA 藥品三元組，飲食查詢自動過濾藥品雜訊（如王子麵不再撈出類澱粉）。
* 飲食防污染：生活飲食物理隱藏檢索工具，從源頭隔絕跨領域誤召回。

### 3. 雙向安全守護（輸入阻斷＋輸出熔斷）
* 輸入端：提示詞注入、自傷意圖 0 延遲阻斷。
* 輸出端：調藥／確診／根治宣稱 0ms 覆寫為安全話術；擅自停藥意圖強制溫和警示。
* 問句預算：單輪最多一個問題，避免長輩認知過載。

### 4. 多模態感知（藥袋＋台語語音）
* 藥袋 QR 優先、OCR 備援：拍照自動帶入用藥，照片只讀記憶體不存檔；記不得藥名引導拍照。
* 台語語音：Breeze-ASR 辨識，講台語也通。

### 5. 就醫備忘錄（Pre-visit Memo）
* 七格交班單：主訴一句話、用藥現況、糖線三數字、待確認方向（黃底）、阿嬤原話、出處小字、醫師勾選欄。
* LINE Flex 大字卡＋15 分鐘 QR Code，閱後即焚概念，調閱寫入審計日誌。

### 6. 長期病歷記憶（Longitudinal Memory）
* 一人一檔：用藥、血糖、症狀、低血糖史跨次累積，血糖誤判血壓已設防。
* 備忘錄加印「跟上次比」，回診變化一目了然。

---

## 系統架構

```text
[病患文字 / 語音 / 藥袋照片] ──► 【感知：ASR / QR-OCR】 ──► 【輸入警衛：注入/自傷阻斷】
                                                                            │
【安全回覆 / 就醫備忘錄】 ◄── 【輸出熔斷＋問句預算】 ◄── 【護理師回話】 ◄── 【臨床規劃：槽位＋領域＋小抄】
                                                                                         │
                                                              【RAG：向量＋圖譜（飲食隱藏／成因藥物強制先查）】
```

* 感知層：台語語音辨識與藥袋影像解析。
* 規劃層：LLM 臨床規劃（超時降 rule 備援），決定查不查書、缺什麼追什麼。
* 檢索層：diabetes-rag 向量＋圖譜雙軌融合。
* 生成層：護理師口氣，2~3 句、繁體、無 Emoji。
* 安全層：輸入輸出雙向守護＋全鏈路審計日誌。

---

## 展示與操作指南

> 目前支援本機運行（LINE 憑證選填，沒有就進 mock 模式照樣全功能測試）。

### 步驟一：環境建置

```bash
git clone <本專案網址>
cd diabetes-chatbot
pip install -r requirements.txt
cp .env.example .env   # 填 GEMINI_API_KEY 或 OPENCODE_API_KEY（二選一即可）
```

### 步驟二：啟動主伺服器

```bash
# 啟動本機伺服器 (Port 8000)
python3 -m uvicorn diabetes_chatbot.server.app:app --host 0.0.0.0 --port 8000
```

### 步驟三：本地試玩（免 LINE 帳號）

```bash
# 健康檢查回 healthy 即活著
curl http://localhost:8000/

# 聊一句（user_id 固定才會記得你）
curl -X POST http://localhost:8000/mock/chat -H "Content-Type: application/json" \
  -d '{"user_id":"grandma_test","text":"護理師早，我吃麵線糊加大腸"}'

# 請它整理就醫備忘錄（回傳含 flex_bubble 與 TFDA-INTAKE-V2 開頭之 qr_payload）
curl -X POST http://localhost:8000/mock/chat -H "Content-Type: application/json" \
  -d '{"user_id":"grandma_test","text":"我下週要回診拿慢箋，幫我整理就醫備忘錄"}'
```

---

## LINE 官方帳號串接指引

1. **外網穿透**：`ngrok http 8000`，複製 HTTPS 網址。
2. **.env 填入**：`LINE_CHANNEL_SECRET`、`LINE_CHANNEL_ACCESS_TOKEN` 後重啟。
3. **LINE Developers Console**：Webhook URL 填 `https://xxxx.ngrok-free.dev/callback`，Verify 成功後開啟 Use webhook；官方帳號後台關閉自動回應、開啟 Webhook。

---

## 執行自動化測試

```bash
# 離線回歸（CI 看這條）
python3 -m pytest diabetes_chatbot/tests/test_clinical_full_alignment.py -k "not live" \
  diabetes_chatbot/tests/test_planner.py diabetes_chatbot/tests/test_diet_rag_filter.py \
  diabetes_chatbot/tests/test_memory_integration.py -q
```

---

## 專案模組分工（v2 內）

```text
v2/
├── server/        # FastAPI 主服務（app.py）＋臨床大腦（handlers.py）
├── planner.py     # 看懂病人在講什麼（LLM 主＋rule 備援）
├── state.py       # 工具動態門（飲食藏檢索／夠格開備忘錄）
├── tools.py       # 查書＋印備忘錄/Flex/QR
├── guard.py       # 輸入輸出安全閘
├── memory.py      # 病患長期病歷
├── perception.py  # 藥袋 QR/OCR＋台語語音
├── prompts.py     # 護理師人設
└── tests/         # 回歸測試
```

跨組依賴：`diabetes-rag/`（RAG 檢索本體）、`tfda_context_gate/intake/qr_ocr_service.py`（藥袋解析）、`models/`（語音模型）、`fixtures/`（測試素材）。

---

## 免責聲明 (Disclaimer)

本系統為健康衛教與看診前資料整理之原型研究展示系統，所提供資訊依據官方公開文件整理，僅供參考，絕不能取代合格醫療專業人員之診斷、諮詢與治療。用藥調整一律由醫師決定。若出現身體不適或急性症狀，請立即前往醫療院所就醫。
