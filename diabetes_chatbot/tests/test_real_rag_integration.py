"""
真正 RAG 模組 (EvidenceRetrievalTool) 整合驗證測試
測試重點：
1. 正式跨組契約對接 (RetrievalRequest -> EvidenceRetrievalTool -> RetrievalResponse)
2. 國健署衛教手冊向量檢索 + TFDA 藥品風險溝通圖譜混合檢索
3. 護理師大模型端到端調用與無卡死平滑降級驗證
"""
import os
import json
import warnings
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
warnings.filterwarnings("ignore")

from diabetes_chatbot.tools import search_handbook, TOOL_SEARCH_HANDBOOK
from diabetes_chatbot.prompts import NURSE_SYSTEM_PROMPT

def test_rag_contract_retrieval():
    print("\n--- 測試 1: 真正 RAG 雙軌混合檢索功能 ---")
    
    # 測試情境 A: TFDA 藥品風險警訊檢索
    query_drug = "SGLT2抑制劑類"
    evidence_drug = search_handbook(query_drug, user_raw_input="我想問 SGLT2 抑制劑這個藥有什麼要注意的？")
    print(f"\n[查詢 A: {query_drug}] 檢索結果摘要：")
    print(evidence_drug[:300] + "...")
    assert "官方臨床證據" in evidence_drug
    assert "SGLT2" in evidence_drug or "第二型糖尿病" in evidence_drug
    
    # 測試情境 B: 國健署糖尿病手冊日常衛教檢索
    query_edu = "常常口渴一直喝水"
    evidence_edu = search_handbook(query_edu, user_raw_input="常常覺得很渴一直喝水是糖尿病嗎？")
    print(f"\n[查詢 B: {query_edu}] 檢索結果摘要：")
    print(evidence_edu[:300] + "...")
    assert "官方" in evidence_edu
    print("\n[測試 1 通過] RAG 跨組契約混合檢索執行完全正常。")


def test_agent_end_to_end_with_real_rag():
    print("\n--- 測試 2: 護理師大模型端到端調用真正 RAG 實測 ---")
    from diabetes_chatbot.server.handlers import get_openai_client, model as active_model
    client = get_openai_client()
    
    user_q = "我最近常覺得口很乾一直喝水，這跟糖尿病有關係嗎？"
    messages = [
        {"role": "system", "content": NURSE_SYSTEM_PROMPT},
        {"role": "user", "content": user_q}
    ]
    
    print(f"病患提問：{user_q}")
    print(f"發送至 {active_model} 進行工具調用決策...")
    
    first_resp = client.chat.completions.create(
        model=active_model,
        messages=messages,
        tools=[TOOL_SEARCH_HANDBOOK],
        temperature=0.2
    )
    msg = first_resp.choices[0].message
    
    if msg.tool_calls:
        tc = msg.tool_calls[0]
        args = json.loads(tc.function.arguments)
        kw = args.get("keyword", "")
        print(f"模型成功調用 search_handbook，提煉關鍵字：【{kw}】")
        
        tool_res = search_handbook(kw, user_raw_input=user_q)
        print(f"RAG 組回傳真實證據片段：\n{tool_res[:200]}...\n")
        
        messages.append(msg)
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": tool_res
        })
        
        final_resp = client.chat.completions.create(
            model=active_model,
            messages=messages,
            temperature=0.4
        )
        reply = final_resp.choices[0].message.content.strip()
        print(f"[護理師最終回答]\n{reply}\n")
        
        # 驗證回答品質
        assert len(reply) > 20
        assert "😊" not in reply and "👍" not in reply  # 零 Emoji
        assert "糖尿病" in reply
        print("[測試 2 通過] 端到端調用真正 RAG 成功，回答專業自然無死機。")
    else:
        print("模型直接回答：", msg.content)

if __name__ == "__main__":
    test_rag_contract_retrieval()
    test_agent_end_to_end_with_real_rag()
    print("\n=== 真正 RAG 模組接駁測試全數通過！ ===")
