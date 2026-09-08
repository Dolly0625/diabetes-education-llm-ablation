import json
import tempfile
import uuid
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from llm_ablation_paper.workstream_1_technical_lead.harness.config import AblationConfig
from llm_ablation_paper.workstream_1_technical_lead.harness.runner import (
    run_ablation_turn,
    run_trajectory,
    get_canonical_tool_snapshot,
    to_contract_trajectory,
)
from llm_ablation_paper.workstream_1_technical_lead.harness.isolation import get_patient_file_for_state

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class CapturingFakeClient:
    def __init__(self, text="fake reply", tool_call=None, responses=None):
        self.captured_tools = None
        self.captured_messages = None
        self.call_count = 0
        self._text = text
        self._tool_call = tool_call
        self._responses = responses
        self._idx = 0
        self.chat = MagicMock()
        self.chat.completions = MagicMock()
        self.chat.completions.create = MagicMock(side_effect=self._create)

    def _create(self, **kwargs):
        self.call_count += 1
        self.captured_tools = kwargs.get("tools")
        self.captured_messages = kwargs.get("messages")
        if self._responses is not None:
            content = self._responses[self._idx % len(self._responses)]
            self._idx += 1
            msg = MagicMock()
            msg.content = content
            msg.tool_calls = None
            choice = MagicMock()
            choice.message = msg
            resp = MagicMock()
            resp.choices = [choice]
            return resp
        if self._tool_call and self.call_count == 1:
            msg = MagicMock()
            msg.content = ""
            msg.tool_calls = [self._tool_call]
            choice = MagicMock()
            choice.message = msg
            resp = MagicMock()
            resp.choices = [choice]
            return resp
        msg = MagicMock()
        msg.content = self._text
        msg.tool_calls = None
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp


def _cleanup(state_dir, run_id):
    try:
        ad = PROJECT_ROOT / "llm_ablation_paper" / "artifacts" / "workstream_1" / run_id
        if ad.exists() and PROJECT_ROOT in ad.parents:
            shutil.rmtree(ad, ignore_errors=True)
    except Exception:
        pass
    try:
        if Path(state_dir).exists():
            shutil.rmtree(Path(state_dir), ignore_errors=True)
    except Exception:
        pass


def _mock_assessment(domain="NONE", engine="python", can_unlock=False, is_visit=False):
    from diabetes_chatbot.planner import PlannerAssessment, ClinicalSlots, SlotStatus, RetrievalDomain
    slots = ClinicalSlots()
    try:
        rd = RetrievalDomain(domain)
    except Exception:
        rd = RetrievalDomain.NONE
    return PlannerAssessment(
        slots=slots,
        is_visit_mode=is_visit,
        is_explicit_request=False,
        is_agenda_confirmed=can_unlock,
        can_unlock_summary_tool=can_unlock,
        retrieval_domain=rd,
        detected_intent="GENERAL_HEALTH",
        talker_guidance="mock guidance" if engine != "neutral" else "",
        engine=engine,
        ddx_candidates=[],
        evidence_links=[],
    )


def test_A_never_calls_any_planner():
    run_id = f"RUN-INT-A-{uuid.uuid4().hex[:6]}"
    state_dir = tempfile.mkdtemp()
    config = AblationConfig.for_condition("A")
    object.__setattr__(config, "run_id", run_id)
    client = CapturingFakeClient(text="hello")
    with patch("diabetes_chatbot.server.ablation_core.evaluate_clinical_planner") as mp, \
         patch("diabetes_chatbot.server.ablation_core.evaluate_clinical_planner_llm") as ml:
        run_ablation_turn(config=config, user_id="p_int_a", message="你好", state_dir=state_dir, model_client=client, patient_id="p_int_a", turn_index=0, run_id=run_id)
        mp.assert_not_called()
        ml.assert_not_called()
    with patch("diabetes_chatbot.planner.evaluate_clinical_planner") as mp2, \
         patch("diabetes_chatbot.planner.evaluate_clinical_planner_llm") as ml2:
        run_id2 = f"RUN-INT-A2-{uuid.uuid4().hex[:6]}"
        sd2 = tempfile.mkdtemp()
        cfg2 = AblationConfig.for_condition("A")
        object.__setattr__(cfg2, "run_id", run_id2)
        run_ablation_turn(config=cfg2, user_id="p_int_a2", message="你好", state_dir=sd2, model_client=client, patient_id="p_int_a2", turn_index=0, run_id=run_id2)
        mp2.assert_not_called()
        ml2.assert_not_called()
        _cleanup(sd2, run_id2)
    _cleanup(state_dir, run_id)


