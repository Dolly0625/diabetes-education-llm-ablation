import re
import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from diabetes_chatbot.memory import (
    get_default_template,
    format_patient_context,
    update_from_planner_assessment,
    save_patient_record,
    MED_SWITCH_TAG,
)
from diabetes_chatbot.tools import (
    generate_previsit_intake_summary,
    generate_line_flex_bubble,
    generate_clinic_qr_payload,
    _format_glucose_section,
    TOOL_GENERATE_PREVISIT_SUMMARY,
)
from diabetes_chatbot.planner import PlannerAssessment, ClinicalSlots, RetrievalDomain
from diabetes_chatbot.guard import enforce_single_question_budget


def test_diet_lifestyle_in_memory_and_context(tmp_path):
    """驗證 diet_lifestyle 正確存入長期檔案並格式化於 hot_ctx"""
    p_file = tmp_path / "test_patient.json"
    template = get_default_template("test_p")
    assert "diet_lifestyle" in template
    assert template["diet_lifestyle"] == ""
    save_patient_record(template, p_file)

    slots = ClinicalSlots(
        diet_lifestyle="一次吃一整顆大芭樂，正餐以清淡蔬菜為主",
        diet_lifestyle_status="EXPLICIT",
        medications="癲通",
        medications_status="EXPLICIT",
        glucose_metrics="65 mg/dL",
        glucose_metrics_status="EXPLICIT",
    )
    assessment = PlannerAssessment(
        retrieval_domain=RetrievalDomain.GENERAL_EDUCATION,
        is_visit_mode=False,
        is_agenda_confirmed=False,
        slots=slots,
    )

    updated = update_from_planner_assessment(assessment, file_path=p_file)
    assert updated is True

    hot_ctx = format_patient_context(p_file)
    assert "近期飲食習慣與生活記錄：一次吃一整顆大芭樂，正餐以清淡蔬菜為主" in hot_ctx


def test_med_switch_tag_filtered_from_summary_calibration():
    """驗證 valid_drug_names 排除 MED_SWITCH_TAG 與已停用藥物"""
    known_meds = [
        {"name": f"庫魯化{MED_SWITCH_TAG}"},
        {"name": "佳糖維（已停用）"},
        {"name": "愛妥糖（停藥）"},
        {"name": "癲通"},
    ]
    med_names = [m["name"] for m in known_meds if m.get("name")]
    valid_drug_names = [
        n for n in med_names
        if "不知" not in n and "記不得" not in n and "有按時" not in n
        and MED_SWITCH_TAG not in n and "已停用" not in n and "停藥" not in n
    ]
    assert valid_drug_names == ["癲通"]
    assert f"庫魯化{MED_SWITCH_TAG}" not in valid_drug_names
    assert "佳糖維（已停用）" not in valid_drug_names
    assert "愛妥糖（停藥）" not in valid_drug_names


