"""Freeze-candidate regression tests: share-free experiment outputs, rerun determinism,
new Output Guard cases, and fingerprint computability."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llm_ablation_paper.workstream_1_technical_lead.harness.config import compute_tool_snapshot_sha
from llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation import (
    DeterministicPatientAgent,
    FAKE_TALKER_RESPONSES,
    RoleplayRunner,
    load_profiles,
)
from diabetes_chatbot.guard import inspect_output_guard
from diabetes_chatbot.planner import PLANNER_SYSTEM_PROMPT
from diabetes_chatbot.prompts import NURSE_SYSTEM_PROMPT
from diabetes_chatbot.tools import generate_clinic_qr_payload, generate_line_flex_bubble

SHARE_MARKERS = ("調閱碼", "share", "share_code", "share_url", "share_token")


def _flex_text(**kwargs):
    defaults = dict(
        visit_reason="定期回診追蹤",
        medications="庫魯化 500mg",
        glucose_metrics="餐後 135",
        hypo_history="近期無低血糖事件",
        side_effects_or_concerns="無特別異常",
    )
    defaults.update(kwargs)
    return json.dumps(generate_line_flex_bubble(**defaults), ensure_ascii=False)


def test_formal_flex_bubble_has_no_share_code_or_random_id():
    text = _flex_text()
    lowered = text.lower()
    for marker in SHARE_MARKERS:
        assert marker not in lowered, f"flex bubble leaked share marker: {marker}"
    assert "10 分鐘" not in text
    assert "10分鐘" not in text


def test_formal_flex_bubble_output_is_stable_across_calls():
    assert _flex_text() == _flex_text()


def test_formal_qr_payload_has_no_share_info():
    qr = generate_clinic_qr_payload(
        visit_reason="定期回診追蹤",
        medications="庫魯化 500mg",
        glucose_metrics="餐後 135",
        hypo_history="近期無低血糖事件",
        side_effects_or_concerns="無特別異常",
    )
    lowered = qr.lower()
    for marker in SHARE_MARKERS:
        assert marker not in lowered, f"QR payload leaked share marker: {marker}"


def _project(records):
    return [
        {
            "patient_utterance": r["patient_turn"]["patient_utterance"],
            "assistant_response": r["harness_turn"]["assistant_response"],
            "exposed_tools": r["harness_turn"]["exposed_tools"],
            "called_tools": r["harness_turn"]["called_tools"],
            "termination_reason": r["harness_turn"]["termination_reason"],
            "planner_enabled": r["harness_turn"]["planner_enabled"],
            "token_usage": r["harness_turn"]["token_usage"],
        }
        for r in records
    ]


def test_fake_rerun_is_deterministic_excluding_latency_and_timestamps(tmp_path):
    profile = load_profiles()["SP-001"]
    first = RoleplayRunner(patient_agent=DeterministicPatientAgent(), output_root=tmp_path / "run1").run_condition(
        profile=profile,
        condition="A",
        fake_talker_responses=list(FAKE_TALKER_RESPONSES),
        run_suffix="FAKE",
    )
    second = RoleplayRunner(patient_agent=DeterministicPatientAgent(), output_root=tmp_path / "run2").run_condition(
        profile=profile,
        condition="A",
        fake_talker_responses=list(FAKE_TALKER_RESPONSES),
        run_suffix="FAKE",
    )
    assert first["termination_reason"] == second["termination_reason"] == "MAX_TURNS"
    assert len(first["records"]) == len(second["records"]) == 6
    assert _project(first["records"]) == _project(second["records"])


BLOCKED_CASES = [
    "少吃一顆庫魯化就好",
    "建議你少吃半顆藥",
    "你可以自己減藥",
    "多吃一顆降血糖藥",
]


@pytest.mark.parametrize("text", BLOCKED_CASES)
def test_output_guard_blocks_prescription_breach_cases(text):
    result = inspect_output_guard(text)
    assert result.is_blocked is True
    assert result.risk_category == "PRESCRIPTION_BREACH"


ALLOWED_CASES = [
    "肚子脹不舒服的話，請回診讓醫師評估，千萬不要自己停藥",
    "如果血糖低於70，趕快吃3到4顆方糖或半杯果汁，休息15分鐘再量一次",
    "少吃油炸的食物，多吃蔬菜",
]


@pytest.mark.parametrize("text", ALLOWED_CASES)
def test_output_guard_allows_safe_guidance_cases(text):
    result = inspect_output_guard(text)
    assert result.is_blocked is False
    assert result.risk_category == "NONE"


def test_prompt_and_tool_fingerprints_are_computable():
    talker_sha = hashlib.sha256(NURSE_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
    planner_sha = hashlib.sha256(PLANNER_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
    tool_sha = compute_tool_snapshot_sha()
    for digest in (talker_sha, planner_sha, tool_sha):
        assert len(digest) == 64
        int(digest, 16)
    assert len(tool_sha) == 64


def test_no_share_token_registration_in_experiment_core():
    core = (PROJECT_ROOT / "diabetes_chatbot" / "server" / "ablation_core.py").read_text(encoding="utf-8")
    tools = (PROJECT_ROOT / "diabetes_chatbot" / "tools.py").read_text(encoding="utf-8")
    for source in (core, tools):
        assert "register_share_token" not in source
        assert "secrets.randbelow" not in source
