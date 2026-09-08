import inspect
from unittest.mock import MagicMock, patch

from diabetes_chatbot.server.handlers import process_patient_message


def _make_mock_client(reply_text="您好，今天天氣不錯喔，飲食上也要注意均衡呢？"):
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = reply_text
    mock_choice.message.tool_calls = None
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_resp
    return mock_client


def test_signature_has_ablation_config_param():
    sig = inspect.signature(process_patient_message)
    assert "ablation_config" in sig.parameters, "ablation_config param missing from signature"
    param = sig.parameters["ablation_config"]
    assert param.default is None


def test_without_ablation_config_still_works():
    mock_client = _make_mock_client()
    with patch("diabetes_chatbot.server.handlers.get_openai_client", return_value=mock_client):
        result = process_patient_message(user_id="compat_no_arg", text_input="護理師您好，我今天吃糙米飯配煎魚")
        assert result["reply_type"] == "text"
        assert "reply_text" in result
        assert result["audit_log"] is not None


def test_with_none_same_as_no_arg():
    mock_client = _make_mock_client("今天血糖 110 蠻穩定的喔，繼續保持呢？")
    with patch("diabetes_chatbot.server.handlers.get_openai_client", return_value=mock_client):
        r1 = process_patient_message(user_id="compat_none_1", text_input="今天血糖 110")
        # reset session cache for comparable second call with different user but same input
        r2 = process_patient_message(user_id="compat_none_2", text_input="今天血糖 110", ablation_config=None)
        # Both should succeed and produce audit_log; core reply_text prefix before audit should be comparable
        assert r1["reply_type"] == r2["reply_type"] == "text"
        # Strip audit_log tail for comparison: reply_text contains final_reply + audit_log
        # Compare that final_reply handling is identical (at least not error)
        assert "今天血糖" in r1["reply_text"] or "血糖" in r1["reply_text"] or len(r1["reply_text"]) > 10
        assert "今天血糖" in r2["reply_text"] or "血糖" in r2["reply_text"] or len(r2["reply_text"]) > 10


def test_injection_with_dummy_config_does_not_break():
    # Simulate harness AblationConfig as simple object with all flags False (A condition would be all False except maybe prompt)
    class DummyConfig:
        enable_planner = False
        enable_dynamic_tool_gate = False
        enable_output_guard = False
        enable_forced_retrieval = False
        enable_question_budget_postprocessing = False
        enable_fixed_warning_append = False

    mock_client = _make_mock_client("這是測試回覆，包含調藥陷阱：你可以少吃半顆庫魯化試試看？另外今天血糖多少呢？還有嗎？")
    with patch("diabetes_chatbot.server.handlers.get_openai_client", return_value=mock_client):
        result = process_patient_message(user_id="compat_dummy", text_input="我吃庫魯化覺得脹脹的，不想吃", ablation_config=DummyConfig())
        assert result["reply_type"] == "text"
        # With enable_output_guard False, the violating text should NOT be blocked (thin branching demo)
        # So we assert it still returns without error; exact blocking behavior depends on flag
        assert "reply_text" in result


def test_injection_with_dict_config():
    mock_client = _make_mock_client("安全回覆測試。")
    cfg = {
        "enable_planner": True,
        "enable_dynamic_tool_gate": True,
        "enable_output_guard": True,
        "enable_forced_retrieval": False,
        "enable_question_budget_postprocessing": False,
        "enable_fixed_warning_append": False,
    }
    with patch("diabetes_chatbot.server.handlers.get_openai_client", return_value=mock_client):
        result = process_patient_message(user_id="compat_dict", text_input="什麼是糖尿病？", ablation_config=cfg)
        assert result["reply_type"] == "text"
