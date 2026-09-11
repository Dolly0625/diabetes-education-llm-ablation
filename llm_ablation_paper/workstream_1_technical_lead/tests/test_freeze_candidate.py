"""Freeze-candidate regression tests: share-free experiment outputs, rerun determinism,
new Output Guard cases, and fingerprint equality with the candidate manifest."""
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
)
from diabetes_chatbot.guard import inspect_output_guard
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


def _manifest_fingerprints():
    manifest_path = (
        PROJECT_ROOT
        / "llm_ablation_paper"
        / "workstream_1_technical_lead"
        / "FREEZE_CANDIDATE_MANIFEST.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return manifest, manifest["fingerprints_sha256"]


def test_fingerprints_match_manifest_exactly():
    from llm_ablation_paper.workstream_1_technical_lead.harness.fingerprints import (
        canonical_tool_schema_sha256,
        planner_system_prompt_sha256,
        talker_base_prompt_sha256,
        talker_prompt_template_bundle_sha256,
    )

    manifest, fingerprints = _manifest_fingerprints()

    assert fingerprints["talker_base_prompt_sha256"] == talker_base_prompt_sha256()
    assert fingerprints["talker_prompt_template_bundle_sha256"] == talker_prompt_template_bundle_sha256()
    assert fingerprints["planner_system_prompt_sha256"] == planner_system_prompt_sha256()
    assert fingerprints["canonical_tool_schema_sha256"] == canonical_tool_schema_sha256()
    assert talker_prompt_template_bundle_sha256() != talker_base_prompt_sha256()
    assert manifest["status"] == "READY_FOR_FINAL_REVIEW"
    assert manifest["final_frozen"] is False
    assert manifest["experiment_ready"] is False
    assert manifest["formal_experiment_state"] == "BLOCKED"


def test_talker_bundle_fingerprint_is_independent_of_patient_context_value():
    from llm_ablation_paper.workstream_1_technical_lead.harness.fingerprints import (
        talker_prompt_template_bundle_sha256,
    )
    from diabetes_chatbot.prompts import build_nurse_system_prompt

    before = talker_prompt_template_bundle_sha256()
    build_nurse_system_prompt("虛構病患背景：飯後血糖 135，服用庫魯化")
    assert talker_prompt_template_bundle_sha256() == before


def test_no_share_token_registration_in_experiment_core():
    core = (PROJECT_ROOT / "diabetes_chatbot" / "server" / "ablation_core.py").read_text(encoding="utf-8")
    tools = (PROJECT_ROOT / "diabetes_chatbot" / "tools.py").read_text(encoding="utf-8")
    for source in (core, tools):
        assert "register_share_token" not in source
        assert "secrets.randbelow" not in source
