import hashlib
import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation import (
    DeterministicPatientAgent,
    FAKE_TALKER_RESPONSES,
    RoleplayRunner,
    load_profiles,
    run_fake_dry_run,
)
from llm_ablation_paper.workstream_1_technical_lead.harness import AblationConfig


def _harness_turn(message: str, turn_index: int) -> dict:
    return {
        "assistant_response": "請問您晚上會喝含糖飲料嗎？",
        "termination_reason": None,
        "turn_index": turn_index,
        "user_message": message,
    }


def test_frozen_profiles_are_read_only_and_complete():
    profiles_path = PROJECT_ROOT / "llm_ablation_paper/workstream_4_patient_simulation/patient_profiles.jsonl"
    before = hashlib.sha256(profiles_path.read_bytes()).hexdigest()
    profiles = load_profiles(profiles_path)
    after = hashlib.sha256(profiles_path.read_bytes()).hexdigest()

    assert before == after
    assert len(profiles) == 12
    assert profiles["SP-001"]["max_turns"] == 6


def test_hidden_fact_requires_direct_question():
    profile = load_profiles()["SP-001"]
    agent = DeterministicPatientAgent()
    initial = agent.next_turn(profile=profile, assistant_output=None, turn_number=1, prior_turns=[])
    assert initial["disclosed_facts"] == []

    not_direct = agent.next_turn(
        profile=profile,
        assistant_output="我了解您的困擾，請繼續說。",
        turn_number=2,
        prior_turns=[{"patient_turn": initial}],
    )
    assert not_direct["disclosed_facts"] == []

    direct = agent.next_turn(
        profile=profile,
        assistant_output="晚上會喝含糖飲料或吃宵夜嗎？",
        turn_number=2,
        prior_turns=[{"patient_turn": initial}],
    )
    assert direct["disclosed_facts"] == ["night_snack"]


def test_retry_is_bounded_and_records_metadata(tmp_path):
    runner = RoleplayRunner(
        patient_agent=DeterministicPatientAgent(),
        output_root=tmp_path,
        retry_delays=(0,),
        sleep=lambda _: None,
    )
    attempts = {"count": 0}

    def flaky_call():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise TimeoutError("temporary timeout")
        return [{"ok": True}]

    result, metadata = runner._run_with_retry(flaky_call)
    assert result == [{"ok": True}]
    assert [item["outcome"] for item in metadata] == ["retry", "success"]


def test_conditions_keep_separate_user_and_state_identity(tmp_path, monkeypatch):
    profile = load_profiles()["SP-001"]
    runner = RoleplayRunner(patient_agent=DeterministicPatientAgent(), output_root=tmp_path)

    def fake_harness(**kwargs):
        turn_index = len(kwargs["messages"]) - 1
        return [_harness_turn(kwargs["messages"][-1], turn_index)]

    monkeypatch.setattr(runner, "_call_harness", fake_harness)
    first = runner.run_condition(profile=profile, condition="A", fake_talker_responses=["x"] * 6)
    second = runner.run_condition(profile=profile, condition="B", fake_talker_responses=["x"] * 6)

    assert first["user_id"] != second["user_id"]
    assert first["run_id"] != second["run_id"]
    assert first["state_dir_id"] == second["state_dir_id"] == "isolated_state"
    assert (tmp_path / first["run_id"] / "isolated_state") != (tmp_path / second["run_id"] / "isolated_state")


