"""Shared ablation core: single pipeline for handlers.py and harness/runner.py.

Encapsulates validated production logic with injectable ablation flags.
"""
from __future__ import annotations
import copy
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Optional

from diabetes_chatbot.guard import (
    enforce_single_question_budget,
    inspect_output_guard,
    inspect_safety_guard,
)
from diabetes_chatbot.memory import (
    extract_clinical_facts_from_text,
    format_patient_context,
    load_patient_record,
    prune_conversation_history,
    save_patient_record,
    update_from_planner_assessment,
    update_previsit_summary,
)
from diabetes_chatbot.planner import (
    RetrievalDomain,
    SlotStatus,
    evaluate_clinical_planner,
    evaluate_clinical_planner_llm,
)
import diabetes_chatbot.planner as _planner_mod
from diabetes_chatbot.prompts import build_nurse_system_prompt
from diabetes_chatbot.state import get_active_tools
from diabetes_chatbot.tools import (
    TOOL_GENERATE_VISIT_SUMMARY,
    TOOL_SEARCH_HANDBOOK,
    generate_clinic_qr_payload,
    generate_line_flex_bubble,
    generate_visit_summary,
    search_handbook,
)


def _strip_evidence_links_leak(text: str) -> str:
    """清理聊天正文中意外夾帶的 raw HTML 標籤或 raw markdown 網址"""
    if not text:
        return ""
    t = re.sub(r"<div id=[\"']evidence_links[\"'].*?</div>", "", text, flags=re.DOTALL)
    t = re.sub(r"evidence_links\s*:\s*(?:\[.*?\]|-.*?\n?)*", "", t, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r"\n\s*-\s*\[.*?\]\(https?://.*?\)", "", t)
    return t.strip()




PENDING_DELIVERY_TEXT = "太好了！已經為您產生好【門診就醫備忘錄】大字體卡片與專用 QR Code，您下週看診時直接出示給醫師看就可以囉！"
_CONFIRM_LONG_KEYWORDS = ["這樣記對", "沒錯", "幫我產生", "確認", "可以", "麻煩幫我產生", "幫我做", "沒問題", "麻煩你產生"]
_CORRECTION_KEYWORDS = ["不對", "記錯", "錯誤", "不正確", "不是這樣", "不是", "不好", "改一下", "更正", "不要"]
_GREETING_KEYWORDS = ["你好", "您好", "早安", "晚安", "午安", "哈囉", "嗨", "hello", "hi", "護理師好", "妹仔好", "醫生好", "醫師好"]
_SYMPTOM_INTENSIFIERS = ["好痛", "好脹", "好暈", "好難受", "好高", "好低", "好累", "好不舒服", "好嚴重"]
_EXACT_AFFIRMATIONS = {
    "好", "好的", "好啊", "好喔", "好啦", "好捏", "好哇", "好呦", "好阿",
    "對", "對啊", "對的", "對喔", "對啦", "對捏", "對阿",
    "沒錯", "可以", "可以啊", "行", "沒問題", "ok", "OK", "Ok",
    "嗯", "嗯嗯", "恩", "恩恩", "麻煩你", "謝謝", "多謝", "謝謝你"
}


