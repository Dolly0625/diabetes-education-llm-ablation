"""
臨床衛教大腦 LLM-based Planner Agent 實戰測試
測試大語言模型作為 Planner Agent，在面對口語化、複雜語境時的表現：
1. 輪次 1：日常早餐閒聊（不誤判為看診）
2. 輪次 2：隱晦表達低血糖不適（自動提煉低血糖槽位）
3. 輪次 3：提及回診拿慢箋（精準指出缺乏用藥槽位）
4. 輪次 4：口述藥名並要求做小卡（精準達成充分度並產出導引）
"""
import os
import sys
import json
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
from openai import OpenAI

from diabetes_chatbot.planner import evaluate_clinical_planner_llm, SlotStatus

load_dotenv(ROOT_DIR / ".env")
api_key = os.getenv("OPENCODE_API_KEY")
base_url = os.getenv("OPENCODE_BASE_URL", "https://opencode.ai/zen/go/v1")
model = "mimo-v2.5"

client = OpenAI(api_key=api_key, base_url=base_url)

def run_llm_planner_test():
    print("=" * 65)
    print("【啟動 臨床衛教大腦 LLM-based Planner Agent 臨床語意實測】")
    print("=" * 65)
    
    test_patient_record = {
        "patient_id": "test_llm_grandpa",
        "medications": [],
        "glucose_metrics": {},
        "reported_symptoms": [],
        "hypo_history": ""
    }
    
    history = []
    
    scenarios = [
        ("第 1 輪【極其口語的早餐分享】", "護理師阿妹仔早！我透早去菜市場買了兩粒肉包配一杯米漿，安捏甘會吃太油？"),
        ("第 2 輪【隱晦表達低血糖困擾】", "我這兩天透中午吃飽飯後，到下午三點多手攏會抖、歸身軀冒冷汗，量血糖只有65捏！"),
        ("第 3 輪【口語提出要去看醫生】", "有啦我有喝甘蔗汁卡好啊。我下禮拜二要帶慢箋去大醫院給主治醫師看。"),
        ("第 4 輪【口述藥名並要求整理備忘錄】", "我早晚吃一顆大顆白色的庫魯化。護理師，幫我整理一份看診的小抄好嗎？")
    ]
    
    for title, user_text in scenarios:
        print(f"\n>>> {title}")
        print(f"[病患口述] {user_text}")
        
        history.append({"role": "user", "content": user_text})
        
        start_t = time.time()
        print("  [Planner Agent 正在雲端進行臨床推論...]", flush=True)
        assessment = evaluate_clinical_planner_llm(
            messages=history,
            patient_record=test_patient_record,
            client=client,
            model=model
        )
        duration = time.time() - start_t
        
        print(f"  [Planner 推論耗時] {duration:.2f} 秒 (引擎: {assessment.engine})")
        print(f"  [Planner 診斷] 看診模式: {assessment.is_visit_mode} | 明確求卡: {assessment.is_explicit_request} | 充分度: {assessment.can_unlock_summary_tool}")
        print(f"  [TADE 槽位狀態]:")
        print(f"    - 訴求 (visit_reason): [{assessment.slots.visit_reason_status.value}] {assessment.slots.visit_reason}")
        print(f"    - 用藥 (medications): [{assessment.slots.medications_status.value}] {assessment.slots.medications}")
        print(f"    - 血糖 (glucose_metrics): [{assessment.slots.glucose_metrics_status.value}] {assessment.slots.glucose_metrics}")
        print(f"    - 低血糖 (hypo_history): [{assessment.slots.hypo_history_status.value}] {assessment.slots.hypo_history}")
        print(f"    - 副作用 (concerns): [{assessment.slots.concerns_status.value}] {assessment.slots.concerns_or_side_effects}")
        
        if assessment.highest_priority_gap:
            print(f"  [最高優先級缺口] 【{assessment.highest_priority_gap}】")
        if assessment.talker_guidance:
            print(f"  [遞給護理師小抄] {assessment.talker_guidance}")
            
        # 模擬護理師簡短回覆，以維持對話歷史
        simulated_nurse_reply = f"已收到您的回覆，衛教處理完畢。"
        history.append({"role": "assistant", "content": simulated_nurse_reply})
        
    print("\n" + "=" * 65)
    print("【LLM-based Planner Agent 臨床語意實測完成】")
    print("=" * 65)

if __name__ == "__main__":
    run_llm_planner_test()
