"""
FastAPI LINE Webhook 伺服器主入口
支援：
1. 本地免憑證開發模擬模式 (Mock Mode)
2. 正式 LINE Messaging API Webhook 簽章驗證與自動分流
"""
import json
import os
import tempfile
import base64
import hashlib
import hmac
import traceback
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from diabetes_chatbot.server.handlers import process_patient_message

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env")

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

app = FastAPI(
    title="TFDA AI 糖尿病專科衛教助理 - LINE Webhook 服務",
    version="2.0.0",
    description="結合 臨床衛教大腦、聯發科 Breeze-ASR-26 台語語音與 LINE Flex 就醫備忘錄之官方 Webhook 伺服器"
)

# 訊息去重集合 (避免網路抖動或客戶端重試造成重複處理)
PROCESSED_MESSAGE_IDS = set()

# 判斷是否具備真實 LINE 密鑰
HAS_LINE_CREDENTIALS = bool(LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN)

import certifi
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

if HAS_LINE_CREDENTIALS:
    from linebot.v3 import WebhookHandler
    from linebot.v3.exceptions import InvalidSignatureError
    from linebot.v3.messaging import (
        ApiClient,
        MessagingApi,
        MessagingApiBlob,
        Configuration,
        FlexContainer,
        FlexMessage,
        PushMessageRequest,
        ReplyMessageRequest,
        TextMessage,
    )
    from linebot.v3.webhooks import (
        AudioMessageContent,
        ImageMessageContent,
        MessageEvent,
        TextMessageContent,
    )

    configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
    configuration.ssl_ca_cert = certifi.where()
    handler = WebhookHandler(LINE_CHANNEL_SECRET)
else:
    handler = None


@app.get("/")
def health_check():
    """服務健康檢查端點"""
    return {
        "status": "healthy",
        "service": "TFDA Diabetes Agent V2",
        "mode": "production (LINE Official)" if HAS_LINE_CREDENTIALS else "local_mock_mode (無需 LINE 憑證即可本地測試)",
        "features": [
            "臨床衛教大腦 Talker/Planner 雙軌",
            "MediaTek Breeze-ASR-26 在地台語語音辨識",
            "健保藥袋 QR/OCR 多模態解析",
            "LINE Flex Message 大字體就醫備忘錄",
            "診間快速掃描 QR Code"
        ]
    }


@app.post("/mock/chat")
async def mock_chat_endpoint(req: Request):
    """
    【本地模擬端點】：供開發者在未申請 LINE 帳號前，直接用 JSON 測試文字、語音或圖片！
    請求範例：
    {
        "user_id": "grandpa_test",
        "text": "護理師早安，我今天早餐吃蛋餅",
        "audio_path": "fixtures/audio/test_patient.wav",
        "image_path": "fixtures/images/medication_bag_front.jpg"
    }
    """
    body = await req.json()
    uid = body.get("user_id", "mock_default_user")
    text_input = body.get("text")
    audio_path = body.get("audio_path")
    image_path = body.get("image_path")

    result = process_patient_message(
        user_id=uid,
        text_input=text_input,
        audio_path=audio_path,
        image_path=image_path
    )
    return JSONResponse(content=result)


@app.post("/callback")
async def line_webhook_callback(request: Request, background_tasks: BackgroundTasks):
    """
    【正式 LINE Webhook 端點】：接收 LINE 官方伺服器轉發之事件
    立即回傳 200 OK，避免 LINE 伺服器因等待大模型生成超時而發起重複重試（Retry Storm）
    """
    if not HAS_LINE_CREDENTIALS:
        return JSONResponse(
            status_code=200,
            content={
                "message": "目前伺服器處於【本機開發模擬模式】。如需正式連線 LINE，請在 .env 設定 LINE_CHANNEL_SECRET 與 LINE_CHANNEL_ACCESS_TOKEN；或直接使用 POST /mock/chat 進行本地全功能測試。"
            }
        )

    signature = request.headers.get("X-Line-Signature", "")
    body = (await request.body()).decode("utf-8")

    # 快速驗證簽章
    hash_val = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256
    ).digest()
    calc_signature = base64.b64encode(hash_val).decode("utf-8")
    if not hmac.compare_digest(signature, calc_signature):
        raise HTTPException(status_code=400, detail="Invalid LINE Signature")

    # 簽章通過，將耗時的模型推論與回覆排入背景任務，主線程立即以 200 OK 響應 LINE 伺服器
    background_tasks.add_task(handler.handle, body, signature)
    return Response(content="OK")


