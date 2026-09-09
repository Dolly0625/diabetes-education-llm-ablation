"""WS4-B Patient Agent roleplay runner.

This module deliberately orchestrates the existing WS1 Harness rather than
reimplementing the production pipeline.  Each patient turn is executed in an
independent Harness subprocess.  The next patient utterance is generated only
after that subprocess has persisted its checkpoint, so a rerun can resume
from the last completed turn without sharing state across A/B/C/D.

The default command is an offline deterministic fake dry run.  A Gemini
Patient Agent is available for the technical lead after the formal experiment
fingerprint is frozen, but this module never starts a 12 x 4 formal batch.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Protocol, TypeVar


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PAPER_ROOT = PROJECT_ROOT / "llm_ablation_paper"
WS4_ROOT = PAPER_ROOT / "workstream_4_patient_simulation"
PROFILES_PATH = WS4_ROOT / "patient_profiles.jsonl"
PATIENT_PROMPT_PATH = WS4_ROOT / "patient_agent_prompt.md"

# Direct ``python scripts/run_patient_simulation.py`` execution places the
# scripts directory—not the repository root—on sys.path.  Add only this
# repository root so the approved WS1 Harness package resolves consistently.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MAX_RETRY_DELAYS_SECONDS = (1, 2, 4, 8)
TERMINATION_REASONS = {
    "PATIENT_GOAL_MET",
    "MAX_TURNS",
    "COMMON_INPUT_BLOCK",
    "ERROR",
}


class PatientAgent(Protocol):
    """A Patient Agent returns the structured JSON contract from the prompt."""

    def next_turn(
        self,
        *,
        profile: dict[str, Any],
        assistant_output: Optional[str],
        turn_number: int,
        prior_turns: list[dict[str, Any]],
    ) -> dict[str, Any]: ...


T = TypeVar("T")


class RetryExhaustedError(RuntimeError):
    """Raised after a bounded call fails, retaining every attempt for artifacts."""

    def __init__(self, attempts: list[dict[str, Any]]) -> None:
        self.attempts = attempts
        super().__init__(json.dumps(attempts, ensure_ascii=False))


def _write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_profiles(path: Path = PROFILES_PATH) -> dict[str, dict[str, Any]]:
    """Load profiles as read-only input and perform minimal contract checks."""
    profiles: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        profile = json.loads(line)
        required = {
            "patient_id", "scenario_type", "known_facts", "hidden_facts",
            "reveal_policy", "patient_goal", "risk_trigger", "max_turns",
        }
        missing = sorted(required - set(profile))
        if missing:
            raise ValueError(f"profile line {line_number} lacks {missing}")
        if profile["patient_id"] in profiles:
            raise ValueError(f"duplicate patient_id: {profile['patient_id']}")
        if profile["max_turns"] != 6:
            raise ValueError(f"{profile['patient_id']} max_turns must remain 6")
        profiles[profile["patient_id"]] = profile
    if len(profiles) != 12:
        raise ValueError(f"expected 12 frozen profiles, got {len(profiles)}")
    return profiles


def validate_patient_turn(turn: dict[str, Any]) -> dict[str, Any]:
    """Fail closed if a simulator response violates the prompt's JSON contract."""
    required = {"patient_utterance", "should_end", "termination_reason", "disclosed_facts", "evidence"}
    missing = required - set(turn)
    unexpected = set(turn) - required
    if missing or unexpected:
        raise ValueError(f"invalid Patient Agent fields; missing={sorted(missing)}, unexpected={sorted(unexpected)}")
    if not isinstance(turn["patient_utterance"], str) or not turn["patient_utterance"].strip():
        raise ValueError("patient_utterance must be a non-empty string")
    if not isinstance(turn["should_end"], bool):
        raise ValueError("should_end must be boolean")
    if turn["termination_reason"] not in TERMINATION_REASONS:
        raise ValueError("invalid termination_reason")
    if not isinstance(turn["disclosed_facts"], list) or not all(isinstance(x, str) for x in turn["disclosed_facts"]):
        raise ValueError("disclosed_facts must be a list of strings")
    if not isinstance(turn["evidence"], str) or not turn["evidence"].strip():
        raise ValueError("evidence must be non-empty")
    forbidden = ("enable_", "condition", "original_answer", "raw_answer")
    lowered = turn["patient_utterance"].lower()
    if any(token in lowered for token in forbidden):
        raise ValueError("patient utterance leaks experiment/internal fields")
    return turn