def test_AB_tools_exactly_canonical():
    canonical = get_canonical_tool_snapshot()
    canonical_names = sorted([t["function"]["name"] for t in canonical])
    assert canonical_names == ["generate_previsit_intake_summary", "search_handbook"]
    for cond in ["A", "B"]:
        run_id = f"RUN-INT-AB-{cond}-{uuid.uuid4().hex[:6]}"
        state_dir = tempfile.mkdtemp()
        config = AblationConfig.for_condition(cond)
        object.__setattr__(config, "run_id", run_id)
        client = CapturingFakeClient(text="hi")
        mock_ass = _mock_assessment(engine="python")
        with patch("diabetes_chatbot.server.ablation_core.evaluate_clinical_planner_llm", return_value=mock_ass):
            with patch("diabetes_chatbot.server.ablation_core.evaluate_clinical_planner", return_value=mock_ass):
                run_ablation_turn(config=config, user_id="p_int_ab", message="你好", state_dir=state_dir, model_client=client, patient_id="p_int_ab", turn_index=0, run_id=run_id)
        assert client.captured_tools is not None
        captured_names = sorted([t["function"]["name"] for t in client.captured_tools])
        assert captured_names == canonical_names
        _cleanup(state_dir, run_id)
    canonical_sha_path = PROJECT_ROOT / "llm_ablation_paper" / "artifacts" / "workstream_1"
    # Also verify tool_snapshot.json always canonical
    run_id3 = f"RUN-INT-CANON-{uuid.uuid4().hex[:6]}"
    sd3 = tempfile.mkdtemp()
    cfg3 = AblationConfig.for_condition("C")
    object.__setattr__(cfg3, "run_id", run_id3)
    c3 = CapturingFakeClient(text="hi")
    run_ablation_turn(config=cfg3, user_id="pc", message="我今天吃糙米飯", state_dir=sd3, model_client=c3, patient_id="pc", turn_index=0, run_id=run_id3)
    from llm_ablation_paper.workstream_1_technical_lead.harness.runner import _resolve_artifact_dir
    ad = _resolve_artifact_dir(Path(sd3), run_id3)
    snap_path = ad / "tool_snapshot.json"
    if not snap_path.exists():
        snap_path = Path(sd3) / "tool_snapshot.json"
    assert snap_path.exists()
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    snap_names = sorted([t["function"]["name"] for t in snap["tools"]])
    assert snap_names == canonical_names
    _cleanup(sd3, run_id3)


def test_BCD_walk_LLM_planner_path():
    for cond in ["B", "C", "D"]:
        run_id = f"RUN-INT-LLM-{cond}-{uuid.uuid4().hex[:6]}"
        state_dir = tempfile.mkdtemp()
        config = AblationConfig.for_condition(cond)
        object.__setattr__(config, "run_id", run_id)
        client = CapturingFakeClient(text="hi")
        mock_ass = _mock_assessment(domain="GENERAL_EDUCATION", engine="llm")
        with patch("diabetes_chatbot.server.ablation_core.evaluate_clinical_planner_llm", return_value=mock_ass) as m_llm:
            with patch("diabetes_chatbot.server.ablation_core.evaluate_clinical_planner", return_value=_mock_assessment(engine="python")) as m_py:
                res = run_ablation_turn(config=config, user_id="p_llm", message="什麼是糖尿病？", state_dir=state_dir, model_client=client, patient_id="p_llm", turn_index=0, run_id=run_id)
            assert m_llm.called
            assert m_llm.call_count >= 1  # retry may cause multiple attempts; at-least-once proves LLM path
            assert res["planner_result_or_neutral"]["engine"] == "llm"
            assert m_llm.called
        _cleanup(state_dir, run_id)


def test_CD_gate_identical_for_same_input():
    msg = "我今天中午吃糙米飯配煎魚"
    exposed = {}
    for cond in ["C", "D"]:
        run_id = f"RUN-INT-CD-{cond}-{uuid.uuid4().hex[:6]}"
        state_dir = tempfile.mkdtemp()
        config = AblationConfig.for_condition(cond)
        object.__setattr__(config, "run_id", run_id)
        client = CapturingFakeClient(text="fake")
        mock_ass = _mock_assessment(domain="DIET_NUTRITION", engine="llm", is_visit=False, can_unlock=False)
        with patch("diabetes_chatbot.server.ablation_core.evaluate_clinical_planner_llm", return_value=mock_ass):
            res = run_ablation_turn(config=config, user_id="p_cd", message=msg, state_dir=state_dir, model_client=client, patient_id="p_cd", turn_index=0, run_id=run_id)
        exposed[cond] = sorted(res["exposed_tools"])
        _cleanup(state_dir, run_id)
    assert exposed["C"] == exposed["D"]
    assert "search_handbook" not in exposed["C"]


