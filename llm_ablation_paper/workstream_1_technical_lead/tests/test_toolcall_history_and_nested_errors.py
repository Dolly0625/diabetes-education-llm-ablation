"""PHASE M4.1 驗證測試：Tool-Call 歷史完整性、Thought Signature 保留、滑動視窗原子性、第二次呼叫 Fail-Closed 與 Nested ERROR 攔截。"""
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from diabetes_chatbot.memory import prune_conversation_history, _sanitize_tool_history
from diabetes_chatbot.server.ablation_core import execute_ablation_turn, _serialize_assistant_tool_message
from llm_ablation_paper.workstream_1_technical_lead.harness.config import formal_ablation_config
from llm_ablation_paper.workstream_1_technical_lead.scripts.run_formal_experiment import (
    check_pilot_completed_cleanly,
    inspect_run_for_nested_errors,
    run_blind_export,
)


def _build_mock_planner_client():
    mock_planner = MagicMock()
    planner_choice = MagicMock()
    planner_choice.message = MagicMock(content=json.dumps({
        "intent": "ASK_QUESTION",
        "retrieval_domain": "GENERAL_EDUCATION",
        "missing_slots": [],
        "highest_priority_gap": None,
        "is_explicit_request": False,
        "can_unlock_summary_tool": False,
        "talker_guidance": "請說明糖尿病衛教"
    }))
    mock_planner.chat.completions.create.return_value = MagicMock(choices=[planner_choice], usage=None)
    return mock_planner


def test_serialize_assistant_tool_message_preserves_thought_signature():
    """驗證序列化 assistant 訊息時完整保留 Google thought_signature 與延伸 metadata。"""
    class MockToolCall:
        def __init__(self):
            self.id = "call_abc_123"
            self.type = "function"
            self.function = MagicMock(name="search_handbook", arguments='{"keyword": "糖尿病飲食"}')
            self.extra_content = {"google": {"thought_signature": "signature_hash_abcdef"}}

    class MockMsg:
        def __init__(self):
            self.role = "assistant"
            self.content = None
            self.tool_calls = [MockToolCall()]

        def model_dump(self, exclude_none=True):
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_abc_123",
                    "type": "function",
                    "function": {"name": "search_handbook", "arguments": '{"keyword": "糖尿病飲食"}'},
                    "extra_content": {"google": {"thought_signature": "signature_hash_abcdef"}},
                }],
            }

    msg = MockMsg()
    serialized = _serialize_assistant_tool_message(msg, "", "search_handbook", {"keyword": "糖尿病飲食"}, "call_abc_123")
    assert serialized["role"] == "assistant"
    assert len(serialized["tool_calls"]) == 1
    tc = serialized["tool_calls"][0]
    assert tc["id"] == "call_abc_123"
    assert "extra_content" in tc
    assert tc["extra_content"]["google"]["thought_signature"] == "signature_hash_abcdef"


def test_search_handbook_tool_response_structure_and_no_trailing_system(tmp_path):
    """驗證 search_handbook 執行後 tool response 補齊 name，second_task 併入 content，且無 trailing system message。"""
    patient_file = tmp_path / "patient.json"
    messages = []
    config = formal_ablation_config("C")

    mock_planner = _build_mock_planner_client()
    mock_talker = MagicMock()

    first_msg = {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": "call_handbook_1",
            "type": "function",
            "function": {"name": "search_handbook", "arguments": '{"keyword": "糖尿病飲食"}'},
            "extra_content": {"google": {"thought_signature": "sig_turn1"}},
        }],
    }
    first_choice = MagicMock()
    first_choice.message = first_msg
    first_resp = MagicMock(choices=[first_choice], usage=MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30))

    second_msg = MagicMock(content="依據國健署手冊建議，糖尿病飲食應定時定量。")
    second_choice = MagicMock(message=second_msg)
    second_resp = MagicMock(choices=[second_choice], usage=MagicMock(prompt_tokens=50, completion_tokens=40, total_tokens=90))

    mock_talker.chat.completions.create.side_effect = [first_resp, second_resp]

    res = execute_ablation_turn(
        user_text="我想了解糖尿病飲食注意事項",
        patient_file=patient_file,
        messages=messages,
        ablation_config=config,
        talker_client=mock_talker,
        planner_client=mock_planner,
        model="gemini-3.5-flash-lite",
        turn_index=1,
    )

    assert len(messages) == 4
    assert messages[0]["role"] == "user"

    asst_msg = messages[1]
    assert asst_msg["role"] == "assistant"
    assert asst_msg["tool_calls"][0]["extra_content"]["google"]["thought_signature"] == "sig_turn1"

    tool_msg = messages[2]
    assert tool_msg["role"] == "tool"
    assert tool_msg["name"] == "search_handbook"
    assert tool_msg["tool_call_id"] == "call_handbook_1"
    assert "【官方手冊衛教解說任務" in tool_msg["content"]

    call_args_list = mock_talker.chat.completions.create.call_args_list
    assert len(call_args_list) == 2
    second_call_messages = call_args_list[1].kwargs["messages"]
    assert second_call_messages[-1]["role"] == "tool"
    assert not any(m["role"] == "system" for m in second_call_messages[1:])


