"""
飲食與餐點查詢 RAG 過濾驗證測試
驗證重點：
1. 使用者提問餐點（如王子麵、大豆乾、豆皮）時，不得回傳類澱粉或胰島素吸收不足等圖譜 ADR 雜訊
2. 飲食情境下若無特定條目，回傳客觀國健署手冊飲食指引，絕不可回傳「依臨床常規…讓 LLM 自由回答」指令
3. 非飲食之藥品查詢（如 SGLT2）不受影響，仍可正常檢索圖譜證據
"""
import pytest
from diabetes_chatbot.tools import search_handbook, _is_diet_or_meal_query


def test_is_diet_or_meal_query_detection():
    """驗證飲食/餐點意圖判定的準確性與確定性"""
    # 典型餐點輸入
    assert _is_diet_or_meal_query("王子麵 豆製品 豆乾 豆皮 澱粉 醣類 糖尿病 飲食", "我吃了王子麵大豆乾蘿蔔 豆皮") is True
    assert _is_diet_or_meal_query("王子麵", "我剛剛吃了一包王子麵") is True
    assert _is_diet_or_meal_query("早餐 燕麥 地瓜", "") is True
    assert _is_diet_or_meal_query("油炸 豆皮", "豆皮熱量高嗎") is True

    # 純藥物與一般數值查詢（不應誤判為飲食）
    assert _is_diet_or_meal_query("SGLT2抑制劑類", "我想問 SGLT2 抑制劑這個藥有什麼要注意的？") is False
    assert _is_diet_or_meal_query("空腹血糖 標準值", "請問糖尿病空腹血糖多少算正常") is False


def test_prince_noodle_case_filters_amyloidosis():
    """
    核心驗證案例：
    使用者輸入「我吃了王子麵大豆乾蘿蔔 豆皮」，關鍵字「王子麵 豆製品 豆乾 豆皮 澱粉 醣類 糖尿病 飲食」
    確認回傳文字絕不含「類澱粉」或「胰島素吸收不足」，且不含自由發揮指令
    """
    user_input = "我吃了王子麵大豆乾蘿蔔 豆皮"
    keyword = "王子麵 豆製品 豆乾 豆皮 澱粉 醣類 糖尿病 飲食"
    
    result = search_handbook(keyword, user_raw_input=user_input)
    
    # 確保回傳非空且具備足夠長度的衛教內容
    assert result and len(result) > 20
    
    # 核心斷言：絕對不得包含類澱粉蛋白與胰島素病理腫塊警訊
    assert "類澱粉" not in result, "檢索結果誤將「類澱粉」注入餐點查詢上下文"
    assert "胰島素吸收不足" not in result, "檢索結果誤將「胰島素吸收不足」注入餐點查詢上下文"
    assert "皮膚澱粉樣變性" not in result, "檢索結果誤將「皮膚澱粉樣變性」注入餐點查詢上下文"
    
    # 核心斷言：不得回傳指示 LLM 自由說明的指令式語句
    assert "依臨床常規" not in result, "檢索結果不得包含指示 LLM 自由發揮的語句"
    assert "親切說明" not in result, "檢索結果不得包含指示 LLM 親切說明的語句"
    
    # 確保包含國健署官方手冊之客觀指引
    assert "官方" in result or "飲食" in result or "衛教" in result


def test_single_food_keyword_fallback_hpa_diet_guidelines():
    """驗證單一食物關鍵字查無完全相符章節時，平滑回傳國健署標準飲食原則"""
    user_input = "我吃了王子麵"
    keyword = "王子麵"
    
    result = search_handbook(keyword, user_raw_input=user_input)
    
    assert result and len(result) > 20
    assert "類澱粉" not in result
    assert "胰島素吸收不足" not in result
    assert "依臨床常規" not in result
    
    # 應包含客觀官方飲食指引要點
    assert "飲食原則" in result or "均衡" in result or "醣" in result


def test_non_diet_drug_query_preserves_graph_evidence():
    """驗證藥物查詢情境下，圖譜臨床證據依然正常保留，不受飲食過濾影響"""
    query_drug = "SGLT2抑制劑類"
    user_q = "我想問 SGLT2 抑制劑這個藥有什麼要注意的？"
    
    result = search_handbook(query_drug, user_raw_input=user_q)
    
    # 藥品查詢應正常帶出臨床證據
    assert "官方臨床證據" in result
    assert "SGLT2" in result or "第二型糖尿病" in result
    assert "依臨床常規" not in result
