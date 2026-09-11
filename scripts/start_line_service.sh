#!/bin/bash
# 一鍵啟動 LINE 專用服務 (FastAPI + ngrok 固定域名)
cd /Users/dolly/Documents/code/diabetes-chatbot || exit 1

# 終止舊有占用 8000 埠的行程
lsof -ti :8000 | xargs kill -9 2>/dev/null
pkill -f ngrok 2>/dev/null

sleep 1

# 1. 啟動 uvicorn (背景常駐，支援熱重載)
nohup python3 -m uvicorn diabetes_chatbot.server.app:app --host 0.0.0.0 --port 8000 --reload --reload-dir diabetes_chatbot > /tmp/uvicorn_line.log 2>&1 &
echo "[1/2] FastAPI 伺服器已於背景啟動 (Port 8000)"

sleep 2

# 2. 啟動 ngrok (固定域名)
nohup /opt/homebrew/bin/ngrok http --domain=heroism-unkempt-pediatric.ngrok-free.dev 8000 > /tmp/ngrok_line.log 2>&1 &
echo "[2/2] ngrok 穿透已啟動: https://heroism-unkempt-pediatric.ngrok-free.dev"

sleep 2

# 3. 自檢健康狀態
STATUS=$(curl -s http://localhost:8000/ | grep -o '"status":"healthy"')
if [ -n "$STATUS" ]; then
    echo "=========================================="
    echo "  LINE 衛教服務已就緒！隨時可以開始展示！"
    echo "  Webhook 網址: https://heroism-unkempt-pediatric.ngrok-free.dev/callback"
    echo "=========================================="
else
    echo "警告：服務健康檢查未回傳 healthy，請檢查 /tmp/uvicorn_line.log"
fi
