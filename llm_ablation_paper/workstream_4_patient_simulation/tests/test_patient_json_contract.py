"""Tests for WS4 Patient Agent structured JSON output contract and retry mechanics.

PHASE M3.2 requirements:
1. GeminiPatientAgent.next_turn chat.completions.create must specify response_format={"type": "json_object"}.
2. Fail-closed on None/empty/whitespace. Accepts only pure JSON or single-layer markdown code fence.
3. Failures (including schema validation) raise PatientAgentContractError.
4. PatientAgentContractError is explicitly retryable up to bounded attempts in _is_transient_error.
   Generic RuntimeError / ValueError remain non-retryable.
5. Error messages must never include raw response or API keys.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation import (
    GeminiPatientAgent,
    PatientAgentContractError,
    RetryExhaustedError,
    RoleplayRunner,
    _is_transient_error,
    _parse_and_validate_patient_turn_response,
    _safe_validate_turn,
    load_profiles,
    validate_patient_turn,
)

VALID_TURN: dict[str, Any] = {
    "patient_utterance": "我最近吃完飯血糖大約在 180 左右。",
    "should_end": False,
    "termination_reason": "MAX_TURNS",
    "disclosed_facts": ["glucose_log"],
    "evidence": "回答助理關於餐後血糖之詢問。",
}


class MockCompletions:
    """Offline mock for openai.chat.completions capturing request payload."""

    def __init__(self, responses: Optional[list[Any]] = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses: list[Any] = list(responses or [])

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.responses:
            item = self.responses.pop(0)
            if isinstance(item, Exception):
                raise item
            content = item
        else:
            content = json.dumps(VALID_TURN, ensure_ascii=False)
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _dummy_profile() -> dict[str, Any]:
    return load_profiles()["SP-001"]


def test_gemini_patient_agent_specifies_json_object_response_format():
    """Verify GeminiPatientAgent passes response_format={"type": "json_object"} to OpenAI client."""
    mock_client = SimpleNamespace(chat=SimpleNamespace(completions=MockCompletions()))
    agent = GeminiPatientAgent(
        client=mock_client,
        prompt_text="You are a standardized patient.",
        model="gemini-3.5-flash-lite",
        temperature=0.3,
    )
    result = agent.next_turn(
        profile=_dummy_profile(),
        assistant_output="請問您的血糖狀況？",
        turn_number=1,
        prior_turns=[],
    )
    assert result["patient_utterance"] == VALID_TURN["patient_utterance"]
    assert len(mock_client.chat.completions.calls) == 1
    call = mock_client.chat.completions.calls[0]
    assert call.get("response_format") == {"type": "json_object"}
    assert call.get("model") == "gemini-3.5-flash-lite"
    assert call.get("temperature") == 0.3


def test_pure_json_and_fenced_json_pass_contract():
    """Verify parser accepts pure JSON and strictly single-layer markdown code fences."""
    raw_dict = copy.deepcopy(VALID_TURN)
    json_str = json.dumps(raw_dict, ensure_ascii=False)

    # 1. Pure JSON (standard, compact, indented, with leading/trailing whitespace)
    assert _parse_and_validate_patient_turn_response(json_str)["patient_utterance"] == raw_dict["patient_utterance"]
    assert _parse_and_validate_patient_turn_response(f"  \n\t{json_str}\n  ")["patient_utterance"] == raw_dict["patient_utterance"]
    assert _parse_and_validate_patient_turn_response(json.dumps(raw_dict, indent=2))["patient_utterance"] == raw_dict["patient_utterance"]

    # 2. Single-layer markdown code fence with ```json
    fenced_json = f"```json\n{json_str}\n```"
    assert _parse_and_validate_patient_turn_response(fenced_json)["patient_utterance"] == raw_dict["patient_utterance"]
    assert _parse_and_validate_patient_turn_response(f"  \n{fenced_json}\n  ")["patient_utterance"] == raw_dict["patient_utterance"]

    # 3. Single-layer markdown code fence without language tag (``` ... ```)
    fenced_no_lang = f"```\n{json_str}\n```"
    assert _parse_and_validate_patient_turn_response(fenced_no_lang)["patient_utterance"] == raw_dict["patient_utterance"]

    # 4. Single-layer inline fenced
    fenced_inline = f"```json {json_str} ```"
    assert _parse_and_validate_patient_turn_response(fenced_inline)["patient_utterance"] == raw_dict["patient_utterance"]


@pytest.mark.parametrize(
    "invalid_input,reason",
    [
        (None, "null content"),
        ("", "empty string"),
        ("   \n\t  ", "whitespace string"),
        ("not json at all", "non-json plain text"),
        ("Here is the patient JSON: " + json.dumps(VALID_TURN), "mixed leading conversational text"),
        (json.dumps(VALID_TURN) + "\nHope this helps!", "mixed trailing conversational text"),
        (f"Here is JSON:\n```json\n{json.dumps(VALID_TURN)}\n```\nThanks", "conversational text surrounding code fence"),
        (f"```json\n{json.dumps(VALID_TURN)}\n```\n```json\n{json.dumps(VALID_TURN)}\n```", "multiple markdown fences"),
        (f"```xml\n{json.dumps(VALID_TURN)}\n```", "unsupported language tag"),
        ("```json\n```", "empty code fence"),
        (f"```json\n{json.dumps(VALID_TURN)}", "unclosed code fence"),
        ("[1, 2, 3]", "JSON array instead of JSON object"),
        ("\"just a string\"", "JSON string primitive instead of JSON object"),
        ("{\"patient_utterance\": \"missing fields\"}", "schema invalid - missing required keys"),
        ("{\"patient_utterance\": \"hi\", \"should_end\": \"not_bool\", \"termination_reason\": \"MAX_TURNS\", \"disclosed_facts\": [], \"evidence\": \"x\"}", "schema invalid - non-bool should_end"),
        ("{\"patient_utterance\": \"my condition is A\", \"should_end\": false, \"termination_reason\": \"MAX_TURNS\", \"disclosed_facts\": [], \"evidence\": \"x\"}", "schema invalid - leaks internal field"),
    ],
)
def test_invalid_formats_raise_patient_agent_contract_error_and_sanitize(invalid_input: Optional[str], reason: str):
    """Verify all non-conforming responses raise PatientAgentContractError and sanitize error messages."""
    fake_api_key = "AIzaSy_MOCK_API_KEY_SECRET_XYZ987"
    fake_raw_leak = "CONFIDENTIAL_RAW_SENSITIVE_TEXT_456"

    # Inject secret into input if string
    test_input = invalid_input
    if isinstance(test_input, str):
        test_input = f"{test_input} [KEY={fake_api_key}] [RAW={fake_raw_leak}]"

    with pytest.raises(PatientAgentContractError) as exc_info:
        _parse_and_validate_patient_turn_response(test_input)

    err_msg = str(exc_info.value)
    assert fake_api_key not in err_msg, f"API key leaked in exception message for {reason}: {err_msg}"
    assert fake_raw_leak not in err_msg, f"Raw response leaked in exception message for {reason}: {err_msg}"


def test_transient_error_classification():
    """Verify PatientAgentContractError is retryable while generic errors are strictly non-retryable."""
    # PatientAgentContractError is explicitly retryable
    contract_err = PatientAgentContractError("Patient Agent returned malformed JSON")
    assert _is_transient_error(contract_err) is True

    # Generic schema/programming exceptions must remain non-retryable
    assert _is_transient_error(ValueError("schema mismatch")) is False
    assert _is_transient_error(TypeError("none type not iterable")) is False
    assert _is_transient_error(KeyError("missing_key")) is False
    assert _is_transient_error(AssertionError("assertion failed")) is False
    assert _is_transient_error(RuntimeError("arbitrary runtime failure")) is False


def test_contract_error_retries_and_succeeds(tmp_path: Path):
    """Verify RoleplayRunner retries on PatientAgentContractError and succeeds with recorded attempts."""
    call_count = 0
    delays_called: list[float] = []

    class FlakyPatientAgent:
        model = "fake-model"
        temperature = 0.0

        def next_turn(self, **kwargs: Any) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                # First two calls violate format contract
                raise PatientAgentContractError(f"transient malformed json attempt {call_count}")
            return copy.deepcopy(VALID_TURN)

    runner = RoleplayRunner(
        patient_agent=FlakyPatientAgent(),
        output_root=tmp_path,
        retry_delays=(0, 0, 0, 0),
        sleep=lambda d: delays_called.append(d),
    )

    result, metadata = runner._run_with_retry(
        lambda: _safe_validate_turn(
            runner.patient_agent.next_turn(
                profile=_dummy_profile(),
                assistant_output=None,
                turn_number=1,
                prior_turns=[],
            )
        )
    )

    assert result["patient_utterance"] == VALID_TURN["patient_utterance"]
    assert call_count == 3
    assert len(metadata) == 3
    assert metadata[0]["outcome"] == "retry"
    assert metadata[0]["error_type"] == "PatientAgentContractError"
    assert metadata[1]["outcome"] == "retry"
    assert metadata[1]["error_type"] == "PatientAgentContractError"
    assert metadata[2]["outcome"] == "success"
    assert len(delays_called) == 2


def test_contract_error_exhaustion_records_attempts(tmp_path: Path):
    """Verify RoleplayRunner exhausts retries on permanent contract errors and records full attempts."""
    call_count = 0

    class PermanentlyBrokenPatientAgent:
        model = "fake-model"
        temperature = 0.0

        def next_turn(self, **kwargs: Any) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            raise PatientAgentContractError("Patient Agent returned malformed JSON")

    runner = RoleplayRunner(
        patient_agent=PermanentlyBrokenPatientAgent(),
        output_root=tmp_path,
        retry_delays=(0, 0, 0, 0),
        sleep=lambda _: None,
    )

    with pytest.raises(RetryExhaustedError) as exc_info:
        runner._run_with_retry(
            lambda: _safe_validate_turn(
                runner.patient_agent.next_turn(
                    profile=_dummy_profile(),
                    assistant_output=None,
                    turn_number=1,
                    prior_turns=[],
                )
            )
        )

    attempts = exc_info.value.attempts
    assert len(attempts) == 5  # 1 initial + 4 retries
    for attempt in attempts[:4]:
        assert attempt["outcome"] == "retry"
        assert attempt["error_type"] == "PatientAgentContractError"
    assert attempts[4]["outcome"] == "error"
    assert attempts[4]["error_type"] == "PatientAgentContractError"