def test_same_raw_breach_only_D_overwrites():
    breach = "你可以少吃一顆庫魯化試試看"
    results = {}
    for cond in ["A", "B", "C", "D"]:
        run_id = f"RUN-INT-BREACH-{cond}-{uuid.uuid4().hex[:6]}"
        state_dir = tempfile.mkdtemp()
        config = AblationConfig.for_condition(cond)
        object.__setattr__(config, "run_id", run_id)
        client = CapturingFakeClient(text=breach)
        mock_ass = _mock_assessment(engine="llm")
        with patch("diabetes_chatbot.server.ablation_core.evaluate_clinical_planner_llm", return_value=mock_ass):
            res = run_ablation_turn(config=config, user_id="p_breach", message="我吃庫魯化脹氣想停藥", state_dir=state_dir, model_client=client, patient_id="p_breach", turn_index=0, run_id=run_id)
        results[cond] = res
        _cleanup(state_dir, run_id)
    for cond in ["A", "B", "C"]:
        assert "少吃一顆" in results[cond]["raw_talker_output"]
        assert "少吃一顆" in results[cond]["assistant_response"]
        assert results[cond]["output_guard_result"]["is_blocked"] is False
        assert results[cond]["assistant_response"] == results[cond]["raw_talker_output"]
    assert "少吃一顆" in results["D"]["raw_talker_output"]
    assert "少吃一顆" not in results["D"]["assistant_response"]
    assert results["D"]["output_guard_result"]["is_blocked"] is True
    assert "臨床安全提醒" in results["D"]["assistant_response"] or "不能自行" in results["D"]["assistant_response"]


def test_tool_call_truly_executed():
    run_id = f"RUN-INT-TOOL-{uuid.uuid4().hex[:6]}"
    state_dir = tempfile.mkdtemp()
    config = AblationConfig.for_condition("B")
    object.__setattr__(config, "run_id", run_id)
    tool_call = MagicMock()
    tool_call.id = "call_123"
    tool_call.function.name = "search_handbook"
    tool_call.function.arguments = json.dumps({"keyword": "糖尿病飲食"})
    client = CapturingFakeClient(tool_call=tool_call, text="second reply after tool")
    mock_ass = _mock_assessment(domain="GENERAL_EDUCATION", engine="llm")
    with patch("diabetes_chatbot.server.ablation_core.evaluate_clinical_planner_llm", return_value=mock_ass):
        with patch("diabetes_chatbot.server.ablation_core.search_handbook", return_value="【官方衛教】糙米飯高纖") as m_search:
            with patch("diabetes_chatbot.tools.search_handbook", return_value="【官方衛教】糙米飯高纖"):
                res = run_ablation_turn(config=config, user_id="p_tool", message="什麼是糖尿病飲食？", state_dir=state_dir, model_client=client, patient_id="p_tool", turn_index=0, run_id=run_id)
                assert m_search.called
                assert m_search.call_count == 1
    assert "search_handbook" in res["called_tools"]
    assert client.call_count == 2
    assert len(res["tool_results"]) == 1
    assert res["tool_results"][0]["tool"] == "search_handbook"
    _cleanup(state_dir, run_id)


def test_resume_does_not_duplicate():
    run_id = f"RUN-INT-RESUME-{uuid.uuid4().hex[:6]}"
    state_dir = tempfile.mkdtemp()
    config = AblationConfig.for_condition("A")
    object.__setattr__(config, "run_id", run_id)
    client = CapturingFakeClient(responses=["reply0", "reply1"])
    results = run_trajectory(config=config, patient_id="p_resume", messages=["你好", "血糖110"], state_dir=state_dir, model_client=client, run_id=run_id)
    assert len(results) == 2
    from llm_ablation_paper.workstream_1_technical_lead.harness.runner import _resolve_artifact_dir
    ad = _resolve_artifact_dir(Path(state_dir), run_id)
    traj = ad / "trajectories.jsonl"
    if not traj.exists():
        traj = Path(state_dir) / "trajectories.jsonl"
    lines_before = [l for l in traj.read_text(encoding="utf-8").strip().splitlines() if l.strip()]
    assert len(lines_before) == 2
    results2 = run_trajectory(config=config, patient_id="p_resume", messages=["你好", "血糖110"], state_dir=state_dir, model_client=client, run_id=run_id, resume=True)
    assert len(results2) == 2
    lines_after = [l for l in traj.read_text(encoding="utf-8").strip().splitlines() if l.strip()]
    assert len(lines_after) == 2
    turns = [json.loads(l)["turn_index"] for l in lines_after]
    assert turns == [0, 1]
    _cleanup(state_dir, run_id)


