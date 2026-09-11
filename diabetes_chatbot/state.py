"""
狀態閥門與動態工具暴露 (Deterministic Tool Exposure)
基於臨床規劃大腦 (Clinical Planner) 臨床資訊充分度進行確定性工具解鎖。
"""
from typing import Optional
from diabetes_chatbot.tools import TOOL_SEARCH_HANDBOOK, TOOL_GENERATE_VISIT_SUMMARY
from diabetes_chatbot.planner import evaluate_clinical_planner, RetrievalDomain, PlannerAssessment

def should_unlock_visit_summary(
    messages: list,
    patient_file_path: Optional[str] = None,
    patient_record: Optional[dict] = None,
    planner_assessment: Optional[PlannerAssessment] = None
) -> bool:
    """判斷是否達到解鎖門診預問診摘要（就醫備忘錄）工具的臨床充分度門檻"""
    if planner_assessment is not None:
        assessment = planner_assessment
    else:
        assessment = evaluate_clinical_planner(
            messages,
            patient_file_path=patient_file_path,
            patient_record=patient_record
        )
    return assessment.can_unlock_summary_tool

def get_active_tools(
    messages: list,
    patient_file_path: Optional[str] = None,
    patient_record: Optional[dict] = None,
    planner_assessment: Optional[PlannerAssessment] = None
) -> list:
    """
    依據當前臨床對話狀態與臨床規劃大腦評估，動態決定暴露給大模型的工具清單 (Dynamic Tool Exposure)。
    - 純飲食營養生活領域 (DIET_NUTRITION)：物理收起檢索工具，不暴露 TOOL_SEARCH_HANDBOOK，杜絕藥品圖譜污染。
    - 藥品安全 (DRUG_SAFETY) 或一般衛教 (GENERAL_EDUCATION)：暴露 TOOL_SEARCH_HANDBOOK 以檢索 TFDA 仿單與衛教手冊。
    - 達到就醫充分度 (can_unlock_summary_tool)：解鎖 TOOL_GENERATE_VISIT_SUMMARY。
    - 支援外部傳入 planner_assessment，避免二次重複計算。
    """
    if planner_assessment is not None:
        assessment = planner_assessment
    else:
        assessment = evaluate_clinical_planner(
            messages,
            patient_file_path=patient_file_path,
            patient_record=patient_record
        )
    
    active_tools = []
    if assessment.can_unlock_summary_tool:
        active_tools.append(TOOL_GENERATE_VISIT_SUMMARY)

    # 檢索工具暴露：純飲食生活分享 (DIET_NUTRITION) 物理收起；飲食提問 (DIET_NUTRITION_KNOWLEDGE)、藥品安全 (DRUG_SAFETY) 與一般衛教 (GENERAL_EDUCATION) 均暴露
    if assessment.retrieval_domain != RetrievalDomain.DIET_NUTRITION:
        if assessment.retrieval_domain in [RetrievalDomain.DRUG_SAFETY, RetrievalDomain.GENERAL_EDUCATION, RetrievalDomain.DIET_NUTRITION_KNOWLEDGE]:
            active_tools.append(TOOL_SEARCH_HANDBOOK)
        elif not assessment.is_visit_mode:
            active_tools.append(TOOL_SEARCH_HANDBOOK)
        
    return active_tools
