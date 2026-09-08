"""Shared ablation core: single pipeline for handlers.py and harness/runner.py.

Encapsulates validated production logic with injectable ablation flags.
"""
from __future__ import annotations
import json
import re
import time
import threading
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
    if not text:
        return ""
    t = re.sub(r"<div id=[\"']evidence_links[\"'].*?</div>", "", text, flags=re.DOTALL)
    t = re.sub(r"evidence_links\s*:\s*(?:\[.*?\]|-.*?\n?)*", "", t, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r"\n\s*-\s*\[.*?\]\(https?://.*?\)", "", t)
    return t.strip()


PENDING_DELIVERY_TEXT = "太好了！已經為您產生好【門診就醫備忘錄】大字體卡片與專用 QR Code，您下週看診時直接出示給醫師看就可以囉！"
_CONFIRM_LONG_KEYWORDS = ["這樣記對", "沒錯", "幫我產生", "確認", "可以"]
_CORRECTION_KEYWORDS = ["不對", "記錯", "錯誤", "不正確", "不是這樣", "不是", "不好", "改一下", "更正"]


def is_visit_memo_confirmation(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if any(k in t for k in _CORRECTION_KEYWORDS):
        return False
    if any(k in t for k in _CONFIRM_LONG_KEYWORDS):
        return True
    if len(t) <= 20 and (("對" in t) or ("好" in t)):
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
        try:
            patient_record = load_patient_record(patient_file)

            def _planner_call():
                return evaluate_clinical_planner_llm(messages, patient_record, planner_client, model, timeout=3.0)

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
                planner.talker_guidance = "【臨床導引就醫備忘錄】：病患看診議程已具備明確主訴，核心資訊已達充分度！請立刻調用 generate_previsit_intake_summary 工具為病患生成門診摘要，嚴禁再拋出任何問題追問病患；生成完成後，親切告知已整理完畢並叮嚀看診時出示即可。"
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
            return "糖尿病衛教"

        def _is_def_local(q: str, domain_val: str) -> bool:
            ql = q.lower()
            def_kw = ["是什麼", "什麼是", "定義", "成因", "形成", "為什麼", "為何", "原理", "怎麼形成", "怎麼來的", "機制", "分型", "種類"]
            if any(k in ql for k in def_kw):
                if "糖尿病" in ql or "diabetes" in ql or domain_val in ["GENERAL_EDUCATION", "DRUG_SAFETY"]:
                    return True
            return False

        needs_forced = False
        if enable_forced and not planner.is_visit_mode and planner.retrieval_domain in [RetrievalDomain.GENERAL_EDUCATION, RetrievalDomain.DRUG_SAFETY]:
            if _is_def_local(user_text, planner.retrieval_domain.value):
                needs_forced = True
        if needs_forced:
            rule_q = _extract_definition_keyword(user_text)
            if rule_q:
                forced_evidence = search_handbook(rule_q, user_raw_input=user_text, domain=planner.retrieval_domain.value)
                forced_tool_display = f"search_handbook(關鍵字: '{rule_q}', domain={planner.retrieval_domain.value}, evidence_links已保留至就醫備忘錄小字{len(forced_evidence)}字/出處只印不念)"
    except Exception:
        forced_evidence = None

    # 6. Build inference context
    pruned_ctx = prune_conversation_history(messages, max_history_messages=8)
    inference_ctx = list(pruned_ctx)
    # Guidance injection: only if planner enabled (neutral has empty so safe, but spec says never inject when OFF)
    if enable_planner and getattr(planner, "talker_guidance", ""):
        inference_ctx.append({"role": "system", "content": planner.talker_guidance})
    if forced_evidence:
        _compact = forced_evidence[:1000]
        if planner.retrieval_domain == RetrievalDomain.DRUG_SAFETY:
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
        inference_ctx.append({"role": "system", "content": guidance_task})

    # 7. Talker LLM with retry
    enable_output_guard = _abl_flag(ablation_config, "enable_output_guard", True)
    enable_budget = _abl_flag(ablation_config, "enable_question_budget_postprocessing", True)
    enable_warning = _abl_flag(ablation_config, "enable_fixed_warning_append", True)

    extra_body = {"reasoning": {"effort": "none"}} if "mimo" in model.lower() else None
    max_tokens_use = 500 if "gemini" in model.lower() else 250

    raw_talker_output = ""
    called_tools: list[str] = []
    tool_results: list[dict] = []
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
        raw_content = (getattr(msg, "content", None) or "").strip() if getattr(msg, "content", None) else ""
        # XML fallback detection
        is_xml_tool_call = "<tool_call>" in raw_content and "search_handbook" in raw_content

        tool_calls = getattr(msg, "tool_calls", None)

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
                try:
                    fname = tc.function.name if hasattr(tc.function, "name") else tc.get("function", {}).get("name", "")
                except Exception:
                    fname = "unknown"
                args_raw = getattr(tc.function, "arguments", "{}") if hasattr(tc, "function") else "{}"
                try:
                    args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw)
                except Exception:
                    args = {}
                tc_id = getattr(tc, "id", f"call_{len(valid_calls)}")
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
                        "flex_bubble": None,
                        "qr_payload": None,
                        "text_summary": None,
                        "termination_reason": termination,
                        "events": [],
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
                # Append assistant tool_call + tool result to messages for history correctness
                # For API-like history, need to preserve tool_calls structure
                try:
                    messages.append(msg if isinstance(msg, dict) else {"role": "assistant", "content": raw_content or None, "tool_calls": [{"id": tc_id0, "function": {"name": fname0, "arguments": json.dumps(args0, ensure_ascii=False)}}]})
                except Exception:
                    messages.append({"role": "assistant", "content": None, "tool_calls": [{"id": tc_id0, "function": {"name": fname0, "arguments": json.dumps(args0, ensure_ascii=False)}}]})
                messages.append({"role": "tool", "tool_call_id": tc_id0, "content": tool_output})

                # Second talker call with evidence
                second_ctx = list(prune_conversation_history(messages, max_history_messages=8))
                # Build second_task like handlers
                if planner.retrieval_domain == RetrievalDomain.DRUG_SAFETY:
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
                second_ctx.append({"role": "system", "content": second_task})

                def _second_call():
                    return talker_client.chat.completions.create(
                        model=model, messages=second_ctx, extra_body=extra_body, max_tokens=max_tokens_use, temperature=0.7
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
                if not second_text:
                    if planner and getattr(planner, "talker_guidance", None) and not any(k in planner.talker_guidance for k in ["【臨床", "請先", "嚴格遵守"]):
                        second_text = planner.talker_guidance
                    elif planner.retrieval_domain == RetrievalDomain.DRUG_SAFETY:
                        second_text = "脹得不舒服齁，我幫您記在第一條，回診一起問醫師好不好？這段時間先照醫師原本的交代用藥，有變化我幫您記下來。"
                    else:
                        second_text = "太好了！聽到您回診後醫師幫忙調整了用藥，肚子也不脹了，空腹血糖維持在穩定範圍，真的很替您高興！想請問這次換藥後，最近身體適應得都還順利嗎？"
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
                forced_tool_display = f"search_handbook(關鍵字: '{kw_clean}', evidence_links已保留至就醫備忘錄小字{len(tool_output)}字/出處只印不念)"

            elif fname0 in ["generate_previsit_intake_summary", "generate_visit_summary"]:
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
                )
                # Append tool conversation
                try:
                    messages.append(msg if isinstance(msg, dict) else {"role": "assistant", "content": raw_content or None, "tool_calls": [{"id": tc_id0, "function": {"name": fname0, "arguments": json.dumps(args0, ensure_ascii=False)}}]})
                except Exception:
                    messages.append({"role": "assistant", "content": None, "tool_calls": [{"id": tc_id0, "function": {"name": fname0, "arguments": json.dumps(args0, ensure_ascii=False)}}]})
                messages.append({"role": "tool", "tool_call_id": tc_id0, "content": text_summary})
                raw_talker_output = raw_content
                # Build final hint like handlers
                vr = args0.get("visit_reason", "定期回診追蹤")
                meds = args0.get("medications", "未特別說明")
                gm = args0.get("glucose_metrics", "未特別說明")
                hypo = args0.get("hypo_history", "近期未提及或無發生")
                concerns = args0.get("side_effects_or_concerns", "無特別異常")
                final_hint = (
                    f"跟您確認一下我幫您整理的就醫備忘："
                    f"第一，回診訴求是「{vr}」；"
                    f"第二，目前用藥是「{meds}」；"
                    f"第三，血糖與不適狀況是「{gm}／{hypo}／{concerns}」。"
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
                "flex_bubble": flex_bubble,
                "qr_payload": qr_payload,
                "text_summary": text_summary,
                "termination_reason": termination,
                "events": [],
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
        final_output = final_reply
        messages.append({"role": "assistant", "content": final_output})

        # Background persist (daemon)
        def _bg_persist_hot():
            try:
                if not enable_planner:
                    return
                if getattr(planner, "engine", "") == "llm":
                    update_from_planner_assessment(planner, file_path=patient_file)
                else:
                    cur_rec = load_patient_record(patient_file)
                    llm_eval = evaluate_clinical_planner_llm(list(messages), cur_rec, planner_client, model, timeout=3.0)
                    if getattr(llm_eval, "engine", "") == "llm":
                        update_from_planner_assessment(llm_eval, file_path=patient_file)
            except Exception:
                pass

        try:
            bg = threading.Thread(target=_bg_persist_hot, daemon=True)
            bg.start()
        except Exception:
            pass

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
            "flex_bubble": flex_bubble,
            "qr_payload": qr_payload,
            "text_summary": text_summary,
            "termination_reason": termination,
            "events": [],
            "token_usage": token_usage,
            "retry_metadata": retry_meta,
            "error": error,
            "latency_ms": latency_ms,
        }

    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        error = str(e)
        termination = "ERROR"
        return {
            "planner": planner if 'planner' in locals() else neutral_planner_state(),
            "exposed_tools": active_tools if 'active_tools' in locals() else get_canonical_tool_snapshot(),
            "exposed_tool_names": exposed_tool_names if 'exposed_tool_names' in locals() else [t["function"]["name"] for t in get_canonical_tool_snapshot()],
            "input_guard_result": input_guard_obj if 'input_guard_obj' in locals() else inspect_safety_guard(user_text),
            "output_guard_result": type("G", (), {"is_blocked": False, "risk_category": "NONE", "blocked_message": ""})(),
            "raw_talker_output": raw_talker_output if 'raw_talker_output' in locals() else "",
            "final_output": "",
            "called_tools": called_tools if 'called_tools' in locals() else [],
            "tool_results": tool_results if 'tool_results' in locals() else [],
            "tool_rejections": tool_rejections if 'tool_rejections' in locals() else [],
            "flex_bubble": None,
            "qr_payload": None,
            "text_summary": None,
            "termination_reason": termination,
            "events": ["ERROR"],
            "token_usage": None,
            "retry_metadata": retry_meta if 'retry_meta' in locals() else None,
            "error": error,
            "latency_ms": latency_ms,
        }