def test_second_talker_call_failure_fail_closed_in_ablation(tmp_path):
    """驗證在消融實驗模式下，第二次 Talker 呼叫失敗時嚴格 Fail-Closed，標記 ERROR 與結構化 error_metadata。"""
    patient_file = tmp_path / "patient.json"
    messages = []
    config = formal_ablation_config("C")

    mock_planner = _build_mock_planner_client()
    mock_talker = MagicMock()
    first_choice = MagicMock()
    first_choice.message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": "call_fail_1",
            "type": "function",
            "function": {"name": "search_handbook", "arguments": '{"keyword": "二甲雙胍"}'},
        }],
    }
    first_resp = MagicMock(choices=[first_choice], usage=None)

    mock_talker.chat.completions.create.side_effect = [
        first_resp,
        RuntimeError("400 Bad Request: Invalid message sequence"),
    ]

    res = execute_ablation_turn(
        user_text="請問二甲雙胍的副作用",
        patient_file=patient_file,
        messages=messages,
        ablation_config=config,
        talker_client=mock_talker,
        planner_client=mock_planner,
        turn_index=2,
    )

    assert res["termination_reason"] == "ERROR"
    assert "Second talker call failed" in str(res["error"])
    assert res["error_metadata"] is not None
    assert res["error_metadata"]["stage"] == "second_talker_call"
    assert res["error_metadata"]["turn"] == 2
    assert any("400 Bad Request" in err for err in res["error_metadata"]["errors"])
    assert "SECOND_TALKER_CALL_FAILED" in res["events"]


def test_prune_conversation_history_atomic_group_and_sanitization():
    """驗證滑動視窗修剪將 user -> assistant(tool_calls) -> tool 視為原子群組，且杜絕孤立 tool。"""
    history = [
        {"role": "system", "content": "護理師"},
        {"role": "user", "content": "問候 1"},
        {"role": "assistant", "content": "回答 1"},
        {"role": "user", "content": "我要查手冊"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "tc_1", "function": {"name": "search_handbook"}}]},
        {"role": "tool", "name": "search_handbook", "tool_call_id": "tc_1", "content": "手冊結果"},
        {"role": "assistant", "content": "根據手冊說明..."},
        {"role": "user", "content": "問候 3"},
        {"role": "assistant", "content": "回答 3"},
    ]

    pruned = prune_conversation_history(history, max_history_messages=4)
    assert pruned[0]["role"] == "system"

    for i, m in enumerate(pruned):
        if m["role"] == "tool":
            assert i > 0
            prev = pruned[i - 1]
            assert prev["role"] == "assistant"
            assert "tool_calls" in prev
            assert any(tc.get("id") == m.get("tool_call_id") for tc in prev["tool_calls"])

    bad_messages = [
        {"role": "system", "content": "護理師"},
        {"role": "tool", "name": "search_handbook", "tool_call_id": "tc_ghost", "content": "孤兒手冊"},
        {"role": "user", "content": "最新問題"},
    ]
    cleaned = _sanitize_tool_history(bad_messages)
    assert len(cleaned) == 2
    assert not any(m["role"] == "tool" for m in cleaned)


