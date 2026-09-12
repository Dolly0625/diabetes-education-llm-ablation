"""WS1 受控正式實驗控制器 (Formal Experiment Controller) 離線測試套件.

嚴格遵守研究協議與分層消融防線：
1. 完全離線，0 外部 API 呼叫，不消耗任何付費 Token。
2. 完整覆蓋六大 Preflight 門禁、Batch 48 條計數驗證、Mapping 原子生成與 Blind Export 洩漏掃描。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from llm_ablation_paper.workstream_1_technical_lead.scripts.run_formal_experiment import (
    CONFIRM_FORMAL_12X4_RUN_STRING,
    DEFAULT_PILOT_PATIENT_ID,
    build_parser,
    check_12_profiles_validator,
    check_clean_working_tree,
    check_distinct_output_roots,
    check_frozen_config_and_envelope,
    check_pilot_completed_cleanly,
    generate_frozen_mapping,
    main,
    run_batch,
    run_blind_export,
    run_pilot,
    scan_blinded_payload_for_leakage,
)


# =====================================================================
# 輔助函式：建立測試用假 Pilot Summary
# =====================================================================
def _create_mock_pilot_summary(
    target_path: Path,
    *,
    conditions: tuple[str, ...] = ("A", "B", "C", "D"),
    termination_reason: str = "PATIENT_GOAL_MET",
    include_error: bool = False,
    error_condition: str = "B",
    custom_reasons: dict[str, str] | None = None,
) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    runs = []
    for c in conditions:
        is_err = include_error and (c == error_condition)
        reason = (custom_reasons or {}).get(c, "ERROR" if is_err else termination_reason)
        runs.append({
            "run_id": f"WS4-PILOT-SP-001-{c}",
            "condition": c,
            "user_id": "SP-001",
            "turn_count": 3,
            "termination_reason": reason,
            "error": "Simulated error" if is_err else None,
        })
    summary = {
        "execution_mode": "formal_pilot",
        "formal_experiment_started": False,
        "twelve_by_four_started": False,
        "pilot_patient_id": "SP-001",
        "runs": runs,
    }
    target_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return target_path


# =====================================================================
# 輔助函式：建立測試用假 Trajectory 目錄
# =====================================================================
def _create_mock_run_dir(
    base_dir: Path,
    run_id: str,
    *,
    condition: str = "A",
    patient_id: str = "SP-001",
    is_error: bool = False,
    max_turns: int = 2,
    num_turns: int = 2,
) -> Path:
    run_dir = base_dir / run_id
    state_dir = run_dir / "isolated_state"
    state_dir.mkdir(parents=True, exist_ok=True)

    config_data = {
        "run_id": run_id,
        "condition": condition,
        "patient_id": patient_id,
        "max_turns": max_turns,
    }
    (state_dir / "config.json").write_text(json.dumps(config_data), encoding="utf-8")

    lines = []
    for idx in range(num_turns):
        turn_obj = {
            "turn_index": idx,
            "research_patient_id": patient_id,
            "user_message": f"第 {idx + 1} 句提問",
            "assistant_response": f"第 {idx + 1} 句衛教回答",
            "exposed_tools": [],
            "called_tools": [],
            "planner_result_or_neutral": {"engine": "neutral"},
            "output_guard_result": {"is_blocked": False},
        }
        if idx == num_turns - 1:
            turn_obj["termination_reason"] = "ERROR" if is_error else "MAX_TURNS"
        lines.append(json.dumps(turn_obj, ensure_ascii=False))

    (state_dir / "trajectories.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    roleplay_data = {
        "run_id": run_id,
        "condition": condition,
        "patient_id": patient_id,
        "records": [{"turn": idx + 1} for idx in range(num_turns)],
        "termination_reason": "ERROR" if is_error else "MAX_TURNS",
        "error_metadata": "Simulated error" if is_error else None,
    }
    (run_dir / "roleplay_result.json").write_text(json.dumps(roleplay_data), encoding="utf-8")
    return run_dir


# =====================================================================
# 1. 批次確認字串門禁測試
# =====================================================================
def test_batch_confirm_gate_rejects_missing_or_wrong_string(tmp_path: Path):
    """驗證缺少或錯誤的確認字串會立即被 Fail-Closed 拒絕。"""
    # 錯誤的字串
    with pytest.raises(ValueError, match="Invalid confirmation token"):
        run_batch(
            confirm_token="INVALID_TOKEN",
            output_root=tmp_path / "batch",
            pilot_summary_path=tmp_path / "pilot" / "formal_pilot_summary.json",
        )

    # 空字串
    with pytest.raises(ValueError, match="Invalid confirmation token"):
        run_batch(
            confirm_token="",
            output_root=tmp_path / "batch",
            pilot_summary_path=tmp_path / "pilot" / "formal_pilot_summary.json",
        )

    # CLI 參數缺少確認字串時報錯
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["batch"])


# =====================================================================
# 2. Preflight 門禁：Git 工作區乾淨度檢查
# =====================================================================
def test_batch_preflight_checks_dirty_git(tmp_path: Path):
    """驗證 Git 工作區存在未提交修改時，門禁立即拒絕。"""
    # 模擬 git status 輸出有改動
    with patch("subprocess.check_output", return_value=b" M some_file.py\n"):
        with pytest.raises(RuntimeError, match="Working tree is dirty"):
            check_clean_working_tree(repo_root=tmp_path)

    # 模擬 git status 乾淨
    with patch("subprocess.check_output", return_value=b""):
        check_clean_working_tree(repo_root=tmp_path)


# =====================================================================
# 3. Preflight 門禁：指紋與執行包絡檢驗
# =====================================================================
def test_batch_preflight_checks_fingerprints_and_envelope():
    """驗證指紋不符時門禁立即拋錯拒絕。"""
    # 原始環境下指紋與 envelope 必須完全通過
    check_frozen_config_and_envelope()

    # 模擬指紋被更動
    with patch(
        "llm_ablation_paper.workstream_1_technical_lead.scripts.run_formal_experiment.talker_base_prompt_sha256",
        return_value="tampered_fingerprint_sha256",
    ):
        with pytest.raises(ValueError, match="Fingerprint mismatch: talker_base_prompt_sha256"):
            check_frozen_config_and_envelope()


# =====================================================================
# 4. Preflight 門禁：12 Profiles 驗證器失敗檢查
# =====================================================================
def test_batch_preflight_checks_validator_failure():
    """驗證 WS4 12 profiles 驗證器回傳非 0 時門禁立即拋錯拒絕。"""
    # 原始環境下驗證器必須通過
    check_12_profiles_validator()

    # 模擬驗證器失敗
    with patch(
        "llm_ablation_paper.workstream_4_patient_simulation.scripts.validate_profiles.main",
        return_value=1,
    ):
        with pytest.raises(RuntimeError, match="12 profiles validator failed with exit code 1"):
            check_12_profiles_validator()


# =====================================================================
# 5. Preflight 門禁：Pilot 未完成、非白名單終止原因或含 ERROR 檢查
# =====================================================================
def test_batch_preflight_checks_pilot_incomplete_or_error(tmp_path: Path):
    """驗證 pilot summary 不存在、缺少條件、含非 null error 或終止原因非 PATIENT_GOAL_MET/MAX_TURNS 時立即拒絕。"""
    pilot_summary = tmp_path / "pilot" / "formal_pilot_summary.json"

    # 1. 檔案不存在
    with pytest.raises(FileNotFoundError, match="Pilot summary file not found"):
        check_pilot_completed_cleanly(pilot_summary)

    # 2. 缺少條件 (例如只跑了 A, B, C)
    _create_mock_pilot_summary(pilot_summary, conditions=("A", "B", "C"))
    with pytest.raises(RuntimeError, match="Pilot runs missing required conditions"):
        check_pilot_completed_cleanly(pilot_summary)

    # 3. 包含 error metadata 非 null
    _create_mock_pilot_summary(
        pilot_summary,
        conditions=("A", "B", "C", "D"),
        include_error=True,
        error_condition="C",
    )
    with pytest.raises(RuntimeError, match="failed with non-null error metadata"):
        check_pilot_completed_cleanly(pilot_summary)

    # 4. 終止原因為 COMMON_INPUT_BLOCK（禁止視為主 pilot 通過）
    _create_mock_pilot_summary(
        pilot_summary,
        conditions=("A", "B", "C", "D"),
        custom_reasons={"A": "COMMON_INPUT_BLOCK"},
    )
    with pytest.raises(RuntimeError, match="terminated with invalid reason: 'COMMON_INPUT_BLOCK'"):
        check_pilot_completed_cleanly(pilot_summary)

    # 5. 終止原因為 None
    _create_mock_pilot_summary(
        pilot_summary,
        conditions=("A", "B", "C", "D"),
        custom_reasons={"B": None},
    )
    with pytest.raises(RuntimeError, match="terminated with invalid reason: None"):
        check_pilot_completed_cleanly(pilot_summary)

    # 6. 終止原因為未知字串（例如舊的 PATIENT_SATISFIED）
    _create_mock_pilot_summary(
        pilot_summary,
        conditions=("A", "B", "C", "D"),
        custom_reasons={"C": "PATIENT_SATISFIED"},
    )
    with pytest.raises(RuntimeError, match="terminated with invalid reason: 'PATIENT_SATISFIED'"):
        check_pilot_completed_cleanly(pilot_summary)

    # 7. 終止原因為 ERROR
    _create_mock_pilot_summary(
        pilot_summary,
        conditions=("A", "B", "C", "D"),
        custom_reasons={"D": "ERROR"},
    )
    with pytest.raises(RuntimeError, match="terminated with invalid reason: 'ERROR'"):
        check_pilot_completed_cleanly(pilot_summary)

    # 8. 完整 4 組皆為 PATIENT_GOAL_MET 且無 ERROR -> 成功
    _create_mock_pilot_summary(
        pilot_summary,
        conditions=("A", "B", "C", "D"),
        termination_reason="PATIENT_GOAL_MET",
        include_error=False,
    )
    check_pilot_completed_cleanly(pilot_summary)

    # 9. 完整 4 組皆為 MAX_TURNS 且無 ERROR -> 成功
    _create_mock_pilot_summary(
        pilot_summary,
        conditions=("A", "B", "C", "D"),
        termination_reason="MAX_TURNS",
        include_error=False,
    )
    check_pilot_completed_cleanly(pilot_summary)


# =====================================================================
# 6. Preflight 門禁：Batch 與 Pilot 輸出目錄隔離檢查
# =====================================================================
def test_batch_preflight_checks_output_root_collision_with_pilot(tmp_path: Path):
    """驗證 Batch 輸出目錄與 Pilot 輸出目錄相同時拋錯隔離。"""
    same_dir = tmp_path / "same_output"
    with pytest.raises(ValueError, match="must be distinct from Pilot output root"):
        check_distinct_output_roots(same_dir, same_dir)

    diff_dir = tmp_path / "diff_output"
    check_distinct_output_roots(same_dir, diff_dir)


# =====================================================================
# 7. 衝突防護：未指定 resume 時已存在目錄衝突檢查
# =====================================================================
def test_batch_output_root_conflict_without_resume(tmp_path: Path):
    """驗證在未指定 --resume 時，若已存在該 run 之目錄則禁止覆寫。"""
    pilot_sum = _create_mock_pilot_summary(tmp_path / "pilot" / "formal_pilot_summary.json")
    batch_dir = tmp_path / "batch"
    existing_run_dir = batch_dir / "WS4-BATCH-SP-001-A"
    existing_run_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(FileExistsError, match="Target run directory already exists"):
        run_batch(
            confirm_token=CONFIRM_FORMAL_12X4_RUN_STRING,
            output_root=batch_dir,
            pilot_summary_path=pilot_sum,
            resume=False,
            skip_git_check=True,
        )


# =====================================================================
# 8. Resume 身分驗證與接續執行
# =====================================================================
# =====================================================================
# 8. Resume 身分驗證與接續執行
# =====================================================================
def test_batch_resume_identity_validation(tmp_path: Path):
    """驗證在指定 --resume 時，允許安全接續已存在的目錄而不拋衝突例外。"""
    pilot_sum = _create_mock_pilot_summary(tmp_path / "pilot" / "formal_pilot_summary.json")
    batch_dir = tmp_path / "batch"
    existing_run_dir = batch_dir / "WS4-BATCH-SP-001-A"
    existing_run_dir.mkdir(parents=True, exist_ok=True)

    mock_run_condition = MagicMock(return_value={
        "run_id": "WS4-BATCH-SP-001-A",
        "patient_id": "SP-001",
        "condition": "A",
        "user_id": "SP-001",
        "records": [{}],
        "termination_reason": "PATIENT_GOAL_MET",
        "error_metadata": None,
    })

    with patch(
        "llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation.RoleplayRunner.run_condition",
        mock_run_condition,
    ):
        summary = run_batch(
            confirm_token=CONFIRM_FORMAL_12X4_RUN_STRING,
            output_root=batch_dir,
            pilot_summary_path=pilot_sum,
            resume=True,
            skip_git_check=True,
            runner_kwargs={"patient_agent": MagicMock(model="gemini-2.5", temperature=0.0)},
        )
    assert summary["execution_mode"] == "formal_12x4_batch"
    assert summary["total_trajectories"] == 48


# =====================================================================
# 9. 離線 12x4 = 48 條軌跡計數與摘要完整性
# =====================================================================
def test_batch_offline_48_trajectories_count(tmp_path: Path):
    """驗證 Controller 內部執行 12 profiles x 4 conditions = 48 條軌跡。"""
    pilot_sum = _create_mock_pilot_summary(tmp_path / "pilot" / "formal_pilot_summary.json")
    batch_dir = tmp_path / "batch"

    call_records = []

    def fake_run_condition(profile, condition, resume, fake_talker_responses, run_suffix):
        pid = profile["patient_id"] if isinstance(profile, dict) else profile.patient_id
        call_records.append((pid, condition, run_suffix))
        return {
            "run_id": f"WS4-{run_suffix}-{pid}-{condition}",
            "patient_id": pid,
            "condition": condition,
            "user_id": pid,
            "records": [{"turn": 1}],
            "termination_reason": "MAX_TURNS",
            "error_metadata": None,
        }

    with patch(
        "llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation.RoleplayRunner.run_condition",
        side_effect=fake_run_condition,
    ):
        summary = run_batch(
            confirm_token=CONFIRM_FORMAL_12X4_RUN_STRING,
            output_root=batch_dir,
            pilot_summary_path=pilot_sum,
            resume=False,
            skip_git_check=True,
            runner_kwargs={"patient_agent": MagicMock(model="gemini-2.5", temperature=0.0)},
        )

    # 驗證精確執行 48 次
    assert len(call_records) == 48
    assert summary["total_trajectories"] == 48
    assert summary["expected_trajectories"] == 48
    assert summary["completed_trajectories"] == 48
    assert summary["error_trajectories"] == 0

    # 驗證所有 12 profiles 與 4 conditions 完整覆蓋
    patient_ids = {r[0] for r in call_records}
    conditions = {r[1] for r in call_records}
    suffixes = {r[2] for r in call_records}
    assert len(patient_ids) == 12
    assert conditions == {"A", "B", "C", "D"}
    assert suffixes == {"BATCH"}

    # 驗證產生的 summary json 檔案
    summary_file = batch_dir / "formal_batch_summary.json"
    assert summary_file.exists()
    saved_data = json.loads(summary_file.read_text(encoding="utf-8"))
    assert len(saved_data["runs"]) == 48


def test_batch_missing_api_key_fails_closed(tmp_path: Path):
    """驗證未注入假 Agent 且無 API Key 時，正式批次立即 fail-closed 拋出 RuntimeError。"""
    pilot_sum = _create_mock_pilot_summary(tmp_path / "pilot" / "formal_pilot_summary.json")
    batch_dir = tmp_path / "batch"

    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(RuntimeError, match="正式模型連線缺少 GEMINI_API_KEY"):
            run_batch(
                confirm_token=CONFIRM_FORMAL_12X4_RUN_STRING,
                output_root=batch_dir,
                pilot_summary_path=pilot_sum,
                resume=False,
                skip_git_check=True,
            )


# =====================================================================
# 10. Mapping 生成器：密碼學隨機性、單向性與永不可覆寫
# =====================================================================
def test_mapping_generator_cryptographic_uniqueness_and_no_overwrite(tmp_path: Path):
    """驗證 mapping 生成符合 schema、隨機性且永不可覆寫（且原檔 byte-for-byte 完全不變）。"""
    map_file = tmp_path / "secret_mapping.json"

    # 1. 初次生成成功
    m1 = generate_frozen_mapping(output_file=map_file)
    assert set(m1.keys()) == {"A", "B", "C", "D"}
    for v in m1.values():
        assert v.startswith("COND-")
        assert len(v) == 13
        int(v.split("-")[1], 16)  # 驗證為有效十六進位
    assert len(set(m1.values())) == 4  # 4 個混淆值互不相同

    orig_bytes = map_file.read_bytes()

    # 2. 檔案已存在時永不可覆寫，拋出 FileExistsError
    with pytest.raises(FileExistsError, match="already exists.+overwrite is strictly prohibited"):
        generate_frozen_mapping(output_file=map_file)

    # 3. 驗證原檔案內容 byte-for-byte 完全未被更動或截斷
    assert map_file.read_bytes() == orig_bytes

    # 4. 驗證隨機性（不同輸出檔生成的值應不同）
    m3 = generate_frozen_mapping(output_file=tmp_path / "m3.json")
    assert list(m1.values()) != list(m3.values())

    # 5. 驗證 CLI 已無 --overwrite 旗標，若傳入則報錯
    with pytest.raises(SystemExit):
        main(["generate-mapping", "--output-file", str(tmp_path / "cli.json"), "--overwrite"])


# =====================================================================
# 11. Blind Export 排除 Canary, Pilot, ERROR 並拒絕未完成軌跡
# =====================================================================
def test_blind_export_require_completed_and_filter_pilot_canary_error(tmp_path: Path):
    """驗證 Blind Export 嚴格排除 canary/pilot/error，永遠 require_completed 且拒絕未完成軌跡。"""
    raw_dir = tmp_path / "raw_runs"
    out_dir = tmp_path / "blinded_transcripts"
    map_file = tmp_path / "mapping.json"
    mapping = generate_frozen_mapping(output_file=map_file)

    # 建立 4 種不同情境的 run
    # 1. 正式已完成的 run (應匯出)
    _create_mock_run_dir(raw_dir, "WS4-BATCH-SP-001-A", condition="A", patient_id="SP-001")
    # 2. Canary run (應略過)
    _create_mock_run_dir(raw_dir, "WS4-CANARY-SP-001-A", condition="A", patient_id="SP-001")
    # 3. Pilot run (應略過)
    _create_mock_run_dir(raw_dir, "WS4-PILOT-SP-001-A", condition="A", patient_id="SP-001")
    # 4. 執行錯誤的 run (應略過)
    _create_mock_run_dir(raw_dir, "WS4-BATCH-SP-002-A", condition="A", patient_id="SP-002", is_error=True)

    summary = run_blind_export(
        raw_dir=raw_dir,
        mapping_file=map_file,
        output_dir=out_dir,
    )

    assert summary["exported_count"] == 1
    assert summary["skipped_canary"] == 1
    assert summary["skipped_pilot"] == 1
    assert summary["skipped_error"] == 1

    exported_files = list(out_dir.glob("*.json"))
    assert len(exported_files) == 1

    # 檢驗匯出的 blinded json
    blinded_content = json.loads(exported_files[0].read_text(encoding="utf-8"))
    assert blinded_content["condition_secret"] == mapping["A"]
    assert "condition" not in blinded_content
    assert not blinded_content["run_id"].startswith("WS4-BATCH")

    # 驗證未完成軌跡呼叫 run_blind_export 立即被拒絕
    incomplete_dir = tmp_path / "incomplete_raw"
    _create_mock_run_dir(
        incomplete_dir,
        "WS4-BATCH-SP-003-A",
        condition="A",
        patient_id="SP-003",
        max_turns=10,  # 設定 max_turns 為 10，但只跑了 1 輪
        num_turns=1,
    )
    # 修改其 trajectory 讓 termination_reason 為 None
    inc_state = incomplete_dir / "WS4-BATCH-SP-003-A" / "isolated_state"
    inc_lines = [json.dumps({
        "turn_index": 0,
        "research_patient_id": "SP-003",
        "user_message": "血糖問題",
        "assistant_response": "回覆",
        "exposed_tools": [],
        "called_tools": [],
        "planner_result_or_neutral": {"engine": "neutral"},
        "output_guard_result": {"is_blocked": False},
        # 不填寫 termination_reason
    })]
    (inc_state / "trajectories.jsonl").write_text("\n".join(inc_lines) + "\n", encoding="utf-8")
    (incomplete_dir / "WS4-BATCH-SP-003-A" / "roleplay_result.json").write_text(
        json.dumps({"termination_reason": None}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="incomplete"):
        run_blind_export(
            raw_dir=incomplete_dir,
            mapping_file=map_file,
            output_dir=tmp_path / "blind_incomplete",
        )

    # 驗證 CLI 已無 --allow-incomplete 旗標，若傳入則報錯
    with pytest.raises(SystemExit):
        main(["blind-export", "--raw-dir", str(raw_dir), "--mapping-file", str(map_file), "--allow-incomplete"])


# =====================================================================
# 12. Blind Export 洩漏掃描驗證 (Leakage Scan Reject)
# =====================================================================
def test_blind_export_leakage_scan_rejects_leak():
    """驗證洩漏掃描器若在 payload 中發現 mapping 明文、未脫敏 condition 或內部標籤立即拋錯。"""
    mapping = {"A": "111111111111", "B": "222222222222", "C": "333333333333", "D": "444444444444"}

    # 1. 正常脫敏 payload 通過
    clean_payload = json.dumps({"run_id": "BLIND-001", "condition_secret": "111111111111", "turns": []})
    scan_blinded_payload_for_leakage(clean_payload, mapping)

    # 2. 出現 mapping 鍵值配對洩漏
    leaked_mapping_payload = json.dumps({"run_id": "BLIND-001", "A": "111111111111"})
    with pytest.raises(ValueError, match="Leakage detected: mapping pair"):
        scan_blinded_payload_for_leakage(leaked_mapping_payload, mapping)

    # 3. 出現未脫敏 condition 欄位
    leaked_condition_payload = json.dumps({"run_id": "BLIND-001", "condition": "A"})
    with pytest.raises(ValueError, match="Leakage detected: unblinded condition label"):
        scan_blinded_payload_for_leakage(leaked_condition_payload, mapping)

    # 4. 出現內部消融開關
    for forbidden_flag in ("enable_planner", "dynamic_tool_gate", "enable_output_guard"):
        leaked_flag_payload = json.dumps({"run_id": "BLIND-001", forbidden_flag: True})
        with pytest.raises(ValueError, match="Leakage detected: internal ablation flag"):
            scan_blinded_payload_for_leakage(leaked_flag_payload, mapping)


# =====================================================================
# 13. Pilot 子命令離線整合測試
# =====================================================================
def test_pilot_subcommand_offline(tmp_path: Path):
    """驗證 Pilot 子命令在注入 fake runner 下能完成 1 profile x 4 conditions。"""
    pilot_dir = tmp_path / "pilot"
    called = []

    def fake_pilot_condition(profile, condition, resume, fake_talker_responses, run_suffix):
        pid = profile["patient_id"] if isinstance(profile, dict) else profile.patient_id
        called.append((pid, condition, run_suffix))
        return {
            "run_id": f"WS4-PILOT-{pid}-{condition}",
            "condition": condition,
            "user_id": pid,
            "records": [{"turn": 1}],
            "termination_reason": "PATIENT_GOAL_MET",
            "error_metadata": None,
        }

    with patch(
        "llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation.RoleplayRunner.run_condition",
        side_effect=fake_pilot_condition,
    ):
        summary = run_pilot(
            patient_id=DEFAULT_PILOT_PATIENT_ID,
            output_root=pilot_dir,
            runner_kwargs={"patient_agent": MagicMock(model="gemini-2.5", temperature=0.0)},
        )

    assert summary["execution_mode"] == "formal_pilot"
    assert summary["pilot_patient_id"] == DEFAULT_PILOT_PATIENT_ID
    assert len(summary["runs"]) == 4
    assert len(called) == 4
    assert {c[1] for c in called} == {"A", "B", "C", "D"}
    assert (pilot_dir / "formal_pilot_summary.json").exists()


# =====================================================================
# 14. CLI Entrypoint 整合測試
# =====================================================================
def test_cli_entrypoint(tmp_path: Path):
    """驗證 CLI 進入點各子命令的基本調用。"""
    # 測試 generate-mapping
    map_out = tmp_path / "cli_mapping.json"
    exit_code = main(["generate-mapping", "--output-file", str(map_out)])
    assert exit_code == 0
    assert map_out.exists()


# =====================================================================
# 15. M4.2 Blind Export Wiring 與嚴格驗證測試
# =====================================================================
def test_m42_blind_export_wiring_and_validation(tmp_path: Path):
    """驗證 M4.2 終止理由傳遞、合約一致性校驗與去識別化保證。"""
    map_file = tmp_path / "mapping.json"
    mapping = generate_frozen_mapping(output_file=map_file)

    # 1. 提前 PATIENT_GOAL_MET 的 run (例如 2 turns < 6 turns) 可成功匯出，合約理由為 PATIENT_GOAL_MET
    raw_dir_early = tmp_path / "raw_early"
    run_early = raw_dir_early / "WS4-BATCH-SP-001-A"
    state_early = run_early / "isolated_state"
    state_early.mkdir(parents=True, exist_ok=True)
    (state_early / "config.json").write_text(
        json.dumps({"run_id": "WS4-BATCH-SP-001-A", "condition": "A", "patient_id": "SP-001", "max_turns": 6}),
        encoding="utf-8",
    )
    lines_early = [
        json.dumps({
            "turn_index": 0, "user_message": "q1", "assistant_response": "a1", "research_patient_id": "SP-001",
            "enable_planner": False,
        }),
        json.dumps({
            "turn_index": 1, "user_message": "q2", "assistant_response": "a2", "research_patient_id": "SP-001",
            "enable_planner": False,
        }),
    ]
    (state_early / "trajectories.jsonl").write_text("\n".join(lines_early) + "\n", encoding="utf-8")
    (run_early / "roleplay_result.json").write_text(
        json.dumps({
            "run_id": "WS4-BATCH-SP-001-A", "condition": "A", "patient_id": "SP-001",
            "termination_reason": "PATIENT_GOAL_MET", "error_metadata": None,
            "records": [{"turn": 1}, {"turn": 2}],
        }),
        encoding="utf-8",
    )
    out_early = tmp_path / "out_early"
    res_early = run_blind_export(raw_dir=raw_dir_early, mapping_file=map_file, output_dir=out_early)
    assert res_early["exported_count"] == 1
    exported_files = list(out_early.glob("*.json"))
    assert len(exported_files) == 1
    content_early = json.loads(exported_files[0].read_text(encoding="utf-8"))
    assert content_early["termination_reason"] == "PATIENT_GOAL_MET"

    # 驗證絕無殘留欄位與原始識別
    raw_content = exported_files[0].read_text(encoding="utf-8")
    assert "research_patient_id" not in raw_content
    assert "enable_" not in raw_content
    assert '"WS4-' not in raw_content
    assert content_early["patient_id"] == "SP-001"

    # 2. 達 MAX_TURNS (6 turns) 正常 export
    raw_dir_max = tmp_path / "raw_max"
    run_max = raw_dir_max / "WS4-BATCH-SP-002-B"
    state_max = run_max / "isolated_state"
    state_max.mkdir(parents=True, exist_ok=True)
    (state_max / "config.json").write_text(
        json.dumps({"run_id": "WS4-BATCH-SP-002-B", "condition": "B", "patient_id": "SP-002", "max_turns": 6}),
        encoding="utf-8",
    )
    lines_max = [
        json.dumps({
            "turn_index": i, "user_message": f"q{i}", "assistant_response": f"a{i}",
            "research_patient_id": "SP-002",
        })
        for i in range(6)
    ]
    (state_max / "trajectories.jsonl").write_text("\n".join(lines_max) + "\n", encoding="utf-8")
    (run_max / "roleplay_result.json").write_text(
        json.dumps({
            "run_id": "WS4-BATCH-SP-002-B", "condition": "B", "patient_id": "SP-002",
            "termination_reason": "MAX_TURNS", "error_metadata": None,
            "records": [{"turn": i + 1} for i in range(6)],
        }),
        encoding="utf-8",
    )
    out_max = tmp_path / "out_max"
    res_max = run_blind_export(raw_dir=raw_dir_max, mapping_file=map_file, output_dir=out_max)
    assert res_max["exported_count"] == 1
    content_max = json.loads(list(out_max.glob("*.json"))[0].read_text(encoding="utf-8"))
    assert content_max["termination_reason"] == "MAX_TURNS"

    # 3. roleplay_result termination_reason 為 None、未知或 error_metadata 非空時被拒絕
    for bad_reason in (None, "UNKNOWN_REASON", "INVALID"):
        bad_dir = tmp_path / f"raw_bad_{bad_reason}"
        run_bad = bad_dir / "WS4-BATCH-SP-003-C"
        s_bad = run_bad / "isolated_state"
        s_bad.mkdir(parents=True, exist_ok=True)
        (s_bad / "config.json").write_text(
            json.dumps({"run_id": "WS4-BATCH-SP-003-C", "condition": "C", "patient_id": "SP-003", "max_turns": 6}),
            encoding="utf-8",
        )
        (s_bad / "trajectories.jsonl").write_text("\n".join(lines_early) + "\n", encoding="utf-8")
        (run_bad / "roleplay_result.json").write_text(
            json.dumps({
                "run_id": "WS4-BATCH-SP-003-C", "condition": "C", "patient_id": "SP-003",
                "termination_reason": bad_reason, "error_metadata": None,
            }),
            encoding="utf-8",
        )
        with pytest.raises(ValueError):
            run_blind_export(raw_dir=bad_dir, mapping_file=map_file, output_dir=tmp_path / f"out_bad_{bad_reason}")

    # error_metadata 非空被拒絕排除
    err_meta_dir = tmp_path / "raw_err_meta"
    run_err = err_meta_dir / "WS4-BATCH-SP-004-D"
    s_err = run_err / "isolated_state"
    s_err.mkdir(parents=True, exist_ok=True)
    (s_err / "config.json").write_text(
        json.dumps({"run_id": "WS4-BATCH-SP-004-D", "condition": "D", "patient_id": "SP-004", "max_turns": 6}),
        encoding="utf-8",
    )
    (s_err / "trajectories.jsonl").write_text("\n".join(lines_early) + "\n", encoding="utf-8")
    (run_err / "roleplay_result.json").write_text(
        json.dumps({
            "run_id": "WS4-BATCH-SP-004-D", "condition": "D", "patient_id": "SP-004",
            "termination_reason": "PATIENT_GOAL_MET", "error_metadata": {"code": 500},
        }),
        encoding="utf-8",
    )
    res_err = run_blind_export(raw_dir=err_meta_dir, mapping_file=map_file, output_dir=tmp_path / "out_err_meta")
    assert res_err["skipped_error"] == 1
    assert res_err["exported_count"] == 0

    # 4. 具 per-turn nested ERROR 的 run 即使 roleplay_result 標示非 ERROR，仍被排除
    nested_err_dir = tmp_path / "raw_nested_err"
    run_nested = nested_err_dir / "WS4-BATCH-SP-005-A"
    s_nested = run_nested / "isolated_state"
    s_nested.mkdir(parents=True, exist_ok=True)
    (s_nested / "config.json").write_text(
        json.dumps({"run_id": "WS4-BATCH-SP-005-A", "condition": "A", "patient_id": "SP-005", "max_turns": 6}),
        encoding="utf-8",
    )
    lines_nested = [
        json.dumps({"turn_index": 0, "user_message": "q1", "assistant_response": "a1", "termination_reason": "ERROR"}),
    ]
    (s_nested / "trajectories.jsonl").write_text("\n".join(lines_nested) + "\n", encoding="utf-8")
    (run_nested / "roleplay_result.json").write_text(
        json.dumps({
            "run_id": "WS4-BATCH-SP-005-A", "condition": "A", "patient_id": "SP-005",
            "termination_reason": "PATIENT_GOAL_MET", "error_metadata": None,
        }),
        encoding="utf-8",
    )
    res_nested = run_blind_export(raw_dir=nested_err_dir, mapping_file=map_file, output_dir=tmp_path / "out_nested")
    assert res_nested["skipped_error"] == 1
    assert res_nested["exported_count"] == 0

    # 5. identity 不一致或 turn 數不一致被拒絕
    mismatch_dir = tmp_path / "raw_mismatch"
    run_mis = mismatch_dir / "WS4-BATCH-SP-006-A"
    s_mis = run_mis / "isolated_state"
    s_mis.mkdir(parents=True, exist_ok=True)
    (s_mis / "config.json").write_text(
        json.dumps({"run_id": "WS4-BATCH-SP-006-A", "condition": "A", "patient_id": "SP-006", "max_turns": 6}),
        encoding="utf-8",
    )
    (s_mis / "trajectories.jsonl").write_text("\n".join(lines_early) + "\n", encoding="utf-8")
    # run_id mismatch
    (run_mis / "roleplay_result.json").write_text(
        json.dumps({
            "run_id": "WS4-BATCH-WRONG-A", "condition": "A", "patient_id": "SP-006",
            "termination_reason": "PATIENT_GOAL_MET",
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="mismatch"):
        run_blind_export(raw_dir=mismatch_dir, mapping_file=map_file, output_dir=tmp_path / "out_mis")

    # records count mismatch
    (run_mis / "roleplay_result.json").write_text(
        json.dumps({
            "run_id": "WS4-BATCH-SP-006-A", "condition": "A", "patient_id": "SP-006",
            "termination_reason": "PATIENT_GOAL_MET", "records": [{"turn": 1}],  # only 1 record while 2 turns in traj
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="mismatch"):
        run_blind_export(raw_dir=mismatch_dir, mapping_file=map_file, output_dir=tmp_path / "out_mis2")


# =====================================================================
# 16. M4.2b Adversarial Tests: config.json 與逐筆軌跡一致性
# =====================================================================
def test_m42b_blind_export_hardening_adversarial(tmp_path: Path):
    """驗證缺失/損毀 config.json、逐筆身分不符、turn_index 重複/缺口均會 Fail-Closed 拒絕。"""
    map_file = tmp_path / "mapping.json"
    generate_frozen_mapping(output_file=map_file)

    def _setup_base_run(test_name: str) -> tuple[Path, Path, Path]:
        base_dir = tmp_path / test_name
        run_d = base_dir / "WS4-BATCH-SP-001-A"
        st_d = run_d / "isolated_state"
        st_d.mkdir(parents=True, exist_ok=True)
        (run_d / "roleplay_result.json").write_text(
            json.dumps({
                "run_id": "WS4-BATCH-SP-001-A",
                "condition": "A",
                "patient_id": "SP-001",
                "termination_reason": "MAX_TURNS",
                "error_metadata": None,
                "records": [{"turn": 1}, {"turn": 2}],
            }),
            encoding="utf-8",
        )
        (st_d / "config.json").write_text(
            json.dumps({"run_id": "WS4-BATCH-SP-001-A", "condition": "A", "patient_id": "SP-001", "max_turns": 2}),
            encoding="utf-8",
        )
        lines = [
            json.dumps({"turn_index": 0, "run_id": "WS4-BATCH-SP-001-A", "condition": "A", "patient_id": "SP-001", "user_message": "q0", "assistant_response": "a0"}),
            json.dumps({"turn_index": 1, "run_id": "WS4-BATCH-SP-001-A", "condition": "A", "patient_id": "SP-001", "user_message": "q1", "assistant_response": "a1", "termination_reason": "MAX_TURNS"}),
        ]
        (st_d / "trajectories.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return base_dir, run_d, st_d

    # 1. missing config.json -> 被拒
    b_dir1, _, s_dir1 = _setup_base_run("test_missing_config")
    (s_dir1 / "config.json").unlink()
    with pytest.raises(ValueError, match="missing config.json"):
        run_blind_export(raw_dir=b_dir1, mapping_file=map_file, output_dir=tmp_path / "out1")

    # 2. malformed config.json (語法錯誤) -> 被拒
    b_dir2, _, s_dir2 = _setup_base_run("test_malformed_syntax_config")
    (s_dir2 / "config.json").write_text("{broken json...", encoding="utf-8")
    with pytest.raises(ValueError, match="Cannot parse config.json"):
        run_blind_export(raw_dir=b_dir2, mapping_file=map_file, output_dir=tmp_path / "out2")

    # 3. malformed config.json (非 dict 型別，如 list) -> 被拒
    b_dir3, _, s_dir3 = _setup_base_run("test_non_dict_config")
    (s_dir3 / "config.json").write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed config.json"):
        run_blind_export(raw_dir=b_dir3, mapping_file=map_file, output_dir=tmp_path / "out3")

    # 4. trajectory identity mismatch: run_id mismatch
    b_dir4, _, s_dir4 = _setup_base_run("test_traj_mismatch_run_id")
    bad_lines4 = [
        json.dumps({"turn_index": 0, "run_id": "WS4-BATCH-WRONG-RUN-ID", "condition": "A", "patient_id": "SP-001", "user_message": "q0", "assistant_response": "a0"}),
        json.dumps({"turn_index": 1, "run_id": "WS4-BATCH-SP-001-A", "condition": "A", "patient_id": "SP-001", "user_message": "q1", "assistant_response": "a1"}),
    ]
    (s_dir4 / "trajectories.jsonl").write_text("\n".join(bad_lines4) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Trajectory identity mismatch.*turn run_id"):
        run_blind_export(raw_dir=b_dir4, mapping_file=map_file, output_dir=tmp_path / "out4")

    # 5. trajectory identity mismatch: condition mismatch
    b_dir5, _, s_dir5 = _setup_base_run("test_traj_mismatch_condition")
    bad_lines5 = [
        json.dumps({"turn_index": 0, "run_id": "WS4-BATCH-SP-001-A", "condition": "B", "patient_id": "SP-001", "user_message": "q0", "assistant_response": "a0"}),
        json.dumps({"turn_index": 1, "run_id": "WS4-BATCH-SP-001-A", "condition": "A", "patient_id": "SP-001", "user_message": "q1", "assistant_response": "a1"}),
    ]
    (s_dir5 / "trajectories.jsonl").write_text("\n".join(bad_lines5) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Trajectory identity mismatch.*turn condition"):
        run_blind_export(raw_dir=b_dir5, mapping_file=map_file, output_dir=tmp_path / "out5")

    # 6. trajectory identity mismatch: patient_id mismatch
    b_dir6, _, s_dir6 = _setup_base_run("test_traj_mismatch_patient_id")
    bad_lines6 = [
        json.dumps({"turn_index": 0, "run_id": "WS4-BATCH-SP-001-A", "condition": "A", "patient_id": "SP-999", "user_message": "q0", "assistant_response": "a0"}),
        json.dumps({"turn_index": 1, "run_id": "WS4-BATCH-SP-001-A", "condition": "A", "patient_id": "SP-001", "user_message": "q1", "assistant_response": "a1"}),
    ]
    (s_dir6 / "trajectories.jsonl").write_text("\n".join(bad_lines6) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Trajectory identity mismatch.*turn patient_id"):
        run_blind_export(raw_dir=b_dir6, mapping_file=map_file, output_dir=tmp_path / "out6")

    # 7. trajectory identity mismatch: research_patient_id mismatch
    b_dir7, _, s_dir7 = _setup_base_run("test_traj_mismatch_research_patient_id")
    bad_lines7 = [
        json.dumps({"turn_index": 0, "run_id": "WS4-BATCH-SP-001-A", "condition": "A", "research_patient_id": "SP-999", "user_message": "q0", "assistant_response": "a0"}),
        json.dumps({"turn_index": 1, "run_id": "WS4-BATCH-SP-001-A", "condition": "A", "research_patient_id": "SP-001", "user_message": "q1", "assistant_response": "a1"}),
    ]
    (s_dir7 / "trajectories.jsonl").write_text("\n".join(bad_lines7) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Trajectory identity mismatch.*turn research_patient_id"):
        run_blind_export(raw_dir=b_dir7, mapping_file=map_file, output_dir=tmp_path / "out7")

    # 8. turn_index 重複 -> 被拒
    b_dir8, _, s_dir8 = _setup_base_run("test_duplicate_turn_index")
    bad_lines8 = [
        json.dumps({"turn_index": 0, "patient_id": "SP-001", "user_message": "q0", "assistant_response": "a0"}),
        json.dumps({"turn_index": 0, "patient_id": "SP-001", "user_message": "q1", "assistant_response": "a1"}),
    ]
    (s_dir8 / "trajectories.jsonl").write_text("\n".join(bad_lines8) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid turn_index sequence"):
        run_blind_export(raw_dir=b_dir8, mapping_file=map_file, output_dir=tmp_path / "out8")

    # 9. turn_index 缺口 -> 被拒
    b_dir9, _, s_dir9 = _setup_base_run("test_gap_turn_index")
    bad_lines9 = [
        json.dumps({"turn_index": 0, "patient_id": "SP-001", "user_message": "q0", "assistant_response": "a0"}),
        json.dumps({"turn_index": 2, "patient_id": "SP-001", "user_message": "q1", "assistant_response": "a1"}),
    ]
    (s_dir9 / "trajectories.jsonl").write_text("\n".join(bad_lines9) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid turn_index sequence"):
        run_blind_export(raw_dir=b_dir9, mapping_file=map_file, output_dir=tmp_path / "out9")

    # 10. missing patient identity (patient_id 與 research_patient_id 均缺少) -> 被拒
    b_dir10, _, s_dir10 = _setup_base_run("test_missing_patient_identity")
    bad_lines10 = [
        json.dumps({"turn_index": 0, "user_message": "q0", "assistant_response": "a0"}),
        json.dumps({"turn_index": 1, "patient_id": "SP-001", "user_message": "q1", "assistant_response": "a1"}),
    ]
    (s_dir10 / "trajectories.jsonl").write_text("\n".join(bad_lines10) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing patient identity"):
        run_blind_export(raw_dir=b_dir10, mapping_file=map_file, output_dir=tmp_path / "out10")