def _value_to_patient_text(value: Any) -> str:
    if isinstance(value, dict):
        # Do not invent a medical interpretation of structured facts.
        if "converted" in value and isinstance(value["converted"], dict):
            converted = value["converted"]
            return f"我餐後量到大約 {converted.get('normalized_value')} {converted.get('normalized_unit')}。"
        return "這個我有記著，不過細節要再看一下。"
    return str(value)


_FACT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "night_snack": ("宵夜", "晚上", "飲料", "含糖"),
    "glucose_log": ("血糖", "飯後", "餐後", "紀錄"),
    "staple_amount": ("白飯", "飯量", "幾碗", "主食"),
    "side_effect_detail": ("副作用", "不舒服", "肚子", "噁心"),
    "adherence": ("按時", "服藥", "吃藥", "漏吃"),
    "nonadherence_intent": ("停藥", "減藥", "自己改", "劑量"),
}


class DeterministicPatientAgent:
    """Offline Patient Agent for tests/dry runs; it never invents profile facts."""

    def _initial_utterance(self, profile: dict[str, Any]) -> str:
        known = profile["known_facts"]
        if profile["scenario_type"] == "FACT_CONTRADICTION" and "initial_statement" in known:
            return str(known["initial_statement"])
        if "language_note" in known:
            return f"我想問一下，{known['language_note']}。{profile['patient_goal']}"
        if "diet_habit" in known:
            return f"我平常是 {known['diet_habit']}，{profile['patient_goal']}。"
        return str(profile["patient_goal"])

    def _directly_asked(self, key: str, assistant_output: str) -> bool:
        lowered = assistant_output.lower()
        keywords = _FACT_KEYWORDS.get(key, tuple(part for part in key.lower().split("_") if part))
        question_like = any(mark in assistant_output for mark in ("？", "?", "請問", "能否", "會不會", "多少"))
        return question_like and any(keyword.lower() in lowered for keyword in keywords)

    def next_turn(
        self,
        *,
        profile: dict[str, Any],
        assistant_output: Optional[str],
        turn_number: int,
        prior_turns: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if assistant_output is None:
            return {
                "patient_utterance": self._initial_utterance(profile),
                "should_end": False,
                "termination_reason": "MAX_TURNS",
                "disclosed_facts": [],
                "evidence": "第一輪僅使用 profile 的 known_facts 與 patient_goal。",
            }

        if turn_number > int(profile["max_turns"]):
            return {
                "patient_utterance": "謝謝你，我先照這樣準備。",
                "should_end": True,
                "termination_reason": "MAX_TURNS",
                "disclosed_facts": [],
                "evidence": "已達 profile.max_turns，不再產生第七輪。",
            }

        hidden = profile["hidden_facts"]
        policy = profile["reveal_policy"]
        disclosed_before = {key for item in prior_turns for key in item["patient_turn"].get("disclosed_facts", [])}

        if profile["scenario_type"] == "FACT_CONTRADICTION" and turn_number >= int(policy["correction_turn"]):
            if "true_value" in hidden and "true_value" not in disclosed_before:
                value = _value_to_patient_text(hidden["true_value"])
                return {
                    "patient_utterance": f"啊，我剛剛講錯了，其實是 {value}",
                    "should_end": False,
                    "termination_reason": "MAX_TURNS",
                    "disclosed_facts": ["true_value"],
                    "evidence": "FACT_CONTRADICTION 已到 correction_turn，依 policy 更正一次。",
                }

        for key, value in hidden.items():
            if key not in disclosed_before and self._directly_asked(key, assistant_output):
                return {
                    "patient_utterance": _value_to_patient_text(value),
                    "should_end": False,
                    "termination_reason": "MAX_TURNS",
                    "disclosed_facts": [key],
                    "evidence": f"助理直接詢問 {key} 的主題，依 on_direct_question_only 揭露。",
                }

        return {
            "patient_utterance": "我目前能想到的大概就是這些，還有什麼要問我嗎？",
            "should_end": False,
            "termination_reason": "MAX_TURNS",
            "disclosed_facts": [],
            "evidence": "未被直接問到未揭露 hidden_facts，因此不主動補充。",
        }


class GeminiPatientAgent:
    """Optional real Patient Agent.  It is not selected by the fake dry run."""

    def __init__(self, client: Any, prompt_text: str, *, model: str, temperature: float) -> None:
        if not model.strip():
            raise ValueError("Patient Agent model must be supplied by the frozen experiment configuration")
        self.client = client
        self.prompt_text = prompt_text
        self.model = model
        self.temperature = temperature

    @classmethod
    def from_environment(cls, *, model: str, temperature: float) -> "GeminiPatientAgent":
        from dotenv import load_dotenv
        from openai import OpenAI

        load_dotenv(PROJECT_ROOT / ".env")
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is absent; the key is never accepted via command arguments")
        base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
        return cls(
            OpenAI(api_key=api_key.strip('"'), base_url=base_url),
            PATIENT_PROMPT_PATH.read_text(encoding="utf-8"),
            model=model,
            temperature=temperature,
        )

    def next_turn(
        self,
        *,
        profile: dict[str, Any],
        assistant_output: Optional[str],
        turn_number: int,
        prior_turns: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload = {
            "profile": profile,
            "assistant_output": assistant_output,
            "turn_number": turn_number,
            "prior_disclosed_facts": [x["patient_turn"]["disclosed_facts"] for x in prior_turns],
        }
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": self.prompt_text},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        )
        try:
            return validate_patient_turn(json.loads(response.choices[0].message.content))
        except Exception as exc:
            raise RuntimeError(f"Patient Agent returned invalid structured JSON: {exc}") from exc


def _is_transient_error(exc: Exception) -> bool:
    return isinstance(exc, (TimeoutError, ConnectionError)) or any(
        marker in str(exc).lower()
        for marker in ("timeout", "temporar", "rate limit", "429", "connection reset")
    )


def _default_config_factory(condition: str):
    from llm_ablation_paper.workstream_1_technical_lead.harness import AblationConfig

    return AblationConfig.for_condition(condition)


def _build_config(
    condition: str,
    run_id: str,
    max_turns: int,
    config_factory: Callable[[str], Any] = _default_config_factory,
):

    if condition not in {"A", "B", "C", "D"}:
        raise ValueError(f"condition must be one of A/B/C/D, got {condition!r}")
    config = config_factory(condition)
    if getattr(config, "condition", None) != condition:
        raise ValueError("WS1 config_factory returned a config for the wrong condition")
    return replace(config, run_id=run_id, max_turns=max_turns)


def _patient_agent_metadata(patient_agent: PatientAgent) -> dict[str, Any]:
    metadata: dict[str, Any] = {"implementation": type(patient_agent).__name__}
    if hasattr(patient_agent, "model"):
        metadata["model"] = getattr(patient_agent, "model")
    if hasattr(patient_agent, "temperature"):
        metadata["temperature"] = getattr(patient_agent, "temperature")
    return metadata


@dataclass
class RoleplayRunner:
    patient_agent: PatientAgent
    output_root: Path
    config_factory: Callable[[str], Any] = _default_config_factory
    retry_delays: tuple[int, ...] = MAX_RETRY_DELAYS_SECONDS
    sleep: Callable[[float], None] = time.sleep

    def _checkpoint_path(self, run_id: str) -> Path:
        return self.output_root / run_id / "ws4_runner_checkpoint.json"

    def _call_harness(
        self,
        *,
        config: Any,
        patient_id: str,
        messages: list[str],
        state_dir: Path,
        run_id: str,
        resume: bool,
        fake_responses: Optional[list[str]],
    ) -> list[dict[str, Any]]:
        from llm_ablation_paper.workstream_1_technical_lead.harness import run_trajectory_subprocess

        return run_trajectory_subprocess(
            config=config,
            patient_id=patient_id,
            messages=messages,
            state_dir=state_dir,
            run_id=run_id,
            resume=resume,
            fake_responses=fake_responses,
            timeout=30.0,
        )

    def _run_with_retry(self, call: Callable[[], T]) -> tuple[T, list[dict[str, Any]]]:
        attempts: list[dict[str, Any]] = []
        for attempt in range(len(self.retry_delays) + 1):
            try:
                result = call()
                attempts.append({"attempt": attempt + 1, "outcome": "success"})
                return result, attempts
            except Exception as exc:
                retryable = _is_transient_error(exc) and attempt < len(self.retry_delays)
                attempts.append({
                    "attempt": attempt + 1,
                    "outcome": "retry" if retryable else "error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                })
                if not retryable:
                    raise RetryExhaustedError(attempts) from exc
                self.sleep(self.retry_delays[attempt])
        raise AssertionError("unreachable")

    def _result_payload(
        self,
        *,
        run_id: str,
        patient_id: str,
        condition: str,
        user_id: str,
        state_dir: Path,
        config: Any,
        records: list[dict[str, Any]],
        termination_reason: str,
        terminal_patient_turn: Optional[dict[str, Any]] = None,
        error_metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "patient_id": patient_id,
            "condition": condition,
            "user_id": user_id,
            "state_dir_id": state_dir.name,
            "config": config.to_dict(),
            "patient_agent": _patient_agent_metadata(self.patient_agent),
            "records": records,
            "terminal_patient_turn": terminal_patient_turn,
            "termination_reason": termination_reason,
            "error_metadata": error_metadata,
        }

    def _persist_terminal_state(
        self,
        *,
        run_dir: Path,
        checkpoint_path: Path,
        result: dict[str, Any],
        pending_patient_turn: Optional[dict[str, Any]] = None,
        pending_patient_retry_metadata: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        checkpoint = {
            "run_id": result["run_id"],
            "patient_id": result["patient_id"],
            "condition": result["condition"],
            "user_id": result["user_id"],
            "records": result["records"],
            "pending_patient_turn": pending_patient_turn,
            "pending_patient_retry_metadata": pending_patient_retry_metadata or [],
            "terminal_patient_turn": result["terminal_patient_turn"],
            "termination_reason": result["termination_reason"],
            "error_metadata": result["error_metadata"],
        }
        _write_json_atomic(checkpoint_path, checkpoint)
        _write_json_atomic(run_dir / "roleplay_result.json", result)

    def run_condition(
        self,
        *,
        profile: dict[str, Any],
        condition: str,
        fake_talker_responses: Optional[list[str]] = None,
        resume: bool = False,
        run_suffix: str = "FAKE",
    ) -> dict[str, Any]:
        patient_id = profile["patient_id"]
        run_id = f"WS4-{run_suffix}-{patient_id}-{condition}"
        run_dir = self.output_root / run_id
        state_dir = run_dir / "isolated_state"
        checkpoint_path = self._checkpoint_path(run_id)
        config = _build_config(condition, run_id, int(profile["max_turns"]), self.config_factory)
        if run_suffix.upper() != "FAKE" and getattr(config, "model", "fake-model") == "fake-model":
            raise ValueError("formal execution requires a frozen WS1 config_factory; fake-model is dry-run only")
        user_id = f"ws4_{patient_id.lower()}_{condition.lower()}_{run_suffix.lower()}"

        records: list[dict[str, Any]] = []
        patient_messages: list[str] = []
        last_assistant: Optional[str] = None
        pending_patient_turn: Optional[dict[str, Any]] = None
        pending_patient_retry_metadata: list[dict[str, Any]] = []
        terminal_patient_turn: Optional[dict[str, Any]] = None
        termination_reason: Optional[str] = None
        if resume:
            if not checkpoint_path.exists():
                raise FileNotFoundError(f"resume requested but checkpoint is missing: {checkpoint_path}")
            saved = _read_json(checkpoint_path)
            if saved["run_id"] != run_id or saved["patient_id"] != patient_id or saved["condition"] != condition:
                raise ValueError("resume checkpoint identity mismatch")
            records = saved["records"]
            patient_messages = [record["patient_turn"]["patient_utterance"] for record in records]
            last_assistant = records[-1]["harness_turn"]["assistant_response"] if records else None
            pending_patient_turn = saved.get("pending_patient_turn")
            pending_patient_retry_metadata = saved.get("pending_patient_retry_metadata", [])
            if pending_patient_turn is not None:
                patient_messages.append(pending_patient_turn["patient_utterance"])
            saved_reason = saved.get("termination_reason")
            if saved_reason != "ERROR":
                termination_reason = saved_reason
                terminal_patient_turn = saved.get("terminal_patient_turn")
        elif run_dir.exists():
            raise FileExistsError(f"run directory already exists; use resume=True: {run_dir}")

        while termination_reason is None and len(records) < int(profile["max_turns"]):
            turn_number = len(records) + 1
            if pending_patient_turn is None:
                try:
                    patient_turn, pending_patient_retry_metadata = self._run_with_retry(
                        lambda: validate_patient_turn(self.patient_agent.next_turn(
                            profile=profile,
                            assistant_output=last_assistant,
                            turn_number=turn_number,
                            prior_turns=records,
                        ))
                    )
                except RetryExhaustedError as exc:
                    error_metadata = {"stage": "patient_agent", "turn": turn_number, "attempts": exc.attempts}
                    result = self._result_payload(
                        run_id=run_id, patient_id=patient_id, condition=condition, user_id=user_id,
                        state_dir=state_dir, config=config, records=records,
                        termination_reason="ERROR", error_metadata=error_metadata,
                    )
                    self._persist_terminal_state(
                        run_dir=run_dir, checkpoint_path=checkpoint_path, result=result,
                    )
                    raise
                pending_patient_turn = patient_turn
            patient_turn = pending_patient_turn
            if patient_turn["should_end"]:
                termination_reason = patient_turn["termination_reason"]
                terminal_patient_turn = patient_turn
                break

            if not patient_messages or patient_messages[-1] != patient_turn["patient_utterance"]:
                patient_messages.append(patient_turn["patient_utterance"])
            one_response = None
            if fake_talker_responses is not None:
                if len(fake_talker_responses) <= len(records):
                    raise ValueError("fake_talker_responses must cover every simulated turn")
                # A fresh subprocess creates a fresh fake client, so provide only
                # the response for this exact Harness turn.
                one_response = [fake_talker_responses[len(records)]]
            try:
                harness_result, retry_metadata = self._run_with_retry(lambda: self._call_harness(
                    config=config,
                    patient_id=user_id,
                    messages=patient_messages,
                    state_dir=state_dir,
                    run_id=run_id,
                    resume=bool(records),
                    fake_responses=one_response,
                ))
            except RetryExhaustedError as exc:
                error_metadata = {"stage": "harness", "turn": turn_number, "attempts": exc.attempts}
                result = self._result_payload(
                    run_id=run_id, patient_id=patient_id, condition=condition, user_id=user_id,
                    state_dir=state_dir, config=config, records=records,
                    termination_reason="ERROR", error_metadata=error_metadata,
                )
                self._persist_terminal_state(
                    run_dir=run_dir,
                    checkpoint_path=checkpoint_path,
                    result=result,
                    pending_patient_turn=patient_turn,
                    pending_patient_retry_metadata=pending_patient_retry_metadata,
                )
                raise
            harness_turn = harness_result[-1]
            record = {
                "turn": turn_number,
                "patient_turn": patient_turn,
                "harness_turn": harness_turn,
                "patient_retry_metadata": pending_patient_retry_metadata,
                "retry_metadata": retry_metadata,
            }
            records.append(record)
            last_assistant = harness_turn["assistant_response"]
            pending_patient_turn = None
            pending_patient_retry_metadata = []

            if harness_turn.get("termination_reason") in {"COMMON_INPUT_BLOCK", "ERROR"}:
                termination_reason = harness_turn["termination_reason"]
            elif turn_number == int(profile["max_turns"]):
                termination_reason = "MAX_TURNS"

            _write_json_atomic(checkpoint_path, {
                "run_id": run_id,
                "patient_id": patient_id,
                "condition": condition,
                "user_id": user_id,
                "records": records,
                "pending_patient_turn": None,
                "pending_patient_retry_metadata": [],
                "terminal_patient_turn": None,
                "termination_reason": termination_reason,
                "error_metadata": None,
            })
            if termination_reason:
                break

        if termination_reason is None:
            termination_reason = "MAX_TURNS"
        result = self._result_payload(
            run_id=run_id,
            patient_id=patient_id,
            condition=condition,
            user_id=user_id,
            state_dir=state_dir,
            config=config,
            records=records,
            terminal_patient_turn=terminal_patient_turn,
            termination_reason=termination_reason,
        )
        self._persist_terminal_state(run_dir=run_dir, checkpoint_path=checkpoint_path, result=result)
        return result


FAKE_TALKER_RESPONSES = [
    "我先了解一下，您平常每餐白飯大約吃多少？",
    "謝謝您。晚上會喝含糖飲料或吃宵夜嗎？",
    "我會把這些飲食狀況整理好，回診時也可以和醫師或衛教師討論。",
    "您先記錄餐點和血糖，有不舒服請依原本醫囑處理並儘快詢問醫療人員。",
    "還有沒有其他想確認的生活習慣？",
    "謝謝您的說明，今天先到這裡。",
]


def _run_deterministic_fake_condition(
    *,
    runner: RoleplayRunner,
    profile: dict[str, Any],
    condition: str,
    fake_talker_responses: list[str],
) -> dict[str, Any]:
    """Run one fake trajectory in exactly one WS1 subprocess.

    The deterministic simulator can safely precompute its next utterance from
    the fixed fake Talker response.  This preserves the required one-process-
    per-trajectory isolation while avoiding a Windows process launch at every
    individual turn.  Live Patient Agent execution remains intentionally
    unavailable until WS1 supplies a streaming callback/frozen fingerprint.
    """
    if not isinstance(runner.patient_agent, DeterministicPatientAgent):
        raise TypeError("fake dry run requires DeterministicPatientAgent")
    patient_id = profile["patient_id"]
    run_id = f"WS4-FAKE-{patient_id}-{condition}"
    run_dir = runner.output_root / run_id
    if run_dir.exists():
        raise FileExistsError(f"fake run already exists: {run_dir}")
    state_dir = run_dir / "isolated_state"
    user_id = f"ws4_{patient_id.lower()}_{condition.lower()}_fake"
    config = _build_config(condition, run_id, int(profile["max_turns"]), runner.config_factory)

    simulated_turns: list[dict[str, Any]] = []
    messages: list[str] = []
    previous_output: Optional[str] = None
    for turn_number in range(1, int(profile["max_turns"]) + 1):
        patient_turn = validate_patient_turn(runner.patient_agent.next_turn(
            profile=profile,
            assistant_output=previous_output,
            turn_number=turn_number,
            prior_turns=simulated_turns,
        ))
        if patient_turn["should_end"]:
            break
        messages.append(patient_turn["patient_utterance"])
        simulated_turns.append({"patient_turn": patient_turn})
        previous_output = fake_talker_responses[turn_number - 1]

    harness_results, retry_metadata = runner._run_with_retry(lambda: runner._call_harness(
        config=config,
        patient_id=user_id,
        messages=messages,
        state_dir=state_dir,
        run_id=run_id,
        resume=False,
        fake_responses=fake_talker_responses[:len(messages)],
    ))
    if len(harness_results) != len(simulated_turns):
        raise RuntimeError(
            f"Harness returned {len(harness_results)} turns for {len(simulated_turns)} patient turns"
        )
    records = [
        {
            "turn": index + 1,
            "patient_turn": simulated_turns[index]["patient_turn"],
            "harness_turn": harness_results[index],
            "retry_metadata": retry_metadata,
        }
        for index in range(len(simulated_turns))
    ]
    termination_reason = "MAX_TURNS" if len(records) == int(profile["max_turns"]) else "PATIENT_GOAL_MET"
    _write_json_atomic(run_dir / "ws4_runner_checkpoint.json", {
        "run_id": run_id,
        "patient_id": patient_id,
        "condition": condition,
        "user_id": user_id,
        "records": records,
        "pending_patient_turn": None,
        "pending_patient_retry_metadata": [],
        "terminal_patient_turn": None,
        "termination_reason": termination_reason,
        "error_metadata": None,
    })
    result = {
        "run_id": run_id,
        "patient_id": patient_id,
        "condition": condition,
        "user_id": user_id,
        "state_dir_id": state_dir.name,
        "config": config.to_dict(),
        "patient_agent": _patient_agent_metadata(runner.patient_agent),
        "records": records,
        "terminal_patient_turn": None,
        "termination_reason": termination_reason,
        "error_metadata": None,
    }
    _write_json_atomic(run_dir / "roleplay_result.json", result)
    return result


def run_fake_dry_run(output_root: Path, patient_id: str = "SP-001") -> dict[str, Any]:
    """Required WS4 1-profile x 4-condition deterministic fake dry run."""
    profiles = load_profiles()
    if patient_id not in profiles:
        raise KeyError(f"unknown frozen profile: {patient_id}")
    runner = RoleplayRunner(patient_agent=DeterministicPatientAgent(), output_root=output_root)
    results = [_run_deterministic_fake_condition(
        runner=runner,
        profile=profiles[patient_id],
        condition=condition,
        fake_talker_responses=FAKE_TALKER_RESPONSES,
    ) for condition in ("A", "B", "C", "D")]
    summary = {
        "execution_mode": "deterministic_fake_dry_run",
        "formal_experiment_started": False,
        "patient_id": patient_id,
        "runtime_configuration_source": "WS1 AblationConfig supplied to WS4 runner",
        "patient_agent": results[0]["patient_agent"],
        "runs": [{
            "run_id": item["run_id"],
            "condition": item["condition"],
            "user_id": item["user_id"],
            "state_dir_id": item["state_dir_id"],
            "turn_count": len(item["records"]),
            "termination_reason": item["termination_reason"],
        } for item in results],
    }
    _write_json_atomic(output_root / "fake_dry_run_summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="WS4-B Patient Agent roleplay runner")
    parser.add_argument("--fake-dry-run", action="store_true", help="run the required one-profile x four-condition fake dry run")
    parser.add_argument("--patient-id", default="SP-001")
    parser.add_argument("--output-root", type=Path, default=WS4_ROOT / "artifacts" / "fake_dry_run_batch")
    args = parser.parse_args()
    if not args.fake_dry_run:
        parser.error("only --fake-dry-run is enabled until WS1 freezes the formal experiment fingerprint")
    summary = run_fake_dry_run(args.output_root, args.patient_id)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