def test_resume_continues_from_runner_checkpoint(tmp_path, monkeypatch):
    profile = load_profiles()["SP-001"]
    runner = RoleplayRunner(patient_agent=DeterministicPatientAgent(), output_root=tmp_path, retry_delays=(), sleep=lambda _: None)
    calls = {"count": 0}

    def interrupted_harness(**kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("non-transient test interruption")
        turn_index = len(kwargs["messages"]) - 1
        return [_harness_turn(kwargs["messages"][-1], turn_index)]

    monkeypatch.setattr(runner, "_call_harness", interrupted_harness)
    with pytest.raises(RuntimeError):
        runner.run_condition(profile=profile, condition="C", fake_talker_responses=["x"] * 6)

    checkpoint_path = tmp_path / "WS4-FAKE-SP-001-C" / "ws4_runner_checkpoint.json"
    failed_checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert failed_checkpoint["termination_reason"] == "ERROR"
    assert failed_checkpoint["error_metadata"]["stage"] == "harness"
    assert failed_checkpoint["pending_patient_turn"] is not None

    def recovered_harness(**kwargs):
        turn_index = len(kwargs["messages"]) - 1
        return [_harness_turn(kwargs["messages"][-1], turn_index)]

    monkeypatch.setattr(runner, "_call_harness", recovered_harness)
    resumed = runner.run_condition(profile=profile, condition="C", fake_talker_responses=["x"] * 6, resume=True)
    assert len(resumed["records"]) == 6
    assert resumed["termination_reason"] == "MAX_TURNS"


def test_fake_dry_run_uses_formal_per_turn_path(tmp_path):
    summary = run_fake_dry_run(tmp_path, patient_id="SP-001")
    assert len(summary["runs"]) == 4
    assert summary["formal_experiment_started"] is False
    total_turns = 0
    for run in summary["runs"]:
        assert run["turn_count"] == 6
        assert run["termination_reason"] == "MAX_TURNS"
        total_turns += run["turn_count"]
        result_path = tmp_path / run["run_id"] / "roleplay_result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        assert len(result["records"]) == 6
        for record in result["records"]:
            assert record["harness_turn"].get("research_patient_id") == "SP-001"
    assert total_turns == 24
    user_ids = {run["user_id"] for run in summary["runs"]}
    state_dirs = {run["state_dir_id"] for run in summary["runs"]}
    assert len(user_ids) == 4
    assert summary["runs"][0]["user_id"] != summary["runs"][1]["user_id"]


def test_patient_goal_met_is_taken_from_structured_patient_agent(tmp_path, monkeypatch):
    class GoalAgent:
        def next_turn(self, *, assistant_output, **_kwargs):
            if assistant_output is None:
                return {
                    "patient_utterance": "我想確認飲食怎麼安排。",
                    "should_end": False,
                    "termination_reason": "MAX_TURNS",
                    "disclosed_facts": [],
                    "evidence": "初始病患訊息。",
                }
            return {
                "patient_utterance": "謝謝你。",
                "should_end": True,
                "termination_reason": "PATIENT_GOAL_MET",
                "disclosed_facts": [],
                "evidence": "助理已回應病患目標，沒有待追問。",
            }

    runner = RoleplayRunner(patient_agent=GoalAgent(), output_root=tmp_path)
    monkeypatch.setattr(runner, "_call_harness", lambda **kwargs: [_harness_turn(kwargs["messages"][-1], 0)])
    result = runner.run_condition(profile=load_profiles()["SP-001"], condition="A", fake_talker_responses=["x"] * 6)

    assert result["termination_reason"] == "PATIENT_GOAL_MET"
    assert len(result["records"]) == 1
    checkpoint = json.loads(
        (tmp_path / result["run_id"] / "ws4_runner_checkpoint.json").read_text(encoding="utf-8")
    )
    assert checkpoint["termination_reason"] == "PATIENT_GOAL_MET"
    assert checkpoint["terminal_patient_turn"]["should_end"] is True
    assert checkpoint["records"] == result["records"]


def test_patient_agent_transient_failure_is_retried(tmp_path, monkeypatch):
    class FlakyPatientAgent:
        def __init__(self):
            self.calls = 0

        def next_turn(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("temporary patient API timeout")
            return {
                "patient_utterance": "我想確認飲食怎麼安排。",
                "should_end": False,
                "termination_reason": "MAX_TURNS",
                "disclosed_facts": [],
                "evidence": "重試後取得合法結構化回覆。",
            }

    agent = FlakyPatientAgent()
    runner = RoleplayRunner(
        patient_agent=agent,
        output_root=tmp_path,
        retry_delays=(0,),
        sleep=lambda _: None,
    )
    end_turn = _harness_turn("我想確認飲食怎麼安排。", 0)
    end_turn["termination_reason"] = "COMMON_INPUT_BLOCK"
    monkeypatch.setattr(runner, "_call_harness", lambda **_kwargs: [end_turn])

    result = runner.run_condition(
        profile=load_profiles()["SP-001"],
        condition="A",
        fake_talker_responses=["x"] * 6,
    )

    assert agent.calls == 2
    assert [item["outcome"] for item in result["records"][0]["patient_retry_metadata"]] == [
        "retry",
        "success",
    ]


def test_retry_exhaustion_persists_error_artifacts(tmp_path):
    class FailingPatientAgent:
        def next_turn(self, **_kwargs):
            raise TimeoutError("patient API remains unavailable")

    runner = RoleplayRunner(
        patient_agent=FailingPatientAgent(),
        output_root=tmp_path,
        retry_delays=(0,),
        sleep=lambda _: None,
    )
    profile = load_profiles()["SP-001"]

    with pytest.raises(RuntimeError):
        runner.run_condition(profile=profile, condition="B", fake_talker_responses=["x"] * 6)

    run_dir = tmp_path / "WS4-FAKE-SP-001-B"
    checkpoint = json.loads((run_dir / "ws4_runner_checkpoint.json").read_text(encoding="utf-8"))
    result = json.loads((run_dir / "roleplay_result.json").read_text(encoding="utf-8"))
    assert checkpoint["termination_reason"] == result["termination_reason"] == "ERROR"
    assert checkpoint["error_metadata"]["stage"] == "patient_agent"
    assert len(checkpoint["error_metadata"]["attempts"]) == 2


def test_ws1_config_is_injected_without_ws4_model_override(tmp_path, monkeypatch):
    def frozen_ws1_config(condition):
        base = AblationConfig.for_condition(condition)
        return base.__class__(
            **{
                **base.to_dict(),
                "model": "technical-lead-frozen-model",
                "temperature": 0.25,
                "seed": 123,
            }
        )

    runner = RoleplayRunner(
        patient_agent=DeterministicPatientAgent(),
        output_root=tmp_path,
        config_factory=frozen_ws1_config,
    )
    terminal = _harness_turn("message", 0)
    terminal["termination_reason"] = "COMMON_INPUT_BLOCK"
    monkeypatch.setattr(runner, "_call_harness", lambda **_kwargs: [terminal])
    result = runner.run_condition(
        profile=load_profiles()["SP-001"],
        condition="C",
        fake_talker_responses=["x"] * 6,
    )

    assert result["config"]["model"] == "technical-lead-frozen-model"
    assert result["config"]["temperature"] == 0.25
    assert result["config"]["seed"] == 123


def test_ws4_runner_does_not_own_judge_configuration():
    source = (
        PROJECT_ROOT
        / "llm_ablation_paper/workstream_4_patient_simulation/scripts/run_patient_simulation.py"
    ).read_text(encoding="utf-8")
    assert "JUDGE_MODEL" not in source
    assert "JUDGE_TEMPERATURE" not in source


def test_harness_error_is_retained_as_terminal_reason(tmp_path, monkeypatch):
    runner = RoleplayRunner(patient_agent=DeterministicPatientAgent(), output_root=tmp_path)
    error_turn = _harness_turn("我想問飲食", 0)
    error_turn["termination_reason"] = "ERROR"
    monkeypatch.setattr(runner, "_call_harness", lambda **_kwargs: [error_turn])

    result = runner.run_condition(profile=load_profiles()["SP-001"], condition="B", fake_talker_responses=["x"] * 6)
    assert result["termination_reason"] == "ERROR"
    assert len(result["records"]) == 1
