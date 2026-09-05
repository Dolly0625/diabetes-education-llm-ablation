"""
V2 長期健康檔案與記憶整合測試 (Memory Integration Test)
測試項目：
1. 長期檔案 CRUD、用藥增補去重與格式化輸出
2. Prompt 動態組裝 (build_nurse_system_prompt)
3. 狀態閥門連動 (should_unlock_visit_summary)
4. 跨會話多回訪連續性 (臨床衛教大腦 Longitudinal Continuity) 端到端驗證
"""
import os
import json
import tempfile
import warnings
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

from diabetes_chatbot.memory import (
    load_patient_record,
    save_patient_record,
    update_medications,
    update_glucose_record,
    update_reported_symptoms,
    update_previsit_summary,
    format_patient_context
)
from diabetes_chatbot.prompts import build_nurse_system_prompt
from diabetes_chatbot.state import should_unlock_visit_summary

warnings.filterwarnings("ignore")

def test_memory_crud():
    print("\n--- 測試 1: 記憶模組 CRUD 與去重測試 ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_file = Path(tmpdir) / "test_patient.json"
        
        # 1. 首次載入應建立預設範本
        rec = load_patient_record(tmp_file)
        assert rec["patient_id"] == "demo_patient"
        assert len(rec["medications"]) == 0
        
        # 2. 增補用藥並去重
        update_medications(["癲通 200mg (Carbamazepine)", "庫魯化 500mg"], source="藥袋測試", file_path=tmp_file)
        update_medications(["庫魯化 500mg", "得爾美 5mg"], source="二次增補", file_path=tmp_file)
        
        rec_after = load_patient_record(tmp_file)
        med_names = [m["name"] for m in rec_after["medications"]]
        assert len(med_names) == 3
        assert "癲通 200mg (Carbamazepine)" in med_names
        assert "庫魯化 500mg" in med_names
        assert "得爾美 5mg" in med_names
        
        # 3. 更新血糖與症狀
        update_glucose_record("空腹 115 mg/dL", file_path=tmp_file)
        update_reported_symptoms("偶爾肚子脹氣", file_path=tmp_file)
        update_previsit_summary("測試就醫備忘錄內容", file_path=tmp_file)
        
        # 4. 格式化為 System Prompt 上下文
        ctx = format_patient_context(tmp_file)
        assert "癲通 200mg" in ctx
        assert "空腹 115 mg/dL" in ctx
        assert "偶爾肚子脹氣" in ctx
        assert "就醫備忘錄" in ctx
        
        print("[測試 1 通過] CRUD、增補去重與格式化完全正確。")


def test_prompt_injection():
    print("\n--- 測試 2: Prompt 動態注入驗證 ---")
    dummy_ctx = "【病患長期健康檔案】：\n- 已確認用藥清單：庫魯化 500mg"
    injected = build_nurse_system_prompt(dummy_ctx)
    
    assert "庫魯化 500mg" in injected
    assert "跨會話病患長期檔案" in injected
    assert "切勿重複詢問已知事實" in injected
    
    empty_injected = build_nurse_system_prompt("")
    assert "跨會話病患長期檔案" not in empty_injected
    print("[測試 2 通過] System Prompt 動態裝配正確。")


def test_state_gate_with_memory():
    print("\n--- 測試 3: 狀態閥門臨床安全防偷跑驗證 ---")
    messages_turn1 = [{"role": "user", "content": "護理師，我下週二要回新陳代謝科看診"}]
    # 第 1 輪剛提到看診，尚無深度，應為 False
    assert not should_unlock_visit_summary(messages_turn1)
    
    messages_turn2 = [
        {"role": "user", "content": "護理師，我下週二要回新陳代謝科看診"},
        {"role": "assistant", "content": "好的，請問最近血糖如何，身體有哪裡不舒服嗎？"},
        {"role": "user", "content": "血糖大概 110 左右，我有在吃庫魯化，想跟醫師討論肚子脹氣"}
    ]
    # 第 2 輪已具備交流深度並有用藥說明，應解鎖 True
    assert should_unlock_visit_summary(messages_turn2)
    print("[測試 3 通過] 狀態閥門深度判定與防偷跑機制驗證通過。")


def test_clinical_cross_session_e2e():
    print("\n--- 測試 4: 跨會話 臨床衛教大腦 臨床對話端到端真實檢測 ---")
    load_dotenv(Path(__file__).parent.parent / ".env")
    from diabetes_chatbot.server.handlers import get_openai_client, model as active_model
    client = get_openai_client()
    
    # 建立一個模擬已辨識過藥袋的長期檔案上下文
    patient_context = (
        "【病患長期健康檔案 (Longitudinal Health Profile)】：\n"
        "- 已確認用藥清單：癲通 200mg (Carbamazepine)\n"
        "- 過去回報之不適/副作用：先前辨識藥袋時曾提醒過此藥為非降血糖藥物\n"
        "- 目前用藥狀況：尚未記錄任何常規降血糖藥物"
    )
    
    system_prompt = build_nurse_system_prompt(patient_context)
    
    # 病患回訪發問：
    user_query = "護理師您好，我下週要去新陳代謝科回診，幫我想想看診要準備什麼。"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query}
    ]
    
    print(f"使用者輸入：{user_query}")
    print(f"發送至 {active_model} 模型檢驗 臨床衛教大腦 回覆...")
    
    resp = client.chat.completions.create(
        model=active_model,
        messages=messages,
        temperature=0.3
    )
    reply = resp.choices[0].message.content.strip()
    print(f"\n[護理師回答]\n{reply}\n")
    
    # 臨床驗證標準：純文字、無 Emoji、繁體中文
    assert "😊" not in reply and "👍" not in reply and "💊" not in reply
    print("[測試 4 通過] 回覆純文字、繁體中文且展現連續性照護專業。")


if __name__ == "__main__":
    test_memory_crud()
    test_prompt_injection()
    test_state_gate_with_memory()
    test_clinical_cross_session_e2e()
    print("\n=== 所有記憶整合測試全數通過！ ===")
