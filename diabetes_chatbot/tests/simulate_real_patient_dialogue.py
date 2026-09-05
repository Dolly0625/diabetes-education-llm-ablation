"""
臨床衛教大腦 臨床真實長輩對話端到端模擬測試
使用全新病患代碼（sim_patient_chen），展示：
1. 輪次 1：日常飲食閒聊，Planner 靜默，親切衛教
2. 輪次 2：低血糖自述，自動記錄數值與症狀，即時 15g 糖衛教
3. 輪次 3：表達看診意願，Planner 精準計算最高缺口（用藥），單題引導
4. 輪次 4：補齊用藥並要求整理，充分度達成，解鎖並產出門診就醫備忘錄
"""
import os
import sys
import json
import time
from pathlib import Path

# 將專案根目錄加入路徑
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
from openai import OpenAI

from diabetes_chatbot.prompts import build_nurse_system_prompt
from diabetes_chatbot.tools import search_handbook, generate_visit_summary
from diabetes_chatbot.planner import evaluate_clinical_planner
from diabetes_chatbot.guard import inspect_safety_guard
from diabetes_chatbot.state import get_active_tools
from diabetes_chatbot.memory import (
    load_patient_record,
    extract_clinical_facts_from_text,
    format_patient_context,
    get_patient_file_path,
    update_previsit_summary,
    prune_conversation_history
)

load_dotenv(ROOT_DIR / ".env")
api_key = os.getenv("OPENCODE_API_KEY")
base_url = os.getenv("OPENCODE_BASE_URL", "https://opencode.ai/zen/go/v1")
model = "mimo-v2.5"

client = OpenAI(api_key=api_key, base_url=base_url)

def run_simulation():
    patient_id = "sim_patient_chen"
    patient_file = get_patient_file_path(patient_id)
    
    # 若存在舊的測試檔案，先清除以確保全新病患狀態
    if patient_file.exists():
        patient_file.unlink()
        
    patient_context = format_patient_context(patient_file)
    system_prompt = build_nurse_system_prompt(patient_context)
    messages = [{"role": "system", "content": system_prompt}]
    
    dialogue_script = [
        ("第 1 輪【日常早餐閒聊】", "護理師早安，我今天早餐吃了兩顆菜包跟一杯糙米漿，這樣會不會吃太多澱粉？"),
        ("第 2 輪【自述低血糖症狀】", "我有時候下午三點多會突然全身冒冷汗、手抖，剛剛測血糖大概 68，我該怎麼辦？"),
        ("第 3 輪【表達回診，Planner 缺口追蹤】", "好的我喝了半杯果汁現在比較好了。我下週三打算去醫院看新陳代謝科門診。"),
        ("第 4 輪【補齊用藥並要求整理備忘錄】", "我每天早晚吃一顆庫魯化。護理師，可以幫我整理看診備忘錄嗎？")
    ]
    
    print("=" * 65)
    print(f"【開始真實臨床端到端對話模擬｜病患：{patient_id}（全新檔案）】")
    print("=" * 65)
    
    for turn_name, user_input in dialogue_script:
        print(f"\n>>> {turn_name}")
        print(f"[病患] {user_input}")
        
        # 1. 安全守護
        guard_res = inspect_safety_guard(user_input)
        if guard_res.is_blocked:
            print(f"[系統守護阻斷]\n{guard_res.blocked_message}")
            continue
            
        # 2. 客觀事實提取
        facts = extract_clinical_facts_from_text(user_input, file_path=patient_file)
        if facts.get("glucose"):
            print(f"  [系統記錄] 自述血糖：{facts['glucose']} mg/dL")
        if facts.get("symptoms"):
            print(f"  [系統記錄] 自述症狀：{', '.join(facts['symptoms'])}")
        if facts.get("medications"):
            print(f"  [系統記錄] 口述藥品：{', '.join(facts['medications'])}")
            
        messages.append({"role": "user", "content": user_input})
        
        # 3. 臨床衛教大腦 Planner 缺口評估
        planner = evaluate_clinical_planner(messages, patient_file_path=str(patient_file))
        active_tools = get_active_tools(messages, patient_file_path=str(patient_file))
        
        print(f"  [Planner 診斷] 看診模式: {planner.is_visit_mode} | 產卡充分度: {planner.can_unlock_summary_tool}")
        if planner.highest_priority_gap:
            print(f"  [Planner 缺口] 當前最高優先級缺口: 【{planner.highest_priority_gap}】")
        if planner.talker_guidance:
            print(f"  [Planner 小抄] {planner.talker_guidance[:60]}...")
            
        # 4. Talker 大模型推論
        pruned = prune_conversation_history(messages, max_history_messages=8)
        inference_ctx = list(pruned)
        if planner.talker_guidance:
            inference_ctx.append({"role": "system", "content": planner.talker_guidance})
            
        resp = client.chat.completions.create(
            model=model,
            messages=inference_ctx,
            tools=active_tools if active_tools else None,
            temperature=0.3
        )
        msg = resp.choices[0].message
        
        if msg.tool_calls:
            tool_call = msg.tool_calls[0]
            func_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            print(f"\n  [大模型決定調用工具] {func_name}")
            
            if func_name == "search_handbook":
                kw = args.get("keyword", "")
                output = search_handbook(kw, user_raw_input=user_input)
                print(f"  [工具執行] 查詢國健署手冊關鍵字：{kw}")
            elif func_name in ["generate_previsit_intake_summary", "generate_visit_summary"]:
                output = generate_visit_summary(
                    visit_reason=args.get("visit_reason", "門診定期追蹤"),
                    medications=args.get("medications", "未特別說明"),
                    glucose_metrics=args.get("glucose_metrics", "未特別說明"),
                    hypo_history=args.get("hypo_history", "近期未提及或無發生"),
                    side_effects_or_concerns=args.get("side_effects_or_concerns", "無特別異常"),
                )
                print(output)
                update_previsit_summary(output, file_path=patient_file)
            else:
                output = "未知工具"
                
            messages.append(msg)
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": output})
            
            # 第二階段輸出對病患的說明
            second_resp = client.chat.completions.create(
                model=model,
                messages=prune_conversation_history(messages, max_history_messages=8),
                temperature=0.4
            )
            reply = second_resp.choices[0].message.content.strip()
            print(f"\n[衛教護理師]\n{reply}")
            messages.append({"role": "assistant", "content": reply})
        else:
            reply = msg.content.strip()
            print(f"\n[衛教護理師]\n{reply}")
            messages.append({"role": "assistant", "content": reply})
            
        time.sleep(1)
        
    print("\n" + "=" * 65)
    print("【端到端對話模擬完成】")
    print("=" * 65)

if __name__ == "__main__":
    run_simulation()