def test_inspect_run_for_nested_errors(tmp_path):
    """驗證 inspect_run_for_nested_errors 能遞迴抓取 roleplay_result 與 trajectories 內的 nested ERROR。"""
    run_dir = tmp_path / "WS4-PILOT-test-A"
    run_dir.mkdir(parents=True)

    clean_rp = {
        "run_id": "WS4-PILOT-test-A",
        "termination_reason": "PATIENT_GOAL_MET",
        "error_metadata": None,
        "records": [{
            "turn": 1,
            "harness_turn": {"termination_reason": "PATIENT_GOAL_MET", "error": None},
        }],
    }
    (run_dir / "roleplay_result.json").write_text(json.dumps(clean_rp, ensure_ascii=False), encoding="utf-8")
    (run_dir / "trajectories.jsonl").write_text(json.dumps({
        "turn_index": 1,
        "termination_reason": "PATIENT_GOAL_MET",
        "error": None,
    }) + "\n", encoding="utf-8")

    has_err, detail = inspect_run_for_nested_errors(run_dir)
    assert not has_err
    assert detail is None

    dirty_rp = {
        "run_id": "WS4-PILOT-test-A",
        "termination_reason": "PATIENT_GOAL_MET",
        "error_metadata": None,
        "records": [{
            "turn": 1,
            "harness_turn": {
                "termination_reason": "PATIENT_GOAL_MET",
                "error": None,
                "retry_metadata": {"errors": ["second_call_error: 400 Bad Request"]},
            },
        }],
    }
    (run_dir / "roleplay_result.json").write_text(json.dumps(dirty_rp, ensure_ascii=False), encoding="utf-8")
    has_err, detail = inspect_run_for_nested_errors(run_dir)
    assert has_err
    assert "non-transient retry error" in detail

    (run_dir / "roleplay_result.json").write_text(json.dumps(clean_rp, ensure_ascii=False), encoding="utf-8")
    (run_dir / "trajectories.jsonl").write_text(json.dumps({
        "turn_index": 2,
        "termination_reason": "ERROR",
        "error": "Second talker call failed",
    }) + "\n", encoding="utf-8")
    has_err, detail = inspect_run_for_nested_errors(run_dir)
    assert has_err
    assert "trajectory turn 2 termination_reason is ERROR" in detail


def test_check_pilot_completed_cleanly_rejects_nested_error(tmp_path):
    """驗證 check_pilot_completed_cleanly 遇到 nested ERROR 時 fail-closed 拋出例外。"""
    pilot_root = tmp_path / "pilot"
    pilot_root.mkdir()

    summary_data = {
        "runs": [
            {"condition": "A", "termination_reason": "PATIENT_GOAL_MET", "error": None, "run_id": "run_A"},
            {"condition": "B", "termination_reason": "PATIENT_GOAL_MET", "error": None, "run_id": "run_B"},
            {"condition": "C", "termination_reason": "PATIENT_GOAL_MET", "error": None, "run_id": "run_C"},
            {"condition": "D", "termination_reason": "PATIENT_GOAL_MET", "error": None, "run_id": "run_D"},
        ]
    }
    summary_file = pilot_root / "formal_pilot_summary.json"
    summary_file.write_text(json.dumps(summary_data, ensure_ascii=False), encoding="utf-8")

    run_c_dir = pilot_root / "run_C"
    run_c_dir.mkdir()
    (run_c_dir / "trajectories.jsonl").write_text(json.dumps({
        "turn_index": 1,
        "termination_reason": "ERROR",
        "error": "Second talker call failed",
    }) + "\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="contains nested ERROR"):
        check_pilot_completed_cleanly(summary_file)

def test_run_blind_export_excludes_nested_error(tmp_path):
    """驗證 run_blind_export 會自動識別並略過內部具有 nested error 的 run。"""
    raw_dir = tmp_path / "batch_raw"
    map_file = tmp_path / "mapping.json"
    out_dir = tmp_path / "blinded_out"
    mapping = {"A": "COND_A_SECRET", "B": "COND_B_SECRET", "C": "COND_C_SECRET", "D": "COND_D_SECRET"}
    map_file.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")

    from llm_ablation_paper.workstream_1_technical_lead.tests.test_formal_experiment_controller import _create_mock_run_dir

    # 1. 建立正常已完成的 run
    _create_mock_run_dir(raw_dir, "WS4-BATCH-SP-001-A", condition="A", patient_id="SP-001")

    # 2. 建立表面上頂層為 MAX_TURNS，但內部 trajectories.jsonl 含有 ERROR 的 run
    run_dirty_dir = raw_dir / "WS4-BATCH-SP-002-A"
    _create_mock_run_dir(raw_dir, "WS4-BATCH-SP-002-A", condition="A", patient_id="SP-002")
    # 注入 nested error 到 trajectories.jsonl
    traj_p = run_dirty_dir / "isolated_state" / "trajectories.jsonl"
    if not traj_p.exists():
        traj_p = run_dirty_dir / "trajectories.jsonl"
    with open(traj_p, "a", encoding="utf-8") as f:
        f.write(json.dumps({"turn_index": 99, "termination_reason": "ERROR", "error": "Nested fail"}) + "\n")

    summary = run_blind_export(
        raw_dir=raw_dir,
        mapping_file=map_file,
        output_dir=out_dir,
    )

    # dirty run 應被判定為 nested error 而略過 (skipped_error = 1)
    assert summary["exported_count"] == 1
    assert summary["skipped_error"] == 1