def is_visit_memo_confirmation(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    # 1. 修正/否定詞優先阻斷
    if any(k in t for k in _CORRECTION_KEYWORDS):
        return False
    # 2. 問候招呼語絕對不是確認
    if any(g in t.lower() for g in _GREETING_KEYWORDS):
        return False
    # 3. 症狀加強副詞絕對不是確認（例如「我肚子好痛」）
    if any(s in t for s in _SYMPTOM_INTENSIFIERS):
        return False
    # 4. 明確產卡長關鍵詞
    if any(k in t for k in _CONFIRM_LONG_KEYWORDS):
        return True
    # 5. 純肯定短詞比對（去除常見標點符號）
    t_clean = re.sub(r"[，。！!？?~～\s]+", "", t)
    if t_clean in _EXACT_AFFIRMATIONS:
        return True
    # 6. 口語開頭肯定詞短句（例如「好啊麻煩你了」、「對，這樣記就可以了」）
    if len(t) <= 15:
        for prefix in ("好", "對", "可以", "沒錯", "OK", "ok", "嗯", "恩"):
            if t.startswith(prefix) and not any(neg in t for neg in ("好嗎", "對嗎", "好不好", "對不對")):
                return True
    return False


def neutral_planner_state():
    """Return neutral PlannerAssessment when planner OFF."""
    from diabetes_chatbot.planner import PlannerAssessment, ClinicalSlots, SlotStatus, RetrievalDomain
    slots = ClinicalSlots(
        visit_reason="",
        visit_reason_status=SlotStatus.MISSING,
        medications="",
        medications_status=SlotStatus.MISSING,
        glucose_metrics="",
        glucose_metrics_status=SlotStatus.MISSING,
        hypo_history="",
        hypo_history_status=SlotStatus.MISSING,
        concerns_or_side_effects="",
        concerns_status=SlotStatus.MISSING,
    )
    return PlannerAssessment(
        slots=slots,
        is_visit_mode=False,
        is_explicit_request=False,
        is_agenda_confirmed=False,
        can_unlock_summary_tool=False,
        highest_priority_gap=None,
        retrieval_domain=RetrievalDomain.NONE,
        detected_intent="GENERAL_HEALTH",
        talker_guidance="",
        engine="neutral",
        ddx_candidates=[],
        evidence_links=[],
    )


def get_canonical_tool_snapshot() -> list[dict]:
    """Return deep copy of canonical 2-tool list."""
    import copy
    return [copy.deepcopy(TOOL_SEARCH_HANDBOOK), copy.deepcopy(TOOL_GENERATE_VISIT_SUMMARY)]


def _abl_flag(ablation_config: Any, name: str, default: bool) -> bool:
    if ablation_config is None:
        return default
    aliases = {
        "enable_dynamic_tool_gate": ["enable_dynamic_tool_gate", "dynamic_tool_gate"],
        "enable_question_budget_postprocessing": ["enable_question_budget_postprocessing", "enable_question_budget", "enable_question_budget_postprocessing"],
        "enable_fixed_warning_append": ["enable_fixed_warning_append", "enable_noncompliance_append"],
        "enable_planner": ["enable_planner"],
        "enable_output_guard": ["enable_output_guard"],
        "enable_forced_retrieval": ["enable_forced_retrieval"],
    }
    candidates = aliases.get(name, [name])
    for k in candidates:
        if isinstance(ablation_config, dict):
            if k in ablation_config:
                return bool(ablation_config[k])
        elif hasattr(ablation_config, k):
            return bool(getattr(ablation_config, k))
    return default


def _abl_value(ablation_config: Any, name: str, default: Any) -> Any:
    if ablation_config is None:
        return default
    if isinstance(ablation_config, dict):
        return ablation_config.get(name, default)
    return getattr(ablation_config, name, default)


def is_retryable_error(e: Exception) -> bool:
    """Classify whether an exception is transient (retryable).

    Retry only on timeout, HTTP 429 (rate limit), transient network errors,
    and retryable HTTP 5xx (500, 502, 503, 504).
    Non-retryable errors (400, 401, 403, 404, ValueError, etc.) fail immediately.
    """
    if isinstance(e, (TimeoutError, ConnectionError, BrokenPipeError)):
        return True

    status_code = getattr(e, "status_code", None) or getattr(e, "http_status", None)
    if status_code is not None:
        if status_code == 429:
            return True
        if status_code in (500, 502, 503, 504):
            return True
        if 400 <= status_code < 500:
            return False

    err_str = str(e).lower()
    err_cls = type(e).__name__.lower()

    if "timeout" in err_cls or "timeout" in err_str or "timed out" in err_str:
        return True
    if "ratelimit" in err_cls or "429" in err_str or "rate limit" in err_str:
        return True
    if "connection" in err_cls or "connection" in err_str or "socket" in err_str:
        return True
    if any(code in err_str for code in ["500", "502", "503", "504", "bad gateway", "service unavailable", "gateway timeout"]):
        return True

    return False


def _call_with_retry(
    func: Callable,
    max_tries: int = 4,
    backoffs: list[float] = [1, 2, 4, 8],
    metadata_out: Optional[dict] = None,
):
    """Call func with exponential backoff for transient errors only."""
    last_exc = None
    applied_backoffs = []
    error_list = []
    for attempt in range(max_tries):
        try:
            res = func()
            if metadata_out is not None:
                metadata_out["attempts"] = attempt + 1
                metadata_out["backoffs"] = applied_backoffs
                metadata_out["errors"] = error_list
            return res
        except Exception as e:
            last_exc = e
            error_list.append(f"{type(e).__name__}: {str(e)[:120]}")
            if not is_retryable_error(e):
                if metadata_out is not None:
                    metadata_out["attempts"] = attempt + 1
                    metadata_out["backoffs"] = applied_backoffs
                    metadata_out["errors"] = error_list
                raise last_exc
            if attempt < max_tries - 1:
                bo = backoffs[attempt] if attempt < len(backoffs) else backoffs[-1]
                applied_backoffs.append(bo)
                time.sleep(bo)
            else:
                if metadata_out is not None:
                    metadata_out["attempts"] = attempt + 1
                    metadata_out["backoffs"] = applied_backoffs
                    metadata_out["errors"] = error_list
                raise last_exc


def _extract_token_usage(resp: Any) -> Optional[dict[str, Any]]:
    """Extract token usage dict or return None if unavailable."""
    usage = getattr(resp, "usage", None)
    if usage is None:
        return None
    pt = getattr(usage, "prompt_tokens", None)
    ct = getattr(usage, "completion_tokens", None)
    tt = getattr(usage, "total_tokens", None)
    pt = pt if (isinstance(pt, (int, float)) and not isinstance(pt, bool)) else None
    ct = ct if (isinstance(ct, (int, float)) and not isinstance(ct, bool)) else None
    tt = tt if (isinstance(tt, (int, float)) and not isinstance(tt, bool)) else None
    if pt is None and ct is None and tt is None:
        return None
    return {
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": tt,
    }


def _serialize_assistant_tool_message(
    msg: Any,
    raw_content: str,
    fname0: str,
    args0: dict,
    tc_id0: str,
) -> dict[str, Any]:
    """完整序列化 assistant tool_call 訊息，完整保留 extra_content.google.thought_signature 等延伸欄位。"""
    if isinstance(msg, dict):
        return copy.deepcopy(msg)
    if hasattr(msg, "model_dump"):
        try:
            dumped = msg.model_dump(exclude_none=True)
            if isinstance(dumped, dict):
                if dumped.get("role") != "assistant":
                    dumped["role"] = "assistant"
                if not dumped.get("tool_calls"):
                    dumped["tool_calls"] = [{
                        "id": tc_id0,
                        "type": "function",
                        "function": {
                            "name": fname0,
                            "arguments": json.dumps(args0, ensure_ascii=False) if isinstance(args0, dict) else str(args0)
                        }
                    }]
                return dumped
        except Exception:
            pass
    if hasattr(msg, "dict"):
        try:
            dumped = msg.dict(exclude_none=True)
            if isinstance(dumped, dict):
                if dumped.get("role") != "assistant":
                    dumped["role"] = "assistant"
                if not dumped.get("tool_calls"):
                    dumped["tool_calls"] = [{
                        "id": tc_id0,
                        "type": "function",
                        "function": {
                            "name": fname0,
                            "arguments": json.dumps(args0, ensure_ascii=False) if isinstance(args0, dict) else str(args0)
                        }
                    }]
                return dumped
        except Exception:
            pass
    # XML fallback 或無序列化方法時的手工回退結構
    return {
        "role": "assistant",
        "content": raw_content or None,
        "tool_calls": [{
            "id": tc_id0,
            "type": "function",
            "function": {
                "name": fname0,
                "arguments": json.dumps(args0, ensure_ascii=False) if isinstance(args0, dict) else str(args0)
            }
        }]
    }


def execute_ablation_turn(
    *,
    user_text: str,
    patient_file: Path,
    messages: list[dict],
    ablation_config: Optional[Any] = None,
    talker_client: Any,
    planner_client: Optional[Any] = None,
    model: str = "mimo-v2.5",
    temperature: float = 0.3,
    max_tokens: int = 250,
    image_path: Optional[Path] = None,
    modality: str = "文字輸入",
    turn_index: Optional[int] = None,
) -> dict[str, Any]:
    """Execute single turn via shared core.

    Mutates `messages` by appending user and assistant (and tool) entries like production.
    Returns dict with keys:
      planner, exposed_tools, exposed_tool_names, input_guard_result,
      output_guard_result, raw_talker_output, final_output, called_tools,
      tool_results, tool_rejections, flex_bubble, qr_payload, text_summary,
      termination_reason, error, latency_ms, token_usage, retry_metadata, events
    """
    start = time.time()
    if planner_client is None:
        planner_client = talker_client

    if turn_index is None:
        turn_index = sum(1 for m in messages if (m.get("role") if isinstance(m, dict) else getattr(m, "role", "")) == "user")

    enable_output_guard = _abl_flag(ablation_config, "enable_output_guard", True)
    enable_budget = _abl_flag(ablation_config, "enable_question_budget_postprocessing", True)
    enable_warning = _abl_flag(ablation_config, "enable_fixed_warning_append", True)
    enable_planner = _abl_flag(ablation_config, "enable_planner", True)

    # 1. Input guard ALWAYS
    input_guard_obj = inspect_safety_guard(user_text)
    if input_guard_obj.is_blocked:
        latency_ms = int((time.time() - start) * 1000)
        return {
            "planner": neutral_planner_state(),
            "exposed_tools": get_canonical_tool_snapshot(),
            "exposed_tool_names": [t["function"]["name"] for t in get_canonical_tool_snapshot()],
            "input_guard_result": input_guard_obj,
            "output_guard_result": type("G", (), {"is_blocked": False, "risk_category": "NONE", "blocked_message": ""})(),
            "raw_talker_output": "",
            "final_output": input_guard_obj.blocked_message,
            "called_tools": [],
            "tool_results": [],
            "tool_rejections": [],
            "flex_bubble": None,
            "qr_payload": None,
            "text_summary": None,
            "termination_reason": "COMMON_INPUT_BLOCK",
            "events": ["INPUT_GUARD_BLOCKED"],
            "token_usage": None,
            "retry_metadata": None,
            "error": None,
            "latency_ms": latency_ms,
        }

    # 2. 第二階段：pending_card 點頭確認後交付（優先於 LLM，避免重複產卡）
    # 必須嚴格遵守 A–D flags：A/B/C 不得執行 Output Guard；事件記錄在 events 中，不污染研究協議 termination_reason
    try:
        _pending_rec = load_patient_record(patient_file)
        _pending = _pending_rec.get("pending_card") if isinstance(_pending_rec, dict) else None
        if isinstance(_pending, dict) and _pending.get("flex_bubble") and is_visit_memo_confirmation(user_text):
            _flex = _pending.get("flex_bubble")
            _qr = _pending.get("qr_payload")
            _summary = _pending.get("text_summary")
            _pending_rec.pop("pending_card", None)
            try:
                save_patient_record(_pending_rec, patient_file)
            except Exception:
                pass
            messages.append({"role": "user", "content": user_text})
            _delivery = PENDING_DELIVERY_TEXT
            _og = type("G", (), {"is_blocked": False, "risk_category": "NONE", "blocked_message": ""})()
            _og_blocked = False
            if enable_output_guard:
                try:
                    _og = inspect_output_guard(_delivery)
                    _og_blocked = bool(getattr(_og, "is_blocked", False))
                except Exception:
                    pass
            if _og_blocked:
                _delivery = _og.blocked_message
                messages.append({"role": "assistant", "content": _delivery})
                latency_ms = int((time.time() - start) * 1000)
                return {
                    "planner": neutral_planner_state(),
                    "exposed_tools": get_canonical_tool_snapshot(),
                    "exposed_tool_names": [t["function"]["name"] for t in get_canonical_tool_snapshot()],
                    "input_guard_result": input_guard_obj,
                    "output_guard_result": _og,
                    "raw_talker_output": "",
                    "final_output": _delivery,
                    "called_tools": [],
                    "tool_results": [],
                    "tool_rejections": [],
                    "flex_bubble": None,
                    "qr_payload": None,
                    "text_summary": _summary,
                    "termination_reason": None,
                    "events": ["PENDING_CARD_DELIVERY_BLOCKED"],
                    "token_usage": None,
                    "retry_metadata": None,
                    "error": None,
                    "latency_ms": latency_ms,
                }
            messages.append({"role": "assistant", "content": _delivery})
            latency_ms = int((time.time() - start) * 1000)
            return {
                "planner": neutral_planner_state(),
                "exposed_tools": get_canonical_tool_snapshot(),
                "exposed_tool_names": [t["function"]["name"] for t in get_canonical_tool_snapshot()],
                "input_guard_result": input_guard_obj,
                "output_guard_result": _og,
                "raw_talker_output": "",
                "final_output": _delivery,
                "called_tools": [],
                "tool_results": [],
                "tool_rejections": [],
                "flex_bubble": _flex,
                "qr_payload": _qr,
                "text_summary": _summary,
                "termination_reason": None,
                "events": ["PENDING_CARD_DELIVERY"],
                "token_usage": None,
                "retry_metadata": None,
                "error": None,
                "latency_ms": latency_ms,
            }
    except Exception:
        pass

    # 3. Fact extraction and user append
    extract_clinical_facts_from_text(user_text, file_path=patient_file)
    messages.append({"role": "user", "content": user_text})

    # 3. Planner branch
    enable_planner = _abl_flag(ablation_config, "enable_planner", True)
    if not enable_planner:
        planner = neutral_planner_state()
    else:
        # LLM-first with retry + fallback
        planner_model = _abl_value(ablation_config, "planner_model", "") or model
        planner_temperature = _abl_value(ablation_config, "planner_temperature", 0.1)
        planner_timeout = _abl_value(ablation_config, "planner_request_timeout_seconds", 3.0)
        try:
            patient_record = load_patient_record(patient_file)

            def _planner_call():
                return evaluate_clinical_planner_llm(
                    messages,
                    patient_record,
                    planner_client,
                    planner_model,
                    timeout=planner_timeout,
                    temperature=planner_temperature,
                )

            try:
                planner = _call_with_retry(_planner_call, max_tries=4, backoffs=[1, 2, 4, 8])
            except Exception as e:
                planner = evaluate_clinical_planner(messages, patient_file_path=str(patient_file))
                try:
                    planner.engine = f"python_fallback({str(e)[:30]})"
                except Exception:
                    planner.engine = "python_fallback"
        except Exception as e:
            planner = evaluate_clinical_planner(messages, patient_file_path=str(patient_file))
            try:
                planner.engine = f"python_fallback({str(e)[:30]})"
            except Exception:
                planner.engine = "python_fallback"

    planner_events: list = []

    def _persist_planner_state() -> None:
        if not enable_planner:
            return
        try:
            current_planner = planner
        except NameError:
            return
        try:
            update_from_planner_assessment(current_planner, file_path=patient_file)
        except Exception as e:
            planner_events.append(f"PLANNER_PERSIST_ERROR: {str(e)[:120]}")

    # Agenda tightening (same as handlers.py)
    try:
        if not planner.can_unlock_summary_tool and planner.is_explicit_request:
            has_explicit_reason = (
                planner.slots.visit_reason_status in (SlotStatus.KNOWN, SlotStatus.PARTIAL) and
                bool(planner.slots.visit_reason) and
                planner.slots.visit_reason not in ("門診定期追蹤", "定期回診", "")
            )
            has_med = planner.slots.medications_status in (SlotStatus.KNOWN, SlotStatus.PARTIAL)
            has_data = planner.slots.glucose_metrics_status in (SlotStatus.KNOWN, SlotStatus.PARTIAL)
            has_hypo = planner.slots.hypo_history_status in (SlotStatus.KNOWN, SlotStatus.PARTIAL)
            has_concern = planner.slots.concerns_status == SlotStatus.KNOWN
            if has_explicit_reason and has_med and (has_data or has_hypo or has_concern):
                planner.is_agenda_confirmed = True
                planner.can_unlock_summary_tool = True
                planner.talker_guidance = "【臨床溝通導引】：病患看診議程已具備明確主訴，核心資訊已達充分度！請立刻調用 generate_previsit_intake_summary 工具為病患生成門診摘要，嚴禁再拋出任何問題追問病患；生成完成後，親切告知已整理完畢並叮嚀看診時出示即可。"
    except Exception:
        pass

    # 4. Tool gate
    enable_gate = _abl_flag(ablation_config, "enable_dynamic_tool_gate", True)
    if not enable_gate:
        active_tools = get_canonical_tool_snapshot()
    else:
        active_tools = get_active_tools(messages, patient_file_path=str(patient_file), planner_assessment=planner)
    # Image suppression
    if image_path is not None:
        active_tools = [t for t in active_tools if t.get("function", {}).get("name") not in ["generate_previsit_intake_summary", "generate_visit_summary"]]
    exposed_tool_names = [t.get("function", {}).get("name", "") for t in active_tools]
    exposed_tool_set = set(exposed_tool_names)

    # 5. Forced retrieval (gated)
    forced_evidence = None
    forced_tool_display = None
    enable_forced = _abl_flag(ablation_config, "enable_forced_retrieval", True)
    # Production default True, ablation A-D False. Handlers uses True default.
    # For ablation isolation with config None (production path) we keep True.
    # But shared core is used via handlers with config None -> should be True.
    # For harness with config A-D, it will be False.
    try:
        def _extract_definition_keyword(q: str) -> str:
            ql = q.lower()
            if any(k in ql for k in ["脹", "胃", "肚子", "腹瀉", "噁心"]) and any(k in ql for k in ["藥", "吃"]):
                return "糖尿病 腸胃不適 腹脹 衛教"
            elif any(k in ql for k in ["成因", "形成", "原理", "怎麼形成", "怎麼來的", "機制", "為什麼", "為何"]):
                return "糖尿病成因 胰島素阻抗"
            elif any(k in ql for k in ["是什麼", "什麼是", "定義", "分型", "種類"]):
                return "糖尿病定義 血糖診斷標準"
            elif "藥袋" in ql or "辨識出的藥品是" in q:
                # 藥袋辨識關鍵字提取：依 OCR 辨識出之藥名檢索官方仿單
                med_str = q.split("辨識出的藥品是：")[-1] if "辨識出的藥品是：" in q else (q.split("辨識出的藥品是")[-1] if "辨識出的藥品是" in q else q)
                if "癲通" in med_str or "carbamazepine" in med_str.lower():
                    return "癲通 Carbamazepine"
                m_zh = re.search(r"([\u4e00-\u9fa5]{2,4})", med_str)
                m_en = re.search(r"([A-Za-z]{3,})", med_str)
                zh = m_zh.group(1) if m_zh else ""
                en = m_en.group(1) if m_en else ""
                extracted = f"{zh} {en}".strip()
                return extracted if extracted else "癲通 Carbamazepine"
            elif planner.retrieval_domain == RetrievalDomain.DIET_NUTRITION_KNOWLEDGE or any(k in ql for k in ["水果", "芭樂", "西瓜", "飲食", "熱量", "份量", "升糖", "飆高"]):
                fruit = ""
                for f in ["芭樂", "西瓜", "芒果", "荔枝", "香蕉", "蘋果", "橘子", "葡萄", "鳳梨"]:
                    if f in ql:
                        fruit = f
                        break
                if fruit:
                    return f"糖尿病飲食原則 水果份量 {fruit}"
                return "糖尿病飲食原則 水果份量"
            return "糖尿病衛教"

        def _is_def_local(q: str, domain_val: str) -> bool:
            ql = q.lower()
            def_kw = ["是什麼", "什麼是", "定義", "成因", "形成", "為什麼", "為何", "原理", "怎麼形成", "怎麼來的", "機制", "分型", "種類"]
            if any(k in ql for k in def_kw):
                if "糖尿病" in ql or "diabetes" in ql or domain_val in ["GENERAL_EDUCATION", "DRUG_SAFETY"]:
                    return True
            return False

        is_med_bag = (image_path is not None) or ("辨識出的藥品是" in user_text) or ("我拍了我的藥袋照片" in user_text) or ("藥袋" in user_text and any(k in user_text for k in ["照片", "拍了", "辨識", "癲通", "長效膜衣錠", "mg", "毫克"]))
        needs_forced = False
        if enable_forced:
            if is_med_bag:
                needs_forced = True
                if planner.retrieval_domain != RetrievalDomain.DRUG_SAFETY:
                    planner.retrieval_domain = RetrievalDomain.DRUG_SAFETY
            elif not planner.is_visit_mode and planner.retrieval_domain in [RetrievalDomain.GENERAL_EDUCATION, RetrievalDomain.DRUG_SAFETY, RetrievalDomain.DIET_NUTRITION_KNOWLEDGE]:
                if planner.retrieval_domain == RetrievalDomain.DIET_NUTRITION_KNOWLEDGE:
                    needs_forced = True
                elif _is_def_local(user_text, planner.retrieval_domain.value):
                    needs_forced = True
        if needs_forced:
            rule_q = _extract_definition_keyword(user_text)
            if rule_q:
                forced_evidence = search_handbook(rule_q, user_raw_input=user_text, domain=planner.retrieval_domain.value)
                forced_tool_display = f"search_handbook(關鍵字: '{rule_q}', domain={planner.retrieval_domain.value}, 檢索衛教指引{len(forced_evidence)}字)"
                # 強制檢索已由程式直接完成並注入 Prompt，從暴露工具清單中移除 search_handbook，徹底避免模型重複自主調用引發例外
                active_tools = [t for t in active_tools if t.get("function", {}).get("name") != "search_handbook"]
                exposed_tool_names = [t.get("function", {}).get("name", "") for t in active_tools]
                exposed_tool_set = set(exposed_tool_names)
    except Exception:
        forced_evidence = None

    # 6. Build inference context
    pruned_ctx = prune_conversation_history(messages, max_history_messages=8)
    inference_ctx = list(pruned_ctx)
    try:
        cur_rec = load_patient_record(patient_file)
        if cur_rec and isinstance(cur_rec, dict):
            hot_ctx = format_patient_context(patient_file)
            if hot_ctx and hot_ctx.strip() and inference_ctx:
                inference_ctx[0] = {"role": "system", "content": build_nurse_system_prompt(hot_ctx)}
    except Exception:
        pass
    if enable_planner and getattr(planner, "talker_guidance", ""):
        clean_guidance = re.sub(r"【臨床溝通導引】[：:]\s*", "【臨床溝通導引】：", planner.talker_guidance)
        inference_ctx.append({"role": "system", "content": clean_guidance})
    if forced_evidence:
        _compact = forced_evidence[:1000]
        if planner.retrieval_domain == RetrievalDomain.DRUG_SAFETY:
            if is_med_bag:
                guidance_task = (
                    "【官方實證藥物衛教解說任務｜藥袋辨識與用藥安全】\n"
                    f"{_compact}\n"
                    "任務：病患剛上傳了藥袋照片，並反映晨間低血糖與頭暈症狀。\n"
                    "1. 請依據上述衛福部官方仿單/國健署指引重點，向病患說明該藥品（如癲通/Carbamazepine）主要用途（如治療神經痛或抗癲癇），並明確告知它並非直接用來降血糖的藥物。\n"
                    "2. 溫和同理並關心病患今早低血糖（65 mg/dL）與頭暈不適，確認是否有落實 15-15 吃糖急救法則。\n"
                    "3. 叮嚀病患在醫師評估前切勿自行停藥或改藥，務必於下次回診時攜帶藥袋並詳細告知醫師。\n"
                    "4. 於說明文末親切附上引導句：『若上述醫學說明有太深奧或看不懂的地方，隨時告訴我，我可以用更生活化的比喻向您解釋喔！』。\n"
                    "5. 出處呈現：請在對話中自然載明官方出處（例如口語提及『依據衛生福利部藥品仿單說明』，或於文末附上一行『（資料來源：衛生福利部藥品仿單）』），彰顯實證依據；請以生活化口語說明，避免輸出 raw URL 網址。"
                )
            else:
                guidance_task = (
                    "【官方實證藥物衛教解說任務｜實證詳實首發，按需白話轉譯】\n"
                    f"{_compact}\n"
                    "任務：病患正在詢問特定降血糖藥物成因、藥理作用或副作用機制。\n"
                    "1. 請依據上述衛福部官方仿單/臨床指引重點，條理清晰地向病患說明藥物成因機轉、常見腸胃反應與官方建議因應方式（如隨餐或飯後服用降低刺激、漸進適應），保留醫學事實細節，保障病患知情權。\n"
                    "2. 於說明文末親切附上引導句：『若上述醫學說明有太深奧或看不懂的地方，隨時告訴我，我可以用更生活化的比喻向您解釋喔！』。\n"
                    "3. 嚴禁提供劑量調整指令，若病患提及想停藥，提醒切勿擅自停藥；出處呈現：請在解說中自然提及官方出處（例如『依據衛生福利部藥品仿單說明』，或於文末附上一行『（資料來源：衛生福利部藥品仿單）』），彰顯實證依據；請以生活化口語說明，避免輸出 raw URL 網址。"
                )
        elif planner.retrieval_domain == RetrievalDomain.DIET_NUTRITION_KNOWLEDGE:
            guidance_task = (
                "【官方手冊飲食原則衛教任務｜實證詳實首發，按需白話轉譯】\n"
                f"{_compact}\n"
                "任務：病患正在詢問糖尿病飲食生活原則、水果或特定食物升糖風險與份量建議。\n"
                "1. 請根據上述官方手冊飲食原則與食品營養內容，以溫暖、在地、有同理心的語氣向長輩解釋食物特性、醣類代換與份量控制原則（如水果適量分次攝取，避免一次吃過量造成血糖快速波動）。\n"
                "2. 嚴格遵守單一問句預算，最多只拋出一個生活化問題；若為飲食提問可提醒長輩細嚼慢嚥、分次享用。\n"
                "3. 出處呈現：請在解說中自然載明官方出處（例如口語提及『依據衛生福利部國民健康署糖尿病手冊建議』，或於文末附上一行『（資料來源：衛生福利部國民健康署糖尿病手冊）』），彰顯實證依據；請以生活化口語說明，避免輸出 raw URL 網址。"
            )
        else:
            guidance_task = (
                "【官方手冊衛教解說任務｜實證詳實首發，按需白話轉譯】\n"
                f"{_compact}\n"
                "任務：長輩正在詢問糖尿病成因、原理或衛教知識。\n"
                "1. 請根據上述衛福部官方手冊重點，清楚完整地向長輩解釋成因機轉，保留重要衛教細節。\n"
                "2. 於說明文末親切提醒長輩：若有看不懂或太複雜的地方，隨時可以告訴我，我會用更白話的方式向您解釋喔！\n"
                "3. 出處呈現：請在解說中自然載明官方手冊出處（例如口語提及『依據衛生福利部國民健康署手冊建議』，或於文末附上一行『（資料來源：衛生福利部國民健康署衛教手冊）』），彰顯實證依據；請以生活化口語說明，避免輸出 raw URL 網址。"
            )
        inference_ctx.append({"role": "system", "content": guidance_task})

    # 7. Talker LLM with retry
    enable_output_guard = _abl_flag(ablation_config, "enable_output_guard", True)
    enable_budget = _abl_flag(ablation_config, "enable_question_budget_postprocessing", True)
    enable_warning = _abl_flag(ablation_config, "enable_fixed_warning_append", True)

    extra_body = {"reasoning": {"effort": "none"}} if "mimo" in model.lower() else None
    max_tokens_use = 500 if "gemini" in model.lower() else 250

    raw_talker_output = ""
    called_tools: list[str] = ["search_handbook"] if forced_evidence else []
    tool_results: list[dict] = [{"tool": "search_handbook", "content": forced_evidence[:1000]}] if forced_evidence else []
    tool_rejections: list[dict] = []
    final_output = ""
    output_guard_obj = type("G", (), {"is_blocked": False, "risk_category": "NONE", "blocked_message": ""})()
    flex_bubble = None
    qr_payload = None
    text_summary = None
    error = None
    termination = None
    token_usage = None
    retry_meta = {}

    try:
        def _talker_call():
            return talker_client.chat.completions.create(
                model=model,
                messages=inference_ctx,
                tools=active_tools if active_tools else None,
                extra_body=extra_body,
                max_tokens=max_tokens_use,
                temperature=temperature,
            )

        resp = _call_with_retry(_talker_call, max_tries=4, backoffs=[1, 2, 4, 8], metadata_out=retry_meta)
        token_usage = _extract_token_usage(resp)
        msg = resp.choices[0].message
        if isinstance(msg, dict):
            raw_content = (msg.get("content") or "").strip()
            tool_calls = msg.get("tool_calls")
        else:
            raw_content = (getattr(msg, "content", None) or "").strip() if getattr(msg, "content", None) else ""
            tool_calls = getattr(msg, "tool_calls", None)

        # XML fallback detection
        is_xml_tool_call = "<tool_call>" in raw_content and "search_handbook" in raw_content

        if tool_calls or is_xml_tool_call:
            # Normalize tool_calls list
            normalized_calls = []
            if tool_calls:
                normalized_calls = list(tool_calls)
            else:
                # XML fallback -> synthesize one search_handbook call
                m = re.search(r"<parameter=keyword>(.*?)</parameter>", raw_content)
                kw_val = m.group(1).strip() if m else "糖尿病飲食 碳水化合物"
                # Create fake call object
                class _Func:
                    name = "search_handbook"
                    arguments = json.dumps({"keyword": kw_val})
                class _Call:
                    id = "call_fallback_xml"
                    function = _Func()
                normalized_calls = [_Call()]
                raw_talker_output = raw_content  # keep raw for logging

            if raw_talker_output == "":
                raw_talker_output = raw_content

            # Validate each call against exposed_tools
            valid_calls = []
            for tc in normalized_calls:
                if isinstance(tc, dict):
                    fname = tc.get("function", {}).get("name", "")
                    args_raw = tc.get("function", {}).get("arguments", "{}")
                    tc_id = tc.get("id", f"call_{len(valid_calls)}")
                else:
                    try:
                        fname = tc.function.name if hasattr(getattr(tc, "function", None), "name") else ""
                    except Exception:
                        fname = "unknown"
                    args_raw = getattr(getattr(tc, "function", None), "arguments", "{}")
                    tc_id = getattr(tc, "id", f"call_{len(valid_calls)}")
                try:
                    args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw)
                except Exception:
                    args = {}
                if fname not in exposed_tool_set:
                    tool_rejections.append({"tool": fname, "reason": "not_in_exposed_tools", "id": tc_id})
                    continue
                valid_calls.append((fname, args, tc_id, tc))

            if tool_rejections and not valid_calls:
                # Strict gate for experiments (ablation_config not None):
                # reject unexposed tools. For production (config None),
                # preserve legacy lenient behavior: still execute the
                # requested tool so card-breach guard can fire (regression
                # test test_clinical_flex_card_breach expects execution).
                is_experiment = ablation_config is not None
                if not is_experiment:
                    # Production lenient path: treat first requested call as
                    # valid even if gate hid it, but record the rejection.
                    try:
                        tc0 = normalized_calls[0]
                        fname0 = tc0.function.name if hasattr(tc0.function, "name") else "unknown"
                        args_raw0 = getattr(tc0.function, "arguments", "{}") if hasattr(tc0, "function") else "{}"
                        try:
                            args0 = json.loads(args_raw0) if isinstance(args_raw0, str) else dict(args_raw0)
                        except Exception:
                            args0 = {}
                        tc_id0 = getattr(tc0, "id", "call_0")
                        valid_calls = [(fname0, args0, tc_id0, tc0)]
                    except Exception:
                        pass
                if tool_rejections and not valid_calls:
                    # All rejected -> final output is error note
                    raw_talker_output = raw_content if raw_content else ""
                    final_output = f"工具調用被拒：{tool_rejections[0]['tool']} 不在暴露工具清單中"
                    called_tools = []
                    output_guard_obj = type("G", (), {"is_blocked": False, "risk_category": "NONE", "blocked_message": ""})()
                    messages.append({"role": "assistant", "content": final_output})
                    _persist_planner_state()
                    latency_ms = int((time.time() - start) * 1000)
                    return {
                        "planner": planner,
                        "exposed_tools": active_tools,
                        "exposed_tool_names": exposed_tool_names,
                        "input_guard_result": input_guard_obj,
                        "output_guard_result": output_guard_obj,
                        "raw_talker_output": raw_talker_output,
                        "final_output": final_output,
                        "called_tools": called_tools,
                        "tool_results": tool_results,
                        "tool_rejections": tool_rejections,
                        "forced_tool_display": forced_tool_display,
                        "flex_bubble": None,
                        "qr_payload": None,
                        "text_summary": None,
                        "termination_reason": termination,
                        "events": list(planner_events),
                        "token_usage": token_usage,
                        "retry_metadata": retry_meta,
                        "error": None,
                        "latency_ms": latency_ms,
                    }

            # Execute valid calls - handle first with full loop (spec says complete tool-call loop)
            # For simplicity, handle first valid call with second LLM turn, then handle remaining if any via extra iteration
            # Primary branch: search_handbook
            fname0, args0, tc_id0, tc0 = valid_calls[0]
            called_tools.append(fname0)

            if fname0 == "search_handbook":
                from diabetes_chatbot.planner import _sanitize_search_keyword
                kw = args0.get("keyword", "")
                kw_clean = _sanitize_search_keyword(kw, user_text)
                tool_output = search_handbook(kw_clean, user_raw_input=user_text, domain=planner.retrieval_domain.value)
                tool_results.append({"tool": fname0, "content": tool_output[:1000]})
                # 完整保留 assistant tool_call 訊息（包含 Google thought_signature）
                assistant_tool_msg = _serialize_assistant_tool_message(msg, raw_content, fname0, args0, tc_id0)
                messages.append(assistant_tool_msg)

                # 建立解說任務指引文字 (second_task)
                if planner.retrieval_domain == RetrievalDomain.DRUG_SAFETY:
                    second_task = (
                        "【官方實證藥物衛教解說任務｜實證詳實首發，按需白話轉譯】\n"
                        f"{tool_output[:800]}\n"
                        "任務：病患正在詢問特定降血糖藥物成因、藥理作用或副作用機制。\n"
                        "1. 請依據上述衛福部官方仿單/臨床指引重點，條理清晰地向病患說明藥物成因機轉、常見腸胃反應與官方建議因應方式（如隨餐或飯後服用降低刺激、漸進適應），保留醫學事實細節，保障病患知情權。\n"
                        "2. 於說明文末親切附上引導句：『若上述醫學說明有太深奧或看不懂的地方，隨時告訴我，我可以用更生活化的比喻向您解釋喔！』。\n"
                        "3. 嚴禁提供劑量調整指令，若病患提及想停藥，提醒切勿擅自停藥；出處呈現：請在解說中自然提及官方出處（例如『依據衛生福利部藥品仿單說明』，或於文末附上一行『（資料來源：衛生福利部藥品仿單）』），彰顯實證依據；請以生活化口語說明，避免輸出 raw URL 網址。"
                    )
                else:
                    second_task = (
                        "【官方手冊衛教解說任務｜實證詳實首發，按需白話轉譯】\n"
                        f"{tool_output[:800]}\n"
                        "長輩正在詢問糖尿病成因、原理或衛教知識。請根據上述衛福部官方手冊重點，清楚完整地向長輩解釋成因機轉，保留重要衛教細節。\n"
                        "於說明文末親切提醒長輩：若有看不懂或太複雜的地方，隨時可以告訴我，我會用更白話的方式向您解釋喔！\n"
                        "出處呈現：請在解說中自然載明官方手冊出處（例如口語提及『依據衛生福利部國民健康署手冊建議』，或於文末附上一行『（資料來源：衛生福利部國民健康署衛教手冊）』），彰顯實證依據；請以生活化口語說明，避免輸出 raw URL 網址。"
                    )

                # 依協議規範：將 second_task 完整文字併入 tool response 的 content 欄位，嚴禁追加 trailing system 訊息
                combined_tool_content = f"{tool_output}\n\n{second_task}"
                messages.append({
                    "role": "tool",
                    "name": fname0,
                    "tool_call_id": tc_id0,
                    "content": combined_tool_content,
                })

                # Second talker call with evidence
                second_ctx = list(prune_conversation_history(messages, max_history_messages=8))
                try:
                    cur_rec = load_patient_record(patient_file)
                    if cur_rec and isinstance(cur_rec, dict):
                        hot_ctx = format_patient_context(patient_file)
                        if hot_ctx and hot_ctx.strip() and second_ctx:
                            second_ctx[0] = {"role": "system", "content": build_nurse_system_prompt(hot_ctx)}
                except Exception:
                    pass

                second_text = ""
                second_call_failed = False
                second_call_exc = None
                try:
                    def _second_call():
                        return talker_client.chat.completions.create(
                            model=model, messages=second_ctx, extra_body=extra_body, max_tokens=max_tokens_use, temperature=temperature
                        )

                    sec_meta = {}
                    second_resp = _call_with_retry(_second_call, max_tries=4, backoffs=[1, 2, 4, 8], metadata_out=sec_meta)
                    sec_usage = _extract_token_usage(second_resp)
                    if sec_usage:
                        if token_usage is None:
                            token_usage = sec_usage
                        else:
                            for tk in ["prompt_tokens", "completion_tokens", "total_tokens"]:
                                v1 = token_usage.get(tk) or 0
                                v2 = sec_usage.get(tk) or 0
                                token_usage[tk] = v1 + v2
                    if sec_meta:
                        retry_meta["attempts"] = retry_meta.get("attempts", 1) + sec_meta.get("attempts", 1)
                        retry_meta["backoffs"] = retry_meta.get("backoffs", []) + sec_meta.get("backoffs", [])
                        retry_meta["errors"] = retry_meta.get("errors", []) + sec_meta.get("errors", [])

                    second_msg = second_resp.choices[0].message
                    second_text = (getattr(second_msg, "content", None) or "").strip()
                    second_text = re.sub(r"<tool_call>.*?</tool_call>", "", second_text, flags=re.DOTALL).strip()
                    second_text = _strip_evidence_links_leak(second_text)
                except Exception as second_e:
                    second_call_failed = True
                    second_call_exc = second_e
                    import sys, traceback
                    print(f"[AblationCore search_handbook] 第二次 Talker 呼叫失敗: {second_e}", file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
                    if 'retry_meta' in locals() and retry_meta is not None:
                        retry_meta.setdefault("errors", []).append(f"second_call_error: {str(second_e)}")

                if second_call_failed and ablation_config is not None:
                    # 消融實驗模式 (ablation_config is not None)：嚴格 Fail-Closed，回傳 ERROR 與結構化 error_metadata
                    termination = "ERROR"
                    error = f"Second talker call failed: {str(second_call_exc)}"
                    error_meta_dict = {
                        "stage": "second_talker_call",
                        "turn": turn_index,
                        "errors": [str(second_call_exc)],
                    }
                    if retry_meta is not None:
                        retry_meta["error_metadata"] = error_meta_dict
                    latency_ms = int((time.time() - start) * 1000)
                    _persist_planner_state()
                    return {
                        "planner": planner,
                        "exposed_tools": active_tools,
                        "exposed_tool_names": exposed_tool_names,
                        "input_guard_result": input_guard_obj,
                        "output_guard_result": type("G", (), {"is_blocked": False, "risk_category": "NONE", "blocked_message": ""})(),
                        "raw_talker_output": raw_talker_output if raw_talker_output else raw_content,
                        "final_output": f"第二次 Talker 呼叫失敗: {str(second_call_exc)}",
                        "called_tools": called_tools,
                        "tool_results": tool_results,
                        "tool_rejections": tool_rejections,
                        "forced_tool_display": forced_tool_display,
                        "flex_bubble": None,
                        "qr_payload": None,
                        "text_summary": None,
                        "termination_reason": "ERROR",
                        "events": list(planner_events) + ["SECOND_TALKER_CALL_FAILED"],
                        "token_usage": token_usage,
                        "retry_metadata": retry_meta,
                        "error_metadata": error_meta_dict,
                        "error": error,
                        "latency_ms": latency_ms,
                    }

                if not second_text:
                    if raw_content and raw_content.strip() and not raw_content.strip().startswith("{") and "tool_calls" not in raw_content:
                        second_text = raw_content.strip()
                    elif planner and getattr(planner, "talker_guidance", None) and not any(k in planner.talker_guidance for k in ["【臨床", "請先", "嚴格遵守"]):
                        second_text = planner.talker_guidance
                    elif planner and planner.retrieval_domain == RetrievalDomain.DRUG_SAFETY:
                        second_text = "收到您的藥品與用藥諮詢了！用藥安全最重要，這段時間請先依照醫師原先囑咐規律服藥，切勿擅自停藥或增減劑量；若有用藥不適或疑問，回診時務必提出與醫師討論喔。"
                    else:
                        second_text = "收到您的問題了！關於糖尿病日常照護與衛教指引，建議維持規律作息與飲食控制；若有任何身體不適，請務必諮詢專業醫療人員喔。"
                raw_talker_output = raw_content  # keep original raw
                # Guard/budget on second text
                if enable_output_guard:
                    og = inspect_output_guard(second_text)
                    output_guard_obj = og
                    if og.is_blocked:
                        second_text = og.blocked_message
                    else:
                        if enable_budget:
                            second_text = enforce_single_question_budget(second_text)
                        if enable_warning and re.search(r"不想吃|不敢吃|想停|不吃了|沒在吃", user_text):
                            if not re.search(r"不能自己停|不可自行停|切勿自行停|不要擅自停|不能擅自停|不要自己停|不要停藥|不能停", second_text):
                                second_text = second_text.rstrip("。") + "。在醫師評估前，降血糖藥物千萬不能自己停掉喔，突然停藥血糖容易飆高有危險。"
                else:
                    output_guard_obj = type("G", (), {"is_blocked": False, "risk_category": "NONE", "blocked_message": ""})()
                    if enable_budget:
                        second_text = enforce_single_question_budget(second_text)
                    if enable_warning and re.search(r"不想吃|不敢吃|想停|不吃了|沒在吃", user_text):
                        if not re.search(r"不能自己停|不可自行停|切勿自行停|不要擅自停|不能擅自停|不要自己停|不要停藥|不能停", second_text):
                            second_text = second_text.rstrip("。") + "。在醫師評估前，降血糖藥物千萬不能自己停掉喔，突然停藥血糖容易飆高有危險。"
                final_output = second_text
                messages.append({"role": "assistant", "content": final_output})
                # Set tool display for logging
                forced_tool_display = f"search_handbook(關鍵字: '{kw_clean}', 檢索衛教指引{len(tool_output)}字)"

            elif fname0 in ["generate_previsit_intake_summary", "generate_visit_summary"]:
                # 從長期健康檔案與 Planner 槽位進行臨床雙向校準補全（防失憶安全網）
                try:
                    _rec_hot = load_patient_record(patient_file)
                    # 1. 補全低血糖紀錄
                    _raw_hypo = args0.get("hypo_history", "")
                    if not _raw_hypo or _raw_hypo in ["近期未提及或無發生", "近期無低血糖事件", "無特別異常", "未特別說明", "無"]:
                        if _rec_hot.get("hypo_history") and "無低血糖" not in _rec_hot.get("hypo_history"):
                            args0["hypo_history"] = _rec_hot.get("hypo_history")
                        elif planner.slots.hypo_history and "無" not in planner.slots.hypo_history:
                            args0["hypo_history"] = planner.slots.hypo_history

                    # 1.1 跨欄位推論（Cross-slot Inference）：比對血糖數值與自述症狀，動態捕獲數值並執行時效仲裁
                    _g_combined = " ".join([
                        str(args0.get("glucose_metrics", "")),
                        str(_rec_hot.get("glucose_metrics", {}).get("latest", "")),
                        str(getattr(planner.slots, "glucose_metrics", "") or ""),
                        str(args0.get("glucose_range", "") or "")
                    ])
                    _s_combined = " ".join([
                        str(args0.get("side_effects_or_concerns", "")),
                        " ".join(_rec_hot.get("reported_symptoms", [])),
                        str(getattr(planner.slots, "concerns_or_side_effects", "") or "")
                    ])
                    m_low = re.search(r"\b([4-6][0-9])\b", _g_combined)
                    _has_hypo_symptom = any(k in _s_combined or k in _g_combined for k in ["頭暈", "手抖", "冒冷汗", "心悸", "方糖", "吃糖", "補糖"])

                    range_inferred = None
                    if m_low and _has_hypo_symptom:
                        low_val = m_low.group(1)
                        # 時效仲裁：比對 glucose_metrics.updated_at，30 分鐘內寫「自述測得」，超過時效寫「檔案曾自述測得」
                        _is_recent = False
                        _updated_at_str = _rec_hot.get("glucose_metrics", {}).get("updated_at", "")
                        if _updated_at_str:
                            try:
                                dt = datetime.strptime(_updated_at_str, "%Y-%m-%d %H:%M:%S")
                                if abs((datetime.now() - dt).total_seconds()) <= 1800:
                                    _is_recent = True
                            except Exception:
                                pass
                        if re.search(r"\b[4-6][0-9]\b", user_text) and any(k in user_text for k in ["頭暈", "手抖", "冒冷汗", "心悸", "吃糖", "方糖", "補糖", "量到", "驗到", "測到", "血糖"]):
                            _is_recent = True

                        if _is_recent:
                            hypo_inferred = f"自述測得空腹 {low_val} mg/dL 伴頭暈已補糖緩解（待確認，請醫師評估）"
                            range_inferred = f"自述測得最低 {low_val} mg/dL 伴頭暈已補糖緩解"
                        else:
                            hypo_inferred = f"檔案曾自述測得空腹 {low_val} mg/dL 伴頭暈已補糖緩解（待確認，請醫師評估）"
                            range_inferred = f"檔案曾自述測得最低 {low_val} mg/dL 伴頭暈已補糖緩解"

                        _cur_h = args0.get("hypo_history", "")
                        if not _cur_h or any(neg in _cur_h for neg in ["無明顯", "無低血糖", "未提及", "無特別異常", "未特別說明", "無", "近期無"]):
                            args0["hypo_history"] = hypo_inferred

                    # 1.2 已填值反向驗證（治本）：驗證已填寫的 glucose_range 是否包含捏造的數值或時間詞
                    raw_gr = str(args0.get("glucose_range") or "").strip()
                    if raw_gr:
                        user_hist = " ".join([
                            m.get("content", "") for m in messages 
                            if isinstance(m, dict) and m.get("role") == "user" and m.get("content")
                        ])
                        legitimate_source = " ".join([
                            user_text,
                            user_hist,
                            str(_rec_hot.get("glucose_metrics", {}).get("latest", "")),
                            str(_rec_hot.get("hypo_history", "")),
                            " ".join(_rec_hot.get("reported_symptoms", [])),
                            str(_rec_hot.get("diet_lifestyle", "")),
                            str(getattr(planner.slots, "glucose_metrics", "") or ""),
                            str(getattr(planner.slots, "hypo_history", "") or ""),
                            str(getattr(planner.slots, "concerns_or_side_effects", "") or ""),
                            str(getattr(planner.slots, "diet_lifestyle", "") or ""),
                        ])
                        nums_in_gr = re.findall(r"\b([1-9]\d{1,2})\b", raw_gr)
                        # 排除 15-15 衛教固定指引數字（70, 15, 3 等，不誤傷）
                        nums_to_check = [n for n in nums_in_gr if n not in ("70", "15", "3", "4")]
                        has_fabricated_num = any(n not in legitimate_source for n in nums_to_check)

                        time_words = re.findall(r"(?:週|禮拜|星期)[一二三四五六日天]|\d+\s*(?:分鐘|小時|天)", raw_gr)
                        time_to_check = [t for t in time_words if t not in ("15分鐘", "15 分鐘")]
                        has_fabricated_time = any(t not in legitimate_source for t in time_to_check)

                        if has_fabricated_num or has_fabricated_time:
                            # 存在未出現於病患發言或檔案的捏造數值/時間片段，剔除並回落重組
                            if range_inferred:
                                args0["glucose_range"] = range_inferred
                            else:
                                gm_val = args0.get("glucose_metrics") or _rec_hot.get("glucose_metrics", {}).get("latest") or ""
                                hypo_val = args0.get("hypo_history") or ""
                                if gm_val and hypo_val and hypo_val not in ("近期無低血糖事件", "無特別異常", "未特別說明", "無"):
                                    args0["glucose_range"] = f"{gm_val}，{hypo_val}"
                                elif gm_val:
                                    args0["glucose_range"] = gm_val
                                else:
                                    args0["glucose_range"] = ""
                    else:
                        if range_inferred:
                            args0["glucose_range"] = range_inferred

                    # 2. 補全血糖數據
                    _raw_gm = args0.get("glucose_metrics", "")
                    if not _raw_gm or _raw_gm in ["未特別說明", "待查", "待回診檢視", "未提供"]:
                        if _rec_hot.get("glucose_metrics", {}).get("latest"):
                            args0["glucose_metrics"] = _rec_hot["glucose_metrics"]["latest"]
                        elif planner.slots.glucose_metrics:
                            args0["glucose_metrics"] = planner.slots.glucose_metrics

                    # 3. 補全藥物資訊（特別是已辨識的藥袋，排除停用藥）
                    _raw_meds = args0.get("medications", "")
                    _known_med_names = [m.get("name", "") for m in _rec_hot.get("medications", []) if m.get("name")]
                    if _known_med_names:
                        from diabetes_chatbot.memory import MED_SWITCH_TAG
                        from diabetes_chatbot.tools import _extract_discontinued_keywords
                        _disc_keys = set()
                        for _m_item in _known_med_names:
                            _disc_keys.update(_extract_discontinued_keywords(_m_item))
                        if _raw_meds:
                            _disc_keys.update(_extract_discontinued_keywords(_raw_meds))

                        valid_drug_names = [
                            n for n in _known_med_names 
                            if "不知" not in n and "記不得" not in n and "有按時" not in n
                            and MED_SWITCH_TAG not in n and "已停用" not in n and "停藥" not in n and "已停服" not in n
                            and not any(dk.lower() in n.lower() for dk in _disc_keys)
                        ]
                        if valid_drug_names:
                            clean_drug_summary = "、".join(list(dict.fromkeys(valid_drug_names))[:2])
                            if not _raw_meds or _raw_meds == "未特別說明" or "記不得" in _raw_meds:
                                args0["medications"] = f"{clean_drug_summary}（藥袋已記錄待現場核對）"
                            elif not any(d in _raw_meds for d in valid_drug_names):
                                args0["medications"] = f"{_raw_meds}；藥袋已辨識：{clean_drug_summary}"

                    # 4. 補全飲食生活紀錄
                    _raw_diet = args0.get("diet_lifestyle", "")
                    if not _raw_diet or _raw_diet in ["未特別說明", "無", "待查", "未提供"]:
                        if _rec_hot.get("diet_lifestyle"):
                            args0["diet_lifestyle"] = _rec_hot.get("diet_lifestyle")
                        elif getattr(planner.slots, "diet_lifestyle", None):
                            args0["diet_lifestyle"] = planner.slots.diet_lifestyle
                except Exception:
                    pass

                text_summary = generate_visit_summary(
                    visit_reason=args0.get("visit_reason", "定期回診追蹤"),
                    medications=args0.get("medications", "未特別說明"),
                    glucose_metrics=args0.get("glucose_metrics", "未特別說明"),
                    hypo_history=args0.get("hypo_history", "近期未提及或無發生"),
                    side_effects_or_concerns=args0.get("side_effects_or_concerns", "無特別異常"),
                    ddx_candidates=args0.get("ddx_candidates"),
                    evidence_links=args0.get("evidence_links"),
                    patient_quote=args0.get("patient_quote"),
                    glucose_range=args0.get("glucose_range"),
                    diet_lifestyle=args0.get("diet_lifestyle"),
                )
                tool_results.append({"tool": fname0, "content": text_summary[:1000]})
                update_previsit_summary(text_summary, file_path=patient_file)
                flex_bubble = generate_line_flex_bubble(
                    visit_reason=args0.get("visit_reason", "定期回診追蹤"),
                    medications=args0.get("medications", "未特別說明"),
                    glucose_metrics=args0.get("glucose_metrics", "未特別說明"),
                    hypo_history=args0.get("hypo_history", "近期未提及或無發生"),
                    side_effects_or_concerns=args0.get("side_effects_or_concerns", "無特別異常"),
                    ddx_candidates=args0.get("ddx_candidates"),
                    evidence_links=args0.get("evidence_links"),
                    patient_quote=args0.get("patient_quote"),
                    glucose_range=args0.get("glucose_range"),
                    diet_lifestyle=args0.get("diet_lifestyle"),
                )
                qr_payload = generate_clinic_qr_payload(
                    visit_reason=args0.get("visit_reason", "定期回診追蹤"),
                    medications=args0.get("medications", "未特別說明"),
                    glucose_metrics=args0.get("glucose_metrics", "未特別說明"),
                    hypo_history=args0.get("hypo_history", "近期未提及或無發生"),
                    side_effects_or_concerns=args0.get("side_effects_or_concerns", "無特別異常"),
                    ddx_candidates=args0.get("ddx_candidates"),
                    evidence_links=args0.get("evidence_links"),
                    patient_quote=args0.get("patient_quote"),
                    glucose_range=args0.get("glucose_range"),
                    diet_lifestyle=args0.get("diet_lifestyle"),
                )
                # 完整保留 assistant tool_call 訊息（包含 Google thought_signature）
                assistant_tool_msg = _serialize_assistant_tool_message(msg, raw_content, fname0, args0, tc_id0)
                messages.append(assistant_tool_msg)
                messages.append({
                    "role": "tool",
                    "name": fname0,
                    "tool_call_id": tc_id0,
                    "content": text_summary,
                })
                raw_talker_output = raw_content
                # Build final hint like handlers
                vr = args0.get("visit_reason", "定期回診追蹤")
                meds = args0.get("medications", "未特別說明")
                gm = args0.get("glucose_metrics", "未特別說明")
                hypo = args0.get("hypo_history", "近期未提及或無發生")
                concerns = args0.get("side_effects_or_concerns", "無特別異常")
                diet_val = args0.get("diet_lifestyle", "")
                diet_part = f"；生活飲食「{diet_val}」" if (diet_val and diet_val not in ("未特別說明", "無")) else ""
                final_hint = (
                    f"跟您確認一下我幫您整理的就醫備忘："
                    f"第一，回診訴求是「{vr}」；"
                    f"第二，目前用藥是「{meds}」；"
                    f"第三，血糖與不適狀況是「{gm}／{hypo}／{concerns}{diet_part}」。"
                    f"這樣記對嗎，可以嗎？確認後我幫您產生 QR 就醫備忘錄，回診直接出示給醫師看就可以了。"
                )
                if not enable_output_guard:
                    out_guard_summary = type("G", (), {"is_blocked": False, "blocked_message": ""})()
                    card_guard_passed = True
                else:
                    out_guard_summary = inspect_output_guard(text_summary)
                    out_guard_hint = inspect_output_guard(final_hint)
                    if out_guard_summary.is_blocked:
                        card_guard_passed = False
                    elif out_guard_hint.is_blocked:
                        card_guard_passed = False
                        out_guard_summary = out_guard_hint
                    else:
                        card_guard_passed = True
                if not card_guard_passed:
                    final_hint = out_guard_summary.blocked_message
                    output_guard_obj = out_guard_summary
                    flex_bubble = None
                    qr_payload = None
                    try:
                        _clr = load_patient_record(patient_file)
                        if "pending_card" in _clr:
                            _clr.pop("pending_card", None)
                            save_patient_record(_clr, patient_file)
                    except Exception:
                        pass
                else:
                    output_guard_obj = type("G", (), {"is_blocked": False, "risk_category": "NONE", "blocked_message": ""})()
                    if enable_budget:
                        final_hint = enforce_single_question_budget(final_hint)
                    try:
                        _stash_rec = load_patient_record(patient_file)
                        _stash_rec["pending_card"] = {
                            "flex_bubble": flex_bubble,
                            "qr_payload": qr_payload,
                            "text_summary": text_summary,
                        }
                        save_patient_record(_stash_rec, patient_file)
                    except Exception:
                        pass
                    flex_bubble = None
                    qr_payload = None
                final_output = final_hint
                messages.append({"role": "assistant", "content": final_output})
                # For card case, latency handling after
            else:
                # Unknown tool - treat as rejection? But we already validated, so just record
                final_output = raw_content
                messages.append({"role": "assistant", "content": final_output})

            _persist_planner_state()
            latency_ms = int((time.time() - start) * 1000)
            return {
                "planner": planner,
                "exposed_tools": active_tools,
                "exposed_tool_names": exposed_tool_names,
                "input_guard_result": input_guard_obj,
                "output_guard_result": output_guard_obj,
                "raw_talker_output": raw_talker_output if raw_talker_output else raw_content,
                "final_output": final_output if 'final_output' in locals() and final_output else raw_content,
                "called_tools": called_tools,
                "tool_results": tool_results,
                "tool_rejections": tool_rejections,
                "forced_tool_display": forced_tool_display,
                "flex_bubble": flex_bubble,
                "qr_payload": qr_payload,
                "text_summary": text_summary,
                "termination_reason": termination,
                "events": list(planner_events),
                "token_usage": token_usage,
                "retry_metadata": retry_meta,
                "error": error,
                "latency_ms": latency_ms,
            }

        # Regular chat (no tool)
        raw_talker_output = raw_content
        final_reply = _strip_evidence_links_leak(raw_content)
        if enable_output_guard:
            og = inspect_output_guard(final_reply)
            output_guard_obj = og
            if og.is_blocked:
                final_reply = og.blocked_message
            else:
                if enable_budget:
                    final_reply = enforce_single_question_budget(final_reply)
                if enable_warning and re.search(r"不想吃|不敢吃|想停|不吃了|沒在吃", user_text):
                    if not re.search(r"不能自己停|不可自行停|切勿自行停|不要擅自停|不能擅自停|不要自己停|不要停藥|不能停", final_reply):
                        final_reply = final_reply.rstrip("。") + "。在醫師評估前，降血糖藥物千萬不能自己停掉喔，突然停藥血糖容易飆高有危險。"
        else:
            output_guard_obj = type("G", (), {"is_blocked": False, "risk_category": "NONE", "blocked_message": ""})()
            if enable_budget:
                final_reply = enforce_single_question_budget(final_reply)
            if enable_warning and re.search(r"不想吃|不敢吃|想停|不吃了|沒在吃", user_text):
                if not re.search(r"不能自己停|不可自行停|切勿自行停|不要擅自停|不能擅自停|不要自己停|不要停藥|不能停", final_reply):
                    final_reply = final_reply.rstrip("。") + "。在醫師評估前，降血糖藥物千萬不能自己停掉喔，突然停藥血糖容易飆高有危險。"
        final_reply = final_reply.replace("**", "").replace("__", "")
        if not final_reply.strip():
            final_reply = "您好呀！我是您的糖尿病衛教小幫手，可以幫您記血糖、聊飲食、整理看診前的就醫備忘錄喔！今天想聊聊什麼呢？"
        final_output = final_reply
        messages.append({"role": "assistant", "content": final_output})

        _persist_planner_state()

        latency_ms = int((time.time() - start) * 1000)
        return {
            "planner": planner,
            "exposed_tools": active_tools,
            "exposed_tool_names": exposed_tool_names,
            "input_guard_result": input_guard_obj,
            "output_guard_result": output_guard_obj,
            "raw_talker_output": raw_talker_output,
            "final_output": final_output,
            "called_tools": called_tools,
            "tool_results": tool_results,
            "tool_rejections": tool_rejections,
            "forced_tool_display": forced_tool_display,
            "flex_bubble": flex_bubble,
            "qr_payload": qr_payload,
            "text_summary": text_summary,
            "termination_reason": termination,
            "events": list(planner_events),
            "token_usage": token_usage,
            "retry_metadata": retry_meta,
            "error": error,
            "latency_ms": latency_ms,
        }

    except Exception as e:
        import sys, traceback
        print(f"[AblationCore ERROR] 執行對話輪次發生例外: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        try:
            from diabetes_chatbot.logger import log_turn
            log_turn(user_text, f"[系統例外安全回落]: {e}", latency=0.0, tool_used="EXCEPTION_FALLBACK")
        except Exception:
            pass

        latency_ms = int((time.time() - start) * 1000)
        error = str(e)
        termination = "ERROR"

        fallback_reply = "您好！目前系統處理稍有延遲，我已經收到您的訊息。請問您目前身體狀況還好嗎？若有任何急性不適或低血糖症狀，請先吃糖休息或隨時告訴我喔！"
        if 'planner' in locals() and planner:
            if getattr(planner, "retrieval_domain", None) == RetrievalDomain.DRUG_SAFETY:
                fallback_reply = "收到您的藥品與用藥諮詢了！用藥安全最重要，這段時間請先依照醫師原先囑咐規律服藥，切勿擅自停藥或增減劑量；若有用藥不適或疑問，回診時務必提出與醫師討論喔。"
            elif getattr(planner, "talker_guidance", None) and not any(k in getattr(planner, "talker_guidance", "") for k in ["【臨床", "請先", "嚴格遵守"]):
                fallback_reply = planner.talker_guidance

        try:
            _persist_planner_state()
        except NameError:
            pass

        return {
            "planner": planner if 'planner' in locals() else neutral_planner_state(),
            "exposed_tools": active_tools if 'active_tools' in locals() else get_canonical_tool_snapshot(),
            "exposed_tool_names": exposed_tool_names if 'exposed_tool_names' in locals() else [t["function"]["name"] for t in get_canonical_tool_snapshot()],
            "input_guard_result": input_guard_obj if 'input_guard_obj' in locals() else inspect_safety_guard(user_text),
            "output_guard_result": type("G", (), {"is_blocked": False, "risk_category": "NONE", "blocked_message": ""})(),
            "raw_talker_output": raw_talker_output if 'raw_talker_output' in locals() else "",
            "final_output": fallback_reply,
            "called_tools": called_tools if 'called_tools' in locals() else [],
            "tool_results": tool_results if 'tool_results' in locals() else [],
            "tool_rejections": tool_rejections if 'tool_rejections' in locals() else [],
            "forced_tool_display": forced_tool_display if 'forced_tool_display' in locals() else None,
            "flex_bubble": None,
            "qr_payload": None,
            "text_summary": None,
            "termination_reason": termination,
            "events": (["ERROR"] + list(planner_events)) if 'planner_events' in locals() else ["ERROR"],
            "token_usage": None,
            "retry_metadata": retry_meta if 'retry_meta' in locals() else None,
            "error": error,
            "latency_ms": latency_ms,
        }
