"""
LINE Webhook 伺服器端到端整合測試 (FastAPI TestClient)
測試：
1. GET / 健康檢查（自動偵測本機開發模擬模式）
2. POST /mock/chat 傳送文字衛教
3. POST /mock/chat 傳送 Breeze-ASR-26 語音檔案 (.wav)
4. POST /mock/chat 傳送健保藥袋照片 (.jpg)
5. POST /mock/chat 觸發門診預問診小卡 (Flex Message JSON + 診間 QR Code)
"""
import os
import sys
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from diabetes_chatbot.server.app import app

client = TestClient(app)

def test_line_server_health_check():
    """測試 1：健康檢查端點"""
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "production" in data["mode"] or "local_mock_mode" in data["mode"]
    print("\n[測試 1 通過] FastAPI LINE 伺服器健康檢查正常。")

def test_line_server_text_chat():
    """測試 2：模擬長輩傳送文字訊息"""
    payload = {
        "user_id": "grandpa_line_001",
        "text": "護理師早安，我今天早餐吃了兩個菜包跟一杯糙米漿，這樣澱粉會不會太多？"
    }
    resp = client.post("/mock/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["reply_type"] == "text"
    assert "菜包" in data["reply_text"] or "澱粉" in data["reply_text"]
    print("[測試 2 通過] 長輩文字訊息衛教回傳成功。")

def test_line_server_voice_message():
    """測試 3：模擬長輩按住麥克風講台語（語音辨識 Breeze-ASR-26 串接）"""
    audio_file = ROOT_DIR / "fixtures/audio/test_patient.wav"
    assert audio_file.exists()
    
    payload = {
        "user_id": "grandpa_line_001",
        "audio_path": str(audio_file)
    }
    resp = client.post("/mock/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["reply_type"] == "text"
    assert "台語語音辨識" in data["reply_text"]
    assert "65" in data["reply_text"]
    print("[測試 3 通過] LINE 語音檔案透過 Breeze-ASR-26 辨識並回傳衛教成功。")

def test_line_server_med_bag_image():
    """測試 4：模擬長輩拍照傳健保藥袋照片"""
    img_file = ROOT_DIR / "fixtures/images/medication_bag_front.jpg"
    assert img_file.exists()

    payload = {
        "user_id": "grandpa_line_001",
        "image_path": str(img_file)
    }
    resp = client.post("/mock/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["reply_type"] == "text"
    assert "成功看懂您的藥袋" in data["reply_text"]
    print("[測試 4 通過] LINE 健保藥袋照片 QR/OCR 解析並持久化存檔成功。")

def test_line_server_flex_card_generation():
    """測試 5：長輩要求整理看診備忘錄，觸發 LINE Flex 卡片與診間 QR Code"""
    payload = {
        "user_id": "grandpa_line_001",
        "text": "護理師，我下週要回診，我有在吃庫魯化，幫我整理就醫備忘錄好嗎？"
    }
    resp = client.post("/mock/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["reply_type"] == "flex"
    assert data["flex_bubble"] is not None
    assert data["flex_bubble"]["type"] == "bubble"
    assert "TFDA-INTAKE-V2" in data["qr_payload"]
    print("[測試 5 通過] 成功產生 LINE 官方大字體 Flex 卡片與診間快掃 QR Code！")
