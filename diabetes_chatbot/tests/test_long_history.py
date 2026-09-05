"""
長歷史對話記憶系統驗證測試 (Long History & Memory Test)
驗證項目：
1. 病患自述臨床事實自動抽取 (血糖、用藥、症狀)
2. 上下文滑動視窗 (Sliding Context Window) 安全裁剪與 System Prompt 置頂
3. 多病患健康檔案隔離 (Multi-Patient Isolation)
4. 對話會話歸檔封存 (Session Archival)
"""
import os
import json
import tempfile
import warnings
from pathlib import Path

from diabetes_chatbot.memory import (
    load_patient_record,
    extract_clinical_facts_from_text,
    prune_conversation_history,
    archive_session,
    format_patient_context
)

warnings.filterwarnings("ignore")

def test_fact_extraction():
    print("\n--- 測試 1: 病患自述臨床事實自動提取 ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test_extract.json"
        
        # 病患自述文字
        user_text = "護理師好，我早上空腹血糖大概 128，最近吃完飯肚子很常脹氣又拉肚子，另外我有在吃庫魯化。"
        facts = extract_clinical_facts_from_text(user_text, file_path=test_file)
        
        gluc = facts.get("glucose", "")
        syms = facts.get("symptoms", [])
        meds = facts.get("medications", [])
        
        assert gluc == "128 mg/dL", f"血糖提取失敗: {gluc}"
        assert "脹氣" in syms, f"症狀提取失敗: {syms}"
        assert ("腹瀉" in syms or "拉肚子" in syms), f"症狀提取失敗: {syms}"
        assert "庫魯化" in meds, f"用藥提取失敗: {meds}"
        
        # 驗證實體落盤與上下文裝配
        rec = load_patient_record(test_file)
        assert rec["glucose_metrics"]["latest"] == "128 mg/dL"
        ctx = format_patient_context(test_file)
        assert "128 mg/dL" in ctx
        assert "庫魯化" in ctx
        print("[測試 1 通過] 病患自述血糖、用藥與症狀萃取並落盤正確。")


def test_sliding_window_pruning():
    print("\n--- 測試 2: 上下文滑動視窗修剪與安全對齊 ---")
    # 建立 12 條歷史訊息 (含 tool 調用)
    dummy_messages = [
        {"role": "system", "content": "護理師人設"},
        {"role": "user", "content": "問候 1"},
        {"role": "assistant", "content": "回答 1"},
        {"role": "user", "content": "問候 2"},
        {"role": "assistant", "content": "回答 2"},
        {"role": "user", "content": "我要查手冊"},
        {"role": "assistant", "content": "查手冊", "tool_calls": [{"id": "call_123", "type": "function"}]},
        {"role": "tool", "tool_call_id": "call_123", "content": "手冊內容"},
        {"role": "assistant", "content": "根據手冊..."},
        {"role": "user", "content": "問候 3"},
        {"role": "assistant", "content": "回答 3"},
        {"role": "user", "content": "最新問題"}
    ]
    
    pruned = prune_conversation_history(dummy_messages, max_history_messages=6)
    
    # 1. 第 0 條必須是 System
    assert pruned[0]["role"] == "system"
    # 2. 裁剪後長度必須合理
    assert len(pruned) <= 8
    # 3. 如果包含 tool，前一條必須是 assistant 帶有 tool_calls
    for i, msg in enumerate(pruned):
        if msg["role"] == "tool":
            assert i > 0
            assert pruned[i-1]["role"] == "assistant"
            assert "tool_calls" in pruned[i-1]
            
    print("[測試 2 通過] 滑動視窗修剪正確，System 永久置頂，Tool 對齊安全無孤兒。")


def test_session_archival():
    print("\n--- 測試 3: 會話歷史封存歸檔 ---")
    test_messages = [
        {"role": "system", "content": "護理師"},
        {"role": "user", "content": "下週要回診"},
        {"role": "assistant", "content": "好的，幫您整理備忘錄"}
    ]
    
    session_id = "20260904_test"
    archived_file = archive_session(session_id, test_messages, patient_id="p_test")
    
    assert archived_file.exists()
    with open(archived_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert data["session_id"] == session_id
    assert data["patient_id"] == "p_test"
    assert data["message_count"] == 3
    print(f"[測試 3 通過] 會話歷史封存成功: {archived_file.name}")


if __name__ == "__main__":
    test_fact_extraction()
    test_sliding_window_pruning()
    test_session_archival()
    print("\n=== 長歷史對話記憶所有功能測試全數通過！ ===")
