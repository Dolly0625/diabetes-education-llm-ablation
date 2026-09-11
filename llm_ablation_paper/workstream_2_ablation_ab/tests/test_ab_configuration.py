"""Workstream 2: A/B Planner Ablation Rigorous Configuration & Invariant Tests.

Verifies:
1. Strict single-variable diff between A and B (enable_planner: False -> True).
2. All canonical tools fully exposed in both A and B.
3. Condition A: planner call count == 0, log uses neutral planner state, no guidance injected.
4. Condition B: executes planner and injects talker_guidance.
5. All unmodeled production assists and output guard fixed OFF for both A and B.
6. Condition B does not leak forced evidence despite retrieval domain classification.
7. Condition A persists facts via extraction, but does not persist planner assessment.
8. Offline fake trajectory execution complies with EXPERIMENT_CONTRACT schema without API calls.
"""
from __future__ import annotations

import copy
import json
import shutil
import tempfile
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from diabetes_chatbot.memory import load_patient_record
from diabetes_chatbot.planner import (
    ClinicalSlots,
    PlannerAssessment,
    RetrievalDomain,
    SlotStatus,
)
from llm_ablation_paper.workstream_1_technical_lead.harness.config import (
    AblationConfig,
    CONFIG_A,
    CONFIG_B,
    config_diff,
    formal_ablation_config,
)
from llm_ablation_paper.workstream_1_technical_lead.harness.isolation import (
    clear_session_cache,
    get_patient_file_for_state,
)
from llm_ablation_paper.workstream_1_technical_lead.harness.runner import (
    get_canonical_tool_snapshot,
    neutral_planner_state,
    run_ablation_turn,
    run_trajectory,
    to_contract_trajectory,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class FakeModelClient:
    """Deterministic, offline fake client for LLM calls that tracks invocations."""

    def __init__(self, reply_text: str = "您好，我是糖尿病衛教助理。"):
        self.reply_text = reply_text
        self.captured_messages: list[dict] | None = None
        self.captured_tools: list[dict] | None = None
        self.call_count: int = 0
        self.chat = MagicMock()
        self.chat.completions = MagicMock()
        self.chat.completions.create = MagicMock(side_effect=self._mock_create)

    def _mock_create(self, **kwargs: Any) -> Any:
        self.call_count += 1
        self.captured_messages = kwargs.get("messages")
        self.captured_tools = kwargs.get("tools")

        msg = MagicMock()
        msg.content = self.reply_text
        msg.tool_calls = None

        choice = MagicMock()
        choice.message = msg

        usage = MagicMock()
        usage.prompt_tokens = 42
        usage.completion_tokens = 18
        usage.total_tokens = 60

        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = usage
        return resp


@pytest.fixture
def temp_env():
    """Provides an isolated temp state dir and cleans up artifacts upon completion."""
    run_id = f"RUN-WS2-{uuid.uuid4().hex[:8]}"
    state_dir = Path(tempfile.mkdtemp(prefix=f"ws2_test_{run_id}_"))
    clear_session_cache()
    yield state_dir, run_id
    clear_session_cache()
    shutil.rmtree(state_dir, ignore_errors=True)
    # Clean any artifacts written to ws1 test directory
    ad = PROJECT_ROOT / "llm_ablation_paper" / "artifacts" / "workstream_1" / run_id
    if ad.exists() and PROJECT_ROOT in ad.parents:
        shutil.rmtree(ad, ignore_errors=True)


def test_ab_config_diff_exact_single_variable():
    """驗證 A 與 B 的組態差異僅有 enable_planner，絕無其他自變項。"""
    diff = config_diff(CONFIG_A, CONFIG_B)
    assert "enable_planner" in diff, "Diff must include enable_planner"
    assert diff["enable_planner"] == {"from": False, "to": True}

    # 除了 condition 標籤與 enable_planner 之外，不能有任何其他屬性差異
    non_label_diffs = {k: v for k, v in diff.items() if k not in ("condition", "enable_planner")}
    assert non_label_diffs == {}, f"Unexpected diffs found between A and B: {non_label_diffs}"

    # 驗證 A/B 配置工廠
    cfg_a = AblationConfig.for_condition("A")
    cfg_b = AblationConfig.for_condition("B")
    assert cfg_a.enable_planner is False
    assert cfg_b.enable_planner is True
    assert cfg_a.model == cfg_b.model
    assert cfg_a.temperature == cfg_b.temperature
    assert cfg_a.max_turns == cfg_b.max_turns


def test_formal_ablation_config_frozen_invariants():
    """驗證正式凍結組態 formal_ablation_config('A') 與 formal_ablation_config('B')：
    1. 除 condition 標籤外，唯一實驗開關差異只有 enable_planner。
    2. Talker 模型（gemini-3.5-flash-lite）、溫度（0.3）。
    3. Planner 模型（兩者均為凍結值 gemini-3.5-flash-lite）、溫度（0.1）、timeout（30.0 秒）。
    4. Patient Agent 模型（gemini-2.5-flash-lite）、溫度（0.3）。
    5. max_turns（6）、seed（42）與其他輔助開關均嚴格相同且固定為 OFF。
    """
    formal_a = formal_ablation_config("A")
    formal_b = formal_ablation_config("B")

    # 1. 組態差異嚴格僅有 condition 與 enable_planner
    diff = config_diff(formal_a, formal_b)
    assert "enable_planner" in diff
    assert diff["enable_planner"] == {"from": False, "to": True}
    non_label_diffs = {k: v for k, v in diff.items() if k not in ("condition", "enable_planner")}
    assert non_label_diffs == {}, f"Unexpected diffs in formal config: {non_label_diffs}"

    # 2. Talker 模型與溫度完全相同
    assert formal_a.model == formal_b.model == "gemini-3.5-flash-lite"
    assert formal_a.temperature == formal_b.temperature == 0.3

    # 3. Planner 模型（兩者均為凍結值）、溫度與 timeout 完全相同
    assert formal_a.planner_model == formal_b.planner_model == "gemini-3.5-flash-lite"
    assert formal_a.planner_temperature == formal_b.planner_temperature == 0.1
    assert formal_a.planner_request_timeout_seconds == formal_b.planner_request_timeout_seconds == 30.0

    # 4. Patient Agent 模型與溫度
    assert formal_a.patient_agent_model == formal_b.patient_agent_model == "gemini-2.5-flash-lite"
    assert formal_a.patient_agent_temperature == formal_b.patient_agent_temperature == 0.3

    # 5. 輪數、種子與輔助開關固定 OFF
    assert formal_a.max_turns == formal_b.max_turns == 6
    assert formal_a.seed == formal_b.seed == 42
    assert formal_a.enable_dynamic_tool_gate is False
    assert formal_b.enable_dynamic_tool_gate is False
    assert formal_a.enable_output_guard is False
    assert formal_b.enable_output_guard is False
    assert formal_a.enable_forced_retrieval is False
    assert formal_b.enable_forced_retrieval is False
    assert formal_a.enable_fixed_warning_append is False
    assert formal_b.enable_fixed_warning_append is False
    assert formal_a.enable_question_budget_postprocessing is False
    assert formal_b.enable_question_budget_postprocessing is False


def test_ab_production_assists_and_guards_fixed_off():
    """驗證 A 與 B 的動態閘門、輸出熔斷及各項生產輔助均嚴格固定為 OFF。"""
    for cfg in (CONFIG_A, CONFIG_B):
        assert cfg.enable_dynamic_tool_gate is False
        assert cfg.dynamic_tool_gate is False
        assert cfg.enable_output_guard is False
        assert cfg.enable_forced_retrieval is False
        assert cfg.enable_fixed_warning_append is False
        assert cfg.enable_noncompliance_append is False
        assert cfg.enable_question_budget_postprocessing is False
        assert cfg.enable_question_budget is False


def test_ab_canonical_tools_identical_and_fully_exposed(temp_env):
    """驗證 A 與 B 暴露給 Talker 的工具清單完全一致，且均為 Canonical Snapshot 全集。"""
    state_dir, run_id = temp_env
    canonical_snapshot = get_canonical_tool_snapshot()
    canonical_names = sorted([t["function"]["name"] for t in canonical_snapshot])
    assert canonical_names == ["generate_previsit_intake_summary", "search_handbook"]

    fake_client_a = FakeModelClient()
    result_a = run_ablation_turn(
        config=replace(CONFIG_A, run_id=f"{run_id}-A"),
        user_id="PATIENT_TOOL_TEST",
        patient_id="PATIENT_TOOL_TEST",
        message="請問糖尿病可以吃香蕉嗎？",
        state_dir=state_dir,
        model_client=fake_client_a,
        turn_index=0,
        run_id=f"{run_id}-A",
    )
    assert sorted(result_a["exposed_tools"]) == canonical_names
    assert len(fake_client_a.captured_tools) == len(canonical_snapshot)

    # 執行 Condition B
    state_dir_b = Path(tempfile.mkdtemp(prefix=f"ws2_b_{run_id}_"))
    try:
        fake_client_b = FakeModelClient()
        result_b = run_ablation_turn(
            config=replace(CONFIG_B, run_id=f"{run_id}-B"),
            user_id="PATIENT_TOOL_TEST",
            patient_id="PATIENT_TOOL_TEST",
            message="請問糖尿病可以吃香蕉嗎？",
            state_dir=state_dir_b,
            model_client=fake_client_b,
            turn_index=0,
            run_id=f"{run_id}-B",
        )
        assert sorted(result_b["exposed_tools"]) == canonical_names
        assert len(fake_client_b.captured_tools) == len(canonical_snapshot)

        # 兩組暴露工具結構必須完全相同
        assert result_a["exposed_tools"] == result_b["exposed_tools"]
    finally:
        shutil.rmtree(state_dir_b, ignore_errors=True)


def test_condition_a_planner_call_count_zero_and_neutral_state(temp_env):
    """驗證 Condition A 完全不呼叫 Planner LLM 與 fallback，日誌使用 neutral planner state。"""
    state_dir, run_id = temp_env
    fake_client = FakeModelClient()

    with patch(
        "diabetes_chatbot.server.ablation_core.evaluate_clinical_planner_llm"
    ) as mock_planner_llm, patch(
        "diabetes_chatbot.server.ablation_core.evaluate_clinical_planner"
    ) as mock_planner_fallback:

        result = run_ablation_turn(
            config=replace(CONFIG_A, run_id=run_id),
            user_id="PATIENT_A_NEUTRAL",
            patient_id="PATIENT_A_NEUTRAL",
            message="我最近常常覺得口渴，而且體重一直降。",
            state_dir=state_dir,
            model_client=fake_client,
            turn_index=0,
            run_id=run_id,
        )

        # 斷言 Planner LLM 與 fallback 完全未被調用（調用次數為 0）
        assert mock_planner_llm.call_count == 0
        assert mock_planner_fallback.call_count == 0

    # 斷言日誌中使用 neutral planner state
    planner_log = result["planner_result_or_neutral"]
    assert planner_log["engine"] == "neutral"
    assert planner_log["talker_guidance"] == ""
    assert planner_log["can_unlock_summary_tool"] is False
    assert planner_log["is_visit_mode"] is False
    assert planner_log["slots"]["visit_reason_status"] == "MISSING"

    # 斷言 Talker 上下文中沒有注入任何臨床溝通導引
    captured_messages = fake_client.captured_messages
    for m in captured_messages:
        content = m.get("content", "")
        assert "【臨床溝通導引】" not in content


def test_condition_b_executes_planner_and_injects_guidance(temp_env):
    """驗證 Condition B 正確執行 Planner，並能將 talker_guidance 注入 Talker 上下文。"""
    state_dir, run_id = temp_env
    fake_client = FakeModelClient()

    custom_guidance = "【臨床溝通導引】：病患主訴口渴多尿，請同理關心並引導說明空腹血糖量測紀錄。"
    mock_assessment = PlannerAssessment(
        slots=ClinicalSlots(),
        is_visit_mode=False,
        is_explicit_request=False,
        is_agenda_confirmed=False,
        can_unlock_summary_tool=False,
        retrieval_domain=RetrievalDomain.NONE,
        detected_intent="SYMPTOM_REPORT",
        talker_guidance=custom_guidance,
        engine="llm_mock",
    )

    with patch(
        "diabetes_chatbot.server.ablation_core.evaluate_clinical_planner_llm",
        return_value=mock_assessment,
    ) as mock_planner_llm:

        result = run_ablation_turn(
            config=replace(CONFIG_B, run_id=run_id),
            user_id="PATIENT_B_GUIDANCE",
            patient_id="PATIENT_B_GUIDANCE",
            message="我最近常常覺得口渴，而且體重一直降。",
            state_dir=state_dir,
            model_client=fake_client,
            turn_index=0,
            run_id=run_id,
        )

        assert mock_planner_llm.call_count >= 1

    # 驗證 Planner assessment 正確記錄
    assert result["planner_result_or_neutral"]["engine"] == "llm_mock"
    assert result["planner_result_or_neutral"]["talker_guidance"] == custom_guidance

    # 驗證 Talker context 成功注入導引
    system_messages = [
        m["content"] for m in fake_client.captured_messages if m.get("role") == "system"
    ]
    assert any(custom_guidance in sm for sm in system_messages)


def test_condition_b_retrieval_domain_does_not_leak_forced_evidence(temp_env):
    """驗證 Condition B 即使 Planner 判斷出特定檢索領域，在 enable_forced_retrieval=False 下絕不注入強制證據。"""
    state_dir, run_id = temp_env
    fake_client = FakeModelClient()

    # 模擬 Planner 判定出 DRUG_SAFETY 領域
    mock_assessment = PlannerAssessment(
        slots=ClinicalSlots(),
        is_visit_mode=False,
        is_explicit_request=False,
        is_agenda_confirmed=False,
        can_unlock_summary_tool=False,
        retrieval_domain=RetrievalDomain.DRUG_SAFETY,
        detected_intent="DRUG_INQUIRY",
        talker_guidance="【臨床溝通導引】：請向病患解說常見藥物副作用，切勿擅自停藥。",
        engine="llm_mock",
    )

    with patch(
        "diabetes_chatbot.server.ablation_core.evaluate_clinical_planner_llm",
        return_value=mock_assessment,
    ), patch(
        "diabetes_chatbot.server.ablation_core.search_handbook"
    ) as mock_search_handbook:

        result = run_ablation_turn(
            config=replace(CONFIG_B, run_id=run_id),
            user_id="PATIENT_B_LEAK_CHECK",
            patient_id="PATIENT_B_LEAK_CHECK",
            message="我吃了降血糖藥肚子很不舒服，我想直接停藥可以嗎？",
            state_dir=state_dir,
            model_client=fake_client,
            turn_index=0,
            run_id=run_id,
        )

        # 斷言強制檢索未被執行
        assert mock_search_handbook.call_count == 0

    # 斷言 Talker 上下文中沒有任何強制檢索任務導引
    for m in fake_client.captured_messages:
        c = m.get("content", "")
        assert "【官方實證藥物衛教解說任務" not in c
        assert "【官方手冊飲食原則衛教任務" not in c

    # 斷言 search_handbook 依然留在暴露工具清單中，未被不當移除
    assert "search_handbook" in result["exposed_tools"]


def test_condition_a_persists_facts_but_not_planner_assessment(temp_env):
    """精確驗證：Condition A 照常持久化病患事實抽取，但絕不持久化 Planner Assessment 結構化槽位。"""
    state_dir, run_id = temp_env
    fake_client = FakeModelClient()
    patient_id = "PATIENT_FACTS_A"

    # 發送包含血糖明確數值的對話
    result_a = run_ablation_turn(
        config=replace(CONFIG_A, run_id=f"{run_id}-A"),
        user_id=patient_id,
        patient_id=patient_id,
        message="護理師好，我今天早上量空腹血糖數值是 195，有偏高嗎？",
        state_dir=state_dir,
        model_client=fake_client,
        turn_index=0,
        run_id=f"{run_id}-A",
    )

    # 檢查病患紀錄 JSON
    patient_file = get_patient_file_for_state(state_dir, patient_id)
    rec = load_patient_record(patient_file)

    # 1. 事實抽取照常運行：A 並非完全不持久化任何狀態
    assert "glucose_metrics" in rec
    assert rec["glucose_metrics"]["latest"] == "195 mg/dL"

    # 2. 但 A 完全沒有持久化 Planner assessment 槽位
    previsit_summary = rec.get("previsit_summary", {})
    # Condition A 中 previsit_summary 槽位應未被 planner assessment 更新
    assert previsit_summary.get("glucose_metrics") in (None, "")


def test_ab_offline_fake_trajectory_contract_compliance(temp_env):
    """驗證 Condition A 與 B 的多輪軌跡離線執行符合 EXPERIMENT_CONTRACT 最低 schema。"""
    state_dir, run_id = temp_env
    fake_client = FakeModelClient(reply_text="收到您的問題，我們會持續關心您的血糖狀況。")

    messages = [
        "你好，我剛被診斷出糖尿病，想了解飲食原則。",
        "那水果的部分每天可以吃多少？",
    ]

    for cond, base_cfg in [("A", CONFIG_A), ("B", CONFIG_B)]:
        cond_run_id = f"{run_id}-{cond}"
        cfg = replace(base_cfg, run_id=cond_run_id)
        traj_dir = state_dir / f"traj_{cond}"
        traj_dir.mkdir(parents=True, exist_ok=True)
        clear_session_cache()

        turns = run_trajectory(
            config=cfg,
            patient_id=f"SP-001-{cond}",
            messages=messages,
            state_dir=traj_dir,
            model_client=fake_client,
            run_id=cond_run_id,
        )

        assert len(turns) == 2

        contract_traj = to_contract_trajectory(
            run_id=cond_run_id,
            state_dir=traj_dir,
        )

        # 驗證最低合約 Schema 欄位
        assert contract_traj["run_id"] == cond_run_id
        assert contract_traj["condition_secret"] == cond
        assert contract_traj["patient_id"] == f"SP-001-{cond}"
        assert contract_traj["model"] == cfg.model
        assert contract_traj["temperature"] == cfg.temperature
        assert "started_at" in contract_traj
        assert len(contract_traj["turns"]) == 2

        for t in contract_traj["turns"]:
            assert "turn" in t
            assert "patient_text" in t
            assert "planner_state" in t
            assert "tools_exposed" in t
            assert "tools_called" in t
            assert "raw_talker_output" in t
            assert "guard_action" in t
            assert "final_output" in t
            assert "latency_ms" in t
            assert "token_usage" in t

            # 驗證 A/B 工具暴露一致
            assert sorted(t["tools_exposed"]) == ["generate_previsit_intake_summary", "search_handbook"]

            # 驗證 A 組 planner_state 為 neutral
            if cond == "A":
                assert t["planner_state"]["engine"] == "neutral"
                assert t["planner_state"]["talker_guidance"] == ""
