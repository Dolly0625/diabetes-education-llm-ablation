import json
import os
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

# 自動將專案根目錄注入 sys.path，讓使用者直接執行腳本時無需手動指定 PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import threading
from dotenv import load_dotenv
from openai import OpenAI

from diabetes_chatbot.prompts import NURSE_SYSTEM_PROMPT, build_nurse_system_prompt
from diabetes_chatbot.tools import search_handbook, generate_visit_summary
from diabetes_chatbot.state import get_active_tools
from diabetes_chatbot.planner import evaluate_clinical_planner, evaluate_clinical_planner_llm
from diabetes_chatbot.logger import log_turn
from diabetes_chatbot.perception import parse_medication_bag, parse_taiwanese_audio
from diabetes_chatbot.guard import (
    enforce_single_question_budget,
    inspect_output_guard,
    inspect_safety_guard,
)
from diabetes_chatbot.memory import (
    load_patient_record,
    update_medications,
    update_previsit_summary,
    format_patient_context,
    get_patient_file_path,
    extract_clinical_facts_from_text,
    prune_conversation_history,
    archive_session,
    update_from_planner_assessment
)

warnings.filterwarnings("ignore")

# 1. 載入環境設定
load_dotenv(Path(__file__).parent.parent / ".env")
api_key = os.getenv("OPENCODE_API_KEY")
base_url = os.getenv("OPENCODE_BASE_URL", "https://opencode.ai/zen/go/v1")
model = "mimo-v2.5"

if not api_key:
    print("【錯誤】未在 .env 找到 OPENCODE_API_KEY！")
    exit(1)

client = OpenAI(api_key=api_key, base_url=base_url)

