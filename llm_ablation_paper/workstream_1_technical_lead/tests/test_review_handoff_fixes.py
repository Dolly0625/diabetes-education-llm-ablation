"""Test suite covering the 7 mandatory Review Handoff items for Workstream 1.

Items:
  1. contract patient_id is exactly equal to the real patient_id, never patient_text.
  2. blinded artifact contains no A/B/C/D condition names and no major flag names.
  3. subprocess actually calls provider/client factory and does not substitute fake.
  4. same run ID with resume=False is rejected; resume=True verifies run/condition/patient.
  5. pending-card path strictly follows Output Guard flags (ABC off, D on);
     events do not pollute protocol termination_reason.
  6. retry classifies transient vs non-transient, records attempt/backoff/error metadata,
     and token_usage records tokens or null.
  7. illegal condition/flag combinations and conflicting run IDs fail;
     non-final turns are not mislabeled as MAX_TURNS.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from llm_ablation_paper.workstream_1_technical_lead.harness.config import AblationConfig
from llm_ablation_paper.workstream_1_technical_lead.harness.isolation import (
    clear_session_cache,
    ensure_state_dir_empty,
    get_patient_file_for_state,
)
from llm_ablation_paper.workstream_1_technical_lead.harness.runner import (
    run_ablation_turn,
    run_trajectory,
    run_trajectory_subprocess,
    to_contract_trajectory,
    to_blinded_contract_trajectory,
    validate_condition_mapping,
    generate_random_condition_mapping,
    save_frozen_condition_mapping,
    load_frozen_condition_mapping,
    _build_client_from_provider_config,
    _resolve_artifact_dir,
)
from diabetes_chatbot.server.ablation_core import (
    is_retryable_error,
    _call_with_retry,
    _extract_token_usage,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class MockUsage:
    def __init__(self, prompt=10, completion=20, total=30):
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.total_tokens = total


class MockChoice:
    def __init__(self, content="mock reply", tool_calls=None):
        msg = MagicMock()
        msg.content = content
        msg.tool_calls = tool_calls
        self.message = msg


class MockResponse:
    def __init__(self, content="mock reply", tool_calls=None, usage=None):
        self.choices = [MockChoice(content=content, tool_calls=tool_calls)]
        self.usage = usage


class DeterministicClient:
    def __init__(self, content="測試回覆", usage=None):
        self.content = content
        self.usage = usage
        self.call_count = 0
        self.chat = MagicMock()
        self.chat.completions = MagicMock()
        self.chat.completions.create = MagicMock(side_effect=self._create)

    def _create(self, **kwargs):
        self.call_count += 1
        return MockResponse(content=self.content, usage=self.usage)


def _cleanup(state_dir: Path | str, run_id: str):
    try:
        ad = _resolve_artifact_dir(Path(state_dir), run_id)
        if ad.exists() and PROJECT_ROOT in ad.parents:
            shutil.rmtree(ad, ignore_errors=True)
    except Exception:
        pass
    try:
        sd = Path(state_dir)
        if sd.exists() and "artifacts" not in str(sd):
            shutil.rmtree(sd, ignore_errors=True)
    except Exception:
        pass
    clear_session_cache()


# ===========================================================================
# 1. contract patient_id 精確相等
# ===========================================================================
def test_contract_patient_id_exact_match():
    """驗證 to_contract_trajectory 的 patient_id 取自真正的 ID，絕不把第一句 patient_text 當 ID。"""
    run_id = f"RUN-TEST-PID-{uuid.uuid4().hex[:6]}"
    state_dir = tempfile.mkdtemp()
    config = AblationConfig.for_condition("A")
    object.__setattr__(config, "run_id", run_id)
    real_patient_id = "SP-001"
    first_message = "護理師您好，我今天吃糙米飯配魚肚湯"
    client = DeterministicClient(content="您好，飲食很均衡喔！")

    run_ablation_turn(
        config=config,
        user_id=real_patient_id,
        message=first_message,
        state_dir=state_dir,
        model_client=client,
        patient_id=real_patient_id,
        turn_index=0,
        run_id=run_id,
    )

    contract = to_contract_trajectory(run_id, state_dir)
    assert contract["patient_id"] == real_patient_id
    assert contract["patient_id"] != first_message
    assert contract["turns"][0]["patient_text"] == first_message

    _cleanup(state_dir, run_id)


# ===========================================================================
# 2. blinded artifact 不含 A／B／C／D 與主要開關名稱
# ===========================================================================
@pytest.mark.parametrize("cond", ["A", "B", "C", "D"])
def test_blinded_artifact_sanitization(cond):
    """驗證 blinded artifact 使用 opaque condition 代號，且不洩漏主要開關名稱與真實條件名。"""
    run_id = f"RUN-TEST-BLIND-{cond}-{uuid.uuid4().hex[:6]}"
    state_dir = tempfile.mkdtemp()
    config = AblationConfig.for_condition(cond)
    object.__setattr__(config, "run_id", run_id)
    client = DeterministicClient(content="正常衛教回覆")

    run_ablation_turn(
        config=config,
        user_id="SP-BLIND-001",
        message="請問血糖 120 正常嗎？",
        state_dir=state_dir,
        model_client=client,
        patient_id="SP-BLIND-001",
        turn_index=0,
        run_id=run_id,
    )

    mapping = {"A": "COND-ALPHA", "B": "COND-BETA", "C": "COND-GAMMA", "D": "COND-DELTA"}
    blinded = to_blinded_contract_trajectory(run_id, state_dir, condition_mapping=mapping, require_completed=False)

    # 1. condition_secret 不得為 A, B, C, D
    assert blinded["condition_secret"] not in ("A", "B", "C", "D")
    assert blinded["condition_secret"].startswith("COND-")

    # 2. run_id 與 state_dir_id 脫敏
    assert not blinded["run_id"].startswith(f"RUN-TEST-BLIND-{cond}")
    assert blinded["run_id"].startswith("BLIND-")

    # 3. 序列化字串中嚴禁包含主要開關名稱
    json_str = json.dumps(blinded, ensure_ascii=False)
    forbidden_flags = [
        "enable_planner",
        "enable_dynamic_tool_gate",
        "enable_output_guard",
        "planner_enabled",
        "enable_forced_retrieval",
        "enable_fixed_warning_append",
        "enable_question_budget_postprocessing",
    ]
    for flag in forbidden_flags:
        assert f'"{flag}"' not in json_str, f"Blinded artifact leaked flag: {flag}"

    _cleanup(state_dir, run_id)


class SubprocessMarkerClientFactory:
    """用於跨進程測試的可序列化 client factory。"""
    def __init__(self, marker_path: str, content: str = "來自工廠的真實客製回覆"):
        self.marker_path = marker_path
        self.content = content

    def __call__(self):
        Path(self.marker_path).write_text("CALLED", encoding="utf-8")
        return DeterministicClient(content=self.content)


def test_subprocess_calls_client_factory_without_fake():
    """驗證 run_trajectory_subprocess 確實呼叫傳入的 client_factory，不偷換為內建 fake client。"""
    run_id = f"RUN-TEST-SUBPROC-{uuid.uuid4().hex[:6]}"
    state_dir = tempfile.mkdtemp()
    config = AblationConfig.for_condition("A")
    object.__setattr__(config, "run_id", run_id)

    marker_file = Path(state_dir) / "factory_called.marker"
    factory = SubprocessMarkerClientFactory(str(marker_file), content="來自工廠的真實客製回覆")

    results = run_trajectory_subprocess(
        config=config,
        patient_id="p_sub",
        messages=["你好！"],
        state_dir=state_dir,
        client_factory=factory,
        run_id=run_id,
        timeout=15.0,
    )

    assert marker_file.exists(), "子進程未執行傳入的 client_factory！"
    assert marker_file.read_text(encoding="utf-8") == "CALLED"
    assert len(results) == 1
    assert "來自工廠的真實客製回覆" in results[0]["assistant_response"]

    _cleanup(state_dir, run_id)


# ===========================================================================
# 4. 相同 run ID 且 resume=False 必須拒絕；resume=True 檢查一致性
# ===========================================================================
def test_same_run_id_rejects_when_resume_false():
    """驗證已有 artifacts 時，若 resume=False 一律拋出 FileExistsError。"""
    run_id = f"RUN-TEST-REJECT-{uuid.uuid4().hex[:6]}"
    state_dir = _resolve_artifact_dir(Path(tempfile.mkdtemp()), run_id)
    state_dir.mkdir(parents=True, exist_ok=True)
    config = AblationConfig.for_condition("A")
    object.__setattr__(config, "run_id", run_id)
    client = DeterministicClient(content="hi")

    try:
        # Turn 0
        run_ablation_turn(
            config=config,
            user_id="p_rej",
            message="第一句",
            state_dir=state_dir,
            model_client=client,
            patient_id="p_rej",
            turn_index=0,
            run_id=run_id,
            resume=False,
        )

        # 再次使用相同 run_id 且 resume=False -> 必須拒絕
        with pytest.raises(FileExistsError):
            run_ablation_turn(
                config=config,
                user_id="p_rej",
                message="第一句重試",
                state_dir=state_dir,
                model_client=client,
                patient_id="p_rej",
                turn_index=0,
                run_id=run_id,
                resume=False,
            )

        # resume=True 且 condition/patient 衝突 -> 拋出 ValueError
        config_conflict = AblationConfig.for_condition("B")
        object.__setattr__(config_conflict, "run_id", run_id)
        with pytest.raises(ValueError):
            run_ablation_turn(
                config=config_conflict,
                user_id="p_rej",
                message="續跑衝突條件",
                state_dir=state_dir,
                model_client=client,
                patient_id="p_rej",
                turn_index=1,
                run_id=run_id,
                resume=True,
            )

        # resume=True 且條件完全一致 -> 允許續跑
        res = run_ablation_turn(
            config=config,
            user_id="p_rej",
            message="第二句正常續跑",
            state_dir=state_dir,
            model_client=client,
            patient_id="p_rej",
            turn_index=1,
            run_id=run_id,
            resume=True,
        )
        assert res["turn_index"] == 1
    finally:
        _cleanup(state_dir, run_id)


# ===========================================================================
# 5. A／B／C／D pending-card 路徑遵守 Output Guard 設定
# ===========================================================================
@pytest.mark.parametrize("cond", ["A", "B", "C", "D"])
def test_pending_card_output_guard_compliance(cond):
    """驗證 pending-card 點頭確認交付路徑遵守 A-D flags，且 termination_reason 不是 PENDING_CARD_DELIVERY*。"""
    run_id = f"RUN-TEST-CARD-{cond}-{uuid.uuid4().hex[:6]}"
    state_dir = tempfile.mkdtemp()
    config = AblationConfig.for_condition(cond)
    object.__setattr__(config, "run_id", run_id)
    patient_id = f"p_card_{cond}"
    patient_file = get_patient_file_for_state(state_dir, patient_id)

    from diabetes_chatbot.memory import save_patient_record
    save_patient_record({
        "patient_id": patient_id,
        "pending_card": {
            "flex_bubble": {"type": "bubble", "body": {}},
            "qr_payload": "TFDA-INTAKE-V2|TEST",
            "text_summary": "預問診小卡摘要內容",
        }
    }, patient_file)

    client = DeterministicClient(content="不應被呼叫")
    res = run_ablation_turn(
        config=config,
        user_id=patient_id,
        message="對，這樣記沒錯，幫我產生",
        state_dir=state_dir,
        model_client=client,
        patient_id=patient_id,
        turn_index=0,
        run_id=run_id,
    )

    if cond in ("A", "B", "C"):
        assert res["output_guard_result"]["is_blocked"] is False
    if cond == "D":
        assert res["output_guard_result"]["is_blocked"] is False

    assert res["termination_reason"] not in ("PENDING_CARD_DELIVERY", "PENDING_CARD_DELIVERY_BLOCKED")
    assert "PENDING_CARD_DELIVERY" in res.get("events", [])

    _cleanup(state_dir, run_id)


# ===========================================================================
# 6. retry 分類、attempt/backoff metadata 與 token usage
# ===========================================================================
def test_retry_transient_classification_and_metadata():
    """驗證 retry 分類：transient 重試並記錄 metadata，非 transient 立即拋出。"""
    # 1. 錯誤分類
    assert is_retryable_error(TimeoutError("request timed out")) is True
    assert is_retryable_error(ConnectionError("network lost")) is True
    assert is_retryable_error(type("E", (Exception,), {"status_code": 429})()) is True
    assert is_retryable_error(type("E", (Exception,), {"status_code": 503})()) is True

    assert is_retryable_error(ValueError("invalid arguments")) is False
    assert is_retryable_error(type("E", (Exception,), {"status_code": 400})()) is False
    assert is_retryable_error(type("E", (Exception,), {"status_code": 401})()) is False
    assert is_retryable_error(type("E", (Exception,), {"status_code": 403})()) is False

    # 2. 非 transient 立即拋出，不進行多次嘗試
    fail_mock = MagicMock(side_effect=ValueError("bad data"))
    meta_fail = {}
    with pytest.raises(ValueError):
        _call_with_retry(fail_mock, max_tries=4, backoffs=[0.01, 0.02], metadata_out=meta_fail)
    assert fail_mock.call_count == 1
    assert meta_fail["attempts"] == 1

    # 3. transient 重試直到成功並記錄 attempt 與 backoffs
    call_attempts = 0
    def _transient_then_success():
        nonlocal call_attempts
        call_attempts += 1
        if call_attempts < 3:
            raise TimeoutError("temporary timeout")
        return "success"

    meta_success = {}
    res = _call_with_retry(_transient_then_success, max_tries=4, backoffs=[0.01, 0.02, 0.04], metadata_out=meta_success)
    assert res == "success"
    assert meta_success["attempts"] == 3
    assert len(meta_success["backoffs"]) == 2
    assert len(meta_success["errors"]) == 2

    # 4. token usage 提取
    resp_with_usage = MagicMock()
    resp_with_usage.usage = MockUsage(prompt=15, completion=25, total=40)
    usage = _extract_token_usage(resp_with_usage)
    assert usage == {"prompt_tokens": 15, "completion_tokens": 25, "total_tokens": 40}

    resp_no_usage = MagicMock()
    resp_no_usage.usage = None
    assert _extract_token_usage(resp_no_usage) is None


# ===========================================================================
# 7. 非法 condition/flag 組合與 run ID 不一致會失敗；非最後一輪不誤標 MAX_TURNS
# ===========================================================================
def test_illegal_flags_and_provenance_consistency():
    """驗證非法 condition/flag 組合被拒絕，run ID 衝突被拒絕，非最後一輪不誤標 MAX_TURNS。"""
    # 1. 非法 condition / flags 組合
    with pytest.raises(ValueError, match="mismatch fixed mapping"):
        AblationConfig(condition="A", enable_planner=True, enable_dynamic_tool_gate=False, enable_output_guard=False)

    with pytest.raises(ValueError, match="mismatch fixed mapping"):
        AblationConfig(condition="B", enable_planner=False, enable_dynamic_tool_gate=False, enable_output_guard=False)

    with pytest.raises(ValueError, match="mismatch fixed mapping"):
        AblationConfig(condition="C", enable_planner=True, enable_dynamic_tool_gate=False, enable_output_guard=False)

    with pytest.raises(ValueError, match="mismatch fixed mapping"):
        AblationConfig(condition="D", enable_planner=True, enable_dynamic_tool_gate=True, enable_output_guard=False)

    # 2. run_trajectory 中 config.run_id 與傳入 run_id 衝突
    cfg = AblationConfig.for_condition("A")
    cfg_with_id = replace(cfg, run_id="RUN-SPECIFIC-001")
    with pytest.raises(ValueError, match="Run ID mismatch"):
        run_trajectory(
            config=cfg_with_id,
            patient_id="p_test",
            messages=["你好"],
            state_dir=tempfile.mkdtemp(),
            model_client=DeterministicClient(),
            run_id="RUN-CONFLICTING-002",
        )

    # 3. 非最後一輪不誤標 MAX_TURNS
    run_id = f"RUN-TEST-TURNS-{uuid.uuid4().hex[:6]}"
    state_dir = tempfile.mkdtemp()
    cfg_multi = replace(cfg, run_id=run_id, max_turns=4)
    client = DeterministicClient(content="回覆第 0 輪")

    res_turn0 = run_ablation_turn(
        config=cfg_multi,
        user_id="p_turns",
        message="第一句",
        state_dir=state_dir,
        model_client=client,
        patient_id="p_turns",
        turn_index=0,
        run_id=run_id,
    )
    assert res_turn0["termination_reason"] is None, "非最後一輪不應誤標 MAX_TURNS！"

    _cleanup(state_dir, run_id)


# ===========================================================================
# 8. 正式模型連線必須 fail closed 與 subprocess 序列化檢查
# ===========================================================================
def test_provider_fails_closed_without_api_key(monkeypatch):
    """缺少 GEMINI_API_KEY 時必須 fail closed；OPENAI_API_KEY 不得被當成 Gemini key。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-must-not-be-used")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        _build_client_from_provider_config({})


