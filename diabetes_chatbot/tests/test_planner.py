"""
臨床衛教大腦 Planner Agent (臨床資訊缺口動態追蹤器) 完整單元測試
涵蓋：
1. 日常閒聊不干擾測試
2. 缺失缺口動態計算與單題導引測試
3. 單輪高充分度病患立即收斂測試
4. 寬容收斂（記不得藥名、現場核對）測試
5. 狀態模組 (state.py) 向後相容性測試
"""
import pytest
from diabetes_chatbot.planner import (
    evaluate_clinical_planner,
    SlotStatus,
    PlannerAssessment
)
from diabetes_chatbot.state import should_unlock_visit_summary, get_active_tools
from diabetes_chatbot.tools import TOOL_SEARCH_HANDBOOK, TOOL_GENERATE_VISIT_SUMMARY

def test_casual_chat_does_not_trigger_visit_mode():
    """日常生活閒聊與衛教：不應啟動看診收斂模式，也不應解鎖產卡工具"""
    messages = [
        {"role": "user", "content": "護理師早安，我今天早餐吃了兩個蛋餅，很飽！"},
        {"role": "assistant", "content": "早安！蛋餅皮屬於碳水化合物，油脂也稍高，記得多搭配無糖豆漿或蔬菜喔。"},
        {"role": "user", "content": "好的，那我散步半小時夠嗎？"}
    ]
    assessment = evaluate_clinical_planner(messages, patient_record={})
    assert not assessment.is_visit_mode
    assert not assessment.can_unlock_summary_tool
    assert assessment.highest_priority_gap is None
    assert assessment.talker_guidance == ""
    
    # 驗證 tools 清單只暴露手冊查詢，不暴露產卡工具
    active = get_active_tools(messages, patient_record={})
    assert TOOL_SEARCH_HANDBOOK in active
    assert TOOL_GENERATE_VISIT_SUMMARY not in active

def test_visit_intent_missing_medication_gap():
    """表達看診意向但未提及用藥：應精準定位最高缺口為 medications，且單題指引"""
    messages = [
        {"role": "user", "content": "護理師，我下週三要回醫院看醫生了。"}
    ]
    assessment = evaluate_clinical_planner(messages, patient_record={})
    assert assessment.is_visit_mode
    assert not assessment.can_unlock_summary_tool
    assert assessment.highest_priority_gap == "medications"
    assert "平常用藥狀況" in assessment.talker_guidance
    assert "最多只問這一個問題" in assessment.talker_guidance
    assert not should_unlock_visit_summary(messages, patient_record={})

def test_visit_intent_known_med_missing_glucose_gap():
    """已提供藥物但缺乏數值：應定位最高缺口為 glucose_metrics"""
    messages = [
        {"role": "user", "content": "我下週要去拿慢箋，我平時都有按時吃庫魯化。"}
    ]
    assessment = evaluate_clinical_planner(messages, patient_record={})
    assert assessment.is_visit_mode
    assert assessment.slots.medications_status == SlotStatus.KNOWN
    assert "庫魯化" in assessment.slots.medications
    assert assessment.highest_priority_gap == "glucose_metrics"
    assert "近期血糖數值" in assessment.talker_guidance

def test_immediate_sufficiency_unlocks_summary_tool():
    """病患單輪表達完整就醫資訊與整理訴求：第一輪即刻達到充分度並解鎖產卡"""
    messages = [
        {"role": "user", "content": "剛量血糖大概 70，庫魯化我每天早晚吃一顆，幫我整理就醫備忘錄"}
    ]
    assessment = evaluate_clinical_planner(messages, patient_record={})
    assert assessment.is_visit_mode
    assert assessment.is_explicit_request
    assert assessment.can_unlock_summary_tool
    assert assessment.slots.medications_status == SlotStatus.KNOWN
    assert assessment.slots.glucose_metrics_status == SlotStatus.KNOWN
    assert "70" in assessment.slots.glucose_metrics
    assert should_unlock_visit_summary(messages, patient_record={})
    
    tools = get_active_tools(messages, patient_record={})
    assert TOOL_GENERATE_VISIT_SUMMARY in tools

def test_soft_sufficiency_with_unknown_medication():
    """寬容收斂：病患表示記不得藥名但會帶藥袋，且告知血糖數值，達到充分度"""
    messages = [
        {"role": "user", "content": "我下週要回診，但我記不得藥名，我會帶藥袋去診間。我最近自測血糖大概 130。"}
    ]
    assessment = evaluate_clinical_planner(messages, patient_record={})
    assert assessment.is_visit_mode
    assert assessment.slots.medications_status == SlotStatus.PARTIAL
    assert assessment.slots.glucose_metrics_status == SlotStatus.KNOWN
    assert assessment.can_unlock_summary_tool
    assert should_unlock_visit_summary(messages, patient_record={})

def test_hypoglycemia_slot_tracking():
    """低血糖病史槽位追蹤：辨識冒冷汗與心悸"""
    messages = [
        {"role": "user", "content": "我下週要看醫生，我吃庫魯化，上週有一次下午突然全身冒冷汗手抖。"}
    ]
    assessment = evaluate_clinical_planner(messages, patient_record={})
    assert assessment.slots.hypo_history_status == SlotStatus.KNOWN
    assert "冒冷汗" in assessment.slots.hypo_history
    assert assessment.can_unlock_summary_tool