def start_interactive_chat(patient_id: str = "demo_patient"):
    # 支援多病患健康檔案路徑
    patient_file = get_patient_file_path(patient_id)
    
    # 載入長期健康檔案，動態組裝 System Prompt
    patient_context = format_patient_context(patient_file)
    system_prompt = build_nurse_system_prompt(patient_context)
    messages = [{"role": "system", "content": system_prompt}]
    
    record = load_patient_record(patient_file)
    meds_known = [m["name"] for m in record.get("medications", [])]
    last_glucose = record.get("glucose_metrics", {}).get("latest", "")
    
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print("=" * 60)
    print("【V2 糖尿病專科衛教護理師 - 具備分級安全守護與長歷史記憶】")
    print(f"  [病患識別代碼] {patient_id}")
    if meds_known:
        print(f"  [長期檔案連線] 已掌握既有用藥：{', '.join(meds_known)}")
    if last_glucose:
        print(f"  [長期檔案連線] 最近紀錄血糖：{last_glucose}")
    if not meds_known and not last_glucose:
        print("  [長期檔案連線] 目前為新病患健康檔案")
        
    print("核心能力：")
    print("  1. 自然日常衛教（例：我剛吃完晚餐、早餐可以吃蛋餅嗎？）")
    print("  2. 官方真實 RAG 查證（例：常常很渴一直喝水是糖尿病嗎？）")
    print("  3. 門診預問診摘要（例：我下週要看醫生，幫我整理就醫備忘錄）")
    print("  4. 健保藥袋照片辨識（例：輸入 fixtures/images/medication_bag_front.jpg）")
    print("  5. 分級安全物理守護（急症/自傷/攻擊 0 延遲斷路；調藥/診斷/閒聊溫暖引導不卡死）")
    print("  - 結束請輸入：q 或 quit")
    print("=" * 60)
    
    while True:
        try:
            user_input = input("\n[你] ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["q", "quit", "exit", "ｑ", "再見"]:
                archive_path = archive_session(session_id, messages, patient_id=patient_id)
                print(f"\n[系統：本次會話歷史已封存至 {archive_path.name}]")
                print("對話結束，祝您身體健康！")
                break
                
            # 支援圖片與語音多模態輸入 (Multimodal Perception)
            actual_content = user_input
            clean_path = user_input.replace("[圖片]", "").replace("[語音]", "").strip()
            
            if any(clean_path.lower().endswith(ext) for ext in [".wav", ".m4a", ".mp3", ".aac", ".flac"]):
                audio_p = Path(clean_path)
                if audio_p.exists():
                    print("\n[系統：正在透過聯發科 Breeze-ASR-26 辨識台灣語音...]", flush=True)
                    audio_res = parse_taiwanese_audio(audio_p)
                    if audio_res.get("success"):
                        actual_content = audio_res["text"]
                        print(f"[系統：語音轉文字成功（耗時 {audio_res['duration']:.2f} 秒）！辨識內容：『{actual_content}』]\n")
                    else:
                        print(f"[系統：{audio_res['message']}]\n")
            elif any(clean_path.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png"]):
                img_p = Path(clean_path)
                if img_p.exists():
                    print("\n[系統：正在透過 QR Code / OCR 感知模組辨識藥袋照片...]", flush=True)
                    ocr_res = parse_medication_bag(img_p)
                    if ocr_res.get("success"):
                        med_names = ", ".join(ocr_res["medications"])
                        print(f"[系統：成功解析！透過【{ocr_res['method']}】辨識出藥品：{med_names}]")
                        # 自動持久化至病患長期健康檔案
                        update_medications(ocr_res["medications"], source=f"藥袋辨識({ocr_res['method']})", file_path=patient_file)
                        print("[系統：已自動將藥品資訊持久化保存至病患長期健康檔案]\n")
                        actual_content = f"我拍了我的藥袋照片，上面辨識出的藥物是：{med_names}"
                    else:
                        print(f"[系統：{ocr_res['message']}]\n")
            else:
                # 第一級：臨床安全分級守護物理斷路器（0 延遲快篩急症、自傷與提示詞攻擊）
                guard_res = inspect_safety_guard(actual_content)
                if guard_res.is_blocked:
                    print(f"\n{guard_res.blocked_message}\n")
                    if guard_res.risk_category in ["EMERGENCY", "MENTAL_HEALTH"]:
                        messages.append({"role": "user", "content": actual_content})
                        messages.append({"role": "assistant", "content": guard_res.blocked_message})
                    log_turn(user_input, guard_res.blocked_message, latency=0.001, tool_used=f"GUARD_BLOCK_{guard_res.risk_category}")
                    continue

                # 非侵入式提取病患自述文字中的血糖、用藥與症狀（調藥、診斷、閒聊均放行在此）
                facts = extract_clinical_facts_from_text(actual_content, file_path=patient_file)
                if facts.get("glucose"):
                    print(f"[系統：已自動記錄病患自述血糖【{facts['glucose']}】至健康檔案]")
                if facts.get("symptoms"):
                    print(f"[系統：已自動記錄自述症狀【{', '.join(facts['symptoms'])}】至健康檔案]")
                if facts.get("medications"):
                    print(f"[系統：已自動記錄口述藥物【{', '.join(facts['medications'])}】至健康檔案]")
                        
            messages.append({"role": "user", "content": actual_content})
            start_time = time.time()
            tool_name_used = "none"
            
            try:
                patient_record_hot = load_patient_record(patient_file)
                planner_assessment = evaluate_clinical_planner_llm(messages, patient_record_hot, client, model, timeout=2.0)
            except Exception as _e:
                planner_assessment = evaluate_clinical_planner(messages, patient_file_path=patient_file)
                try:
                    planner_assessment.engine = f"python_fallback({str(_e)[:30]})"
                except Exception:
                    planner_assessment.engine = "python_fallback"
            try:
                if not planner_assessment.can_unlock_summary_tool and planner_assessment.is_explicit_request:
                    from diabetes_chatbot.planner import SlotStatus as _SS2
                    has_med2 = planner_assessment.slots.medications_status in (_SS2.KNOWN, _SS2.PARTIAL)
                    has_data2 = planner_assessment.slots.glucose_metrics_status in (_SS2.KNOWN, _SS2.PARTIAL)
                    has_hypo2 = planner_assessment.slots.hypo_history_status in (_SS2.KNOWN, _SS2.PARTIAL)
                    has_concern2 = planner_assessment.slots.concerns_status == _SS2.KNOWN
                    if has_med2 and (has_data2 or has_hypo2 or has_concern2):
                        planner_assessment.is_agenda_confirmed = True
                        planner_assessment.can_unlock_summary_tool = True
                        planner_assessment.talker_guidance = "【臨床導引就醫備忘錄】：病患看診議程已確認，核心資訊已達充分度！請立刻調用 generate_previsit_intake_summary 工具為病患生成門診摘要，嚴禁再拋出任何問題追問病患；生成完成後，親切告知已整理完畢並叮嚀看診時出示即可。"
            except Exception:
                pass
            active_tools = get_active_tools(messages, patient_file_path=patient_file, planner_assessment=planner_assessment)

            # 強制程式檢索（不問模型）：GENERAL_EDUCATION定義 或 DRUG_SAFETY，rule-rewritten query = user text stripped
            forced_evidence = None
            forced_tool_display = None
            try:
                from diabetes_chatbot.planner import RetrievalDomain as _RD2

                def _extract_definition_keyword2(q: str) -> str:
                    ql = q.lower()
                    if any(k in ql for k in ["成因", "形成", "原理", "怎麼形成", "怎麼來的", "機制", "為什麼", "為何"]):
                        return "糖尿病成因 胰島素阻抗"
                    elif any(k in ql for k in ["是什麼", "什麼是", "定義", "分型", "種類"]):
                        return "糖尿病定義 血糖診斷標準"
                    return "糖尿病衛教"

                def _is_def_local2(q: str, domain_val: str) -> bool:
                    ql = q.lower()
                    def_kw = ["是什麼", "什麼是", "定義", "成因", "形成", "為什麼", "為何", "原理", "怎麼形成", "怎麼來的", "機制", "分型", "種類"]
                    if any(k in ql for k in def_kw):
                        if "糖尿病" in ql or "diabetes" in ql or domain_val == "GENERAL_EDUCATION":
                            return True
                    return False

                # 僅在長輩詢問「成因、定義、原理」（GENERAL_EDUCATION）時進行正規化輔助檢索，絕不拿病患長句口語整段搜尋！
                needs_forced = False
                if not planner_assessment.is_visit_mode and planner_assessment.retrieval_domain == _RD2.GENERAL_EDUCATION:
                    if _is_def_local2(actual_content, planner_assessment.retrieval_domain.value):
                        needs_forced = True

                if needs_forced:
                    rule_q2 = _extract_definition_keyword2(actual_content)
                    if rule_q2:
                        forced_evidence = search_handbook(rule_q2, user_raw_input=actual_content, domain=planner_assessment.retrieval_domain.value)
                        forced_tool_display = f"search_handbook(關鍵字: '{rule_q2}', domain={planner_assessment.retrieval_domain.value}, evidence_links已保留至就醫備忘錄小字{len(forced_evidence)}字/出處只印不念)"
                        tool_name_used = forced_tool_display
            except Exception:
                forced_evidence = None
            
            # 滑動上下文視窗修剪 (Sliding Context Window)，確保 System Prompt 置頂且 Token 不膨脹
            pruned_context = prune_conversation_history(messages, max_history_messages=8)
            
            # 臨時注入 臨床衛教大腦 臨床導引就醫備忘錄給 Talker Agent（不污染長期對話紀錄）
            inference_context = list(pruned_context)
            if planner_assessment.talker_guidance:
                inference_context.append({"role": "system", "content": planner_assessment.talker_guidance})
            if forced_evidence:
                _compact2 = forced_evidence[:1000]
                inference_context.append({
                    "role": "system",
                    "content": (
                        "【強制檢索證據｜出處只印不念，僅供 paraphrase】\n"
                        f"{_compact2}\n"
                        "任務：請用溫暖口語 paraphrase 重點，2~3句內完成，同理後收話；嚴禁背誦仿單原文、嚴禁條列發生率/出處/來源/仿單，嚴禁說常見所以沒關係；證據僅供就醫備忘錄 evidence_links 小字列印，絕不口頭念給病患。"
                    )
                })
            
            print("\n[衛教護理師正在思考...]", flush=True)
            first_resp = client.chat.completions.create(
                model=model,
                messages=inference_context,
                tools=active_tools if active_tools else None,
                temperature=0.3,
            )
            msg = first_resp.choices[0].message
            
            # 若模型決定調用工具
            if msg.tool_calls:
                tool_call = msg.tool_calls[0]
                func_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                tool_name_used = func_name
                
                if func_name == "search_handbook":
                    kw = args.get("keyword", "")
                    from diabetes_chatbot.planner import _sanitize_search_keyword
                    kw_clean = _sanitize_search_keyword(kw, user_input)
                    print(f"[系統：護理師正在調用 TFDA 藥品風險圖譜與國健署手冊 RAG，查詢【{kw_clean}】...]\n")
                    tool_output = search_handbook(
                        kw_clean,
                        user_raw_input=user_input,
                        domain=planner_assessment.retrieval_domain.value
                    )
                    evidence_links = tool_output
                    print("[系統：已保留證據至就醫備忘錄 evidence_links，出處只印不念，不口頭念給病患]\n")
                    messages.append(msg)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": evidence_links
                    })
                    print("[衛教護理師正在組織衛教內容...]\n", end="", flush=True)
                    empathy_ctx = list(prune_conversation_history(messages[:-1], max_history_messages=8))
                    empathy_ctx.append({"role": "system", "content": "【副作用同理收話任務｜出處只印不念】病患反映不適或詢問副作用時，請以「同理＋收話」固定句型回應，例如『脹得不舒服齁，我幫您記在第一條，回診一起問醫師』。嚴禁背誦仿單原文、嚴禁說常見所以沒關係、嚴禁解釋機轉；證據僅供就醫備忘錄小字列印，絕不口頭念給病患。"})
                    stream = client.chat.completions.create(
                        model=model,
                        messages=empathy_ctx,
                        temperature=0.7,
                        stream=True
                    )
                    full_reply = []
                    for chunk in stream:
                        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                            token = chunk.choices[0].delta.content
                            sys.stdout.write(token)
                            sys.stdout.flush()
                            full_reply.append(token)
                    print()
                    raw_reply = "".join(full_reply).strip()
                    if not raw_reply:
                        raw_reply = "脹得不舒服齁，我幫您記在第一條，回診一起問醫師好不好？這段時間先照醫師原本的交代用藥，有變化我幫您記下來。"
                    if "官方臨床證據" in raw_reply or "來源：" in raw_reply or "仿單" in raw_reply or "常見" in raw_reply:
                        raw_reply = "脹得不舒服齁，我幫您記在第一條，回診一起問醫師好不好？這段時間先照醫師原本的交代用藥，有變化我幫您記下來。"
                    out_guard = inspect_output_guard(raw_reply)
                    if out_guard.is_blocked:
                        reply_text = out_guard.blocked_message
                        print(f"[系統安全覆寫] 偵測到輸出違規（{out_guard.risk_category}），已啟動安全保護：\n{reply_text}\n")
                    else:
                        reply_text = enforce_single_question_budget(raw_reply)
                        print(f"[衛教護理師]\n{reply_text}\n")
                elif func_name in ["generate_previsit_intake_summary", "generate_visit_summary"]:
                    print("[系統：護理師正在為您生成新陳代謝科 門診預問診摘要（就醫備忘錄）...]\n")
                    tool_output = generate_visit_summary(
                        visit_reason=args.get("visit_reason", "門診定期追蹤"),
                        medications=args.get("medications", "未特別說明"),
                        glucose_metrics=args.get("glucose_metrics", "未特別說明"),
                        hypo_history=args.get("hypo_history", "近期未提及或無發生"),
                        side_effects_or_concerns=args.get("side_effects_or_concerns", "無特別異常"),
                    )
                    print(tool_output + "\n")
                    update_previsit_summary(tool_output, file_path=patient_file)
                    print("[系統：已將本次門診預問診摘要存檔至病患長期健康檔案]\n")
                    messages.append(msg)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_output
                    })
                    vr = args.get("visit_reason", "門診定期追蹤")
                    meds = args.get("medications", "未特別說明")
                    gm = args.get("glucose_metrics", "未特別說明")
                    hypo = args.get("hypo_history", "近期未提及或無發生")
                    concerns = args.get("side_effects_or_concerns", "無特別異常")
                    raw_reply = (
                        f"跟您確認一下我幫您整理的就醫備忘："
                        f"第一，回診訴求是「{vr}」；"
                        f"第二，目前用藥是「{meds}」；"
                        f"第三，血糖與不適狀況是「{gm}／{hypo}／{concerns}」。"
                        f"這樣記對嗎，可以嗎？確認後我幫您產生 QR 就醫備忘錄，回診直接出示給醫師看就可以了。"
                    )
                    out_guard = inspect_output_guard(raw_reply)
                    if out_guard.is_blocked:
                        reply_text = out_guard.blocked_message
                        print(f"[系統安全覆寫] 偵測到輸出違規（{out_guard.risk_category}），已啟動安全保護：\n{reply_text}\n")
                    else:
                        reply_text = enforce_single_question_budget(raw_reply)
                        print(f"[衛教護理師]\n{reply_text}\n")
                else:
                    tool_output = "未知工具。"
                    messages.append(msg)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_output
                    })
                    print("[衛教護理師正在組織衛教內容...]\n", end="", flush=True)
                    stream_context = prune_conversation_history(messages, max_history_messages=8)
                    stream = client.chat.completions.create(
                        model=model,
                        messages=stream_context,
                        temperature=0.7,
                        stream=True
                    )
                    full_reply = []
                    for chunk in stream:
                        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                            token = chunk.choices[0].delta.content
                            sys.stdout.write(token)
                            sys.stdout.flush()
                            full_reply.append(token)
                    print()
                    raw_reply = "".join(full_reply).strip()
                    out_guard = inspect_output_guard(raw_reply)
                    if out_guard.is_blocked:
                        reply_text = out_guard.blocked_message
                        print(f"[系統安全覆寫] 偵測到輸出違規（{out_guard.risk_category}），已啟動安全保護：\n{reply_text}\n")
                    else:
                        reply_text = enforce_single_question_budget(raw_reply)
                        print(f"[衛教護理師]\n{reply_text}\n")
            else:
                raw_reply = msg.content.strip()
                out_guard = inspect_output_guard(raw_reply)
                if out_guard.is_blocked:
                    reply_text = out_guard.blocked_message
                    print(f"[系統安全覆寫] 偵測到輸出違規（{out_guard.risk_category}），已啟動安全保護：\n{reply_text}\n")
                else:
                    reply_text = enforce_single_question_budget(raw_reply)
                    print(f"[衛教護理師]\n{reply_text}\n")
                
            latency = time.time() - start_time
            messages.append({"role": "assistant", "content": reply_text})
            log_turn(user_input, reply_text, latency, tool_used=tool_name_used)
            
            def _async_persist_hot(planner_hot, p_file, msgs_snapshot):
                try:
                    if planner_hot.engine == "llm":
                        changed = update_from_planner_assessment(planner_hot, file_path=p_file)
                        if changed:
                            pass
                    else:
                        cur_rec = load_patient_record(p_file)
                        llm_eval = evaluate_clinical_planner_llm(msgs_snapshot, cur_rec, client, model, timeout=2.0)
                        if llm_eval.engine == "llm":
                            changed = update_from_planner_assessment(llm_eval, file_path=p_file)
                            if changed:
                                pass
                except Exception:
                    pass

            bg_thread = threading.Thread(
                target=_async_persist_hot,
                args=(planner_assessment, patient_file, list(messages)),
                daemon=True
            )
            bg_thread.start()
            
        except KeyboardInterrupt:
            archive_path = archive_session(session_id, messages, patient_id=patient_id)
            print(f"\n[系統：已中斷對話，對話紀錄已封存至 {archive_path.name}]")
            break

if __name__ == "__main__":
    target_patient = sys.argv[1] if len(sys.argv) > 1 else "demo_patient"
    start_interactive_chat(target_patient)
