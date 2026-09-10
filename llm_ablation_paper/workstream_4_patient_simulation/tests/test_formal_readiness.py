"""test_formal_readiness — R8 formal hardening tests (real, no paid API)."""
import importlib.util
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
    _is_transient_error,
    load_profiles,
    run_input_block_canary,
)
from llm_ablation_paper.workstream_1_technical_lead.harness import AblationConfig
from llm_ablation_paper.workstream_1_technical_lead.harness import resolve_provider_credentials
from llm_ablation_paper.workstream_1_technical_lead.harness.runner import _build_client_from_provider_config


def _openai_error(cls_name: str, status: int) -> Exception:
    import httpx
    import openai

    cls = getattr(openai, cls_name)
    request = httpx.Request("POST", "https://example.com/v1/chat/completions")
    response = httpx.Response(status, request=request)
    try:
        return cls(f"test {cls_name} {status}", response=response, body=None)
    except TypeError:
        return cls(request=request)


@pytest.mark.parametrize("cls_name,status", [
    ("APITimeoutError", 408),
    ("APIConnectionError", 503),
    ("InternalServerError", 500),
    ("RateLimitError", 429),
    ("APIStatusError", 408),
    ("APIStatusError", 409),
    ("APIStatusError", 429),
    ("APIStatusError", 500),
    ("APIStatusError", 502),
    ("APIStatusError", 503),
    ("APIStatusError", 504),
])
def test_retry_status_matrix_retries(cls_name, status):
    assert _is_transient_error(_openai_error(cls_name, status)) is True


@pytest.mark.parametrize("cls_name,status", [
    ("APIStatusError", 400),
    ("APIStatusError", 401),
    ("APIStatusError", 403),
    ("APIStatusError", 404),
    ("APIStatusError", 422),
    ("BadRequestError", 400),
    ("AuthenticationError", 401),
    ("PermissionDeniedError", 403),
    ("NotFoundError", 404),
    ("UnprocessableEntityError", 422),
])
def test_retry_status_matrix_no_retry(cls_name, status):
    assert _is_transient_error(_openai_error(cls_name, status)) is False


@pytest.mark.parametrize("exc", [
    ValueError("schema error"),
    TypeError("type error"),
    KeyError("missing"),
    AssertionError("contract error"),
])
def test_retry_non_retryable_classes(exc):
    assert _is_transient_error(exc) is False


def test_retry_builtin_transient():
    assert _is_transient_error(TimeoutError("timed out")) is True
    assert _is_transient_error(ConnectionError("connection reset")) is True


def test_timeout_default_preserved_and_non_positive_rejected():
    runner = RoleplayRunner(patient_agent=DeterministicPatientAgent(), output_root=Path("/tmp"))
    assert runner.subprocess_timeout_seconds == 30.0
    with pytest.raises(ValueError, match="positive"):
        RoleplayRunner(
            patient_agent=DeterministicPatientAgent(),
            output_root=Path("/tmp"),
            subprocess_timeout_seconds=0,
        )
    with pytest.raises(ValueError, match="positive"):
        RoleplayRunner(
            patient_agent=DeterministicPatientAgent(),
            output_root=Path("/tmp"),
            subprocess_timeout_seconds=-5,
        )


def test_timeout_forwarded_to_subprocess(tmp_path, monkeypatch):
    import llm_ablation_paper.workstream_1_technical_lead.harness as harness_pkg

    captured = {}

    def fake_subprocess(**kwargs):
        captured.update(kwargs)
        message = kwargs["messages"][-1]
        return [{
            "assistant_response": "ok",
            "termination_reason": None,
            "turn_index": len(kwargs["messages"]) - 1,
            "user_message": message,
        }]

    monkeypatch.setattr(harness_pkg, "run_trajectory_subprocess", fake_subprocess)
    runner = RoleplayRunner(
        patient_agent=DeterministicPatientAgent(),
        output_root=tmp_path,
        subprocess_timeout_seconds=77.0,
    )
    runner.run_condition(
        profile=load_profiles()["SP-001"],
        condition="A",
        fake_talker_responses=["x"] * 6,
    )
    assert captured["timeout"] == 77.0


