"""WS1 final-freeze readiness tests: frozen formal config, talker/planner
temperature wiring, synchronous planner-state persistence, pilot entrypoint
fail-closed behavior, and manifest/config fingerprint equality."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation as run_simulation
from llm_ablation_paper.workstream_1_technical_lead.harness.config import (
    AblationConfig,
    FORMAL_MAX_TURNS,
    FORMAL_PATIENT_AGENT_MODEL,
    FORMAL_PATIENT_AGENT_TEMPERATURE,
    FORMAL_PLANNER_REQUEST_TIMEOUT_SECONDS,
    FORMAL_PLANNER_TEMPERATURE,
    FORMAL_SEED,
    FORMAL_SUBPROCESS_TIMEOUT_SECONDS,
    FORMAL_TALKER_MODEL,
    FORMAL_TALKER_TEMPERATURE,
    config_diff,
    formal_ablation_config,
    formal_runtime_spec,
    is_frozen_formal_config,
    require_frozen_formal_config,
)
from llm_ablation_paper.workstream_1_technical_lead.harness.fingerprints import (
    canonical_tool_schema_sha256,
    formal_runtime_config_canonical_sha256,
    planner_system_prompt_sha256,
    talker_base_prompt_sha256,
    talker_prompt_template_bundle_sha256,
)
from diabetes_chatbot.memory import load_patient_record
from diabetes_chatbot.planner import PLANNER_SYSTEM_PROMPT
from diabetes_chatbot.server import ablation_core


def _message(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _response(message):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class _Completions:
    def __init__(self, script):
        self.script = script
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.script(kwargs, len(self.calls))


class RecordingClient:
    def __init__(self, script):
        self.completions = _Completions(script)
        self.chat = SimpleNamespace(completions=self.completions)


def _is_planner_call(kwargs):
    messages = kwargs.get("messages") or []
    return bool(messages) and messages[0].get("content") == PLANNER_SYSTEM_PROMPT


def _planner_json(**slots):
    payload = {
        "detected_intent": "GENERAL_HEALTH",
        "retrieval_domain": "NONE",
        "is_visit_mode": False,
        "is_explicit_request": False,
        "is_agenda_confirmed": False,
        "can_unlock_summary_tool": False,
        "highest_priority_gap": None,
        "talker_guidance": "",
        "ddx_candidates": [],
        "evidence_links": [],
    }
    for key in (
        "visit_reason",
        "medications",
        "glucose_metrics",
        "hypo_history",
        "concerns_or_side_effects",
        "diet_lifestyle",
    ):
        payload[key] = {"content": "", "status": "MISSING"}
    payload.update(slots)
    return json.dumps(payload, ensure_ascii=False)


def test_formal_conditions_only_three_switches_change():
    a, b, c, d = (formal_ablation_config(cond) for cond in ("A", "B", "C", "D"))
    diff_ab = config_diff(a, b)
    diff_bc = config_diff(b, c)
    diff_cd = config_diff(c, d)
    assert set(diff_ab) == {"condition", "enable_planner"}
    assert diff_ab["enable_planner"] == {"from": False, "to": True}
    assert set(diff_bc) == {"condition", "enable_dynamic_tool_gate"}
    assert diff_bc["enable_dynamic_tool_gate"] == {"from": False, "to": True}
    assert set(diff_cd) == {"condition", "enable_output_guard"}
    assert diff_cd["enable_output_guard"] == {"from": False, "to": True}
    for cfg in (a, b, c, d):
        assert cfg.enable_forced_retrieval is False
        assert cfg.enable_fixed_warning_append is False
        assert cfg.enable_question_budget_postprocessing is False


def test_formal_config_values_match_protocol():
    cfg = formal_ablation_config("B")
    assert cfg.model == FORMAL_TALKER_MODEL == "gemini-3.5-flash-lite"
    assert cfg.temperature == FORMAL_TALKER_TEMPERATURE == 0.3
    assert cfg.planner_model == "gemini-3.5-flash-lite"
    assert cfg.planner_temperature == FORMAL_PLANNER_TEMPERATURE == 0.1
    assert cfg.planner_request_timeout_seconds == FORMAL_PLANNER_REQUEST_TIMEOUT_SECONDS == 30.0
    assert cfg.patient_agent_model == FORMAL_PATIENT_AGENT_MODEL == "gemini-3.5-flash-lite"
    assert cfg.patient_agent_temperature == FORMAL_PATIENT_AGENT_TEMPERATURE == 0.3
    assert cfg.max_turns == FORMAL_MAX_TURNS == 6
    assert cfg.seed == FORMAL_SEED == 42
    assert FORMAL_SUBPROCESS_TIMEOUT_SECONDS == 120.0
    spec = formal_runtime_spec()
    assert spec["input_guard"] == "ON"
    assert spec["subprocess_timeout_seconds"] == 120.0
    assert spec["planner_request_timeout_seconds"] == 30.0


def test_fake_factory_is_not_formal_and_cannot_be_required():
    fake = AblationConfig.for_condition("A")
    formal = formal_ablation_config("A")
    assert fake.model == "fake-model"
    assert formal.model == "gemini-3.5-flash-lite"
    assert is_frozen_formal_config(fake) is False
    assert is_frozen_formal_config(formal) is True
    with pytest.raises(ValueError):
        require_frozen_formal_config(fake)


def test_talker_temperature_is_formal_value_in_first_and_second_call(tmp_path, monkeypatch):
    cfg = formal_ablation_config("A")
    tool_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="search_handbook", arguments=json.dumps({"keyword": "糖尿病"})),
    )

    def script(kwargs, n):
        if n == 1:
            return _response(_message(content=None, tool_calls=[tool_call]))
        return _response(_message(content="第二次回覆：依據手冊建議。", tool_calls=None))

    client = RecordingClient(script)
    monkeypatch.setattr(ablation_core, "search_handbook", lambda *a, **k: "官方手冊重點")
    result = ablation_core.execute_ablation_turn(
        user_text="糖尿病定義是什麼？",
        patient_file=tmp_path / "p.json",
        messages=[],
        ablation_config=cfg,
        talker_client=client,
        model=cfg.model,
        temperature=cfg.temperature,
    )
    temperatures = [call.get("temperature") for call in client.completions.calls]
    assert temperatures == [0.3, 0.3]
    assert result["final_output"]


def test_planner_uses_formal_temperature_and_timeout_and_A_skips_planner(tmp_path):
    planner_json = _planner_json()

    def script(kwargs, n):
        if _is_planner_call(kwargs):
            return _response(_message(content=planner_json))
        return _response(_message(content="收到，我們一起來看。"))

    cfg_b = formal_ablation_config("B")
    client_b = RecordingClient(script)
    ablation_core.execute_ablation_turn(
        user_text="我吃庫魯化肚子脹",
        patient_file=tmp_path / "b.json",
        messages=[],
        ablation_config=cfg_b,
        talker_client=client_b,
        model=cfg_b.model,
        temperature=cfg_b.temperature,
    )
    planner_calls = [c for c in client_b.completions.calls if _is_planner_call(c)]
    assert len(planner_calls) == 1
    assert planner_calls[0]["temperature"] == 0.1
    assert planner_calls[0]["timeout"] == 30.0

    cfg_a = formal_ablation_config("A")
    client_a = RecordingClient(script)
    ablation_core.execute_ablation_turn(
        user_text="你好",
        patient_file=tmp_path / "a.json",
        messages=[],
        ablation_config=cfg_a,
        talker_client=client_a,
        model=cfg_a.model,
        temperature=cfg_a.temperature,
    )
    assert not any(_is_planner_call(c) for c in client_a.completions.calls)


def test_sync_persist_visible_next_turn(tmp_path):
    planner_json = _planner_json(
        medications={"content": "庫魯化", "status": "KNOWN"},
        concerns_or_side_effects={"content": "腹脹", "status": "KNOWN"},
    )

    def script(kwargs, n):
        if _is_planner_call(kwargs):
            return _response(_message(content=planner_json))
        return _response(_message(content="收到，我們一起來看。"))

    cfg = formal_ablation_config("B")
    patient_file = tmp_path / "p.json"
    first = RecordingClient(script)
    ablation_core.execute_ablation_turn(
        user_text="我吃庫魯化會腹脹",
        patient_file=patient_file,
        messages=[],
        ablation_config=cfg,
        talker_client=first,
        model=cfg.model,
        temperature=cfg.temperature,
    )
    persisted = json.dumps(load_patient_record(patient_file), ensure_ascii=False)
    assert "庫魯化" in persisted
    assert "腹脹" in persisted

    second = RecordingClient(script)
    ablation_core.execute_ablation_turn(
        user_text="那我要注意什麼？",
        patient_file=patient_file,
        messages=[],
        ablation_config=cfg,
        talker_client=second,
        model=cfg.model,
        temperature=cfg.temperature,
    )
    planner_prompts = [c["messages"][1]["content"] for c in second.completions.calls if _is_planner_call(c)]
    assert planner_prompts
    assert "庫魯化" in planner_prompts[0]


def test_no_daemon_persist_thread_and_single_planner_call_site():
    source = (PROJECT_ROOT / "diabetes_chatbot" / "server" / "ablation_core.py").read_text(encoding="utf-8")
    assert "threading" not in source
    assert "daemon=True" not in source
    assert source.count("evaluate_clinical_planner_llm(") == 1
    assert "update_from_planner_assessment(" in source


def test_formal_pilot_fails_closed_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr(
        run_simulation.GeminiPatientAgent,
        "from_environment",
        classmethod(lambda cls, **kwargs: None),
    )
    called = {"count": 0}

    def spy(self, **kwargs):
        called["count"] += 1
        raise AssertionError("formal pilot must not reach subprocess without a key")

    monkeypatch.setattr(run_simulation.RoleplayRunner, "run_condition", spy)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        run_simulation.run_formal_pilot("SP-001", output_root=tmp_path)
    assert called["count"] == 0


def test_formal_pilot_wires_frozen_config_and_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "sk-test-not-used")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr(
        run_simulation.GeminiPatientAgent,
        "from_environment",
        classmethod(lambda cls, **kwargs: SimpleNamespace(implementation="stub")),
    )
    captured = {}

    def fake_run_condition(self, **kwargs):
        captured["config_factory"] = self.config_factory
        captured["timeout"] = self.subprocess_timeout_seconds
        captured["provider_config"] = self.provider_config
        return {
            "run_id": f"STUB-{kwargs['condition']}",
            "condition": kwargs["condition"],
            "user_id": "u",
            "records": [{}] * 6,
            "termination_reason": "MAX_TURNS",
        }

    monkeypatch.setattr(run_simulation.RoleplayRunner, "run_condition", fake_run_condition)
    summary = run_simulation.run_formal_pilot("SP-001", output_root=tmp_path)
    cfg = captured["config_factory"]("B")
    assert cfg.model == FORMAL_TALKER_MODEL
    assert cfg.temperature == FORMAL_TALKER_TEMPERATURE
    assert cfg.planner_request_timeout_seconds == FORMAL_PLANNER_REQUEST_TIMEOUT_SECONDS
    assert captured["timeout"] == FORMAL_SUBPROCESS_TIMEOUT_SECONDS
    assert captured["provider_config"] == {"provider": "gemini"}
    assert summary["twelve_by_four_started"] is False
    assert summary["formal_experiment_started"] is False
    assert len(summary["runs"]) == 4


def test_cli_requires_explicit_formal_pilot_and_patient_id(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_patient_simulation.py"])
    with pytest.raises(SystemExit):
        run_simulation.main()
    monkeypatch.setattr(sys, "argv", ["run_patient_simulation.py", "--formal-pilot"])
    with pytest.raises(SystemExit):
        run_simulation.main()


def test_condition_state_dirs_stay_isolated(tmp_path, monkeypatch):
    from llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation import (
        DeterministicPatientAgent,
        FAKE_TALKER_RESPONSES,
        load_profiles,
    )

    runner = run_simulation.RoleplayRunner(patient_agent=DeterministicPatientAgent(), output_root=tmp_path)

    def fake_harness(**kwargs):
        return [{"assistant_response": "ok", "termination_reason": None, "turn_index": 0, "user_message": kwargs["messages"][-1]}]

    monkeypatch.setattr(runner, "_call_harness", fake_harness)
    profile = load_profiles()["SP-001"]
    first = runner.run_condition(profile=profile, condition="A", fake_talker_responses=list(FAKE_TALKER_RESPONSES))
    second = runner.run_condition(profile=profile, condition="B", fake_talker_responses=list(FAKE_TALKER_RESPONSES))
    assert first["user_id"] != second["user_id"]
    assert (tmp_path / first["run_id"]) != (tmp_path / second["run_id"])


def test_manifest_formal_config_and_fingerprints_exact_match():
    manifest = json.loads(
        (
            PROJECT_ROOT
            / "llm_ablation_paper"
            / "workstream_1_technical_lead"
            / "FREEZE_CANDIDATE_MANIFEST.json"
        ).read_text(encoding="utf-8")
    )
    fingerprints = manifest["fingerprints_sha256"]
    assert fingerprints["talker_base_prompt_sha256"] == talker_base_prompt_sha256()
    assert fingerprints["talker_prompt_template_bundle_sha256"] == talker_prompt_template_bundle_sha256()
    assert fingerprints["planner_system_prompt_sha256"] == planner_system_prompt_sha256()
    assert fingerprints["canonical_tool_schema_sha256"] == canonical_tool_schema_sha256()
    assert manifest["formal_runtime_config_canonical_sha256"] == formal_runtime_config_canonical_sha256()
    formal = manifest["formal_runtime_config"]
    assert formal["talker_model"] == FORMAL_TALKER_MODEL
    assert formal["talker_temperature"] == FORMAL_TALKER_TEMPERATURE
    assert formal["planner_model"] == FORMAL_TALKER_MODEL
    assert formal["planner_temperature"] == FORMAL_PLANNER_TEMPERATURE
    assert formal["planner_request_timeout_seconds"] == FORMAL_PLANNER_REQUEST_TIMEOUT_SECONDS
    assert formal["patient_agent_model"] == FORMAL_PATIENT_AGENT_MODEL
    assert formal["patient_agent_temperature"] == FORMAL_PATIENT_AGENT_TEMPERATURE
    assert formal["max_turns"] == FORMAL_MAX_TURNS
    assert formal["seed"] == FORMAL_SEED
    assert manifest["status"] == "FROZEN"
    assert manifest["final_frozen"] is True
    assert manifest["final_freeze_tag"] == "llm-ablation-ws1-freeze-v1.1"
    assert manifest["supersedes_tag"] == "llm-ablation-ws1-freeze-v1"
    assert manifest["runtime_code_commit"] == "a61c32a93c24a3e698ee266246da30103da5d38a"
    assert manifest["timeout_status"] == "FINAL_FROZEN"
    assert manifest["experiment_ready"] is False
    assert manifest["formal_experiment_state"] == "BLOCKED"


def test_all_formal_conditions_pass_exact_gate():
    for cond in ("A", "B", "C", "D"):
        cfg = formal_ablation_config(cond)
        assert is_frozen_formal_config(cfg) is True
        require_frozen_formal_config(cfg)


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    [
        ("model", "some-real-model"),
        ("temperature", 0.7),
        ("planner_model", "some-real-model"),
        ("planner_temperature", 0.2),
        ("planner_temperature", 0.7),
        ("planner_request_timeout_seconds", 3.0),
        ("patient_agent_model", "some-real-model"),
        ("patient_agent_temperature", 0.7),
        ("max_turns", 5),
        ("seed", 7),
        ("enable_forced_retrieval", True),
        ("enable_fixed_warning_append", True),
        ("enable_question_budget_postprocessing", True),
        ("enable_planner", False),
        ("enable_dynamic_tool_gate", True),
        ("enable_output_guard", True),
    ],
)
def test_exact_gate_rejects_single_field_mutation(field, tampered_value):
    cfg = formal_ablation_config("B")
    object.__setattr__(cfg, field, tampered_value)
    assert is_frozen_formal_config(cfg) is False
    with pytest.raises(ValueError, match=field):
        require_frozen_formal_config(cfg)


def test_exact_gate_rejects_bad_condition_and_cross_condition_flags():
    cfg = formal_ablation_config("B")
    object.__setattr__(cfg, "condition", "X")
    assert is_frozen_formal_config(cfg) is False
    with pytest.raises(ValueError, match="condition"):
        require_frozen_formal_config(cfg)
    cfg_c = formal_ablation_config("C")
    object.__setattr__(cfg_c, "enable_dynamic_tool_gate", False)
    assert is_frozen_formal_config(cfg_c) is False
    with pytest.raises(ValueError, match="enable_dynamic_tool_gate"):
        require_frozen_formal_config(cfg_c)


def test_gate_error_message_does_not_leak_env_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "CANARY-SECRET-123")
    cfg = formal_ablation_config("B")
    object.__setattr__(cfg, "seed", 7)
    with pytest.raises(ValueError) as excinfo:
        require_frozen_formal_config(cfg)
    message = str(excinfo.value)
    assert "CANARY-SECRET-123" not in message
    assert "api_key" not in message.lower()
    assert "seed" in message


def test_run_condition_gate_fails_before_provider_and_subprocess(tmp_path, monkeypatch):
    from llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation import (
        DeterministicPatientAgent,
        load_profiles,
    )

    def tampered_factory(condition):
        cfg = formal_ablation_config(condition)
        object.__setattr__(cfg, "planner_temperature", 0.9)
        return cfg

    provider_calls = {"count": 0}
    harness_calls = {"count": 0}
    patient_calls = {"count": 0}

    def fake_ensure_provider_ready(provider_config):
        provider_calls["count"] += 1
        return ("gemini", "stub")

    monkeypatch.setattr(
        "llm_ablation_paper.workstream_1_technical_lead.harness.ensure_provider_ready",
        fake_ensure_provider_ready,
    )

    agent = DeterministicPatientAgent()
    original_next_turn = agent.next_turn

    def counting_next_turn(**kwargs):
        patient_calls["count"] += 1
        return original_next_turn(**kwargs)

    monkeypatch.setattr(agent, "next_turn", counting_next_turn)

    runner = run_simulation.RoleplayRunner(
        patient_agent=agent,
        output_root=tmp_path,
        config_factory=tampered_factory,
        provider_config={"provider": "gemini"},
        subprocess_timeout_seconds=120.0,
    )

    def counting_harness(**kwargs):
        harness_calls["count"] += 1
        raise AssertionError("harness must not run when the gate rejects")

    monkeypatch.setattr(runner, "_call_harness", counting_harness)

    profile = load_profiles()["SP-001"]
    with pytest.raises(ValueError):
        runner.run_condition(profile=profile, condition="B", run_suffix="PILOT")
    assert provider_calls["count"] == 0
    assert harness_calls["count"] == 0
    assert patient_calls["count"] == 0


def test_run_condition_gate_passes_with_valid_formal_config(tmp_path, monkeypatch):
    from llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation import (
        DeterministicPatientAgent,
        load_profiles,
    )

    provider_calls = {"count": 0}
    harness_calls = {"count": 0}
    patient_calls = {"count": 0}

    def fake_ensure_provider_ready(provider_config):
        provider_calls["count"] += 1
        return ("gemini", "stub")

    monkeypatch.setattr(
        "llm_ablation_paper.workstream_1_technical_lead.harness.ensure_provider_ready",
        fake_ensure_provider_ready,
    )

    class ImmediateEndPatientAgent(DeterministicPatientAgent):
        # 最小 stub：在第一回合即結束，使 run_condition 通過門禁後退出，不觸碰 harness subprocess
        model = FORMAL_PATIENT_AGENT_MODEL
        temperature = FORMAL_PATIENT_AGENT_TEMPERATURE

        def next_turn(self, *, profile, assistant_output, turn_number, prior_turns):
            patient_calls["count"] += 1
            return {
                "patient_utterance": "謝謝，我沒有其他問題了。",
                "should_end": True,
                "termination_reason": "PATIENT_GOAL_MET",
                "disclosed_facts": [],
                "evidence": "Positive control: end immediately after the gate passes.",
            }

    runner = run_simulation.RoleplayRunner(
        patient_agent=ImmediateEndPatientAgent(),
        output_root=tmp_path,
        config_factory=lambda condition: formal_ablation_config(condition),
        provider_config={"provider": "gemini"},
        subprocess_timeout_seconds=120.0,
    )

    def counting_harness(**kwargs):
        harness_calls["count"] += 1
        raise AssertionError("positive control ends before any harness turn")

    monkeypatch.setattr(runner, "_call_harness", counting_harness)

    profile = load_profiles()["SP-001"]
    result = runner.run_condition(profile=profile, condition="B", run_suffix="PILOT")
    assert result["termination_reason"] == "PATIENT_GOAL_MET"
    assert provider_calls["count"] == 1
    assert patient_calls["count"] >= 1
    assert harness_calls["count"] == 0


def test_run_condition_envelope_gate_rejects_bad_subprocess_timeout(tmp_path, monkeypatch):
    from llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation import (
        DeterministicPatientAgent,
        load_profiles,
    )

    provider_calls = {"count": 0}
    harness_calls = {"count": 0}
    patient_calls = {"count": 0}

    def fake_ensure_provider_ready(provider_config):
        provider_calls["count"] += 1
        return ("gemini", "stub")

    monkeypatch.setattr(
        "llm_ablation_paper.workstream_1_technical_lead.harness.ensure_provider_ready",
        fake_ensure_provider_ready,
    )

    class ValidPatientAgent(DeterministicPatientAgent):
        model = FORMAL_PATIENT_AGENT_MODEL
        temperature = FORMAL_PATIENT_AGENT_TEMPERATURE

        def next_turn(self, **kwargs):
            patient_calls["count"] += 1
            return super().next_turn(**kwargs)

    runner = run_simulation.RoleplayRunner(
        patient_agent=ValidPatientAgent(),
        output_root=tmp_path,
        config_factory=lambda condition: formal_ablation_config(condition),
        provider_config={"provider": "gemini"},
        subprocess_timeout_seconds=77.0,  # 錯誤 timeout
    )

    def counting_harness(**kwargs):
        harness_calls["count"] += 1
        raise AssertionError("harness must not run when the envelope gate rejects")

    monkeypatch.setattr(runner, "_call_harness", counting_harness)

    profile = load_profiles()["SP-001"]
    with pytest.raises(ValueError, match="subprocess_timeout_seconds"):
        runner.run_condition(profile=profile, condition="B", run_suffix="PILOT")
    assert provider_calls["count"] == 0
    assert harness_calls["count"] == 0
    assert patient_calls["count"] == 0


def test_run_condition_envelope_gate_rejects_bad_patient_agent_model(tmp_path, monkeypatch):
    from llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation import (
        DeterministicPatientAgent,
        load_profiles,
    )

    provider_calls = {"count": 0}
    harness_calls = {"count": 0}
    patient_calls = {"count": 0}

    def fake_ensure_provider_ready(provider_config):
        provider_calls["count"] += 1
        return ("gemini", "stub")

    monkeypatch.setattr(
        "llm_ablation_paper.workstream_1_technical_lead.harness.ensure_provider_ready",
        fake_ensure_provider_ready,
    )

    class WrongModelPatientAgent(DeterministicPatientAgent):
        model = "wrong-patient-model"
        temperature = FORMAL_PATIENT_AGENT_TEMPERATURE

        def next_turn(self, **kwargs):
            patient_calls["count"] += 1
            return super().next_turn(**kwargs)

    runner = run_simulation.RoleplayRunner(
        patient_agent=WrongModelPatientAgent(),
        output_root=tmp_path,
        config_factory=lambda condition: formal_ablation_config(condition),
        provider_config={"provider": "gemini"},
        subprocess_timeout_seconds=120.0,
    )

    def counting_harness(**kwargs):
        harness_calls["count"] += 1
        raise AssertionError("harness must not run when the envelope gate rejects")

    monkeypatch.setattr(runner, "_call_harness", counting_harness)

    profile = load_profiles()["SP-001"]
    with pytest.raises(ValueError, match=r"patient_agent\.model"):
        runner.run_condition(profile=profile, condition="B", run_suffix="PILOT")
    assert provider_calls["count"] == 0
    assert harness_calls["count"] == 0
    assert patient_calls["count"] == 0


def test_run_condition_envelope_gate_rejects_bad_patient_agent_temperature(tmp_path, monkeypatch):
    from llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation import (
        DeterministicPatientAgent,
        load_profiles,
    )

    provider_calls = {"count": 0}
    harness_calls = {"count": 0}
    patient_calls = {"count": 0}

    def fake_ensure_provider_ready(provider_config):
        provider_calls["count"] += 1
        return ("gemini", "stub")

    monkeypatch.setattr(
        "llm_ablation_paper.workstream_1_technical_lead.harness.ensure_provider_ready",
        fake_ensure_provider_ready,
    )

    class WrongTempPatientAgent(DeterministicPatientAgent):
        model = FORMAL_PATIENT_AGENT_MODEL
        temperature = 0.99

        def next_turn(self, **kwargs):
            patient_calls["count"] += 1
            return super().next_turn(**kwargs)

    runner = run_simulation.RoleplayRunner(
        patient_agent=WrongTempPatientAgent(),
        output_root=tmp_path,
        config_factory=lambda condition: formal_ablation_config(condition),
        provider_config={"provider": "gemini"},
        subprocess_timeout_seconds=120.0,
    )

    def counting_harness(**kwargs):
        harness_calls["count"] += 1
        raise AssertionError("harness must not run when the envelope gate rejects")

    monkeypatch.setattr(runner, "_call_harness", counting_harness)

    profile = load_profiles()["SP-001"]
    with pytest.raises(ValueError, match=r"patient_agent\.temperature"):
        runner.run_condition(profile=profile, condition="B", run_suffix="PILOT")
    assert provider_calls["count"] == 0
    assert harness_calls["count"] == 0
    assert patient_calls["count"] == 0


@pytest.mark.parametrize(
    "agent_factory,expected_match",
    [
        (lambda: SimpleNamespace(temperature=FORMAL_PATIENT_AGENT_TEMPERATURE), r"patient_agent\.model"),
        (lambda: SimpleNamespace(model=FORMAL_PATIENT_AGENT_MODEL), r"patient_agent\.temperature"),
        (lambda: SimpleNamespace(), r"patient_agent\.model"),
    ],
)
def test_run_condition_envelope_gate_rejects_missing_patient_agent_attributes(
    tmp_path, monkeypatch, agent_factory, expected_match
):
    from llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation import load_profiles

    provider_calls = {"count": 0}
    harness_calls = {"count": 0}

    def fake_ensure_provider_ready(provider_config):
        provider_calls["count"] += 1
        return ("gemini", "stub")

    monkeypatch.setattr(
        "llm_ablation_paper.workstream_1_technical_lead.harness.ensure_provider_ready",
        fake_ensure_provider_ready,
    )

    runner = run_simulation.RoleplayRunner(
        patient_agent=agent_factory(),
        output_root=tmp_path,
        config_factory=lambda condition: formal_ablation_config(condition),
        provider_config={"provider": "gemini"},
        subprocess_timeout_seconds=120.0,
    )

    def counting_harness(**kwargs):
        harness_calls["count"] += 1
        raise AssertionError("harness must not run when attributes are missing")

    monkeypatch.setattr(runner, "_call_harness", counting_harness)

    profile = load_profiles()["SP-001"]
    with pytest.raises(ValueError, match=expected_match):
        runner.run_condition(profile=profile, condition="B", run_suffix="PILOT")
    assert provider_calls["count"] == 0
    assert harness_calls["count"] == 0


def test_envelope_gate_error_message_does_not_leak_values_or_canary_key(tmp_path, monkeypatch):
    from llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation import load_profiles

    canary_key = "CANARY-SECRET-ENVELOPE-KEY-99999"
    bad_model = "CANARY-BAD-MODEL-VALUE"
    monkeypatch.setenv("GEMINI_API_KEY", canary_key)

    class CanaryTamperedPatientAgent:
        model = bad_model
        temperature = 0.8888

    runner = run_simulation.RoleplayRunner(
        patient_agent=CanaryTamperedPatientAgent(),
        output_root=tmp_path,
        config_factory=lambda condition: formal_ablation_config(condition),
        provider_config={"provider": "gemini"},
        subprocess_timeout_seconds=77.7,
    )

    profile = load_profiles()["SP-001"]
    with pytest.raises(ValueError) as excinfo:
        runner.run_condition(profile=profile, condition="B", run_suffix="PILOT")

    msg = str(excinfo.value)
    assert "subprocess_timeout_seconds" in msg
    assert "patient_agent.model" in msg
    assert "patient_agent.temperature" in msg
    assert "77.7" not in msg
    assert bad_model not in msg
    assert "0.8888" not in msg
    assert canary_key not in msg
    assert "gemini_api_key" not in msg.lower()


def test_adversarial_reproduction_unfrozen_runner_envelope_rejected(tmp_path, monkeypatch):
    """對抗測試：重現原審查所發現之三個漏網值同時存在的情境，證明現已 fail-closed 拒絕。"""
    from llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation import (
        DeterministicPatientAgent,
        load_profiles,
    )

    provider_calls = {"count": 0}
    harness_calls = {"count": 0}
    patient_calls = {"count": 0}

    def fake_ensure_provider_ready(provider_config):
        provider_calls["count"] += 1
        return ("gemini", "stub")

    monkeypatch.setattr(
        "llm_ablation_paper.workstream_1_technical_lead.harness.ensure_provider_ready",
        fake_ensure_provider_ready,
    )

    class AdversarialPatientAgent(DeterministicPatientAgent):
        model = "wrong-patient-model"
        temperature = 0.99

        def next_turn(self, *, profile, assistant_output, turn_number, prior_turns):
            patient_calls["count"] += 1
            return {
                "patient_utterance": "這是不應該執行的回合。",
                "should_end": True,
                "termination_reason": "PATIENT_GOAL_MET",
                "disclosed_facts": [],
                "evidence": "Adversarial stub that previously sneaked through.",
            }

    runner = run_simulation.RoleplayRunner(
        patient_agent=AdversarialPatientAgent(),
        output_root=tmp_path,
        config_factory=lambda condition: formal_ablation_config(condition),
        provider_config={"provider": "gemini"},
        subprocess_timeout_seconds=77.0,
    )

    def counting_harness(**kwargs):
        harness_calls["count"] += 1
        raise AssertionError("subprocess must not spawn in adversarial condition")

    monkeypatch.setattr(runner, "_call_harness", counting_harness)

    profile = load_profiles()["SP-001"]
    with pytest.raises(ValueError) as excinfo:
        runner.run_condition(profile=profile, condition="B", run_suffix="PILOT")

    msg = str(excinfo.value)
    assert "subprocess_timeout_seconds" in msg
    assert "patient_agent.model" in msg
    assert "patient_agent.temperature" in msg
    assert provider_calls["count"] == 0
    assert patient_calls["count"] == 0
    assert harness_calls["count"] == 0


def test_fake_dry_run_accepts_custom_timeout_and_deterministic_patient(tmp_path, monkeypatch):
    from llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation import (
        DeterministicPatientAgent,
        FAKE_TALKER_RESPONSES,
        load_profiles,
    )

    runner = run_simulation.RoleplayRunner(
        patient_agent=DeterministicPatientAgent(),
        output_root=tmp_path,
        subprocess_timeout_seconds=77.0,  # fake dry-run 允許自訂 timeout
    )

    assert runner.subprocess_timeout_seconds == 77.0

    def fake_harness(**kwargs):
        return [{
            "assistant_response": "ok",
            "termination_reason": None,
            "turn_index": 0,
            "user_message": kwargs["messages"][-1],
        }]

    monkeypatch.setattr(runner, "_call_harness", fake_harness)
    profile = load_profiles()["SP-001"]
    result = runner.run_condition(
        profile=profile,
        condition="A",
        fake_talker_responses=list(FAKE_TALKER_RESPONSES),
        run_suffix="FAKE",
    )
    assert result["termination_reason"] == "MAX_TURNS"
    assert len(result["records"]) == 6


def test_fake_dry_run_path_skips_gate(tmp_path, monkeypatch):
    from llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation import (
        DeterministicPatientAgent,
        FAKE_TALKER_RESPONSES,
        load_profiles,
    )

    def forbidden_gate(config):
        raise AssertionError("FAKE path must not consult the formal gate")

    monkeypatch.setattr(run_simulation, "require_frozen_formal_config", forbidden_gate)

    runner = run_simulation.RoleplayRunner(patient_agent=DeterministicPatientAgent(), output_root=tmp_path)

    def fake_harness(**kwargs):
        return [{"assistant_response": "ok", "termination_reason": None, "turn_index": 0, "user_message": kwargs["messages"][-1]}]

    monkeypatch.setattr(runner, "_call_harness", fake_harness)
    profile = load_profiles()["SP-001"]
    result = runner.run_condition(profile=profile, condition="A", fake_talker_responses=list(FAKE_TALKER_RESPONSES))
    assert result["termination_reason"] == "MAX_TURNS"
    assert len(result["records"]) == 6


def test_patient_model_migration_refreeze_regression():
    """PHASE M3.1: 驗證 Patient Agent 模型遷移至 gemini-3.5-flash-lite 後之重新凍結不變量。

    斷言 runtime config 與 manifest 皆為 gemini-3.5-flash-lite，且相對舊值只有 patient_agent_model 改變：
    A–D flags、talker/planner model、temperature、max_turns、seed、以及四個 prompt/tool 指紋均不變。
    """
    manifest_path = PROJECT_ROOT / "llm_ablation_paper" / "workstream_1_technical_lead" / "FREEZE_CANDIDATE_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    runtime_cfg = manifest["formal_runtime_config"]

    # 1. Runtime config 與 Manifest 之 patient_agent_model 皆為 gemini-3.5-flash-lite
    assert FORMAL_PATIENT_AGENT_MODEL == "gemini-3.5-flash-lite"
    assert runtime_cfg["patient_agent_model"] == "gemini-3.5-flash-lite"
    for cond in ("A", "B", "C", "D"):
        cfg = formal_ablation_config(cond)
        assert cfg.patient_agent_model == "gemini-3.5-flash-lite"

    # 2. 舊 baseline 與新 runtime spec 比對：唯獨 patient_agent_model 改變
    old_runtime_spec = {
        "talker_model": "gemini-3.5-flash-lite",
        "talker_temperature": 0.3,
        "planner_model": "gemini-3.5-flash-lite",
        "planner_temperature": 0.1,
        "planner_request_timeout_seconds": 30.0,
        "patient_agent_model": "gemini-2.5-flash-lite",
        "patient_agent_temperature": 0.3,
        "max_turns": 6,
        "seed": 42,
        "subprocess_timeout_seconds": 120.0,
        "input_guard": "ON",
        "enable_forced_retrieval": False,
        "enable_fixed_warning_append": False,
        "enable_question_budget_postprocessing": False,
        "conditions": {
            "A": {"enable_planner": False, "enable_dynamic_tool_gate": False, "enable_output_guard": False},
            "B": {"enable_planner": True, "enable_dynamic_tool_gate": False, "enable_output_guard": False},
            "C": {"enable_planner": True, "enable_dynamic_tool_gate": True, "enable_output_guard": False},
            "D": {"enable_planner": True, "enable_dynamic_tool_gate": True, "enable_output_guard": True},
        },
    }
    current_spec = formal_runtime_spec()
    diff_keys = [k for k in old_runtime_spec if old_runtime_spec[k] != current_spec[k]]
    assert diff_keys == ["patient_agent_model"], f"Expected ONLY patient_agent_model to change, got: {diff_keys}"
    assert old_runtime_spec["patient_agent_model"] == "gemini-2.5-flash-lite"
    assert current_spec["patient_agent_model"] == "gemini-3.5-flash-lite"

    # 3. 驗證四個 prompt 與 tool schema 指紋完全維持不變
    fps = manifest["fingerprints_sha256"]
    assert fps["talker_base_prompt_sha256"] == talker_base_prompt_sha256() == "2c2a3850a8885a2598403971f2faec6d4dcbea414a120c4711dff9540073ce55"
    assert fps["talker_prompt_template_bundle_sha256"] == talker_prompt_template_bundle_sha256() == "9a6b133ac53437e8a567d3c336fe43a99c57faeb82152c21ada6fe4799723f2b"
    assert fps["planner_system_prompt_sha256"] == planner_system_prompt_sha256() == "53d6b0f2ebb864116f0d914295b549a9d6d1236825f01cc9925e2185c842a409"
    assert fps["canonical_tool_schema_sha256"] == canonical_tool_schema_sha256() == "e548a8c6a5d02577c971c0f77499adf8902cd0c4db1aa5263654f74d66ed776e"

    # 4. 驗證 formal_runtime_config_canonical_sha256 吻合重算值
    assert manifest["formal_runtime_config_canonical_sha256"] == formal_runtime_config_canonical_sha256() == "1fc99f380f2df276751e75b061cd7b08a2fb9be49b0cc37854447f3059e63997"

