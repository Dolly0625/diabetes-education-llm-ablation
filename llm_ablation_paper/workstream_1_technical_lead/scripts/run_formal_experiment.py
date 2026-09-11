#!/usr/bin/env python3
"""受控正式實驗控制器 (WS1 Formal Experiment Controller).

嚴格遵守研究協議與分層消融防線：
1. pilot: 執行 1 profile (SP-001) x 4 conditions (A/B/C/D)，重用既有 RoleplayRunner pipeline。
2. batch: 讀取 12 frozen profiles -> 48 條軌跡。執行前強制檢驗 6 大 Fail-Closed 門禁，
   且必須顯式指定 --confirm-formal-run "I_CONFIRM_FORMAL_12X4_EXPERIMENT_RUN"。
3. blind-export: 載入私有 mapping 產生脫敏盲評檔案，排除 canary/pilot/ERROR，並執行嚴格洩漏掃描。
4. generate-mapping: 密碼學安全生成 A-D 混淆映射表，原子保存且禁止覆寫。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

# 設定專案根目錄
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llm_ablation_paper.workstream_1_technical_lead.harness.config import (
    FORMAL_PATIENT_AGENT_MODEL,
    FORMAL_PATIENT_AGENT_TEMPERATURE,
    FORMAL_SUBPROCESS_TIMEOUT_SECONDS,
    formal_ablation_config,
    require_frozen_formal_config,
)
from llm_ablation_paper.workstream_1_technical_lead.harness.fingerprints import (
    canonical_tool_schema_sha256,
    formal_runtime_config_canonical_sha256,
    planner_system_prompt_sha256,
    talker_base_prompt_sha256,
    talker_prompt_template_bundle_sha256,
)
from llm_ablation_paper.workstream_1_technical_lead.harness.runner import (
    generate_random_condition_mapping,
    load_frozen_condition_mapping,
    to_blinded_contract_trajectory,
    validate_condition_mapping,
)
from llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation import (
    GeminiPatientAgent,
    RoleplayRunner,
    load_profiles,
    require_frozen_formal_execution_envelope,
)

CONFIRM_FORMAL_12X4_RUN_STRING = "I_CONFIRM_FORMAL_12X4_EXPERIMENT_RUN"
DEFAULT_PILOT_PATIENT_ID = "SP-001"
DEFAULT_ARTIFACTS_ROOT = PROJECT_ROOT / "llm_ablation_paper" / "artifacts"
DEFAULT_PILOT_ROOT = DEFAULT_ARTIFACTS_ROOT / "pilot"
DEFAULT_BATCH_ROOT = DEFAULT_ARTIFACTS_ROOT / "raw_transcripts"
DEFAULT_BLINDED_ROOT = DEFAULT_ARTIFACTS_ROOT / "blinded_transcripts"
DEFAULT_MAPPING_FILE = DEFAULT_ARTIFACTS_ROOT / "frozen_config" / "frozen_condition_mapping.json"


# =====================================================================
# 1. Mapping 生成器 (Cryptographic Randomness & Atomic No-Overwrite)
# =====================================================================
def generate_frozen_mapping(
    *,
    output_file: Path | str = DEFAULT_MAPPING_FILE,
) -> dict[str, str]:
    """生成密碼學安全隨機之 A-D 混淆映射表，並以原子方式保存。已存在時永不可覆寫（fail-closed）。"""
    out_path = Path(output_file).resolve()
    if out_path.exists():
        raise FileExistsError(
            f"Frozen mapping file already exists at {out_path}; overwrite is strictly prohibited (fail-closed)."
        )

    mapping = generate_random_condition_mapping()
    validate_condition_mapping(mapping)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".tmp." + uuid.uuid4().hex[:8])
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    tmp_path.replace(out_path)
    return mapping


# =====================================================================
# 2. 六大 Preflight 驗證器 (Fail-Closed)
# =====================================================================
def check_clean_working_tree(repo_root: Path = PROJECT_ROOT) -> None:
    """驗證 Git 工作區乾淨，無未提交或未追蹤變更。"""
    try:
        status_out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
        ).decode("utf-8").strip()
    except Exception as e:
        raise RuntimeError(f"Failed to check git status: {e}") from e
    if status_out:
        raise RuntimeError(
            "Working tree is dirty; formal batch execution requires a clean git working tree (fail-closed).\n"
            f"Git status:\n{status_out}"
        )


def check_frozen_config_and_envelope() -> None:
    """驗證 formal config, execution envelope 與 fingerprints 吻合。"""
    manifest_path = (
        PROJECT_ROOT
        / "llm_ablation_paper"
        / "workstream_1_technical_lead"
        / "FREEZE_CANDIDATE_MANIFEST.json"
    )
    if not manifest_path.exists():
        raise FileNotFoundError(f"Freeze manifest missing at {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fps = manifest.get("fingerprints_sha256", {})

    if fps.get("talker_base_prompt_sha256") != talker_base_prompt_sha256():
        raise ValueError("Fingerprint mismatch: talker_base_prompt_sha256")
    if fps.get("talker_prompt_template_bundle_sha256") != talker_prompt_template_bundle_sha256():
        raise ValueError("Fingerprint mismatch: talker_prompt_template_bundle_sha256")
    if fps.get("planner_system_prompt_sha256") != planner_system_prompt_sha256():
        raise ValueError("Fingerprint mismatch: planner_system_prompt_sha256")
    if fps.get("canonical_tool_schema_sha256") != canonical_tool_schema_sha256():
        raise ValueError("Fingerprint mismatch: canonical_tool_schema_sha256")
    if manifest.get("formal_runtime_config_canonical_sha256") != formal_runtime_config_canonical_sha256():
        raise ValueError("Fingerprint mismatch: formal_runtime_config_canonical_sha256")

    dummy_agent = type("StubAgent", (), {
        "model": FORMAL_PATIENT_AGENT_MODEL,
        "temperature": FORMAL_PATIENT_AGENT_TEMPERATURE,
    })()

    for cond in ("A", "B", "C", "D"):
        cfg = formal_ablation_config(cond)
        require_frozen_formal_config(cfg)
        require_frozen_formal_execution_envelope(
            config=cfg,
            patient_agent=dummy_agent,
            subprocess_timeout_seconds=FORMAL_SUBPROCESS_TIMEOUT_SECONDS,
        )


def check_12_profiles_validator() -> None:
    """驗證 WS4 12 profiles 驗證器完全通過。"""
    from llm_ablation_paper.workstream_4_patient_simulation.scripts.validate_profiles import main as validate_main
    code = validate_main([])
    if code != 0:
        raise RuntimeError(f"12 profiles validator failed with exit code {code} (fail-closed)")


PILOT_VALID_COMPLETION_REASONS = frozenset({"PATIENT_GOAL_MET", "MAX_TURNS"})


def inspect_run_for_nested_errors(run_dir: Path) -> tuple[bool, Optional[str]]:
    """遞迴檢視 run_dir 下的 roleplay_result.json 與 trajectories.jsonl 內部每一輪。

    若發現任一輪：
      - record.harness_turn (或 record) 的 termination_reason == "ERROR"
      - record.harness_turn (或 record) 的 error 非 None 且非空
      - retry_meta.errors 含有非瞬態失敗 (如 second_call_error、400、BadRequest 等)
    一律回傳 (True, error_detail)。
    若無錯誤則回傳 (False, None)。
    """
    p_dir = Path(run_dir).resolve()
    roleplay_file = p_dir / "roleplay_result.json"
    if not roleplay_file.exists() and (p_dir.parent / "roleplay_result.json").exists():
        roleplay_file = p_dir.parent / "roleplay_result.json"

    # 1. 檢視 roleplay_result.json
    if roleplay_file.exists():
        try:
            rp_data = json.loads(roleplay_file.read_text(encoding="utf-8"))
            if rp_data.get("termination_reason") == "ERROR":
                return True, f"roleplay_result termination_reason is ERROR (error_metadata: {rp_data.get('error_metadata')})"
            if rp_data.get("error_metadata") is not None:
                return True, f"roleplay_result contains error_metadata: {rp_data.get('error_metadata')}"

            # 檢視每一輪 records
            for rec in rp_data.get("records", []):
                h_turn = rec.get("harness_turn") or {}
                if h_turn.get("termination_reason") == "ERROR":
                    return True, f"turn {rec.get('turn')} harness_turn termination_reason is ERROR"
                if h_turn.get("error") is not None and str(h_turn.get("error")).strip():
                    return True, f"turn {rec.get('turn')} harness_turn contains error: {h_turn.get('error')}"
                if h_turn.get("error_metadata") is not None:
                    return True, f"turn {rec.get('turn')} harness_turn contains error_metadata: {h_turn.get('error_metadata')}"

                # 檢視 retry_metadata
                for meta_key in ("retry_metadata", "patient_retry_metadata"):
                    meta = rec.get(meta_key) or h_turn.get(meta_key) or {}
                    if isinstance(meta, dict):
                        for err in meta.get("errors", []):
                            err_s = str(err).lower()
                            if any(k in err_s for k in ["second_call_error", "badrequest", "invalid parameter", "validationerror", "400"]):
                                return True, f"turn {rec.get('turn')} non-transient retry error: {err}"
        except Exception as e:
            if not isinstance(e, (json.JSONDecodeError, OSError)):
                raise

    # 2. 檢視 trajectories.jsonl
    traj_candidates = [
        p_dir / "trajectories.jsonl",
        p_dir / "isolated_state" / "trajectories.jsonl",
    ]
    if p_dir.name == "isolated_state":
        traj_candidates.append(p_dir.parent / "trajectories.jsonl")
    for tp in traj_candidates:
        if tp.exists():
            try:
                for line in tp.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    turn_obj = json.loads(line)
                    if turn_obj.get("termination_reason") == "ERROR":
                        return True, f"trajectory turn {turn_obj.get('turn_index')} termination_reason is ERROR"
                    if turn_obj.get("error") is not None and str(turn_obj.get("error")).strip():
                        return True, f"trajectory turn {turn_obj.get('turn_index')} contains error: {turn_obj.get('error')}"
                    if turn_obj.get("error_metadata") is not None:
                        return True, f"trajectory turn {turn_obj.get('turn_index')} contains error_metadata: {turn_obj.get('error_metadata')}"
                    meta = turn_obj.get("retry_metadata") or {}
                    if isinstance(meta, dict):
                        for err in meta.get("errors", []):
                            err_s = str(err).lower()
                            if any(k in err_s for k in ["second_call_error", "badrequest", "invalid parameter", "validationerror", "400"]):
                                return True, f"trajectory turn {turn_obj.get('turn_index')} non-transient retry error: {err}"
            except Exception as e:
                if not isinstance(e, (json.JSONDecodeError, OSError)):
                    raise

    return False, None


def check_pilot_completed_cleanly(pilot_summary_path: Path) -> None:
    """驗證 pilot summary 存在且四組 A/B/C/D 完整且無 ERROR，終止理由必須為 PATIENT_GOAL_MET 或 MAX_TURNS。"""
    p = Path(pilot_summary_path).resolve()
    if not p.exists():
        raise FileNotFoundError(
            f"Pilot summary file not found at {p}. Pilot must be successfully completed before batch (fail-closed)."
        )
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"Cannot parse pilot summary JSON: {e}") from e

    runs = data.get("runs", [])
    completed_conds = set()
    pilot_root = p.parent

    for r in runs:
        cond = r.get("condition")
        reason = r.get("termination_reason")
        err = r.get("error")
        run_id = r.get("run_id")

        if err is not None:
            raise RuntimeError(
                f"Pilot run for condition {cond} failed with non-null error metadata: {err!r}. Formal batch cannot proceed."
            )
        if reason not in PILOT_VALID_COMPLETION_REASONS:
            raise RuntimeError(
                f"Pilot run for condition {cond} terminated with invalid reason: {reason!r}. "
                f"Must be one of {sorted(PILOT_VALID_COMPLETION_REASONS)} (COMMON_INPUT_BLOCK, ERROR, None, or unknown are rejected) (fail-closed)."
            )

        # 深入檢驗 run 目錄下的內部輪次 (fail-closed)
        # run_id 為 None/缺漏時不得對其做路徑運算；僅在候選目錄存在時才遞迴檢視。
        candidate_dirs: list[Path] = []
        if run_id:
            candidate_dirs.append(pilot_root / run_id)
        if cond:
            candidate_dirs.append(pilot_root / f"WS4-PILOT-{DEFAULT_PILOT_PATIENT_ID}-{cond}")
        for cdir in candidate_dirs:
            if cdir.exists():
                has_nested_err, err_detail = inspect_run_for_nested_errors(cdir)
                if has_nested_err:
                    raise RuntimeError(
                        f"Pilot run for condition {cond} ({cdir.name}) contains nested ERROR: {err_detail}. "
                        f"Formal batch cannot proceed (fail-closed)."
                    )

        completed_conds.add(cond)
    required = {"A", "B", "C", "D"}
    if not required.issubset(completed_conds):
        raise RuntimeError(
            f"Pilot runs missing required conditions {sorted(required - completed_conds)}. Only found: {sorted(completed_conds)}"
        )


def check_distinct_output_roots(batch_root: Path, pilot_root: Path) -> None:
    """驗證 batch 輸出目錄與 pilot 輸出目錄彼此隔離。"""
    if batch_root.resolve() == pilot_root.resolve():
        raise ValueError(
            f"Batch output root ({batch_root}) must be distinct from Pilot output root ({pilot_root})."
        )


# =====================================================================
# 3. Pilot 執行子命令 (重用既有 RoleplayRunner)
# =====================================================================
def run_pilot(
    *,
    patient_id: str = DEFAULT_PILOT_PATIENT_ID,
    output_root: Optional[Path] = None,
    resume: bool = False,
    runner_kwargs: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """執行 1 profile x 4 conditions pilot，重用既有 RoleplayRunner。"""
    pilot_root = Path(output_root).resolve() if output_root is not None else DEFAULT_PILOT_ROOT.resolve()
    profiles = load_profiles()
    if patient_id not in profiles:
        raise KeyError(f"Unknown patient profile: {patient_id}")

    provider_config = {"provider": "gemini"}

    # 支援測試時之 Mock 注入
    if runner_kwargs is not None and "patient_agent" in runner_kwargs:
        patient_agent = runner_kwargs["patient_agent"]
        if "provider_config" in runner_kwargs:
            provider_config = runner_kwargs["provider_config"]
        client_factory = runner_kwargs.get("client_factory")
        fake_talker_responses = runner_kwargs.get("fake_talker_responses")
    else:
        from llm_ablation_paper.workstream_1_technical_lead.harness import ensure_provider_ready
        ensure_provider_ready(provider_config)
        patient_agent = GeminiPatientAgent.from_environment(
            model=FORMAL_PATIENT_AGENT_MODEL,
            temperature=FORMAL_PATIENT_AGENT_TEMPERATURE,
        )
        client_factory = None
        fake_talker_responses = None

    runner = RoleplayRunner(
        patient_agent=patient_agent,
        output_root=pilot_root,
        config_factory=lambda condition: formal_ablation_config(condition),
        provider_config=provider_config,
        client_factory=client_factory,
        subprocess_timeout_seconds=FORMAL_SUBPROCESS_TIMEOUT_SECONDS,
    )

    results = []
    for cond in ("A", "B", "C", "D"):
        res = runner.run_condition(
            profile=profiles[patient_id],
            condition=cond,
            resume=resume,
            fake_talker_responses=fake_talker_responses,
            run_suffix="PILOT",
        )
        results.append(res)

    for item in results:
        run_dir = pilot_root / item["run_id"]
        has_err, err_detail = inspect_run_for_nested_errors(run_dir)
        if has_err:
            item["termination_reason"] = "ERROR"
            if item.get("error_metadata") is None:
                item["error_metadata"] = {"nested_error": err_detail}

    summary = {
        "execution_mode": "formal_pilot",
        "formal_experiment_started": False,
        "twelve_by_four_started": False,
        "pilot_patient_id": patient_id,
        "run_suffix": "PILOT",
        "output_root": str(pilot_root),
        "runtime_configuration_source": "WS1 frozen formal config",
        "subprocess_timeout_seconds": FORMAL_SUBPROCESS_TIMEOUT_SECONDS,
        "runs": [{
            "run_id": item["run_id"],
            "condition": item["condition"],
            "user_id": item["user_id"],
            "turn_count": len(item.get("records", [])),
            "termination_reason": item.get("termination_reason"),
            "error": item.get("error_metadata"),
        } for item in results],
    }
    pilot_root.mkdir(parents=True, exist_ok=True)
    summary_path = pilot_root / "formal_pilot_summary.json"
    tmp_sum = summary_path.with_suffix(".tmp." + uuid.uuid4().hex[:8])
    with open(tmp_sum, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    tmp_sum.replace(summary_path)
    return summary


# =====================================================================
# 4. Batch 執行子命令 (Controller 內完成 12x4 = 48 條)
# =====================================================================
def run_batch(
    *,
    confirm_token: str,
    output_root: Optional[Path] = None,
    pilot_summary_path: Optional[Path] = None,
    resume: bool = False,
    skip_git_check: bool = False,
    runner_kwargs: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """執行完整 12x4 = 48 條消融實驗軌跡。"""
    # 1. 嚴格比對確認字串
    if confirm_token != CONFIRM_FORMAL_12X4_RUN_STRING:
        raise ValueError(
            f"Invalid confirmation token. Formal 12x4 batch requires exact string "
            f"--confirm-formal-run '{CONFIRM_FORMAL_12X4_RUN_STRING}' (fail-closed)."
        )

    batch_root = Path(output_root).resolve() if output_root is not None else DEFAULT_BATCH_ROOT.resolve()
    p_summary = (
        Path(pilot_summary_path).resolve()
        if pilot_summary_path is not None
        else (DEFAULT_PILOT_ROOT / "formal_pilot_summary.json").resolve()
    )
    pilot_root = p_summary.parent

    # 2. 六大 Preflight 驗證 (Fail-closed)
    if not skip_git_check:
        check_clean_working_tree()
    check_frozen_config_and_envelope()
    check_12_profiles_validator()
    check_pilot_completed_cleanly(p_summary)
    check_distinct_output_roots(batch_root, pilot_root)

    profiles = load_profiles()
    sorted_patient_ids = sorted(profiles.keys())
    if len(sorted_patient_ids) != 12:
        raise ValueError(f"Expected exactly 12 patient profiles, got {len(sorted_patient_ids)}")

    # 3. 檢查已存在衝突（若無 --resume）
    if not resume:
        for pid in sorted_patient_ids:
            for cond in ("A", "B", "C", "D"):
                target_dir = batch_root / f"WS4-BATCH-{pid}-{cond}"
                if target_dir.exists():
                    raise FileExistsError(
                        f"Target run directory already exists: {target_dir}. "
                        "Cannot overwrite formal batch runs. Use --resume to resume existing runs."
                    )

    provider_config = {"provider": "gemini"}
    if runner_kwargs is not None and "patient_agent" in runner_kwargs:
        patient_agent = runner_kwargs["patient_agent"]
        if "provider_config" in runner_kwargs:
            provider_config = runner_kwargs["provider_config"]
        client_factory = runner_kwargs.get("client_factory")
        fake_talker_responses = runner_kwargs.get("fake_talker_responses")
    else:
        from llm_ablation_paper.workstream_1_technical_lead.harness import ensure_provider_ready
        ensure_provider_ready(provider_config)
        patient_agent = GeminiPatientAgent.from_environment(
            model=FORMAL_PATIENT_AGENT_MODEL,
            temperature=FORMAL_PATIENT_AGENT_TEMPERATURE,
        )
        client_factory = None
        fake_talker_responses = None

    runner = RoleplayRunner(
        patient_agent=patient_agent,
        output_root=batch_root,
        config_factory=lambda condition: formal_ablation_config(condition),
        provider_config=provider_config,
        client_factory=client_factory,
        subprocess_timeout_seconds=FORMAL_SUBPROCESS_TIMEOUT_SECONDS,
    )

    batch_root.mkdir(parents=True, exist_ok=True)
    results = []
    # 4. Controller 內部執行 12 profiles x 4 conditions = 48 runs
    for pid in sorted_patient_ids:
        prof = profiles[pid]
        for cond in ("A", "B", "C", "D"):
            res = runner.run_condition(
                profile=prof,
                condition=cond,
                resume=resume,
                fake_talker_responses=fake_talker_responses,
                run_suffix="BATCH",
            )
            results.append(res)

    for item in results:
        run_dir = batch_root / item["run_id"]
        has_err, err_detail = inspect_run_for_nested_errors(run_dir)
        if has_err:
            item["termination_reason"] = "ERROR"
            if item.get("error_metadata") is None:
                item["error_metadata"] = {"nested_error": err_detail}

    summary = {
        "execution_mode": "formal_12x4_batch",
        "total_trajectories": len(results),
        "expected_trajectories": 48,
        "completed_trajectories": len([r for r in results if r.get("termination_reason") != "ERROR"]),
        "error_trajectories": len([r for r in results if r.get("termination_reason") == "ERROR"]),
        "output_root": str(batch_root),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "runs": [{
            "run_id": item["run_id"],
            "patient_id": item["patient_id"],
            "condition": item["condition"],
            "user_id": item["user_id"],
            "turn_count": len(item.get("records", [])),
            "termination_reason": item.get("termination_reason"),
            "error": item.get("error_metadata"),
        } for item in results],
    }
    summary_path = batch_root / "formal_batch_summary.json"
    tmp_sum = summary_path.with_suffix(".tmp." + uuid.uuid4().hex[:8])
    with open(tmp_sum, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    tmp_sum.replace(summary_path)
    return summary


# =====================================================================
# 5. Blind Export 子命令 (洩漏掃描與盲化導出)
# =====================================================================
def scan_blinded_payload_for_leakage(payload_str: str, mapping: dict[str, str]) -> None:
    """嚴格掃描盲化後的 payload 字串，若發現 mapping 明文、內部標籤或未脫敏 condition 立即拋錯。"""
    # 1. 不得出現 mapping 鍵值配對或未脫敏 condition
    for real_cond, opaque_id in mapping.items():
        if f'"{real_cond}": "{opaque_id}"' in payload_str or f'"{real_cond}":"{opaque_id}"' in payload_str:
            raise ValueError(f"Leakage detected: mapping pair {real_cond}:{opaque_id} in payload")
        if f'"condition": "{real_cond}"' in payload_str or f'"condition":"{real_cond}"' in payload_str:
            raise ValueError(f"Leakage detected: unblinded condition label {real_cond} in payload")

    # 2. 不得出現內部消融標誌
    forbidden_keys = [
        "enable_planner", "enable_dynamic_tool_gate", "enable_output_guard",
        "enable_forced_retrieval", "enable_fixed_warning_append",
        "enable_question_budget_postprocessing", "dynamic_tool_gate"
    ]
    for fk in forbidden_keys:
        if f'"{fk}"' in payload_str:
            raise ValueError(f"Leakage detected: internal ablation flag {fk} in payload")


def run_blind_export(
    *,
    raw_dir: Path | str,
    mapping_file: Path | str,
    output_dir: Path | str = DEFAULT_BLINDED_ROOT,
    require_completed: bool = True,
) -> dict[str, Any]:
    """使用私有 mapping 生成 WS5 盲評用的 blinded transcripts。永遠 require_completed=True，拒絕未完成軌跡。"""
    if not require_completed:
        raise ValueError(
            "Formal blind-export strictly requires completed trajectories; "
            "incomplete export is prohibited (fail-closed)."
        )
    raw_path = Path(raw_dir).resolve()
    map_path = Path(mapping_file).resolve()
    out_path = Path(output_dir).resolve()

    mapping = load_frozen_condition_mapping(map_path)
    out_path.mkdir(parents=True, exist_ok=True)

    traj_files = list(raw_path.glob("**/trajectories.jsonl"))
    if not traj_files:
        raise FileNotFoundError(f"No trajectories.jsonl found under {raw_path}")

    exported = []
    skipped_canary = 0
    skipped_pilot = 0
    skipped_error = 0

    for tf in sorted(traj_files):
        run_dir = tf.parent
        parent_run_dir = run_dir.parent if run_dir.name == "isolated_state" else run_dir
        run_id = parent_run_dir.name

        # 排除 canary
        if "CANARY" in run_id.upper():
            skipped_canary += 1
            continue
        # 排除 pilot
        if "PILOT" in run_id.upper():
            skipped_pilot += 1
            continue

        # 排除 ERROR (含頂層與 nested ERROR)
        has_err, err_detail = inspect_run_for_nested_errors(parent_run_dir)
        if has_err:
            skipped_error += 1
            continue

        state_dir = run_dir if (run_dir / "trajectories.jsonl").exists() else (parent_run_dir / "isolated_state")
        blinded_obj = to_blinded_contract_trajectory(
            run_id=run_id,
            state_dir=state_dir,
            condition_mapping=mapping,
            require_completed=True,
        )

        payload_str = json.dumps(blinded_obj, ensure_ascii=False)
        scan_blinded_payload_for_leakage(payload_str, mapping)

        b_id = blinded_obj["run_id"]
        target_file = out_path / f"{b_id}.json"
        tmp_target = target_file.with_suffix(".tmp." + uuid.uuid4().hex[:8])
        with open(tmp_target, "w", encoding="utf-8") as f:
            json.dump(blinded_obj, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        tmp_target.replace(target_file)
        exported.append(b_id)

    summary = {
        "status": "exported",
        "exported_count": len(exported),
        "skipped_canary": skipped_canary,
        "skipped_pilot": skipped_pilot,
        "skipped_error": skipped_error,
        "output_dir": str(out_path),
        "exported_ids": exported,
    }
    return summary


# =====================================================================
# 6. CLI 解析與進入點
# =====================================================================
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="WS1 Formal Experiment Controller: pilot, 12x4 batch, and blinded export.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True, help="Subcommand to execute")

    # 1. generate-mapping
    p_map = subparsers.add_parser("generate-mapping", help="Generate cryptographically random condition mapping")
    p_map.add_argument("--output-file", type=Path, default=DEFAULT_MAPPING_FILE, help="Target file for secret mapping")

    # 2. pilot
    p_pilot = subparsers.add_parser("pilot", help="Run 1 patient (SP-001) x 4 conditions pilot")
    p_pilot.add_argument("--patient-id", type=str, default=DEFAULT_PILOT_PATIENT_ID, help="Patient ID for pilot")
    p_pilot.add_argument("--output-root", type=Path, default=DEFAULT_PILOT_ROOT, help="Output root for pilot runs")
    p_pilot.add_argument("--resume", action="store_true", help="Resume interrupted pilot runs")

    # 3. batch
    p_batch = subparsers.add_parser("batch", help="Run formal 12 profiles x 4 conditions (48 runs) batch")
    p_batch.add_argument(
        "--confirm-formal-run",
        type=str,
        required=True,
        help=f"Must exactly match '{CONFIRM_FORMAL_12X4_RUN_STRING}'",
    )
    p_batch.add_argument("--output-root", type=Path, default=DEFAULT_BATCH_ROOT, help="Output root for batch runs")
    p_batch.add_argument(
        "--pilot-summary-path",
        type=Path,
        default=DEFAULT_PILOT_ROOT / "formal_pilot_summary.json",
        help="Path to pilot summary file for validation",
    )
    p_batch.add_argument("--resume", action="store_true", help="Resume interrupted batch runs")

    # 4. blind-export
    p_export = subparsers.add_parser("blind-export", help="Export blinded trajectories with private mapping")
    p_export.add_argument("--raw-dir", type=Path, required=True, help="Root directory containing raw trajectories")
    p_export.add_argument("--mapping-file", type=Path, required=True, help="Path to secret condition mapping JSON")
    p_export.add_argument("--output-dir", type=Path, default=DEFAULT_BLINDED_ROOT, help="Target directory for blinded JSONs")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.subcommand == "generate-mapping":
        mapping = generate_frozen_mapping(
            output_file=args.output_file,
        )
        print(f"PASS: Secret mapping generated and saved to {args.output_file} (A-D opaque keys ready).")
        return 0

    elif args.subcommand == "pilot":
        summary = run_pilot(
            patient_id=args.patient_id,
            output_root=args.output_root,
            resume=args.resume,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    elif args.subcommand == "batch":
        summary = run_batch(
            confirm_token=args.confirm_formal_run,
            output_root=args.output_root,
            pilot_summary_path=args.pilot_summary_path,
            resume=args.resume,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    elif args.subcommand == "blind-export":
        summary = run_blind_export(
            raw_dir=args.raw_dir,
            mapping_file=args.mapping_file,
            output_dir=args.output_dir,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