def test_different_conditions_dont_pollute_state():
    dir_a = tempfile.mkdtemp()
    dir_c = tempfile.mkdtemp()
    run_id_a = f"RUN-INT-ISO-A-{uuid.uuid4().hex[:6]}"
    run_id_c = f"RUN-INT-ISO-C-{uuid.uuid4().hex[:6]}"
    config_a = AblationConfig.for_condition("A")
    config_c = AblationConfig.for_condition("C")
    object.__setattr__(config_a, "run_id", run_id_a)
    object.__setattr__(config_c, "run_id", run_id_c)
    client = CapturingFakeClient(text="fake")
    run_ablation_turn(config=config_a, user_id="iso_patient", message="血糖 150", state_dir=dir_a, model_client=client, patient_id="iso_patient", turn_index=0, run_id=run_id_a)
    run_ablation_turn(config=config_c, user_id="iso_patient", message="血糖 200", state_dir=dir_c, model_client=client, patient_id="iso_patient", turn_index=0, run_id=run_id_c)
    rec_a = json.loads(get_patient_file_for_state(dir_a, "iso_patient").read_text(encoding="utf-8")) if get_patient_file_for_state(dir_a, "iso_patient").exists() else {}
    rec_c = json.loads(get_patient_file_for_state(dir_c, "iso_patient").read_text(encoding="utf-8")) if get_patient_file_for_state(dir_c, "iso_patient").exists() else {}
    assert "150" in str(rec_a)
    assert "200" not in str(rec_a)
    assert "200" in str(rec_c)
    assert "150" not in str(rec_c)
    _cleanup(dir_a, run_id_a)
    _cleanup(dir_c, run_id_c)
    try:
        shutil.rmtree(dir_a, ignore_errors=True)
        shutil.rmtree(dir_c, ignore_errors=True)
    except Exception:
        pass


def test_production_no_config_maintains_behavior():
    client = CapturingFakeClient(text="您好，飲食很均衡喔")
    with patch("diabetes_chatbot.server.handlers.get_openai_client", return_value=client):
        from diabetes_chatbot.server.handlers import process_patient_message
        result = process_patient_message(user_id="prod_test", text_input="護理師您好，我今天吃糙米飯")
        assert result["reply_type"] == "text"
        assert "reply_text" in result
        assert len(result["reply_text"]) > 10
        assert result["audit_log"] is not None
        assert "糙米" in result["reply_text"] or "均衡" in result["reply_text"] or "飲食" in result["reply_text"] or len(result["reply_text"]) > 20


def test_contract_adapter():
    run_id = f"RUN-INT-CONTRACT-{uuid.uuid4().hex[:6]}"
    state_dir = tempfile.mkdtemp()
    config = AblationConfig.for_condition("B")
    object.__setattr__(config, "run_id", run_id)
    client = CapturingFakeClient(text="contract reply")
    run_ablation_turn(config=config, user_id="p_contract", message="你好", state_dir=state_dir, model_client=client, patient_id="p_contract", turn_index=0, run_id=run_id)
    contract = to_contract_trajectory(run_id, state_dir)
    assert contract["run_id"] == run_id
    assert "turns" in contract
    assert len(contract["turns"]) == 1
    assert contract["turns"][0]["patient_text"] == "你好"
    assert "planner_state" in contract["turns"][0]
    assert "tools_exposed" in contract["turns"][0]
    assert "tools_called" in contract["turns"][0]
    assert "raw_talker_output" in contract["turns"][0]
    assert "guard_action" in contract["turns"][0]
    assert "final_output" in contract["turns"][0]
    assert "termination_reason" in contract
    _cleanup(state_dir, run_id)


def test_state_dir_rejection():
    run_id = f"RUN-INT-REJECT-{uuid.uuid4().hex[:6]}"
    state_dir = PROJECT_ROOT / "llm_ablation_paper" / "artifacts" / "workstream_1" / run_id
    state_dir.mkdir(parents=True, exist_ok=True)
    config = AblationConfig.for_condition("A")
    object.__setattr__(config, "run_id", run_id)
    client = CapturingFakeClient(text="hi")
    run_ablation_turn(config=config, user_id="p_rej", message="你好", state_dir=state_dir, model_client=client, patient_id="p_rej", turn_index=0, run_id=run_id)
    other_run = f"RUN-INT-REJECT2-{uuid.uuid4().hex[:6]}"
    config2 = AblationConfig.for_condition("A")
    object.__setattr__(config2, "run_id", other_run)
    with pytest.raises(FileExistsError):
        run_ablation_turn(config=config2, user_id="p_rej", message="你好2", state_dir=state_dir, model_client=client, patient_id="p_rej", turn_index=0, run_id=other_run, resume=False)
    res = run_ablation_turn(config=config, user_id="p_rej", message="你好2", state_dir=state_dir, model_client=client, patient_id="p_rej", turn_index=1, run_id=run_id, resume=True)
    assert res["turn_index"] == 1
    _cleanup(state_dir, run_id)
    try:
        shutil.rmtree(PROJECT_ROOT / "llm_ablation_paper" / "artifacts" / "workstream_1" / other_run, ignore_errors=True)
    except Exception:
        pass
