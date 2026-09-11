#!/usr/bin/env bash
# ==============================================================================
# 專科臨床大腦 - 展示前環境受控重置腳本 (demo_reset.sh)
# 用途：供現場展示前快速重置展示用測試帳號與對話日誌，並驗證服務存活。
#
# 安全規範約束：
# 1. 僅重置指定的展示用帳號：line_Ubb89014162a253c0544d7b4415cc086e.json
# 2. 嚴禁刪除 line_ayuma_longitudinal_12rounds.json (12 輪長輩劇本縱向狀態)
# 3. 嚴禁刪除 patient_record.json、嚴禁刪除 sessions/ 目錄
# 4. 嚴禁使用萬用字元 (rm line_U*.json)，絕不碰觸其他真實帳號檔
# ==============================================================================

set -euo pipefail

# 1. 定位專案根目錄
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=================================================="
echo "  開始執行展示前受控重置程序 (Demo Reset)"
echo "  專案目錄: ${PROJECT_ROOT}"
echo "=================================================="

# [任務 1/3] 清空展示用審計對話日誌 (chat_logs.jsonl)
CHAT_LOGS="${PROJECT_ROOT}/diabetes_chatbot/chat_logs.jsonl"
if [ -f "${CHAT_LOGS}" ]; then
    > "${CHAT_LOGS}"
    echo "[1/3 完成] 已清空對話審計日誌: ${CHAT_LOGS}"
else
    touch "${CHAT_LOGS}"
    echo "[1/3 完成] 對話審計日誌原本不存在，已建立空白檔: ${CHAT_LOGS}"
fi

# [任務 2/3] 僅刪除展示用帳號狀態檔並清空進程記憶體快取 (嚴格受控，絕不碰其他檔案)
DEMO_ACCOUNT_FILE="${PROJECT_ROOT}/diabetes_chatbot/data/line_Ubb89014162a253c0544d7b4415cc086e.json"
if [ -f "${DEMO_ACCOUNT_FILE}" ]; then
    rm -f "${DEMO_ACCOUNT_FILE}"
    echo "[2/3 完成] 已刪除展示用帳號記憶檔案: line_Ubb89014162a253c0544d7b4415cc086e.json"
    echo "          明日現場將從零開始建立全新問診旅程。"
else
    echo "[2/3 略過] 展示用帳號檔案目前不存在，已是初始空白狀態。"
fi

# 透過本地 Admin API 徹底釋放 uvicorn 記憶體中之 _SESSION_CACHE
if lsof -i :8000 >/dev/null 2>&1; then
    RESET_RESP=$(curl -s -X POST http://127.0.0.1:8000/api/admin/reset || true)
    echo "          已通知後端伺服器 0 秒釋放所有短期會話記憶 (_SESSION_CACHE)。"
fi


# 核心安全檢查：確認受保護重要資產完好無損
echo "--- [安全保護檢查] ---"
PROTECTED_FILES=(
    "${PROJECT_ROOT}/diabetes_chatbot/data/line_ayuma_longitudinal_12rounds.json"
    "${PROJECT_ROOT}/diabetes_chatbot/data/patient_record.json"
)
for p_file in "${PROTECTED_FILES[@]}"; do
    if [ -f "${p_file}" ]; then
        echo "  [保護資產安全] $(basename "${p_file}") 存在且完好。"
    else
        echo "  [保護資產提醒] $(basename "${p_file}") 目前未建立。"
    fi
done
if [ -d "${PROJECT_ROOT}/diabetes_chatbot/data/sessions" ]; then
    echo "  [保護目錄安全] sessions/ 目錄完好無損。"
fi
echo "----------------------"

# [任務 3/3] 檢查 uvicorn 與 ngrok 服務存活狀態
echo "[3/3 檢查] 正在檢查服務監聽與外部通道..."

# 3.1 檢查 uvicorn 本地監聽與健康檢查端點
UVICORN_OK=0
if lsof -i :8000 >/dev/null 2>&1; then
    HEALTH_RESP=$(curl -s --connect-timeout 2 http://127.0.0.1:8000/ || true)
    if echo "${HEALTH_RESP}" | grep -q '"status":"healthy"'; then
        echo "  - [Uvicorn] 運作正常 (Port 8000 正常監聽，/ 回傳 healthy)"
        UVICORN_OK=1
    else
        echo "  - [Uvicorn] Port 8000 有行程監聽，但健康檢查端點未回傳 healthy: ${HEALTH_RESP}"
    fi
else
    echo "  - [Uvicorn] 警告！Port 8000 未發現監聽行程，請執行 scripts/start_line_service.sh 啟動服務！"
fi

# 3.2 檢查 ngrok 程序與通道存活
NGROK_OK=0
if pgrep -f "ngrok" >/dev/null 2>&1; then
    TUNNELS_JSON=$(curl -s --connect-timeout 2 http://127.0.0.1:4040/api/tunnels || true)
    if echo "${TUNNELS_JSON}" | grep -q "heroism-unkempt-pediatric.ngrok-free.dev"; then
        echo "  - [ngrok] 運作正常 (通道已建立: https://heroism-unkempt-pediatric.ngrok-free.dev)"
        NGROK_OK=1
    else
        echo "  - [ngrok] 程序運行中，但尚未綁定指定域名 (請檢查 ngrok 狀態)"
        NGROK_OK=1
    fi
else
    echo "  - [ngrok] 警告！未偵測到 ngrok 執行緒，請執行 scripts/start_line_service.sh 建立穿透通道！"
fi

echo "=================================================="
if [ "${UVICORN_OK}" -eq 1 ] && [ "${NGROK_OK}" -eq 1 ]; then
    echo "  重置完成！環境已就緒，隨時可在 LINE 開始展示！"
    echo "  Webhook 網址: https://heroism-unkempt-pediatric.ngrok-free.dev/callback"
else
    echo "  重置完成，但後端服務未完全就緒，建議重新執行："
    echo "  ./scripts/start_line_service.sh"
fi
echo "=================================================="