def test_timeout_failure_keeps_error_and_attempts(tmp_path, monkeypatch):
    runner = RoleplayRunner(
        patient_agent=DeterministicPatientAgent(),
        output_root=tmp_path,
        retry_delays=(0,),
        sleep=lambda _: None,
    )

    def always_timeout(**kwargs):
        raise TimeoutError("Subprocess trajectory timed out after 77.0s")

    import llm_ablation_paper.workstream_1_technical_lead.harness as harness_pkg

    monkeypatch.setattr(harness_pkg, "run_trajectory_subprocess", always_timeout)
    with pytest.raises(RuntimeError):
        runner.run_condition(
            profile=load_profiles()["SP-001"],
            condition="A",
            fake_talker_responses=["x"] * 6,
        )
    run_dir = tmp_path / "WS4-FAKE-SP-001-A"
    checkpoint = json.loads((run_dir / "ws4_runner_checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["termination_reason"] == "ERROR"
    attempts = checkpoint["error_metadata"]["attempts"]
    assert len(attempts) == 2
    assert [a["outcome"] for a in attempts] == ["retry", "error"]
    assert attempts[0]["error_type"] == "TimeoutError"


def _formal_config_factory(condition):
    base = AblationConfig.for_condition(condition)
    return base.__class__(
        **{**base.to_dict(), "model": "test-formal-model", "temperature": 0.3, "seed": 42}
    )


def test_formal_run_with_client_factory_rejected(tmp_path):
    runner = RoleplayRunner(
        patient_agent=DeterministicPatientAgent(),
        output_root=tmp_path,
        config_factory=_formal_config_factory,
        client_factory=lambda: None,
    )
    with pytest.raises(ValueError, match="client_factory"):
        runner.run_condition(
            profile=load_profiles()["SP-001"],
            condition="A",
            run_suffix="FORMAL",
        )


def test_formal_run_without_env_key_fails_before_subprocess(tmp_path, monkeypatch):
    import llm_ablation_paper.workstream_1_technical_lead.harness as harness_pkg

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    called = {"count": 0}

    def spy_subprocess(**kwargs):
        called["count"] += 1
        raise AssertionError("subprocess must not spawn")

    monkeypatch.setattr(harness_pkg, "run_trajectory_subprocess", spy_subprocess)
    runner = RoleplayRunner(
        patient_agent=DeterministicPatientAgent(),
        output_root=tmp_path,
        config_factory=_formal_config_factory,
    )
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY.*OPENAI_API_KEY"):
        runner.run_condition(
            profile=load_profiles()["SP-001"],
            condition="A",
            run_suffix="FORMAL",
        )
    assert called["count"] == 0


@pytest.mark.parametrize("secret_key", ["api_key", "auth_token", "client_secret"])
def test_formal_provider_config_with_secret_rejected(tmp_path, monkeypatch, secret_key):
    monkeypatch.setenv("GEMINI_API_KEY", "sk-test-key")
    runner = RoleplayRunner(
        patient_agent=DeterministicPatientAgent(),
        output_root=tmp_path,
        config_factory=_formal_config_factory,
        provider_config={secret_key: "sk-test-key"},
    )
    with pytest.raises(ValueError, match="must not contain secrets"):
        runner.run_condition(
            profile=load_profiles()["SP-001"],
            condition="A",
            run_suffix="FORMAL",
        )


def test_research_patient_id_and_blinded_export(tmp_path):
    from llm_ablation_paper.workstream_1_technical_lead.harness import to_blinded_contract_trajectory

    runner = RoleplayRunner(patient_agent=DeterministicPatientAgent(), output_root=tmp_path)
    result = runner.run_condition(
        profile=load_profiles()["SP-001"],
        condition="A",
        fake_talker_responses=list(FAKE_TALKER_RESPONSES),
        run_suffix="FAKE",
    )
    assert result["patient_id"] == "SP-001"
    assert result["user_id"] == "ws4_sp-001_a_fake"
    for record in result["records"]:
        assert record["harness_turn"]["research_patient_id"] == "SP-001"
        assert record["harness_turn"]["patient_id"] == "SP-001"

    mapping = {"A": "COND-AAAA1111", "B": "COND-BBBB2222", "C": "COND-CCCC3333", "D": "COND-DDDD4444"}
    blinded = to_blinded_contract_trajectory(
        result["run_id"],
        tmp_path / result["run_id"] / "isolated_state",
        condition_mapping=mapping,
        require_completed=True,
    )
    assert blinded["patient_id"] == "SP-001"
    assert blinded["run_id"].startswith("BLIND-")
    assert blinded["state_dir_id"].startswith("STATE-BLIND-")
    assert blinded["condition_secret"] == "COND-AAAA1111"
    dump = json.dumps(blinded, ensure_ascii=False).lower()
    assert "ws4_sp-" not in dump
    assert "enable_" not in dump

    def _keys(item):
        if isinstance(item, dict):
            for key, value in item.items():
                yield key
                yield from _keys(value)
        elif isinstance(item, list):
            for value in item:
                yield from _keys(value)

    leaked = {k for k in _keys(blinded) if k in {"condition", "mapping"}}
    assert leaked == set()


def test_common_input_block_canary(tmp_path):
    result = run_input_block_canary(tmp_path, condition="A")
    assert result["termination_reason"] == "COMMON_INPUT_BLOCK"
    assert result.get("canary") is True
    assert result.get("is_canary") is True
    assert "FAKE" in result["run_id"]
    assert "CANARY" in result["run_id"]
    assert result["patient_id"] == "SP-CANARY-INPUT-BLOCK"
    canary_dir = tmp_path / "canary_input_block"
    assert (canary_dir / result["run_id"] / "roleplay_result.json").exists()
    assert not (tmp_path / "WS4-FAKE-SP-001-A").exists()


def test_ws4_require_source_csv_fail_closed(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "real_artifact_integration",
        PROJECT_ROOT / "llm_ablation_paper/workstream_4_patient_simulation/tests/test_real_artifact_integration.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from _pytest.outcomes import Failed

    monkeypatch.setattr(module, "_has_source_csv", lambda: False)
    monkeypatch.setenv("WS4_REQUIRE_SOURCE_CSV", "1")
    with pytest.raises(Failed, match="fail closed"):
        module._require_source_csv_or_skip()
    monkeypatch.delenv("WS4_REQUIRE_SOURCE_CSV", raising=False)
    with pytest.raises(pytest.skip.Exception):
        module._require_source_csv_or_skip()


def test_base_url_precedence(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    _, default_url = resolve_provider_credentials({})
    assert "generativelanguage.googleapis.com" in default_url

    monkeypatch.setenv("GEMINI_BASE_URL", "https://gemini.example/v1beta/openai/")
    _, url = resolve_provider_credentials({})
    assert url == "https://gemini.example/v1beta/openai/"

    monkeypatch.delenv("GEMINI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openai.example/v1")
    _, url = resolve_provider_credentials({})
    assert url == "https://openai.example/v1"

    _, url = resolve_provider_credentials({"base_url": "https://explicit.example/v1"})
    assert url == "https://explicit.example/v1"

    _, url = resolve_provider_credentials({"base_url": "   "})
    assert url == "https://openai.example/v1"

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-fallback")
    key, _ = resolve_provider_credentials({})
    assert key == "sk-openai-fallback"


def test_provider_key_never_leaks_into_exception(monkeypatch):
    from unittest.mock import patch

    sentinel = "SENTINEL-KEY-DO-NOT-LEAK-12345"
    monkeypatch.setenv("GEMINI_API_KEY", sentinel)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with patch("openai.OpenAI", side_effect=Exception("boom")):
        with pytest.raises(RuntimeError) as exc_info:
            _build_client_from_provider_config({})
    assert sentinel not in str(exc_info.value)
    assert sentinel not in json.dumps(AblationConfig.for_condition("A").to_dict())


def test_artifacts_dir_override_avoids_repo_writes(tmp_path):
    repo_artifacts = PROJECT_ROOT / "llm_ablation_paper" / "artifacts" / "workstream_1"
    runner = RoleplayRunner(patient_agent=DeterministicPatientAgent(), output_root=tmp_path)
    result = runner.run_condition(
        profile=load_profiles()["SP-001"],
        condition="A",
        fake_talker_responses=list(FAKE_TALKER_RESPONSES),
        run_suffix="FAKE",
    )
    assert (tmp_path / result["run_id"] / "isolated_state" / "trajectories.jsonl").exists()
    assert not (repo_artifacts / result["run_id"]).exists()


def test_subprocess_formal_preflight_fails_closed_before_spawn(tmp_path, monkeypatch):
    from llm_ablation_paper.workstream_1_technical_lead.harness import run_trajectory_subprocess

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = _formal_config_factory("A")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY.*OPENAI_API_KEY"):
        run_trajectory_subprocess(
            config=config, patient_id="p_preflight", messages=["hi"], state_dir=tmp_path
        )
    assert not (tmp_path / "trajectories.jsonl").exists()


def test_subprocess_rejects_callable_model_client(tmp_path):
    from llm_ablation_paper.workstream_1_technical_lead.harness import run_trajectory_subprocess

    config = AblationConfig.for_condition("A")
    with pytest.raises(TypeError, match="unsupported model_client"):
        run_trajectory_subprocess(
            config=config,
            patient_id="p_callable",
            messages=["hi"],
            state_dir=tmp_path,
            model_client=lambda: None,
        )
