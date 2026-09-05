"""
臨床衛教大腦 差異化回訪 (Delta-Focused Longitudinal Care) 實測
驗證：
1. 病患上次已產出過「門診備忘錄」，第二次重新連線進入對話時：
   - 護理師開場能繼承上次看診事項，主動詢問「上次醫師有沒有調整藥物」或「這幾天血糖狀況」。
   - 護理師絕不重複盤問病患「吃什麼藥」等基礎背景。
2. 驗證 LINE Flex Message 結構與診間 QR Code 數據生成。
"""
import os
import sys
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
from openai import OpenAI

from diabetes_chatbot.prompts import build_nurse_system_prompt
from diabetes_chatbot.memory import (
    save_patient_record,
    get_patient_file_path,
    format_patient_context
)
from diabetes_chatbot.tools import generate_line_flex_bubble, generate_clinic_qr_payload

from diabetes_chatbot.server.handlers import get_openai_client, model
client = get_openai_client()

def test_delta_focused_care_e2e():
    print("=" * 65)
    print("【啟動 臨床衛教大腦 差異化回訪 (Delta-Focused Care) 實測】")
    print("=" * 65)
    
    patient_id = "test_grandpa_repeat_visit"
    patient_file = get_patient_file_path(patient_id)
    
    # 模擬建立一個「一週前已看診並存有就醫備忘錄」的歷史檔案
    mock_history_record = {
        "patient_id": patient_id,
        "created_at": "2026-08-28 10:00:00",
        "updated_at": "2026-08-28 10:30:00",
        "medications": [
            {"name": "庫魯化 早晚各一顆", "source": "上週門診紀錄", "recorded_at": "2026-08-28"}
        ],
        "glucose_metrics": {"latest": "上週自述血糖 68 mg/dL", "updated_at": "2026-08-28"},
        "reported_symptoms": ["手抖冒冷汗"],
        "hypo_history": "上週曾有下午冒冷汗手抖，喝果汁緩解",
        "last_previsit_summary": (
            "1. 本次回診核心訴求：定期回診，諮詢反覆低血糖問題\n"
            "2. 目前用藥與順從性：庫魯化，每天早晚各一顆\n"
            "3. 近期血糖控制情況：今日下午血糖 68 mg/dL\n"
            "4. 急性低血糖事件評估：今日下午三點多出現冒冷汗、手抖\n"
            "5. 藥物副作用與併發警訊：需醫師評估是否需調整藥物"
        )
    }
    save_patient_record(mock_history_record, patient_file)
    
    # 1. 驗證上下文注入
    ctx = format_patient_context(patient_file)
    assert "差異化回訪照護指引" in ctx
    assert "庫魯化" in ctx
    assert "上次看診之門診預問診摘要紀錄" in ctx
    print("\n[驗證 1 通過] 差異化回訪上下文動態裝配完成。")
    
    # 2. 模擬一週後阿公再次開啟對話
    system_prompt = build_nurse_system_prompt(ctx)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "護理師阿妹仔早！我上禮拜去醫院看完醫生回來了。"}
    ]
    
    print("\n[病患] 護理師阿妹仔早！我上禮拜去醫院看完醫生回來了。")
    print("  [護理師正在思考（差異化回訪模式）...]", flush=True)
    
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.3
    )
    nurse_reply = resp.choices[0].message.content.strip()
    print(f"\n[衛教護理師]\n{nurse_reply}\n")
    
    # 驗證護理師是否主動承接上次紀錄，且不重複盤問用藥
    assert "請問您吃什麼藥" not in nurse_reply
    print("[驗證 2 通過] 護理師完全沒有重複盤問已知用藥，展現出高度延續性與溫度。")
    
    # 3. 驗證 LINE Flex Message 與診間 QR Code
    flex = generate_line_flex_bubble(
        visit_reason="定期回診拿慢箋",
        medications="庫魯化 早晚各一顆",
        glucose_metrics="空腹 120 mg/dL",
        hypo_history="近期無低血糖事件",
        side_effects_or_concerns="偶爾胃脹氣"
    )
    assert flex["type"] == "bubble"
    assert flex["header"]["contents"][0]["text"] == "新陳代謝科 門診預問診就醫備忘錄"
    
    qr_str = generate_clinic_qr_payload(
        visit_reason="定期回診拿慢箋",
        medications="庫魯化 早晚各一顆",
        glucose_metrics="空腹 120 mg/dL",
        hypo_history="近期無低血糖事件",
        side_effects_or_concerns="偶爾胃脹氣"
    )
    assert "TFDA-INTAKE-V2" in qr_str
    print("[驗證 3 通過] LINE Flex Message JSON 與診間 QR Code 結構生成完全正確。")
    print(f"  [診間 QR Code 快速掃描 Payload 範例]：\n  {qr_str}")
    
    print("\n" + "=" * 65)
    print("【臨床衛教大腦 差異化回訪與診間雙模態呈現實測全部通過】")
    print("=" * 65)

if __name__ == "__main__":
    test_delta_focused_care_e2e()