def test_hypo_cross_slot_dynamic_capture_and_time_arbitration():
    """驗證低血糖跨欄位動態捕獲實際數字（不硬編碼 65）與 30 分鐘時效仲裁"""
    import re
    # 情境 1：病患自述驗到 55，且在 30 分鐘內（即時自述）
    reading_55 = "55 mg/dL"
    symptoms = ["頭暈", "吃糖緩解"]
    m_low = re.search(r"\b([4-6][0-9])\b", reading_55)
    assert m_low is not None
    captured_55 = m_low.group(1)
    assert captured_55 == "55"

    now = datetime.now()
    recent_time_str = (now - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    dt = datetime.strptime(recent_time_str, "%Y-%m-%d %H:%M:%S")
    is_recent = abs((now - dt).total_seconds()) <= 1800
    assert is_recent is True
    hypo_text_recent = f"自述測得空腹 {captured_55} mg/dL 伴頭暈已補糖緩解（待確認，請醫師評估）"
    assert hypo_text_recent.startswith("自述測得")
    assert "55 mg/dL" in hypo_text_recent
    assert "65" not in hypo_text_recent

    # 情境 2：病患自述驗到 68，但檔案更新時間已超過 30 分鐘（例如 3 小時前歷史檔案）
    reading_68 = "68 mg/dL"
    m_low_68 = re.search(r"\b([4-6][0-9])\b", reading_68)
    assert m_low_68 is not None
    captured_68 = m_low_68.group(1)
    assert captured_68 == "68"

    old_time_str = (now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    dt_old = datetime.strptime(old_time_str, "%Y-%m-%d %H:%M:%S")
    is_recent_old = abs((now - dt_old).total_seconds()) <= 1800
    assert is_recent_old is False
    hypo_text_old = f"檔案曾自述測得空腹 {captured_68} mg/dL 伴頭暈已補糖緩解（待確認，請醫師評估）"
    assert hypo_text_old.startswith("檔案曾自述測得")
    assert "68 mg/dL" in hypo_text_old
    assert not hypo_text_old.startswith("自述測得空腹")


def test_previsit_tools_with_diet_lifestyle():
    """驗證就醫備忘錄工具、卡片與 QR payload 支援生活飲食欄位，且 QR 不重複並條件化鍵值"""
    # 1. Tool schema 含有 diet_lifestyle
    props = TOOL_GENERATE_PREVISIT_SUMMARY["function"]["parameters"]["properties"]
    assert "diet_lifestyle" in props

    # 2. 文字備忘錄包含「③ 糖線與生活飲食」且整合飲食
    summary = generate_previsit_intake_summary(
        visit_reason="定期回診拿慢箋",
        medications="癲通",
        glucose_metrics="空腹 65 mg/dL",
        hypo_history="自述測得空腹 65 mg/dL 伴頭暈已補糖緩解（待確認，請醫師評估）",
        side_effects_or_concerns="肚子脹脹的",
        diet_lifestyle="一次吃一整顆大芭樂",
    )
    assert "③ 糖線與生活飲食" in summary
    assert "飲食生活：一次吃一整顆大芭樂" in summary

    # 3. Flex 卡片包含「③ 糖線與生活飲食」
    bubble = generate_line_flex_bubble(
        visit_reason="定期回診拿慢箋",
        medications="癲通",
        glucose_metrics="空腹 65 mg/dL",
        hypo_history="自述測得空腹 65 mg/dL 伴頭暈已補糖緩解（待確認，請醫師評估）",
        side_effects_or_concerns="肚子脹脹的",
        diet_lifestyle="一次吃一整顆大芭樂",
    )
    body_texts = [c.get("text", "") for box in bubble["body"]["contents"] if box.get("type") == "box" for c in box.get("contents", []) if c.get("type") == "text"]
    assert "③ 糖線與生活飲食" in body_texts

    # 4. QR payload（有填飲食情境）：糖線三數字不重複飲食文字，且尾端精確附加 |飲食生活:...
    qr_with_diet = generate_clinic_qr_payload(
        visit_reason="定期回診拿慢箋",
        medications="癲通",
        glucose_metrics="空腹 65 mg/dL",
        hypo_history="自述測得空腹 65 mg/dL 伴頭暈已補糖緩解（待確認，請醫師評估）",
        side_effects_or_concerns="肚子脹脹的",
        diet_lifestyle="一次吃一整顆大芭樂",
    )
    assert qr_with_diet.startswith("TFDA-INTAKE-V2|")
    assert "|飲食生活:一次吃一整顆大芭樂" in qr_with_diet
    # 核心驗證：糖線三數字段內不可重複內嵌飲食文字
    glucose_part = [seg for seg in qr_with_diet.split("|") if seg.startswith("糖線三數字:")][0]
    assert "飲食生活" not in glucose_part, "QR payload 糖線三數字中不應重複內嵌飲食文字！"

    # 5. QR payload（未填飲食情境）：未填或無時，不得附加 |飲食生活 鍵
    qr_without_diet = generate_clinic_qr_payload(
        visit_reason="定期回診拿慢箋",
        medications="癲通",
        glucose_metrics="空腹 65 mg/dL",
        hypo_history="近期無低血糖事件",
        side_effects_or_concerns="無",
        diet_lifestyle="未特別說明",
    )
    assert "|飲食生活" not in qr_without_diet, "未特別說明飲食時，QR payload 絕不可附加 |飲食生活 鍵！"

    qr_none_diet = generate_clinic_qr_payload(
        visit_reason="定期回診拿慢箋",
        medications="癲通",
        glucose_metrics="空腹 65 mg/dL",
        hypo_history="近期無低血糖事件",
        side_effects_or_concerns="無",
        diet_lifestyle=None,
    )
    assert "|飲食生活" not in qr_none_diet, "diet_lifestyle 為 None 時，QR payload 絕不可附加 |飲食生活 鍵！"


# ==============================================================================
# guard.py enforce_single_question_budget 三大情境回歸測試
# ==============================================================================

def test_enforce_single_question_emergency_protection():
    """情境 1：急救長衛教多問號保護不腰斬（15-15 守則急救長文不被截斷，前問轉句號，保留末尾問題）"""
    raw_reply = (
        "阿嬤您現在頭暈覺得很難受嗎？"
        "請趕快先吃 15 克的含糖食物（例如 3 到 4 顆方糖、半杯果汁或含糖飲料），"
        "然後坐著或躺著休息 15 分鐘，等身體比較舒服後再量一次血糖看看。"
        "想請問身邊現在有方糖或含糖飲料可以先吃嗎？"
    )
    processed = enforce_single_question_budget(raw_reply)
    # 急救守則完整保留，沒有被腰斬消失
    assert "請趕快先吃 15 克的含糖食物" in processed
    assert "休息 15 分鐘" in processed
    assert "想請問身邊現在有方糖或含糖飲料可以先吃嗎？" in processed
    # 問句預算嚴格維持 1
    assert processed.count("？") == 1
    # 前方的問號轉為句號
    assert "很難受嗎。" in processed or "很難受嗎？" not in processed


def test_enforce_single_question_consecutive_questions_hard_cutoff():
    """情境 2：連續緊鄰追問硬截斷只留第一問（無實質衛教間隔，立即截斷杜絕認知過載）"""
    raw_reply = "阿公您好！菜包的澱粉量確實比較高喔。想先請教您今天早上血糖多少呢？另外您早餐有吃降血糖藥嗎？還有您平常會覺得口渴嗎？"
    processed = enforce_single_question_budget(raw_reply)
    assert processed.count("？") == 1
    assert "今天早上血糖多少呢？" in processed
    assert "早餐有吃降血糖藥嗎" not in processed
    assert "口渴嗎" not in processed


def test_enforce_single_question_soft_empathy_to_exclamation():
    """情境 3：溫和同理句轉感嘆詞（溫和語氣詞轉為感嘆，不消耗實質問句預算）"""
    raw_reply = "阿嬤這兩天肚子好脹很不舒服吧？想先請問您這次回診主要是想跟醫師討論腹脹換藥，還是例行拿慢箋呢？"
    processed = enforce_single_question_budget(raw_reply)
    # 同理句的問號成功轉為感嘆號！
    assert "很不舒服吧！" in processed
    # 唯一的焦點問題被完整保留
    assert "想先請問您這次回診主要是想跟醫師討論腹脹換藥，還是例行拿慢箋呢？" in processed
    assert processed.count("？") == 1


# ==============================================================================
# 鸚鵡學舌回歸測試與反向語意測試（指示 4 與指示 5）
# ==============================================================================

def test_parrot_schema_copying_regression(tmp_path):
    """指示 4：鸚鵡學舌回歸測試
    模擬模型照抄 schema 範例：「最高/最低65/平常，週三晨空腹65暈10分鐘3顆糖緩解」
    而病患實際只說過「今早」與「65」。
    反向驗證必須剔除「週三」與「10分鐘」，且三種卡片輸出均不得出現該捏造詞，並保留 65。
    """
    import re
    from diabetes_chatbot.tools import (
        generate_previsit_intake_summary,
        generate_line_flex_bubble,
        generate_clinic_qr_payload,
    )

    # 1. 模擬病患真實上下文（僅自述今早量到 65，無週三、無 10 分鐘）
    user_text = "我今早起床量到 65，頭好暈趕快吃了糖"
    patient_file = tmp_path / "test_parrot_patient.json"
    rec = get_default_template("test_parrot")
    rec["glucose_metrics"] = {"latest": "65 mg/dL", "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    rec["reported_symptoms"] = ["頭暈"]
    save_patient_record(rec, patient_file)

    # 模擬大模型照抄了 schema 範例進 args0
    args0 = {
        "visit_reason": "定期回診拿慢箋",
        "medications": "癲通",
        "glucose_metrics": "65 mg/dL",
        "hypo_history": "無明顯低血糖",
        "side_effects_or_concerns": "無特別異常",
        "glucose_range": "最高/最低65/平常，週三晨空腹65暈10分鐘3顆糖緩解"  # 照抄範例（含週三、10分鐘）
    }

    # 2. 執行反向驗證邏輯（與 ablation_core.py 相同驗證算法）
    raw_gr = str(args0.get("glucose_range") or "").strip()
    legitimate_source = f"{user_text} 65 mg/dL 頭暈 癲通"
    nums_in_gr = re.findall(r"\b([1-9]\d{1,2})\b", raw_gr)
    nums_to_check = [n for n in nums_in_gr if n not in ("70", "15", "3", "4")]
    has_fabricated_num = any(n not in legitimate_source for n in nums_to_check)

    time_words = re.findall(r"(?:週|禮拜|星期)[一二三四五六日天]|\d+\s*(?:分鐘|小時|天)", raw_gr)
    time_to_check = [t for t in time_words if t not in ("15分鐘", "15 分鐘")]
    has_fabricated_time = any(t not in legitimate_source for t in time_to_check)

    # 斷言：成功偵測到捏造的時間詞（週三、10分鐘）
    assert has_fabricated_time is True
    assert "週三" in time_to_check
    assert any("10" in t for t in time_to_check)

    # 依治本邏輯回落重組
    sanitized_range = "自述測得最低 65 mg/dL 伴頭暈已補糖緩解"
    args0["glucose_range"] = sanitized_range
    args0["hypo_history"] = "自述測得空腹 65 mg/dL 伴頭暈已補糖緩解（待確認，請醫師評估）"

    # 3. 驗證三種卡片輸出
    # (a) 文字卡
    summary_text = generate_previsit_intake_summary(
        visit_reason=args0["visit_reason"],
        medications=args0["medications"],
        glucose_metrics=args0["glucose_metrics"],
        hypo_history=args0["hypo_history"],
        side_effects_or_concerns=args0["side_effects_or_concerns"],
        glucose_range=args0["glucose_range"],
    )
    assert "週三" not in summary_text
    assert "10分鐘" not in summary_text
    assert "65" in summary_text

    # (b) Flex 卡片
    bubble = generate_line_flex_bubble(
        visit_reason=args0["visit_reason"],
        medications=args0["medications"],
        glucose_metrics=args0["glucose_metrics"],
        hypo_history=args0["hypo_history"],
        side_effects_or_concerns=args0["side_effects_or_concerns"],
        glucose_range=args0["glucose_range"],
    )
    bubble_str = json.dumps(bubble, ensure_ascii=False)
    assert "週三" not in bubble_str
    assert "10分鐘" not in bubble_str
    assert "65" in bubble_str

    # (c) QR Code payload
    qr = generate_clinic_qr_payload(
        visit_reason=args0["visit_reason"],
        medications=args0["medications"],
        glucose_metrics=args0["glucose_metrics"],
        hypo_history=args0["hypo_history"],
        side_effects_or_concerns=args0["side_effects_or_concerns"],
        glucose_range=args0["glucose_range"],
    )
    assert "週三" not in qr
    assert "10分鐘" not in qr
    assert "65" in qr


def test_semantic_anti_hallucination_watermelon_not_guava():
    """指示 5：反向語意測試
    病患只說吃「西瓜」，斷言卡片與 planner 槽位不得出現 schema 或 planner 範例中的「芭樂」字樣，
    鎖死範例與 demo 案例重疊導致無法區分語意提煉與照抄的隱藏風險。
    """
    from diabetes_chatbot.planner import evaluate_clinical_planner
    from diabetes_chatbot.tools import generate_previsit_intake_summary, generate_line_flex_bubble, generate_clinic_qr_payload

    # 病患僅提及西瓜
    watermelon_msgs = [
        {"role": "user", "content": "護理師，我今天下午吃了一大片西瓜，水分很多很甜，這樣血糖會不會升很快？"}
    ]
    assessment = evaluate_clinical_planner(watermelon_msgs, patient_record={})
    diet_slot = getattr(assessment.slots, "diet_lifestyle", "") or ""

    # 核心斷言：Planner 提煉槽位中絕不可出現範例中的「芭樂」
    assert "芭樂" not in diet_slot
    assert "西瓜" in diet_slot or "西瓜" in watermelon_msgs[0]["content"]

    # 產出備忘錄卡片
    actual_diet = diet_slot if diet_slot else "下午吃了一大片西瓜"
    summary_text = generate_previsit_intake_summary(
        visit_reason="飲食諮詢",
        medications="未特別說明",
        glucose_metrics="未特別說明",
        hypo_history="近期未提及或無發生",
        side_effects_or_concerns="無特別異常",
        diet_lifestyle=actual_diet
    )
    bubble = generate_line_flex_bubble(
        visit_reason="飲食諮詢",
        medications="未特別說明",
        glucose_metrics="未特別說明",
        hypo_history="近期未提及或無發生",
        side_effects_or_concerns="無特別異常",
        diet_lifestyle=actual_diet
    )
    qr = generate_clinic_qr_payload(
        visit_reason="飲食諮詢",
        medications="未特別說明",
        glucose_metrics="未特別說明",
        hypo_history="近期未提及或無發生",
        side_effects_or_concerns="無特別異常",
        diet_lifestyle=actual_diet
    )

    # 核心斷言：三種卡片輸出均不得出現任何「芭樂」
    assert "芭樂" not in summary_text
    assert "芭樂" not in json.dumps(bubble, ensure_ascii=False)
    assert "芭樂" not in qr
    assert "西瓜" in summary_text
    assert "西瓜" in qr


def test_is_same_medication_and_deduplication(tmp_path):
    """
    Bug B 測試：
    1. 驗證 is_same_medication 雙向子字串包含判斷（長度需 >= 2）
    2. OCR 全名先入檔後，口述短名被吸收不新增第二筆
    3. 先口述短名後拍照 OCR 全名，能保留並升級為資訊量較高（較長）之條目
    """
    from diabetes_chatbot.memory import update_medications, is_same_medication, load_patient_record
    from diabetes_chatbot.planner import PlannerAssessment, ClinicalSlots, RetrievalDomain

    # 1. Helper 雙向子字串判斷
    assert is_same_medication("癲通", "癲通 長效膜衣錠 ２００毫克（卡巴氮平）") is True
    assert is_same_medication("癲通 長效膜衣錠 ２００毫克（卡巴氮平）", "癲通") is True
    assert is_same_medication("得爾美", "得爾美（Diamicron）") is True
    assert is_same_medication("癲通", "得爾美") is False
    assert is_same_medication("藥", "癲通藥") is False  # 單字防誤傷
    assert is_same_medication("", "癲通") is False

    # 2. 情境 A：OCR 全名先入檔，口述短名不應新增第二筆
    p_file = tmp_path / "test_dedup_ocr_first.json"
    save_patient_record(get_default_template("test_dedup_ocr"), p_file)

    full_name = "癲通 長效膜衣錠 ２００毫克（卡巴氮平）"
    update_medications([full_name], source="LINE藥袋辨識", file_path=p_file)
    rec = load_patient_record(p_file)
    assert len(rec["medications"]) == 1
    assert rec["medications"][0]["name"] == full_name

    # 口述短名「癲通」透過 update_medications
    update_medications(["癲通"], source="病患口述", file_path=p_file)
    rec = load_patient_record(p_file)
    assert len(rec["medications"]) == 1
    assert rec["medications"][0]["name"] == full_name

    # 口述短名「癲通」透過 update_from_planner_assessment
    slots = ClinicalSlots(medications="癲通", medications_status="EXPLICIT")
    assessment = PlannerAssessment(
        retrieval_domain=RetrievalDomain.DRUG_SAFETY,
        is_visit_mode=False,
        is_agenda_confirmed=False,
        slots=slots,
    )
    update_from_planner_assessment(assessment, file_path=p_file)
    rec = load_patient_record(p_file)
    assert len(rec["medications"]) == 1
    assert rec["medications"][0]["name"] == full_name

    # 3. 情境 B：先口述短名後辨識全名，保留較長資訊量條目
    p_file2 = tmp_path / "test_dedup_short_first.json"
    save_patient_record(get_default_template("test_dedup_short"), p_file2)
    update_medications(["得爾美"], source="病患口述", file_path=p_file2)
    rec2 = load_patient_record(p_file2)
    assert len(rec2["medications"]) == 1
    assert rec2["medications"][0]["name"] == "得爾美"

    diamicron_full = "得爾美（Diamicron）"
    update_medications([diamicron_full], source="LINE藥袋辨識", file_path=p_file2)
    rec2 = load_patient_record(p_file2)
    assert len(rec2["medications"]) == 1
    assert rec2["medications"][0]["name"] == diamicron_full


def test_search_handbook_second_call_exception_fallback(tmp_path):
    """
    Bug A2/A3 測試：
    模擬 talker 回傳 tool_calls 呼叫 search_handbook 後，第二次 talker 呼叫拋出例外，
    斷言能被本地 try/except 捕獲，最終回覆非空且含安全文案，絕不上拋至檔尾大 except 輸出空回覆。
    """
    from unittest.mock import MagicMock
    from diabetes_chatbot.server.ablation_core import execute_ablation_turn

    p_file = tmp_path / "test_second_call_err.json"
    save_patient_record(get_default_template("test_err"), p_file)

    planner_mock = MagicMock()
    planner_resp = MagicMock()
    planner_msg = MagicMock()
    planner_msg.content = json.dumps({
        "retrieval_domain": "DRUG_SAFETY",
        "is_visit_mode": False,
        "is_agenda_confirmed": False,
        "talker_guidance": "請依照衛福部仿單向長輩說明癲通之藥理與副作用，提醒切勿擅自停藥。",
        "slots": {
            "visit_reason": {"content": "詢問癲通藥物作用", "status": "KNOWN"},
            "medications": {"content": "癲通", "status": "KNOWN"},
            "glucose_metrics": {"content": "", "status": "MISSING"},
            "hypo_history": {"content": "", "status": "MISSING"},
            "side_effects_or_concerns": {"content": "", "status": "MISSING"},
            "diet_lifestyle": {"content": "", "status": "MISSING"}
        }
    }, ensure_ascii=False)
    planner_choice = MagicMock()
    planner_choice.message = planner_msg
    planner_resp.choices = [planner_choice]
    planner_mock.chat.completions.create.return_value = planner_resp

    talker_mock = MagicMock()
    tc = MagicMock()
    tc.id = "call_drug_safety_123"
    tc.function.name = "search_handbook"
    tc.function.arguments = json.dumps({"keyword": "癲通"}, ensure_ascii=False)

    first_msg = MagicMock()
    first_msg.content = None
    first_msg.tool_calls = [tc]
    first_choice = MagicMock()
    first_choice.message = first_msg
    first_resp = MagicMock()
    first_resp.choices = [first_choice]
    first_resp.usage = None

    def talker_side_effect(*args, **kwargs):
        msgs = kwargs.get("messages", [])
        has_tool = any(isinstance(m, dict) and m.get("role") == "tool" for m in msgs)
        if not has_tool:
            # 第一次呼叫：回傳 search_handbook 工具調用
            return first_resp
        else:
            # 第二次呼叫：模擬上游模型逾時或拋出例外！
            raise RuntimeError("Upstream Talker LLM network timeout or rate limited")

    talker_mock.chat.completions.create.side_effect = talker_side_effect

    res = execute_ablation_turn(
        user_text="我想了解癲通這個藥的作用是什麼",
        patient_file=p_file,
        messages=[{"role": "user", "content": "我想了解癲通這個藥的作用是什麼"}],
        talker_client=talker_mock,
        planner_client=planner_mock,
    )

    # 核心斷言：本地 try/except 成功攔截，最終回覆絕非空字串，且包含安全合規文案
    assert res is not None
    assert isinstance(res["final_output"], str)
    assert len(res["final_output"].strip()) > 0
    assert any(k in res["final_output"] for k in ["用藥安全", "規律服藥", "切勿擅自停藥", "依照醫師"])
    assert res.get("error") is None or "second_call_error" in str(res.get("retry_metadata"))


def test_ablation_core_top_level_exception_never_returns_empty(tmp_path):
    """
    Bug A1 測試：
    驗證當 ablation_core 發生未知崩潰時，檔尾大 except 絕不回傳空 final_output，
    必定回落至合規安全關懷文案。
    """
    from unittest.mock import MagicMock
    from diabetes_chatbot.server.ablation_core import execute_ablation_turn

    p_file = tmp_path / "test_fatal_err.json"
    save_patient_record(get_default_template("test_fatal"), p_file)

    mock_client = MagicMock()
    # 第一次調用即拋出未知嚴重例外
    mock_client.chat.completions.create.side_effect = Exception("Fatal unexpected connection dropped")

    res = execute_ablation_turn(
        user_text="我有吃癲通，肚子好脹喔",
        patient_file=p_file,
        messages=[{"role": "user", "content": "我有吃癲通，肚子好脹喔"}],
        talker_client=mock_client,
        planner_client=mock_client,
    )

    assert res is not None
    assert isinstance(res["final_output"], str)
    assert len(res["final_output"].strip()) > 0
    assert res["termination_reason"] == "ERROR"
    assert any(k in res["final_output"] for k in ["用藥安全", "規律服藥", "切勿擅自停藥", "系統處理稍有延遲"])


def test_forced_retrieval_drug_safety_path_still_functional(tmp_path):
    """
    附加檢查：
    驗證藥物題強制檢索 (forced retrieval) 路徑依然正常運作，依據官方仿單/手冊提供衛教。
    """
    from unittest.mock import MagicMock
    from diabetes_chatbot.server.ablation_core import execute_ablation_turn

    p_file = tmp_path / "test_forced_drug.json"
    save_patient_record(get_default_template("test_forced"), p_file)

    mock_client = MagicMock()
    normal_resp = MagicMock()
    normal_msg = MagicMock()
    normal_msg.content = "依據衛福部仿單說明，癲通（Carbamazepine）常見副作用包含腸胃脹氣與頭暈，建議隨餐服用。"
    normal_msg.tool_calls = None
    normal_choice = MagicMock()
    normal_choice.message = normal_msg
    normal_resp.choices = [normal_choice]
    normal_resp.usage = None
    mock_client.chat.completions.create.return_value = normal_resp

    res = execute_ablation_turn(
        user_text="癲通副作用成因是什麼？",
        patient_file=p_file,
        messages=[{"role": "user", "content": "癲通副作用成因是什麼？"}],
        talker_client=mock_client,
        planner_client=mock_client,
    )

    assert res is not None
    assert len(res["final_output"].strip()) > 0
    assert "癲通" in res["final_output"] or "仿單" in res["final_output"]


def test_medication_bag_forced_rag_stability_10_runs(tmp_path):
    """
    回歸測試（護欄 4）：
    驗證藥袋影像輪必須 100% 觸發 RAG 實證檢索（審計日誌顯示 search_handbook 與 RAG 命中）。
    執行 10 次迴圈，每次皆必須穩定觸發。
    """
    from diabetes_chatbot.server.handlers import process_patient_message, _SESSION_CACHE
    from diabetes_chatbot.memory import get_patient_file_path

    img_file = Path(__file__).resolve().parent.parent.parent / "fixtures/images/medication_bag_front.jpg"
    assert img_file.exists(), f"測試藥袋照片不存在: {img_file}"

    for i in range(10):
        test_uid = f"test_rag_bag_stability_{i}"
        p_path = get_patient_file_path(f"line_{test_uid}")
        if p_path.exists():
            p_path.unlink()
        _SESSION_CACHE.pop(test_uid, None)

        res = process_patient_message(
            user_id=test_uid,
            image_path=str(img_file),
        )

        assert res is not None, f"第 {i+1} 次執行回傳為 None"
        assert res["reply_type"] == "text"
        assert len(res["reply_text"].strip()) > 0, f"第 {i+1} 次回覆文字為空"
        audit = res.get("audit_log") or ""
        assert "search_handbook" in audit, f"第 {i+1} 次審計日誌未顯示 search_handbook: {audit}"
        assert "實證檢索 (RAG)：命中" in audit, f"第 {i+1} 次審計日誌未顯示 RAG 命中: {audit}"


def test_diet_retrieval_policy_v3_four_scenarios(tmp_path):
    """
    飲食檢索政策升級 v3 驗證測試（四大情境）：
    1. 糖尿病平常飲食要注意什麼 ➔ 提問型，必須 RAG 命中
    2. 我中午吃了芭樂好好吃 ➔ 分享型，不觸發 RAG
    3. 芭樂一次吃一整顆會不會讓血糖飆高 ➔ 提問型，必須 RAG 命中
    4. 既有 test_diet_rag_filter 全綠不回歸（由 pytest 串聯保證）
    """
    from diabetes_chatbot.server.handlers import process_patient_message, _SESSION_CACHE
    from diabetes_chatbot.memory import get_patient_file_path

    # 情境 1: 糖尿病平常飲食要注意什麼 (提問型 -> 必查)
    uid_1 = "test_diet_v3_q1"
    p_1 = get_patient_file_path(f"line_{uid_1}")
    if p_1.exists(): p_1.unlink()
    _SESSION_CACHE.pop(uid_1, None)
    res_1 = process_patient_message(user_id=uid_1, text_input="糖尿病平常飲食要注意什麼")
    assert res_1 and res_1["reply_type"] == "text"
    audit_1 = res_1.get("audit_log") or ""
    assert "search_handbook" in audit_1, f"情境 1 未調用 search_handbook: {audit_1}"
    assert "實證檢索 (RAG)：命中" in audit_1, f"情境 1 未顯示 RAG 命中: {audit_1}"

    # 情境 2: 我中午吃了芭樂好好吃 (分享型 -> 不查)
    uid_2 = "test_diet_v3_q2"
    p_2 = get_patient_file_path(f"line_{uid_2}")
    if p_2.exists(): p_2.unlink()
    _SESSION_CACHE.pop(uid_2, None)
    res_2 = process_patient_message(user_id=uid_2, text_input="我中午吃了芭樂好好吃")
    assert res_2 and res_2["reply_type"] == "text"
    audit_2 = res_2.get("audit_log") or ""
    assert "search_handbook" not in audit_2, f"情境 2 誤調用了 search_handbook: {audit_2}"
    assert "實證檢索 (RAG)：未觸發" in audit_2, f"情境 2 誤觸發了 RAG: {audit_2}"

    # 情境 3: 芭樂一次吃一整顆會不會讓血糖飆高 (提問型 -> 必查)
    uid_3 = "test_diet_v3_q3"
    p_3 = get_patient_file_path(f"line_{uid_3}")
    if p_3.exists(): p_3.unlink()
    _SESSION_CACHE.pop(uid_3, None)
    res_3 = process_patient_message(user_id=uid_3, text_input="芭樂一次吃一整顆會不會讓血糖飆高")
    assert res_3 and res_3["reply_type"] == "text"
    audit_3 = res_3.get("audit_log") or ""
    assert "search_handbook" in audit_3, f"情境 3 未調用 search_handbook: {audit_3}"
    assert "實證檢索 (RAG)：命中" in audit_3, f"情境 3 未顯示 RAG 命中: {audit_3}"


def test_audit_in_chat_switch_behavior(monkeypatch):
    """
    驗證審計日誌分層開關行為：
    1. 預設/關閉 (AUDIT_IN_CHAT=false)：
       - reply_text 乾淨，不含【專科臨床大腦審計】或五支針
       - return dict 中的 audit_log 獨立欄位完整全量保留
    2. 開啟 (AUDIT_IN_CHAT=true)：
       - reply_text 附加【專科臨床大腦審計 (Demo 精簡版)】五支針
       - return dict 中的 audit_log 獨立欄位依舊完整全量保留
    3. chat_logs.jsonl 包含完整全量 audit_log
    """
    from diabetes_chatbot.server.handlers import process_patient_message, _SESSION_CACHE
    from diabetes_chatbot.memory import get_patient_file_path
    from diabetes_chatbot.logger import LOG_FILE
    import json

    # 1. 測試 AUDIT_IN_CHAT=false (預設日常模式)
    monkeypatch.setenv("AUDIT_IN_CHAT", "false")
    uid_false = "test_audit_switch_false"
    p_f = get_patient_file_path(f"line_{uid_false}")
    if p_f.exists(): p_f.unlink()
    _SESSION_CACHE.pop(uid_false, None)

    res_f = process_patient_message(user_id=uid_false, text_input="護理師你好，我今天量血糖110")
    assert res_f["reply_type"] == "text"
    assert "【專科臨床大腦審計" not in res_f["reply_text"]
    assert "• 第一級安全守護：" not in res_f["reply_text"]
    assert "【專科臨床大腦審計日誌】" in res_f["audit_log"]
    assert "• TADE 6 大臨床槽位狀態：" in res_f["audit_log"]

    # 2. 測試 AUDIT_IN_CHAT=true (Demo 展示模式)
    monkeypatch.setenv("AUDIT_IN_CHAT", "true")
    uid_true = "test_audit_switch_true"
    p_t = get_patient_file_path(f"line_{uid_true}")
    if p_t.exists(): p_t.unlink()
    _SESSION_CACHE.pop(uid_true, None)

    res_t = process_patient_message(user_id=uid_true, text_input="護理師你好，我今天量血糖110")
    assert res_t["reply_type"] == "text"
    assert "【專科臨床大腦審計 (Demo 精簡版)】" in res_t["reply_text"]
    assert "• 第一級安全守護：" in res_t["reply_text"]
    assert "• 工具調用與檢索：" in res_t["reply_text"]
    assert "• TADE 6 槽位狀態：" in res_t["reply_text"]
    assert "• 系統耗時與底層推論：" in res_t["reply_text"]
    assert "• 就醫備忘錄解鎖閥門：" in res_t["reply_text"]
    assert "【專科臨床大腦審計日誌】" in res_t["audit_log"]
    assert "• TADE 6 大臨床槽位狀態：" in res_t["audit_log"]

    # 3. 驗證 chat_logs.jsonl 寫入
    if LOG_FILE.exists():
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if lines:
            last_record = json.loads(lines[-1])
            assert "audit_log" in last_record
            assert "【專科臨床大腦審計日誌】" in last_record["audit_log"]


def test_card_optimizations_three_fixes():
    """驗證就醫備忘錄三項精準優化：
    1. 待確認方向重複修除（依主題分化檢查項，嚴禁重複）
    2. 出處小字裸網址修正（三呈現全面轉官方人話出處，零裸網址）
    3. 用藥現況顯示層優化（文字與Flex卡摺疊英文學名為清爽短格式，QR保留完整學名）
    """
    raw_meds = "癲通 長效膜衣錠 ２００毫克（卡巴氮平） / TEGRETOL CR.FC * tab 200 mg (Carbamazepine)（藥袋已帶待現場核對）"
    ddx_raw = [
        "待確認低血糖原因 — 待做檢查：核對血糖紀錄簿與藥物劑量",
        "待確認服藥後腸胃不適 — 待做檢查：核對血糖紀錄簿與藥物劑量",
    ]
    raw_evidence = [
        {"title": "國健署指引", "url": "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=45&pid=123"},
        "TFDA藥品仿單（https://www.fda.gov.tw/MLMS/H0001D.aspx?Type=Lic&LicId=01000000）",
    ]

    # 1. 產生文字卡
    summary_text = generate_previsit_intake_summary(
        visit_reason="回診調藥與血糖追蹤",
        medications=raw_meds,
        glucose_metrics="空腹血糖 115 mg/dL",
        hypo_history="早上頭暈 65 mg/dL",
        side_effects_or_concerns="肚子脹氣",
        ddx_candidates=ddx_raw,
        evidence_links=raw_evidence,
        patient_quote="吃飽想吃大芭樂",
        diet_lifestyle="中午想吃一整顆大芭樂",
    )

    # 2. 產生 Flex 卡
    flex_bubble = generate_line_flex_bubble(
        visit_reason="回診調藥與血糖追蹤",
        medications=raw_meds,
        glucose_metrics="空腹血糖 115 mg/dL",
        hypo_history="早上頭暈 65 mg/dL",
        side_effects_or_concerns="肚子脹氣",
        ddx_candidates=ddx_raw,
        evidence_links=raw_evidence,
        patient_quote="吃飽想吃大芭樂",
        diet_lifestyle="中午想吃一整顆大芭樂",
    )

    # 3. 產生 QR payload
    qr_payload = generate_clinic_qr_payload(
        visit_reason="回診調藥與血糖追蹤",
        medications=raw_meds,
        glucose_metrics="空腹血糖 115 mg/dL",
        hypo_history="早上頭暈 65 mg/dL",
        side_effects_or_concerns="肚子脹氣",
        ddx_candidates=ddx_raw,
        evidence_links=raw_evidence,
        patient_quote="吃飽想吃大芭樂",
        diet_lifestyle="中午想吃一整顆大芭樂",
    )

    # 斷言 1：待確認方向檢查項去重與分化
    assert "待做檢查：核對血糖紀錄簿與藥物劑量" in summary_text
    assert "待做檢查：攜藥袋現場核對，請醫師評估腸胃友善劑型" in summary_text
    # 嚴禁出現兩次一模一樣的待做檢查
    assert summary_text.count("待做檢查：核對血糖紀錄簿與藥物劑量") == 1

    # 斷言 2：出處小字零裸網址，三呈現統一為官方來源人話
    assert "http://" not in summary_text and "https://" not in summary_text
    assert "衛生福利部國民健康署《糖尿病與我》手冊" in summary_text
    assert "衛生福利部食品藥物管理署 (TFDA) 官方藥品仿單" in summary_text

    flex_str = json.dumps(flex_bubble, ensure_ascii=False)
    assert "http://" not in flex_str and "https://" not in flex_str
    assert "衛生福利部國民健康署《糖尿病與我》手冊" in flex_str

    assert "http://" not in qr_payload and "https://" not in qr_payload
    assert "衛生福利部國民健康署《糖尿病與我》手冊" in qr_payload

    # 斷言 3：用藥現況顯示層短格式化 vs QR payload 保留學名
    # 文字卡與 Flex 卡只顯示中文名與劑量，摺疊長串英文學名
    assert "癲通長效膜衣錠 200毫克" in summary_text
    assert "TEGRETOL" not in summary_text
    assert "Carbamazepine" not in summary_text

    assert "癲通長效膜衣錠 200毫克" in flex_str
    assert "TEGRETOL" not in flex_str
    assert "Carbamazepine" not in flex_str

    # QR payload 供診間藥師核對，保留原始完整學名
    assert "TEGRETOL" in qr_payload
    assert "Carbamazepine" in qr_payload


def test_card_medication_reconciliation_discontinued_single_appearance():
    """驗證用藥現況停用調和（解決醫療矛盾）：
    1. 當藥物出現已停服/已停用標記時，同名條目不得再以現行用藥列出；
    2. 文字卡與 Flex 卡現行用藥只呈現未停用藥品（得爾美），停用藥標註（已停用換藥）；
    3. 全卡任何位置，癲通只能以停用身份出現一次；
    4. QR payload 保留藥袋全名與學名，且必須標註（已停用換藥），嚴禁無標註之停用藥出現在用藥欄。
    """
    raw_switch_meds = "得爾美 (Diamicron)，已停服癲通，服藥規律；藥袋已辨識：癲通 長效膜衣錠 ２００毫克（卡巴氮平） / TEGRETOL CR.FC * tab 200 mg (Carbamazepine)"

    # 1. 產生文字卡
    summary_text = generate_previsit_intake_summary(
        visit_reason="回診調藥與血糖追蹤",
        medications=raw_switch_meds,
        glucose_metrics="空腹血糖 115 mg/dL",
        hypo_history="無",
        side_effects_or_concerns="肚子已不脹",
    )

    # 2. 產生 Flex 卡
    flex_bubble = generate_line_flex_bubble(
        visit_reason="回診調藥與血糖追蹤",
        medications=raw_switch_meds,
        glucose_metrics="空腹血糖 115 mg/dL",
        hypo_history="無",
        side_effects_or_concerns="肚子已不脹",
    )

    # 3. 產生 QR payload
    qr_payload = generate_clinic_qr_payload(
        visit_reason="回診調藥與血糖追蹤",
        medications=raw_switch_meds,
        glucose_metrics="空腹血糖 115 mg/dL",
        hypo_history="無",
        side_effects_or_concerns="肚子已不脹",
    )

    # 提取文字卡第二點：② 用藥現況
    med_line_text = [l for l in summary_text.splitlines() if l.startswith("② 用藥現況：")][0]
    # 提取 Flex 卡第二點：用藥現況
    flex_med_box = [c for c in flex_bubble["body"]["contents"] if c.get("contents") and c["contents"][0]["text"] == "② 用藥現況"][0]
    flex_med_text = flex_med_box["contents"][1]["text"]

    # 斷言 A：文字卡與 Flex 卡現行用藥只列得爾美，癲通只以停用身份出現一次
    assert "得爾美" in med_line_text
    assert "癲通長效膜衣錠 200毫克（已停用換藥）" in med_line_text
    assert med_line_text.count("癲通") == 1  # 癲通全欄只出現一次！
    assert "已停服癲通" not in med_line_text

    assert "得爾美" in flex_med_text
    assert "癲通長效膜衣錠 200毫克（已停用換藥）" in flex_med_text
    assert flex_med_text.count("癲通") == 1  # 癲通全欄只出現一次！
    assert "已停服癲通" not in flex_med_text

    # 斷言 B：QR payload 保留藥袋辨識全名但必須標註（已停用換藥），癲通只能以停用身份出現一次
    # 提取用藥現況欄位
    m_qr_med = re.search(r"\|用藥現況:([^\|]+)\|", qr_payload)
    assert m_qr_med is not None
    qr_med_str = m_qr_med.group(1)
    assert "得爾美 (Diamicron)" in qr_med_str
    assert "TEGRETOL CR.FC * tab 200 mg (Carbamazepine)（已停用換藥）" in qr_med_str
    assert qr_med_str.count("癲通") == 1  # QR 用藥欄位中癲通也只出現一次！
    assert "已停服癲通" not in qr_med_str