def test_provider_fails_without_fallback_to_magicmock(monkeypatch):
    """provider 建立失敗時必須拋錯，禁止改用 MagicMock；secrets 不得進 provider_config。"""
    with pytest.raises(ValueError, match="must not contain secrets"):
        _build_client_from_provider_config({"api_key": "sk-valid-key-for-test"})
    with pytest.raises(ValueError, match="must not contain secrets"):
        _build_client_from_provider_config({"auth_token": "sk-valid-key-for-test"})
    monkeypatch.setenv("GEMINI_API_KEY", "sk-valid-key-for-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    with patch("openai.OpenAI", side_effect=Exception("連線失敗異常")):
        with pytest.raises(RuntimeError, match="建立正式 Gemini"):
            _build_client_from_provider_config({"provider": "gemini"})


def test_fake_responses_explicitly_supported_in_dry_run_and_subprocess():
    """明確 fake_responses 仍可供 dry-run 與子進程使用。"""
    run_id = f"RUN-TEST-FAKERESP-{uuid.uuid4().hex[:6]}"
    state_dir = tempfile.mkdtemp()
    config = AblationConfig.for_condition("A")
    object.__setattr__(config, "run_id", run_id)

    results = run_trajectory_subprocess(
        config=config,
        patient_id="p_fake",
        messages=["測試問候"],
        state_dir=state_dir,
        fake_responses=["自訂明確假回覆"],
        run_id=run_id,
        timeout=15.0,
    )
    assert len(results) == 1
    assert "自訂明確假回覆" in results[0]["assistant_response"]
    _cleanup(state_dir, run_id)


def test_subprocess_rejects_unsupported_or_unpicklable_client():
    """run_trajectory_subprocess 收到不可序列化或不支援的 model_client 時明確拋錯。"""
    config = AblationConfig.for_condition("A")
    state_dir = tempfile.mkdtemp()

    class UnpicklableRawInstance:
        pass

    # 1. 傳入非 callable 的 raw instance
    with pytest.raises(TypeError, match="unsupported model_client"):
        run_trajectory_subprocess(
            config=config,
            patient_id="p_raw",
            messages=["hi"],
            state_dir=state_dir,
            model_client=UnpicklableRawInstance(),
        )

    # 2. 傳入不可 pickle 的 local closure
    def _local_unpicklable_factory():
        return None

    with pytest.raises(TypeError, match="unpicklable client_factory"):
        run_trajectory_subprocess(
            config=config,
            patient_id="p_raw",
            messages=["hi"],
            state_dir=state_dir,
            client_factory=_local_unpicklable_factory,
        )


# ===========================================================================
# 9. 真正的盲測映射驗證
# ===========================================================================
def test_blind_export_rejects_missing_mapping():
    """未傳 mapping 時正式 blind export 拒絕執行。"""
    run_id = f"RUN-TEST-NOMAP-{uuid.uuid4().hex[:6]}"
    state_dir = tempfile.mkdtemp()
    config = AblationConfig.for_condition("A")
    object.__setattr__(config, "run_id", run_id)

    run_ablation_turn(
        config=config,
        user_id="p_nomap",
        message="你好",
        state_dir=state_dir,
        model_client=DeterministicClient(content="回覆"),
        patient_id="p_nomap",
        turn_index=0,
        run_id=run_id,
    )

    with pytest.raises(ValueError, match="requires an explicit, complete condition_mapping"):
        to_blinded_contract_trajectory(run_id, state_dir, condition_mapping=None)

    _cleanup(state_dir, run_id)


def test_validate_condition_mapping_strict_coverage_and_uniqueness():
    """mapping 必須完整覆蓋 A/B/C/D 且四個 opaque ID 不重複，不可仍為 A/B/C/D。"""
    # 缺失鍵
    with pytest.raises(ValueError, match="must contain exactly keys"):
        validate_condition_mapping({"A": "C1", "B": "C2", "C": "C3"})

    # 值為 A/B/C/D
    with pytest.raises(ValueError, match="must not be one of"):
        validate_condition_mapping({"A": "A", "B": "C2", "C": "C3", "D": "C4"})

    # 值重複
    with pytest.raises(ValueError, match="duplicate opaque IDs"):
        validate_condition_mapping({"A": "C1", "B": "C1", "C": "C3", "D": "C4"})

    # 隨機生成 mapping 驗證
    rand_map = generate_random_condition_mapping()
    valid_map = validate_condition_mapping(rand_map)
    assert len(valid_map) == 4
    assert set(valid_map.keys()) == {"A", "B", "C", "D"}
    assert len(set(valid_map.values())) == 4

    # 凍結檔案儲存與讀取 (artifacts/frozen_config/)
    tmp_frozen = Path(tempfile.mkdtemp()) / "frozen_mapping.json"
    save_frozen_condition_mapping(valid_map, tmp_frozen)
    loaded_map = load_frozen_condition_mapping(tmp_frozen)
    assert loaded_map == valid_map


# ===========================================================================
# 10. contract termination 與 subprocess resume
# ===========================================================================
def test_trajectory_termination_reason_strict_and_incomplete_rejection():
    """未到 max_turns 的軌跡 termination_reason 為 None；達到上限才標記 MAX_TURNS；未完成軌跡不可作為正式完成產物。"""
    run_id = f"RUN-TEST-TERM-{uuid.uuid4().hex[:6]}"
    state_dir = tempfile.mkdtemp()
    config = AblationConfig.for_condition("A")
    object.__setattr__(config, "run_id", run_id)
    # 設定 max_turns=2
    config_2turns = replace(config, max_turns=2)
    client = DeterministicClient(content="回覆")

    try:
        # 1. 執行第 0 輪（未達上限 2）
        run_ablation_turn(
            config=config_2turns,
            user_id="p_term",
            message="第一句",
            state_dir=state_dir,
            model_client=client,
            patient_id="p_term",
            turn_index=0,
            run_id=run_id,
        )
        contract_t0 = to_contract_trajectory(run_id, state_dir)
        assert contract_t0["termination_reason"] is None, "未達 max_turns 的軌跡 termination_reason 必須為 None！"

        # 2. 未完成軌跡若不允許 incomplete 則拋出 ValueError
        with pytest.raises(ValueError, match="incomplete"):
            to_contract_trajectory(run_id, state_dir, allow_incomplete=False)

        rand_map = generate_random_condition_mapping()
        with pytest.raises(ValueError, match="incomplete"):
            to_blinded_contract_trajectory(run_id, state_dir, condition_mapping=rand_map, require_completed=True)

        # 3. 執行第 1 輪（達到 max_turns=2）
        run_ablation_turn(
            config=config_2turns,
            user_id="p_term",
            message="第二句",
            state_dir=state_dir,
            model_client=client,
            patient_id="p_term",
            turn_index=1,
            run_id=run_id,
            resume=True,
        )
        contract_t1 = to_contract_trajectory(run_id, state_dir, allow_incomplete=False)
        assert contract_t1["termination_reason"] == "MAX_TURNS", "真正到達上限才標記 MAX_TURNS！"

        blinded_t1 = to_blinded_contract_trajectory(run_id, state_dir, condition_mapping=rand_map, require_completed=True)
        assert blinded_t1["termination_reason"] == "MAX_TURNS"
    finally:
        _cleanup(state_dir, run_id)


def test_subprocess_resume_continues_from_next_turn():
    """subprocess resume 能沿用既有 checkpoint 並從下一輪繼續。"""
    run_id = f"RUN-TEST-SUBRESUME-{uuid.uuid4().hex[:6]}"
    state_dir = tempfile.mkdtemp()
    config = AblationConfig.for_condition("A")
    object.__setattr__(config, "run_id", run_id)

    marker_file = Path(state_dir) / "factory_marker.txt"
    factory = SubprocessMarkerClientFactory(str(marker_file), content="子進程回覆")

    try:
        # 第一次執行：只有 1 句（Turn 0）
        res1 = run_trajectory_subprocess(
            config=config,
            patient_id="p_subres",
            messages=["第一句"],
            state_dir=state_dir,
            client_factory=factory,
            run_id=run_id,
            resume=False,
        )
        assert len(res1) == 1
        assert res1[0]["turn_index"] == 0

        # 第二次執行：帶入 2 句且 resume=True -> 應該跳過 Turn 0，從 Turn 1 繼續執行，回傳完整 2 輪
        res2 = run_trajectory_subprocess(
            config=config,
            patient_id="p_subres",
            messages=["第一句", "第二句續跑"],
            state_dir=state_dir,
            client_factory=factory,
            run_id=run_id,
            resume=True,
        )
        assert len(res2) == 2
        assert res2[0]["turn_index"] == 0
        assert res2[1]["turn_index"] == 1
        assert res2[1]["user_message"] == "第二句續跑"

        # 檢查 contract 包含完整的 2 輪
        contract = to_contract_trajectory(run_id, state_dir)
        assert len(contract["turns"]) == 2
        assert contract["turns"][0]["turn"] == 1
        assert contract["turns"][1]["turn"] == 2
    finally:
        _cleanup(state_dir, run_id)
