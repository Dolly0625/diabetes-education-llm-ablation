"""
LINE 訊息分流與 V2 臨床大腦轉接器 (LINE Webhook Event Handlers)
將 LINE 的文字、語音 (.m4a)、圖片 (藥袋) 統一轉接至 V2 臨床大腦核心。
"""
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Optional, Union

from dotenv import load_dotenv
from openai import OpenAI

from diabetes_chatbot.guard import (
    enforce_single_question_budget,
    inspect_output_guard,
    inspect_safety_guard,
)
from diabetes_chatbot.logger import log_turn
from diabetes_chatbot.memory import (
    extract_clinical_facts_from_text,
    format_patient_context,
    get_patient_file_path,
    load_patient_record,
    prune_conversation_history,
    update_from_planner_assessment,
    update_medications,
    update_previsit_summary,
)
from diabetes_chatbot.perception import parse_medication_bag, parse_taiwanese_audio
from diabetes_chatbot.planner import evaluate_clinical_planner, evaluate_clinical_planner_llm
from diabetes_chatbot.prompts import build_nurse_system_prompt
from diabetes_chatbot.state import get_active_tools
from diabetes_chatbot.tools import (
    generate_clinic_qr_payload,
    generate_line_flex_bubble,
    generate_visit_summary,
    search_handbook,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env")

gemini_key = os.getenv("GEMINI_API_KEY")
provider = os.getenv("LLM_PROVIDER", "gemini" if gemini_key else "opencode")

if provider == "gemini" and gemini_key:
    api_key = gemini_key.strip('"')
    base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    model_display = "Gemini-3.5-Flash-Lite"
else:
    api_key = os.getenv("OPENCODE_API_KEY")
    base_url = os.getenv("OPENCODE_BASE_URL", "https://opencode.ai/zen/go/v1")
    model = "mimo-v2.5"
    model_display = "MiMo-V2.5 (思考模式：關閉)"

_client: Optional[OpenAI] = None

def get_openai_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=api_key, base_url=base_url)
    return _client

def _strip_evidence_links_leak(text: str) -> str:
    """物理過濾聊天正文中意外洩漏的 evidence_links 或官方出處標籤，嚴格落實出處只印不念"""
    import re
    if not text:
        return ""
    t = re.sub(r"<div id=[\"']evidence_links[\"'].*?</div>", "", text, flags=re.DOTALL)
    t = re.sub(r"evidence_links\s*:\s*(?:\[.*?\]|-.*?\n?)*", "", t, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r"\n\s*-\s*\[.*?\]\(https?://.*?\)", "", t)
    return t.strip()


# 跨對話會話記憶快取 (記憶每個 line user_id 的短期 messages 歷史)
_SESSION_CACHE: dict[str, list[dict]] = {}

def get_user_messages(user_id: str, patient_file: Path) -> list[dict]:
    """取得或初始化使用者的短期對話歷史"""
    if user_id not in _SESSION_CACHE:
        ctx = format_patient_context(patient_file)
        sys_prompt = build_nurse_system_prompt(ctx)
        _SESSION_CACHE[user_id] = [{"role": "system", "content": sys_prompt}]
    return _SESSION_CACHE[user_id]

def _format_slot_display(content: str, status: Any) -> str:
    """格式化臨床槽位狀態文字"""
    from diabetes_chatbot.planner import SlotStatus
    status_str = status.value if hasattr(status, "value") else str(status)
    if status_str in (SlotStatus.KNOWN.value, "KNOWN"):
        return f"已掌握（{content}）" if content else "已掌握"
    elif status_str in (SlotStatus.PARTIAL.value, "PARTIAL"):
        return f"部分掌握（{content}）" if content else "部分掌握"
    else:
        return "尚缺（尚未提及）"


