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
from typing import Any, Optional, Union, TYPE_CHECKING

from dotenv import load_dotenv
from openai import OpenAI

if TYPE_CHECKING:
    from llm_ablation_paper.workstream_1_technical_lead.harness.config import AblationConfig
else:
    try:
        from llm_ablation_paper.workstream_1_technical_lead.harness.config import AblationConfig  # type: ignore
    except Exception:  # TODO: harness not yet created — resilient fallback for backward compat
        AblationConfig = None  # type: ignore

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
from diabetes_chatbot.server.ablation_core import execute_ablation_turn as _core_execute, get_canonical_tool_snapshot

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
    image_path: Optional[Union[str, Path]] = None,
    ablation_config: Optional["AblationConfig"] = None,
) -> dict[str, Any]:
    """
    V2 臨床大腦入口：處理來自 LINE 的文字、語音或圖片，並產出回覆內容。
    Delegates core pipeline to ablation_core.execute_ablation_turn for unified logic.
    """
    start_time = time.time()
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

    # Delegate to shared core
    core_res = _core_execute(
        user_text=actual_text,
        patient_file=patient_file,
        messages=messages,
        ablation_config=ablation_config,
        talker_client=client,
        planner_client=client,
        model=model,
        temperature=0.3,
        max_tokens=250,
        image_path=Path(image_path) if image_path else None,
        modality=input_modality,
    )
    planner = core_res["planner"]
    final_reply = core_res["final_output"]
    latency = time.time() - start_time

    # Input guard blocked special audit
    if core_res["termination_reason"] == "COMMON_INPUT_BLOCK":
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
            "reply_text": f"{core_res['final_output']}\n\n{audit_log}",
            "flex_bubble": None,
            "qr_payload": None,
            "audit_log": audit_log
        }

    # Determine tool display and rag_hit
    called = core_res.get("called_tools", [])
    tool_display = ", ".join(called) if called else "無 (常規對話)"
    # If forced retrieval or search handbook second path, mark rag_hit
    # Core tracks via planner domain but we approximate: if called contains search_handbook or forced evidence existed
    rag_hit = "search_handbook" in called or core_res.get("tool_results") and any(r.get("tool")=="search_handbook" for r in core_res.get("tool_results",[]))
    # For card generation, tool_display update
    if core_res.get("flex_bubble") is not None or core_res.get("text_summary"):
        tool_display = "generate_visit_summary(產出門診預問診就醫備忘錄)"

    # Flex vs text decision
    flex_bubble = core_res.get("flex_bubble")
    qr_payload = core_res.get("qr_payload")
    if flex_bubble is not None and core_res["output_guard_result"].is_blocked:
        flex_bubble = None
        qr_payload = None
        reply_type = "text"
    elif flex_bubble is not None:
        reply_type = "flex"
    else:
        reply_type = "text"

    # Log and audit
    tool_used_log = tool_display
    log_turn(actual_text, final_reply, latency=latency, tool_used=tool_used_log)
    is_card = flex_bubble is not None
    if is_card:
        print(f"[LINE Webhook] 使用者 {user_id} 門診卡生成完成，總耗時: {latency:.2f} 秒 (模型: {model_display})")
    elif rag_hit:
        print(f"[LINE Webhook] 使用者 {user_id} 手冊衛教回覆完成，總耗時: {latency:.2f} 秒 (模型: {model_display})")
    else:
        print(f"[LINE Webhook] 使用者 {user_id} 常規衛教回覆完成，總耗時: {latency:.2f} 秒 (模型: {model_display})")

    guard_passed = not core_res["output_guard_result"].is_blocked if not core_res["termination_reason"]=="COMMON_INPUT_BLOCK" else True
    audit_log = build_audit_log(
        latency=latency,
        modality=input_modality,
        guard_passed=guard_passed,
        tool_used=tool_used_log,
        rag_hit=bool(rag_hit),
        slots=planner.slots,
        talker_guidance=planner.talker_guidance,
        can_unlock=planner.can_unlock_summary_tool
    )

    if reply_type == "flex":
        return {
            "reply_type": reply_type,
            "reply_text": final_reply,
            "flex_bubble": flex_bubble,
            "qr_payload": qr_payload,
            "audit_log": audit_log
        }
    else:
        full_reply_text = f"{prefix_note}{final_reply}\n\n{audit_log}"
        return {
            "reply_type": "text",
            "reply_text": full_reply_text,
            "flex_bubble": None,
            "qr_payload": None,
            "audit_log": audit_log
        }
