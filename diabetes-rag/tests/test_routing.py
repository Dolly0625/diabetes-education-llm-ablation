import pytest
from rag_retrieval.contract.enums import IntentTag, RetrievalRoute
from rag_retrieval.routing import decide_route

def test_decide_route_empty():
    assert decide_route([]) == RetrievalRoute.HYBRID

def test_decide_route_general_education():
    assert decide_route([IntentTag.GENERAL_EDUCATION]) == RetrievalRoute.HYBRID

def test_decide_route_medication_info():
    assert decide_route([IntentTag.GENERAL_MEDICATION_INFORMATION]) == RetrievalRoute.HYBRID

def test_decide_route_symptom_info():
    assert decide_route([IntentTag.SYMPTOM_INFORMATION]) == RetrievalRoute.HYBRID

def test_decide_route_medication_change():
    # 修正為正確的 IntentTag
    assert decide_route([IntentTag.MEDICATION_CHANGE_REQUEST]) == RetrievalRoute.GRAPH

def test_decide_route_diagnosis_and_non_medical():
    # 針對要求的 DIAGNOSIS_REQUEST 與 NON_MEDICAL 進行測試
    assert decide_route([IntentTag.DIAGNOSIS_REQUEST]) == RetrievalRoute.VECTOR
    assert decide_route([IntentTag.NON_MEDICAL]) == RetrievalRoute.VECTOR

def test_decide_route_mixed_intents():
    assert decide_route([IntentTag.MEDICATION_CHANGE_REQUEST, IntentTag.GENERAL_EDUCATION]) == RetrievalRoute.HYBRID