def build_audit_log(
    latency: float,
    modality: str,
    guard_passed: bool,
    tool_used: str,
    rag_hit: bool,
    slots: Any,
    talker_guidance: str,
    can_unlock: bool,
    model_display_name: Optional[str] = None
) -> str:
    """
    建構展示專用之 專科臨床大腦技術審計日誌 (Audit Log)
    嚴格遵循繁體中文與零 Emoji 規範，並將內部指引命名為「指揮訊息」
    """
    disp_model = model_display_name or model_display
    guard_text = "PASS (未觸發紅旗/急症急診邊界)" if guard_passed else "FAIL (觸發急症紅旗阻斷 Fail-Closed)"
    rag_text = "命中 (TFDA 糖尿病臨床指引衛教手冊)" if rag_hit else "未觸發 (常規對話無須檢索)"
    gate_text = "已解鎖 (臨床充分度達標)" if can_unlock else "鎖定中 (臨床資訊尚未齊全，避免濫發空卡)"

    guidance_clean = (talker_guidance or "").strip()
    if not guidance_clean:
        guidance_display = "日常衛教陪伴模式（全心傾聽衛教，無額外干預指令）"
    else:
        clean_lines = [line.strip() for line in guidance_clean.split("\n") if line.strip()]
        guidance_display = "\n  ".join(clean_lines)

    lines = [
        "----------------------------------",
        "【專科臨床大腦審計日誌】",
        f"• 感知輸入模態：{modality}",
        f"• 系統處理耗時：{latency:.2f} 秒",
        f"• 底層推論模型：{disp_model}",
        f"• 第一級安全守護：{guard_text}",
        f"• 工具調用 (Tool Call)：{tool_used}",
        f"• 實證檢索 (RAG)：{rag_text}",
        "• TADE 5 大臨床槽位狀態：",
        f"  - 本次回診訴求：{_format_slot_display(slots.visit_reason, slots.visit_reason_status)}",
        f"  - 目前用藥狀況：{_format_slot_display(slots.medications, slots.medications_status)}",
        f"  - 血糖數據監測：{_format_slot_display(slots.glucose_metrics, slots.glucose_metrics_status)}",
        f"  - 低血糖病史：{_format_slot_display(slots.hypo_history, slots.hypo_history_status)}",
        f"  - 副作用與疑慮：{_format_slot_display(slots.concerns_or_side_effects, slots.concerns_status)}",
        "• Planner → Talker 指揮訊息：",
        f"  {guidance_display}",
        f"• 就醫備忘錄解鎖閥門：{gate_text}",
        "----------------------------------"
    ]
    return "\n".join(lines)