# 若有真實憑證，註冊 LINE 事件監聽器
if HAS_LINE_CREDENTIALS:
    @handler.add(MessageEvent, message=TextMessageContent)
    def handle_text_message(event):
        try:
            msg_id = event.message.id
            if msg_id in PROCESSED_MESSAGE_IDS:
                print(f"[LINE Webhook 去重] 忽略重複訊息 ID: {msg_id}")
                return
            PROCESSED_MESSAGE_IDS.add(msg_id)
            if len(PROCESSED_MESSAGE_IDS) > 2000:
                PROCESSED_MESSAGE_IDS.clear()

            user_id = event.source.user_id
            user_text = event.message.text
            print(f"[LINE Webhook] 收到使用者 {user_id} 文字訊息: {user_text}")
            res = process_patient_message(user_id=user_id, text_input=user_text)

            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                if res.get("reply_type") == "flex" and res.get("flex_bubble"):
                    bubble_container = FlexContainer.from_json(json.dumps(res["flex_bubble"]))
                    messages_to_send = [FlexMessage(alt_text="新陳代謝科 門診預問診就醫備忘錄", contents=bubble_container)]
                    if res.get("audit_log"):
                        messages_to_send.append(TextMessage(text=res["audit_log"]))
                else:
                    messages_to_send = [TextMessage(text=res.get("reply_text", "收到您的訊息"))]

                # 優先使用 reply_message，若逾期則自動無縫降級為 push_message
                try:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=messages_to_send
                        )
                    )
                    print(f"[LINE Webhook] 成功以 reply_message 回覆使用者 {user_id}")
                except Exception as reply_err:
                    print(f"[LINE Webhook 提示] reply_token 已失效 ({reply_err})，立即改用 push_message 送達...")
                    line_bot_api.push_message(
                        PushMessageRequest(
                            to=user_id,
                            messages=messages_to_send
                        )
                    )
                    print(f"[LINE Webhook] 成功以 push_message 推送訊息給使用者 {user_id}")
        except Exception as e:
            print(f"[LINE Webhook 錯誤] 處理文字訊息失敗: {e}")
            traceback.print_exc()

    @handler.add(MessageEvent, message=AudioMessageContent)
    def handle_audio_message(event):
        try:
            msg_id = event.message.id
            if msg_id in PROCESSED_MESSAGE_IDS:
                print(f"[LINE Webhook 去重] 忽略重複語音訊息 ID: {msg_id}")
                return
            PROCESSED_MESSAGE_IDS.add(msg_id)

            user_id = event.source.user_id
            print(f"[LINE Webhook] 收到使用者 {user_id} 語音訊息: {msg_id}")

            with ApiClient(configuration) as api_client:
                blob_api = MessagingApiBlob(api_client)
                content_bytes = blob_api.get_message_content(message_id=msg_id)
                
                with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as tmp:
                    tmp.write(content_bytes)
                    tmp_path = Path(tmp.name)

                try:
                    res = process_patient_message(user_id=user_id, audio_path=tmp_path)
                finally:
                    if tmp_path.exists():
                        tmp_path.unlink()

                line_bot_api = MessagingApi(api_client)
                if res.get("reply_type") == "flex" and res.get("flex_bubble"):
                    bubble_container = FlexContainer.from_json(json.dumps(res["flex_bubble"]))
                    messages_to_send = [FlexMessage(alt_text="新陳代謝科 門診預問診就醫備忘錄", contents=bubble_container)]
                    if res.get("audit_log"):
                        messages_to_send.append(TextMessage(text=res["audit_log"]))
                else:
                    messages_to_send = [TextMessage(text=res.get("reply_text", "語音已接收完成"))]

                try:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=messages_to_send
                        )
                    )
                    print(f"[LINE Webhook] 成功以 reply_message 回覆語音給使用者 {user_id}")
                except Exception as reply_err:
                    print(f"[LINE Webhook 提示] reply_token 已失效 ({reply_err})，改用 push_message 推送...")
                    line_bot_api.push_message(
                        PushMessageRequest(
                            to=user_id,
                            messages=messages_to_send
                        )
                    )
                    print(f"[LINE Webhook] 成功以 push_message 推送語音回覆給使用者 {user_id}")
        except Exception as e:
            print(f"[LINE Webhook 錯誤] 處理語音訊息失敗: {e}")
            traceback.print_exc()

    @handler.add(MessageEvent, message=ImageMessageContent)
    def handle_image_message(event):
        try:
            msg_id = event.message.id
            if msg_id in PROCESSED_MESSAGE_IDS:
                print(f"[LINE Webhook 去重] 忽略重複圖片訊息 ID: {msg_id}")
                return
            PROCESSED_MESSAGE_IDS.add(msg_id)

            user_id = event.source.user_id
            print(f"[LINE Webhook] 收到使用者 {user_id} 圖片訊息: {msg_id}")

            with ApiClient(configuration) as api_client:
                blob_api = MessagingApiBlob(api_client)
                content_bytes = blob_api.get_message_content(message_id=msg_id)
                
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    tmp.write(content_bytes)
                    tmp_path = Path(tmp.name)

                try:
                    res = process_patient_message(user_id=user_id, image_path=tmp_path)
                finally:
                    if tmp_path.exists():
                        tmp_path.unlink()

                line_bot_api = MessagingApi(api_client)
                if res.get("reply_type") == "flex" and res.get("flex_bubble"):
                    bubble_container = FlexContainer.from_json(json.dumps(res["flex_bubble"]))
                    messages_to_send = [FlexMessage(alt_text="新陳代謝科 門診預問診就醫備忘錄", contents=bubble_container)]
                    if res.get("audit_log"):
                        messages_to_send.append(TextMessage(text=res["audit_log"]))
                else:
                    messages_to_send = [TextMessage(text=res.get("reply_text", "圖片已接收完成"))]

                try:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=messages_to_send
                        )
                    )
                    print(f"[LINE Webhook] 成功以 reply_message 回覆圖片給使用者 {user_id}")
                except Exception as reply_err:
                    print(f"[LINE Webhook 提示] reply_token 已失效 ({reply_err})，改用 push_message 推送...")
                    line_bot_api.push_message(
                        PushMessageRequest(
                            to=user_id,
                            messages=messages_to_send
                        )
                    )
                    print(f"[LINE Webhook] 成功以 push_message 推送圖片回覆給使用者 {user_id}")
        except Exception as e:
            print(f"[LINE Webhook 錯誤] 處理圖片訊息失敗: {e}")
            traceback.print_exc()