def process_patient_message(
    user_id: str,
    text_input: Optional[str] = None,
    audio_path: Optional[Union[str, Path]] = None,
    image_path: Optional[Union[str, Path]] = None
) -> dict[str, Any]:
    """
    V2 臨床大腦入口：處理來自 LINE 的文字、語音或圖片，並產出回覆內容。
    回傳格式：
    {
        "reply_type": "text" | "flex",
        "reply_text": str,
        "flex_bubble": dict | None,
        "qr_payload": str | None,
        "audit_log": str | None
    }
    """
    start_time = time.time()
    tool_name_used = "無 (常規對話)"
    patient_file = get_patient_file_path(f"line_{user_id}")
    messages = get_user_messages(user_id, patient_file)
    client = get_openai_client()
    
    actual_text = ""
    prefix_note = ""
    input_modality = "文字輸入"

    # 1. 處理語音輸入 (Breeze-ASR-26 在地台語辨識)
    if audio_path:
        input_modality = "MediaTek Breeze-ASR-26 在地台語語音辨識"
        audio_res = parse_taiwanese_audio(audio_path)
        if audio_res.get("success"):
            actual_text = audio_res["text"]
            prefix_note = f"[已透過台語語音辨識出：『{actual_text}』]\n\n"
        else:
            return {
                "reply_type": "text",
                "reply_text": "阿公阿嬤拍謝，剛才那段錄音稍微有點不清楚，方便您再按住麥克風說一次嗎？",
                "flex_bubble": None,
                "qr_payload": None,
                "audit_log": None
            }

    # 2. 處理圖片輸入 (健保藥袋 QR/OCR)
    elif image_path:
        input_modality = "健保藥袋 QR/OCR 多模態影像解析"
        ocr_res = parse_medication_bag(image_path)
        if ocr_res.get("success"):
            med_names = ", ".join(ocr_res["medications"])
            update_medications(ocr_res["medications"], source="LINE藥袋辨識", file_path=patient_file)
            actual_text = f"我拍了我的藥袋照片，上面辨識出的藥品是：{med_names}"
            prefix_note = f"[成功看懂您的藥袋！已幫您記錄目前服用藥品：{med_names}]\n\n"
        else:
            return {
                "reply_type": "text",
                "reply_text": "這張藥袋照片有點反光或模糊，請幫我在光線明亮的地方，將印有藥名或 QR Code 的正面拍清楚再傳一次喔！",
                "flex_bubble": None,
                "qr_payload": None,
                "audit_log": None
            }

    # 3. 處理文字輸入
    elif text_input:
        input_modality = "文字輸入"
        actual_text = text_input.strip()

    if not actual_text:
        return {
            "reply_type": "text",
            "reply_text": "您好！我是您的糖尿病衛教護理師，今天有什麼想了解或需要幫忙的嗎？",
            "flex_bubble": None,
            "qr_payload": None,
            "audit_log": None
        }

    # 4. 第一級：物理安全守護斷路器
    guard_res = inspect_safety_guard(actual_text)
    if guard_res.is_blocked:
        latency = time.time() - start_time
        guard_audit_lines = [
            "----------------------------------",
            "【專科臨床大腦審計日誌】",
            f"• 感知輸入模態：{input_modality}",
            f"• 系統處理耗時：{latency:.2f} 秒",
            f"• 底層推論模型：{model_display}",
            "• 第一級安全守護：FAIL (觸發急症紅旗阻斷 Fail-Closed)",
            "• 工具調用 (Tool Call)：阻斷不執行",
            "• 實證檢索 (RAG)：阻斷不執行",
            "• 處置動作：立刻引導撥打 119 急救電話或前往急診就醫",
            "----------------------------------"
        ]
        audit_log = "\n".join(guard_audit_lines)
        return {
            "reply_type": "text",
            "reply_text": f"{guard_res.blocked_message}\n\n{audit_log}",
            "flex_bubble": None,
            "qr_payload": None,
            "audit_log": audit_log
        }

    # 5. 第二級：非侵入式客觀事實背景入庫
    extract_clinical_facts_from_text(actual_text, file_path=patient_file)
    messages.append({"role": "user", "content": actual_text})

    # 6. 第三級：臨床衛教大腦 Planner 臨床資訊缺口評估與工具閥門 — LLM-first hot path (A-zone) with timeout fallback
    try:
        patient_record_hot = load_patient_record(patient_file)
        planner = evaluate_clinical_planner_llm(messages, patient_record_hot, client, model, timeout=3.0)
    except Exception as _e:
        planner = evaluate_clinical_planner(messages, patient_file_path=patient_file)
        try:
            planner.engine = f"python_fallback({str(_e)[:30]})"
        except Exception:
            planner.engine = "python_fallback"
    try:
        if not planner.can_unlock_summary_tool and planner.is_explicit_request:
            from diabetes_chatbot.planner import SlotStatus as _SS
            # 選項 A：嚴格收緊後門 —— 必須同時具備明確具體的回診訴求，而非空泛未填
            has_explicit_reason = (
                planner.slots.visit_reason_status in (_SS.KNOWN, _SS.PARTIAL) and
                bool(planner.slots.visit_reason) and
                planner.slots.visit_reason not in ("門診定期追蹤", "定期回診", "")
            )
            has_med = planner.slots.medications_status in (_SS.KNOWN, _SS.PARTIAL)
            has_data = planner.slots.glucose_metrics_status in (_SS.KNOWN, _SS.PARTIAL)
            has_hypo = planner.slots.hypo_history_status in (_SS.KNOWN, _SS.PARTIAL)
            has_concern = planner.slots.concerns_status == _SS.KNOWN
            if has_explicit_reason and has_med and (has_data or has_hypo or has_concern):
                planner.is_agenda_confirmed = True
                planner.can_unlock_summary_tool = True
                planner.talker_guidance = "【臨床導引就醫備忘錄】：病患看診議程已具備明確主訴，核心資訊已達充分度！請立刻調用 generate_previsit_intake_summary 工具為病患生成門診摘要，嚴禁再拋出任何問題追問病患；生成完成後，親切告知已整理完畢並叮嚀看診時出示即可。"
    except Exception:
        pass
    active_tools = get_active_tools(messages, patient_file_path=patient_file, planner_assessment=planner)
    if image_path:
        # 上傳藥袋照片為感知登記環節，物理收起產卡工具，回歸親切確認藥品文字
        active_tools = [t for t in active_tools if t.get("function", {}).get("name") not in ["generate_previsit_intake_summary", "generate_visit_summary"]]

    # 6b. 定義/成因型查詢正規化輔助檢索（出處只印不念）
    forced_evidence = None
    forced_tool_display = None
    try:
        from diabetes_chatbot.planner import RetrievalDomain as _RD

        def _extract_definition_keyword(q: str) -> str:
            ql = q.lower()
            if any(k in ql for k in ["脹", "胃", "肚子", "腹瀉", "噁心"]) and any(k in ql for k in ["藥", "吃"]):
                return "糖尿病 腸胃不適 腹脹 衛教"
            elif any(k in ql for k in ["成因", "形成", "原理", "怎麼形成", "怎麼來的", "機制", "為什麼", "為何"]):
                return "糖尿病成因 胰島素阻抗"
            elif any(k in ql for k in ["是什麼", "什麼是", "定義", "分型", "種類"]):
                return "糖尿病定義 血糖診斷標準"
            return "糖尿病衛教"

        def _is_def_local(q: str, domain_val: str) -> bool:
            ql = q.lower()
            def_kw = ["是什麼", "什麼是", "定義", "成因", "形成", "為什麼", "為何", "原理", "怎麼形成", "怎麼來的", "機制", "分型", "種類"]
            if any(k in ql for k in def_kw):
                if "糖尿病" in ql or "diabetes" in ql or domain_val in ["GENERAL_EDUCATION", "DRUG_SAFETY"]:
                    return True
            return False

        # 在長輩詢問「成因、定義、原理」（GENERAL_EDUCATION 或 DRUG_SAFETY）時進行正規化輔助檢索，絕不拿病患長句口語整段搜尋！
        needs_forced = False
        if not planner.is_visit_mode and planner.retrieval_domain in [_RD.GENERAL_EDUCATION, _RD.DRUG_SAFETY]:
            if _is_def_local(actual_text, planner.retrieval_domain.value):
                needs_forced = True

        if needs_forced:
            rule_q = _extract_definition_keyword(actual_text)
            if rule_q:
                forced_evidence = search_handbook(rule_q, user_raw_input=actual_text, domain=planner.retrieval_domain.value)
                forced_tool_display = f"search_handbook(關鍵字: '{rule_q}', domain={planner.retrieval_domain.value}, evidence_links已保留至就醫備忘錄小字{len(forced_evidence)}字/出處只印不念)"
                tool_name_used = forced_tool_display
    except Exception:
        forced_evidence = None

    # 7. 第四級：滑動視窗修剪與指揮訊息注入
    pruned_ctx = prune_conversation_history(messages, max_history_messages=8)
    inference_ctx = list(pruned_ctx)
    if planner.talker_guidance:
        inference_ctx.append({"role": "system", "content": planner.talker_guidance})
    if forced_evidence:
        _compact = forced_evidence[:1000]
        if planner.retrieval_domain == _RD.DRUG_SAFETY:
            guidance_task = (
                "【官方實證藥物衛教解說任務｜實證詳實首發，按需白話轉譯】\n"
                f"{_compact}\n"
                "任務：病患正在詢問特定降血糖藥物成因、藥理作用或副作用機制。\n"
                "1. 請依據上述衛福部官方仿單/臨床指引重點，條理清晰地向病患說明藥物成因機轉、常見腸胃反應與官方建議因應方式（如隨餐或飯後服用降低刺激、漸進適應），保留醫學事實細節，保障病患知情權。\n"
                "2. 於說明文末親切附上引導句：『若上述醫學說明有太深奧或看不懂的地方，隨時告訴我，我可以用更生活化的比喻向您解釋喔！』。\n"
                "3. 嚴禁提供劑量調整指令，若病患提及想停藥，提醒切勿擅自停藥；出處只印在就醫備忘錄小字，口語對話自然稱『依據衛福部仿單說明』即可，絕不可輸出 raw evidence_links 及網址。"
            )
        else:
            guidance_task = (
                "【官方手冊衛教解說任務｜實證詳實首發，按需白話轉譯】\n"
                f"{_compact}\n"
                "任務：長輩正在詢問糖尿病成因、原理或衛教知識。\n"
                "1. 請根據上述衛福部官方手冊重點，清楚完整地向長輩解釋成因機轉，保留重要衛教細節。\n"
                "2. 於說明文末親切提醒長輩：若有看不懂或太複雜的地方，隨時可以告訴我，我會用更白話的方式向您解釋喔！\n"
                "3. 口語對話自然說明即可，絕不可輸出 raw evidence_links 及網址。"
            )
        inference_ctx.append({
            "role": "system",
            "content": guidance_task
        })

    # 8. 第五級：Talker 專科護理師大腦推論 (關閉 thinking 模式以確保極速回覆)
    extra_body = {"reasoning": {"effort": "none"}} if "mimo" in model.lower() else None
    max_tokens_to_use = 500 if "gemini" in model.lower() else 250
    resp = client.chat.completions.create(
        model=model,
        messages=inference_ctx,
        tools=active_tools if active_tools else None,
        extra_body=extra_body,
        max_tokens=max_tokens_to_use,
        temperature=0.3
    )
    msg = resp.choices[0].message

    # 9. 工具調用分支 (查手冊 或 產門診卡，支援原生 tool_calls 或 XML 格式解析)
    raw_content = (msg.content or "").strip()
    is_xml_tool_call = "<tool_call>" in raw_content and "search_handbook" in raw_content
    
    if msg.tool_calls or is_xml_tool_call:
        if msg.tool_calls:
            tool_call = msg.tool_calls[0]
            func_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            tc_id = tool_call.id
            tool_name_used = func_name
        else:
            func_name = "search_handbook"
            import re
            m = re.search(r"<parameter=keyword>(.*?)</parameter>", raw_content)
            kw_val = m.group(1).strip() if m else "糖尿病飲食 碳水化合物"
            args = {"keyword": kw_val}
            tc_id = "call_fallback_xml"
            msg.tool_calls = None
            tool_name_used = "search_handbook"

        if func_name == "search_handbook":
            import re
            kw = args.get("keyword", "")
            from diabetes_chatbot.planner import _sanitize_search_keyword
            kw_clean = _sanitize_search_keyword(kw, actual_text)
            tool_output = search_handbook(kw_clean, user_raw_input=actual_text, domain=planner.retrieval_domain.value)
            evidence_links = tool_output
            tool_display = f"search_handbook(關鍵字: '{kw_clean}', evidence_links已保留至就醫備忘錄小字{len(evidence_links)}字/出處只印不念)"
            second_context = list(prune_conversation_history(messages, max_history_messages=8))
            if planner.retrieval_domain == _RD.DRUG_SAFETY:
                second_task = (
                    "【官方實證藥物衛教解說任務｜實證詳實首發，按需白話轉譯】\n"
                    f"{tool_output[:800]}\n"
                    "任務：病患正在詢問特定降血糖藥物成因、藥理作用或副作用機制。\n"
                    "1. 請依據上述衛福部官方仿單/臨床指引重點，條理清晰地向病患說明藥物成因機轉、常見腸胃反應與官方建議因應方式（如隨餐或飯後服用降低刺激、漸進適應），保留醫學事實細節，保障病患知情權。\n"
                    "2. 於說明文末親切附上引導句：『若上述醫學說明有太深奧或看不懂的地方，隨時告訴我，我可以用更生活化的比喻向您解釋喔！』。\n"
                    "3. 嚴禁提供劑量調整指令，若病患提及想停藥，提醒切勿擅自停藥；出處只印在就醫備忘錄小字，口語對話自然稱『依據衛福部仿單說明』即可，絕不可輸出 raw evidence_links 及網址。"
                )
            else:
                second_task = (
                    "【官方手冊衛教解說任務｜實證詳實首發，按需白話轉譯】\n"
                    f"{tool_output[:800]}\n"
                    "長輩正在詢問糖尿病成因、原理或衛教知識。請根據上述衛福部官方手冊重點，清楚完整地向長輩解釋成因機轉，保留重要衛教細節。\n"
                    "於說明文末親切提醒長輩：若有看不懂或太複雜的地方，隨時可以告訴我，我會用更白話的方式向您解釋喔！\n"
                    "口語對話自然說明即可，絕對禁止輸出 raw evidence_links、網址或未排版 JSON。"
                )
            second_context.append({
                "role": "system",
                "content": second_task
            })

            second_resp = client.chat.completions.create(
                model=model,
                messages=second_context,
                extra_body=extra_body,
                max_tokens=max_tokens_to_use,
                temperature=0.7
            )
            final_text = (second_resp.choices[0].message.content or "").strip()
            final_text = re.sub(r"<tool_call>.*?</tool_call>", "", final_text, flags=re.DOTALL).strip()
            final_text = _strip_evidence_links_leak(final_text)
            if not final_text:
                if planner.retrieval_domain == _RD.DRUG_SAFETY:
                    final_text = "脹得不舒服齁，我幫您記在第一條，回診一起問醫師好不好？這段時間先照醫師原本的交代用藥，有變化我幫您記下來。"
                else:
                    final_text = "糖尿病就像是身體裡幫忙把糖分送進細胞的『鑰匙』（胰島素）變少或生鏽了，糖分留在血管裡排不出去。我們平常飲食定時定量、配合同伴照護，就能維持得很穩定喔！"
            out_guard = inspect_output_guard(final_text)
            if out_guard.is_blocked:
                final_text = out_guard.blocked_message
            else:
                final_text = enforce_single_question_budget(final_text)
                import re
                if re.search(r"不想吃|不敢吃|想停|不吃了|沒在吃", actual_text):
                    if not re.search(r"不能自己停|不可自行停|切勿自行停|不要擅自停|不能擅自停|不要自己停|不要停藥|不能停", final_text):
                        final_text = final_text.rstrip("。") + "。在醫師評估前，降血糖藥物千萬不能自己停掉喔，突然停藥血糖容易飆高有危險。"

            messages.append({"role": "assistant", "content": final_text})
            latency = time.time() - start_time
            log_turn(actual_text, final_text, latency=latency, tool_used=tool_display)
            print(f"[LINE Webhook] 使用者 {user_id} 手冊衛教回覆完成，總耗時: {latency:.2f} 秒 (模型: {model_display})")

            audit_log = build_audit_log(
                latency=latency,
                modality=input_modality,
                guard_passed=True,
                tool_used=tool_display,
                rag_hit=True,
                slots=planner.slots,
                talker_guidance=planner.talker_guidance,
                can_unlock=planner.can_unlock_summary_tool
            )

            full_reply_text = f"{prefix_note}{final_text}\n\n{audit_log}"
            return {
                "reply_type": "text",
                "reply_text": full_reply_text,
                "flex_bubble": None,
                "qr_payload": None,
                "audit_log": audit_log
            }

        elif func_name in ["generate_previsit_intake_summary", "generate_visit_summary"]:
            tool_display = "generate_visit_summary(產出門診預問診就醫備忘錄)"
            text_summary = generate_visit_summary(
                visit_reason=args.get("visit_reason", "定期回診追蹤"),
                medications=args.get("medications", "未特別說明"),
                glucose_metrics=args.get("glucose_metrics", "未特別說明"),
                hypo_history=args.get("hypo_history", "近期未提及或無發生"),
                side_effects_or_concerns=args.get("side_effects_or_concerns", "無特別異常"),
                ddx_candidates=args.get("ddx_candidates"),
                evidence_links=args.get("evidence_links"),
                patient_quote=args.get("patient_quote"),
                glucose_range=args.get("glucose_range"),
            )
            update_previsit_summary(text_summary, file_path=patient_file)
            flex_bubble = generate_line_flex_bubble(
                visit_reason=args.get("visit_reason", "定期回診追蹤"),
                medications=args.get("medications", "未特別說明"),
                glucose_metrics=args.get("glucose_metrics", "未特別說明"),
                hypo_history=args.get("hypo_history", "近期未提及或無發生"),
                side_effects_or_concerns=args.get("side_effects_or_concerns", "無特別異常"),
                ddx_candidates=args.get("ddx_candidates"),
                evidence_links=args.get("evidence_links"),
                patient_quote=args.get("patient_quote"),
                glucose_range=args.get("glucose_range"),
            )
            qr_payload = generate_clinic_qr_payload(
                visit_reason=args.get("visit_reason", "定期回診追蹤"),
                medications=args.get("medications", "未特別說明"),
                glucose_metrics=args.get("glucose_metrics", "未特別說明"),
                hypo_history=args.get("hypo_history", "近期未提及或無發生"),
                side_effects_or_concerns=args.get("side_effects_or_concerns", "無特別異常"),
                ddx_candidates=args.get("ddx_candidates"),
                evidence_links=args.get("evidence_links"),
                patient_quote=args.get("patient_quote"),
                glucose_range=args.get("glucose_range"),
            )

            messages.append(msg)
            messages.append({"role": "tool", "tool_call_id": tc_id, "content": text_summary})

            vr = args.get("visit_reason", "定期回診追蹤")
            meds = args.get("medications", "未特別說明")
            gm = args.get("glucose_metrics", "未特別說明")
            hypo = args.get("hypo_history", "近期未提及或無發生")
            concerns = args.get("side_effects_or_concerns", "無特別異常")
            final_hint = (
                f"跟您確認一下我幫您整理的就醫備忘："
                f"第一，回診訴求是「{vr}」；"
                f"第二，目前用藥是「{meds}」；"
                f"第三，血糖與不適狀況是「{gm}／{hypo}／{concerns}」。"
                f"這樣記對嗎，可以嗎？確認後我幫您產生 QR 就醫備忘錄，回診直接出示給醫師看就可以了。"
            )
            out_guard_hint = inspect_output_guard(final_hint)
            out_guard_summary = inspect_output_guard(text_summary)
            card_guard_passed = (not out_guard_hint.is_blocked) and (not out_guard_summary.is_blocked)
            if out_guard_hint.is_blocked:
                final_hint = out_guard_hint.blocked_message
            elif out_guard_summary.is_blocked:
                final_hint = out_guard_summary.blocked_message
            else:
                final_hint = enforce_single_question_budget(final_hint)
            if not card_guard_passed:
                flex_bubble = None
                qr_payload = None
                reply_type = "text"
            else:
                reply_type = "flex"
            messages.append({"role": "assistant", "content": final_hint})

            latency = time.time() - start_time
            log_turn(actual_text, final_hint, latency=latency, tool_used=tool_display)
            print(f"[LINE Webhook] 使用者 {user_id} 門診卡生成完成，總耗時: {latency:.2f} 秒 (模型: {model_display})")

            audit_log = build_audit_log(
                latency=latency,
                modality=input_modality,
                guard_passed=card_guard_passed,
                tool_used=tool_display,
                rag_hit=False,
                slots=planner.slots,
                talker_guidance=planner.talker_guidance,
                can_unlock=planner.can_unlock_summary_tool
            )

            return {
                "reply_type": reply_type,
                "reply_text": final_hint,
                "flex_bubble": flex_bubble,
                "qr_payload": qr_payload,
                "audit_log": audit_log
            }

    # 10. 常規親切衛教對話（若已強制檢索，證據已注入 Talker，無需再調 tool）
    final_reply = _strip_evidence_links_leak(msg.content.strip())
    out_guard = inspect_output_guard(final_reply)
    if out_guard.is_blocked:
        final_reply = out_guard.blocked_message
    else:
        final_reply = enforce_single_question_budget(final_reply)
        import re
        if re.search(r"不想吃|不敢吃|想停|不吃了|沒在吃", actual_text):
            if not re.search(r"不能自己停|不可自行停|切勿自行停|不要擅自停|不能擅自停|不要自己停|不要停藥|不能停", final_reply):
                final_reply = final_reply.rstrip("。") + "。在醫師評估前，降血糖藥物千萬不能自己停掉喔，突然停藥血糖容易飆高有危險。"
    messages.append({"role": "assistant", "content": final_reply})

    def _bg_persist_hot(planner_hot, p_file, msgs_snapshot):
        try:
            if planner_hot.engine == "llm":
                update_from_planner_assessment(planner_hot, file_path=p_file)
            else:
                cur_rec = load_patient_record(p_file)
                llm_eval = evaluate_clinical_planner_llm(msgs_snapshot, cur_rec, client, model, timeout=3.0)
                if llm_eval.engine == "llm":
                    update_from_planner_assessment(llm_eval, file_path=p_file)
        except Exception:
            pass

    bg = threading.Thread(target=_bg_persist_hot, args=(planner, patient_file, list(messages)), daemon=True)
    bg.start()

    latency = time.time() - start_time
    log_turn(actual_text, final_reply, latency=latency, tool_used=tool_name_used)
    print(f"[LINE Webhook] 使用者 {user_id} 常規衛教回覆完成，總耗時: {latency:.2f} 秒 (模型: {model_display})")

    audit_log = build_audit_log(
        latency=latency,
        modality=input_modality,
        guard_passed=not out_guard.is_blocked,
        tool_used=tool_name_used,
        rag_hit=forced_evidence is not None,
        slots=planner.slots,
        talker_guidance=planner.talker_guidance,
        can_unlock=planner.can_unlock_summary_tool
    )

    full_reply_text = f"{prefix_note}{final_reply}\n\n{audit_log}"

    return {
        "reply_type": "text",
        "reply_text": full_reply_text,
        "flex_bubble": None,
        "qr_payload": None,
        "audit_log": audit_log
    }
