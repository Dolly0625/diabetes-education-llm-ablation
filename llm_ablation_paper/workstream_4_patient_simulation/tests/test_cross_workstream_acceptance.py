"""WS4 Cross-Workstream Acceptance Tests (STAGE 1 & STAGE 2: Full Fake E2E).

This test module verifies the end-to-end cross-workstream contracts between:
- Workstream 4 (Patient Simulation / agy2)
- Workstream 1 (Batch Controller / agy1)
- Workstream 5 (LLM Judge & Analysis / agy3)

STAGE 2 Implementation:
1. Orchestrates agy1 Batch Controller (`run_batch`) in fake/offline mode to generate
   48 raw trajectories (12 profiles x 4 conditions).
2. Executes `run_blind_export` to produce 48 blinded transcripts with secret mapping.
3. Verifies zero leaks (no condition A-D, no enable_* flags, no mapping pairs,
   no raw talker/planner/guard states).
4. Executes agy3 `run_judge.py --mode fake` to evaluate all 48 trajectories.
5. Executes agy3 `run_analysis.py` to aggregate results into summary.json, tables,
   results.csv, and failure_distribution.png, verifying missing != zero.
6. Verifies fail-closed rejection on incomplete, pilot, canary, or leaked inputs.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
import uuid
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llm_ablation_paper.workstream_1_technical_lead.harness.config import (
    FORMAL_MAX_TURNS,
    FORMAL_SEED,
    formal_ablation_config,
)
from llm_ablation_paper.workstream_1_technical_lead.harness.runner import (
    to_blinded_contract_trajectory,
)
from llm_ablation_paper.workstream_1_technical_lead.scripts.run_formal_experiment import (
    CONFIRM_FORMAL_12X4_RUN_STRING,
    PILOT_VALID_COMPLETION_REASONS,
    build_parser,
    check_pilot_completed_cleanly,
    generate_frozen_mapping,
    main as formal_experiment_main,
    run_batch,
    run_blind_export,
    scan_blinded_payload_for_leakage,
)
from llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation import (
    DeterministicPatientAgent,
    FAKE_TALKER_RESPONSES,
    RoleplayRunner,
    TERMINATION_REASONS,
    load_profiles,
    run_input_block_canary,
)
from llm_ablation_paper.workstream_5_judge_analysis.run_analysis import (
    load_and_invert_condition_mapping,
    run_analysis_cli,
)
from llm_ablation_paper.workstream_5_judge_analysis.run_judge import (
    FORMAL_CONFIRM_TOKEN,
    run_judge_cli,
)


# ==============================================================================
# Contract Definitions and Validators
# ==============================================================================

EXPECTED_PATIENT_IDS = {f"SP-{i:03d}" for i in range(1, 13)}
EXPECTED_CONDITIONS = {"A", "B", "C", "D"}
EXPECTED_TOTAL_TRAJECTORIES = 48


def validate_agy1_batch_manifest_contract(manifest: dict[str, Any]) -> None:
    """Validate agy1 Batch Controller output manifest against cross-workstream contracts.

    Invariants enforced:
    - Exactly 48 trajectories (12 profiles x 4 conditions).
    - All 12 frozen profiles represented without missing or unexpected profiles.
    - Each profile has exactly conditions A, B, C, D with matched seed (FORMAL_SEED).
    - Isolated run_id, user_id, and state_dir per trajectory.
    - No pilot trajectories or canary data mixed in.
    - All trajectories completed with recognized termination reasons.
    """
    runs = manifest.get("runs", [])
    if len(runs) != EXPECTED_TOTAL_TRAJECTORIES:
        raise ValueError(
            f"agy1 batch manifest must contain exactly {EXPECTED_TOTAL_TRAJECTORIES} runs, got {len(runs)}"
        )

    seen_pairs: set[tuple[str, str]] = set()
    user_ids: set[str] = set()
    run_ids: set[str] = set()
    state_dirs: set[str] = set()

    for item in runs:
        pid = item.get("patient_id")
        cond = item.get("condition")
        run_id = item.get("run_id", "")
        user_id = item.get("user_id", "")
        state_dir = item.get("state_dir_id", "")
        seed = item.get("seed")
        reason = item.get("termination_reason")

        if pid not in EXPECTED_PATIENT_IDS:
            raise ValueError(f"unknown or non-frozen patient_id in formal batch: {pid}")
        if cond not in EXPECTED_CONDITIONS:
            raise ValueError(f"unknown condition: {cond}")
        if (pid, cond) in seen_pairs:
            raise ValueError(f"duplicate (patient_id, condition) pair: ({pid}, {cond})")
        seen_pairs.add((pid, cond))

        # Seed pairing (checked if provided)
        if seed is not None and seed != FORMAL_SEED:
            raise ValueError(f"trajectory {run_id} seed {seed} does not match FORMAL_SEED {FORMAL_SEED}")

        # Unique identity & state isolation
        if not run_id or run_id in run_ids:
            raise ValueError(f"duplicate or missing run_id: {run_id}")
        run_ids.add(run_id)

        if not user_id or user_id in user_ids:
            raise ValueError(f"duplicate or missing user_id: {user_id}")
        user_ids.add(user_id)

        if state_dir:
            if state_dir in state_dirs:
                raise ValueError(f"duplicate state_dir: {state_dir}")
            state_dirs.add(state_dir)

        # Anti-pollution checks
        lower_run = (run_id + user_id + state_dir).lower()
        if "pilot" in lower_run:
            raise ValueError(f"pilot pollution detected in formal batch run: {run_id}")
        if "canary" in lower_run:
            raise ValueError(f"canary data leaked into formal comparison runs: {run_id}")

        if reason not in TERMINATION_REASONS:
            raise ValueError(f"invalid termination reason in run {run_id}: {reason}")

    # Check 12 x 4 coverage
    profile_coverage = {pid: set() for pid in EXPECTED_PATIENT_IDS}
    for pid, cond in seen_pairs:
        profile_coverage[pid].add(cond)
    for pid, conds in profile_coverage.items():
        if conds != EXPECTED_CONDITIONS:
            raise ValueError(f"patient {pid} missing conditions: {EXPECTED_CONDITIONS - conds}")


def validate_agy3_judge_input_contract(blinded_trajectories: list[dict[str, Any]]) -> None:
    """Validate input collection to agy3 LLM Judge CLI.

    Invariants enforced:
    - Exactly 48 completed blinded trajectories.
    - Exactly 12 profiles with 4 unique opaque condition secrets each.
    - Strictly no pilot data, canary data, or raw condition leakages.
    - All internal flags (enable_*, planner_model, etc.) physically stripped.
    """
    if len(blinded_trajectories) != EXPECTED_TOTAL_TRAJECTORIES:
        raise ValueError(
            f"Judge input must contain exactly {EXPECTED_TOTAL_TRAJECTORIES} blinded trajectories, "
            f"got {len(blinded_trajectories)}"
        )

    profile_conditions: dict[str, set[str]] = {pid: set() for pid in EXPECTED_PATIENT_IDS}
    all_run_ids: set[str] = set()

    def _inspect_for_leakage(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                k_lower = k.lower()
                if k_lower in {"condition", "mapping", "planner_model", "judge_model"}:
                    raise ValueError(f"forbidden key leaked at {path}.{k}")
                if k_lower.startswith("enable_"):
                    raise ValueError(f"internal toggle leaked at {path}.{k}")
                if isinstance(v, str):
                    v_lower = v.lower()
                    if "ws4_sp-" in v_lower or "pilot" in v_lower:
                        raise ValueError(f"internal identifier leaked in value at {path}.{k}: {v}")
                _inspect_for_leakage(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, elem in enumerate(obj):
                _inspect_for_leakage(elem, f"{path}[{i}]")

    for idx, item in enumerate(blinded_trajectories):
        pid = item.get("patient_id")
        if pid not in EXPECTED_PATIENT_IDS:
            raise ValueError(f"trajectory {idx} has invalid patient_id: {pid}")

        blinded_run_id = item.get("run_id", "")
        if not blinded_run_id.startswith("BLIND-"):
            raise ValueError(f"run_id must be blinded (BLIND-*), got {blinded_run_id}")
        if blinded_run_id in all_run_ids:
            raise ValueError(f"duplicate blinded run_id: {blinded_run_id}")
        all_run_ids.add(blinded_run_id)

        secret = item.get("condition_secret")
        if not secret or not isinstance(secret, str):
            raise ValueError(f"missing or invalid condition_secret in trajectory {blinded_run_id}")
        if secret in EXPECTED_CONDITIONS:
            raise ValueError(f"unblinded raw condition name leaked: {secret}")

        profile_conditions[pid].add(secret)

        turns = item.get("turns") if "turns" in item else item.get("records")
        if not isinstance(turns, list) or len(turns) == 0:
            raise ValueError(f"trajectory {blinded_run_id} has empty or non-list turns/records")

        # Deep inspection for leakage
        _inspect_for_leakage(item)

    # Verify 4 distinct condition secrets per profile
    for pid, secrets in profile_conditions.items():
        if len(secrets) != 4:
            raise ValueError(f"profile {pid} must have exactly 4 condition secrets, got {len(secrets)}")


# ==============================================================================
# Part 1: WS4 Runner Contract Tests (Fake Fixtures, No agy1/agy3 Dependency)
# ==============================================================================

def test_ws4_runner_isolated_state_and_user_contract(tmp_path: Path):
    """Verify that WS4 runner executes all 4 conditions with strictly isolated IDs and states."""
    profiles = load_profiles()
    profile = profiles["SP-001"]
    runner = RoleplayRunner(patient_agent=DeterministicPatientAgent(), output_root=tmp_path)

    results = [
        runner.run_condition(
            profile=profile,
            condition=cond,
            fake_talker_responses=list(FAKE_TALKER_RESPONSES),
            run_suffix="FAKE",
        )
        for cond in ("A", "B", "C", "D")
    ]

    # Verify 4 distinct conditions
    assert [r["condition"] for r in results] == ["A", "B", "C", "D"]

    # Verify user_id isolation (none equal)
    user_ids = [r["user_id"] for r in results]
    assert len(set(user_ids)) == 4
    for uid in user_ids:
        assert "sp-001" in uid.lower()

    # Verify run_id isolation
    run_ids = [r["run_id"] for r in results]
    assert len(set(run_ids)) == 4

    # Verify state directory isolation on disk
    for r in results:
        state_dir = tmp_path / r["run_id"] / "isolated_state"
        assert state_dir.exists()
        assert (state_dir / "trajectories.jsonl").exists()
        assert (tmp_path / r["run_id"] / "ws4_runner_checkpoint.json").exists()


def test_ws4_runner_checkpoint_resume_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify checkpoint persistence and resume recovery contract."""
    profile = load_profiles()["SP-002"]
    runner = RoleplayRunner(
        patient_agent=DeterministicPatientAgent(),
        output_root=tmp_path,
        retry_delays=(),
        sleep=lambda _: None,
    )

    harness_calls = {"count": 0}

    def failing_harness(**kwargs):
        harness_calls["count"] += 1
        if harness_calls["count"] == 3:
            raise RuntimeError("simulated transient network partition")
        turn_idx = len(kwargs["messages"]) - 1
        return [{
            "run_id": kwargs.get("run_id", "WS4-FAKE-SP-002-B"),
            "condition": "B",
            "patient_id": "SP-002",
            "assistant_response": "請問您有規律驗血糖嗎？",
            "termination_reason": None,
            "turn_index": turn_idx,
            "user_message": kwargs["messages"][-1],
        }]

    monkeypatch.setattr(runner, "_call_harness", failing_harness)

    # First attempt fails at turn 3
    with pytest.raises(RuntimeError, match="network partition"):
        runner.run_condition(profile=profile, condition="B", fake_talker_responses=["ok"] * 6)

    ckpt_path = tmp_path / "WS4-FAKE-SP-002-B" / "ws4_runner_checkpoint.json"
    assert ckpt_path.exists()
    checkpoint = json.loads(ckpt_path.read_text(encoding="utf-8"))
    assert checkpoint["termination_reason"] == "ERROR"
    assert len(checkpoint["records"]) == 2

    # Second attempt with resume=True succeeds
    def succeeding_harness(**kwargs):
        turn_idx = len(kwargs["messages"]) - 1
        return [{
            "run_id": kwargs.get("run_id", "WS4-FAKE-SP-002-B"),
            "condition": "B",
            "patient_id": "SP-002",
            "assistant_response": "請問您有規律驗血糖嗎？",
            "termination_reason": None,
            "turn_index": turn_idx,
            "user_message": kwargs["messages"][-1],
        }]

    monkeypatch.setattr(runner, "_call_harness", succeeding_harness)
    resumed = runner.run_condition(
        profile=profile,
        condition="B",
        fake_talker_responses=["ok"] * 6,
        resume=True,
    )

    assert resumed["termination_reason"] == "MAX_TURNS"
    assert len(resumed["records"]) == FORMAL_MAX_TURNS


def test_ws4_runner_all_termination_reasons_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify that all four TERMINATION_REASONS conform to the contract."""
    profile = load_profiles()["SP-003"]

    # 1. MAX_TURNS
    runner_max = RoleplayRunner(patient_agent=DeterministicPatientAgent(), output_root=tmp_path)
    res_max = runner_max.run_condition(
        profile=profile, condition="A", fake_talker_responses=list(FAKE_TALKER_RESPONSES)
    )
    assert res_max["termination_reason"] == "MAX_TURNS"

    # 2. PATIENT_GOAL_MET
    class EarlyGoalAgent:
        def next_turn(self, *, assistant_output, **_):
            if assistant_output is None:
                return {
                    "patient_utterance": "我想詢問飲食問題。",
                    "should_end": False,
                    "termination_reason": "MAX_TURNS",
                    "disclosed_facts": [],
                    "evidence": "初次提問",
                }
            return {
                "patient_utterance": "好的，我完全清楚了，謝謝！",
                "should_end": True,
                "termination_reason": "PATIENT_GOAL_MET",
                "disclosed_facts": [],
                "evidence": "目標滿足",
            }

    runner_goal = RoleplayRunner(patient_agent=EarlyGoalAgent(), output_root=tmp_path)
    res_goal = runner_goal.run_condition(
        profile=profile, condition="B", fake_talker_responses=list(FAKE_TALKER_RESPONSES)
    )
    assert res_goal["termination_reason"] == "PATIENT_GOAL_MET"

    # 3. COMMON_INPUT_BLOCK (Canary)
    res_canary = run_input_block_canary(tmp_path, condition="A")
    assert res_canary["termination_reason"] == "COMMON_INPUT_BLOCK"
    assert res_canary.get("canary") is True

    # 4. ERROR
    runner_err = RoleplayRunner(
        patient_agent=DeterministicPatientAgent(), output_root=tmp_path, retry_delays=(), sleep=lambda _: None
    )

    def error_turn(**kwargs):
        turn = {
            "run_id": kwargs.get("run_id", "WS4-FAKE-SP-001-C"),
            "condition": "C",
            "patient_id": "SP-001",
            "assistant_response": "error response",
            "termination_reason": "ERROR",
            "turn_index": len(kwargs["messages"]) - 1,
            "user_message": kwargs["messages"][-1],
        }
        return [turn]

    monkeypatch.setattr(runner_err, "_call_harness", error_turn)
    res_err = runner_err.run_condition(
        profile=profile, condition="C", fake_talker_responses=list(FAKE_TALKER_RESPONSES)
    )
    assert res_err["termination_reason"] == "ERROR"


def test_ws4_blinded_export_contract(tmp_path: Path):
    """Verify that WS1 to_blinded_contract_trajectory safely exports WS4 results without leakage."""
    profile = load_profiles()["SP-004"]
    runner = RoleplayRunner(patient_agent=DeterministicPatientAgent(), output_root=tmp_path)
    result = runner.run_condition(
        profile=profile, condition="D", fake_talker_responses=list(FAKE_TALKER_RESPONSES)
    )

    fake_mapping = {
        "A": "COND-0000AAAA",
        "B": "COND-0000BBBB",
        "C": "COND-0000CCCC",
        "D": "COND-0000DDDD",
    }

    state_dir = tmp_path / result["run_id"] / "isolated_state"
    blinded = to_blinded_contract_trajectory(
        run_id=result["run_id"],
        state_dir=state_dir,
        condition_mapping=fake_mapping,
        require_completed=True,
    )

    # Invariants
    assert blinded["patient_id"] == "SP-004"
    assert blinded["run_id"].startswith("BLIND-")
    assert blinded["state_dir_id"].startswith("STATE-BLIND-")
    assert blinded["condition_secret"] == "COND-0000DDDD"
    assert len(blinded["turns"]) == FORMAL_MAX_TURNS

    # No forbidden keys or leakages
    dumped = json.dumps(blinded, ensure_ascii=False).lower()
    assert "enable_" not in dumped
    assert "planner_model" not in dumped
    assert "ws4_sp-" not in dumped
    assert "ws4-fake" not in dumped


# ==============================================================================
# Part 2: Cross-Workstream Acceptance Contract Specifications
# ==============================================================================

def test_contract_agy1_batch_controller_contract_spec():
    """Verify agy1 Batch Controller validator on synthetic compliant and non-compliant manifests."""
    valid_runs = []
    for i in range(1, 13):
        pid = f"SP-{i:03d}"
        for cond in ("A", "B", "C", "D"):
            valid_runs.append({
                "patient_id": pid,
                "condition": cond,
                "seed": FORMAL_SEED,
                "run_id": f"WS4-FORMAL-{pid}-{cond}",
                "user_id": f"ws4_{pid}_{cond}_formal",
                "state_dir_id": f"state_{pid}_{cond}",
                "termination_reason": "MAX_TURNS",
            })

    valid_manifest = {
        "execution_mode": "formal_batch",
        "formal_experiment_started": True,
        "runs": valid_runs,
    }

    # Should pass without error
    validate_agy1_batch_manifest_contract(valid_manifest)

    # Test 1: Wrong trajectory count (47 instead of 48)
    invalid_manifest_short = copy.deepcopy(valid_manifest)
    invalid_manifest_short["runs"].pop()
    with pytest.raises(ValueError, match="48"):
        validate_agy1_batch_manifest_contract(invalid_manifest_short)

    # Test 2: Seed mismatch
    invalid_manifest_seed = copy.deepcopy(valid_manifest)
    invalid_manifest_seed["runs"][0]["seed"] = 999
    with pytest.raises(ValueError, match="FORMAL_SEED"):
        validate_agy1_batch_manifest_contract(invalid_manifest_seed)

    # Test 3: Pilot pollution
    invalid_manifest_pilot = copy.deepcopy(valid_manifest)
    invalid_manifest_pilot["runs"][0]["run_id"] = "WS4-PILOT-SP-001-A"
    with pytest.raises(ValueError, match="pilot pollution"):
        validate_agy1_batch_manifest_contract(invalid_manifest_pilot)

    # Test 4: Canary pollution
    invalid_manifest_canary = copy.deepcopy(valid_manifest)
    invalid_manifest_canary["runs"][0]["run_id"] = "WS4-FORMAL-SP-CANARY-INPUT-BLOCK-A"
    invalid_manifest_canary["runs"][0]["patient_id"] = "SP-CANARY-INPUT-BLOCK"
    with pytest.raises(ValueError, match="non-frozen patient_id"):
        validate_agy1_batch_manifest_contract(invalid_manifest_canary)


def test_contract_agy3_judge_input_validation_contract():
    """Verify agy3 LLM Judge input validator on compliant and non-compliant blinded inputs."""
    valid_blinded = []
    fake_secrets = {
        "A": "COND-1111AAAA",
        "B": "COND-2222BBBB",
        "C": "COND-3333CCCC",
        "D": "COND-4444DDDD",
    }
    for i in range(1, 13):
        pid = f"SP-{i:03d}"
        for cond in ("A", "B", "C", "D"):
            valid_blinded.append({
                "patient_id": pid,
                "run_id": f"BLIND-RUN-{pid}-{cond}",
                "state_dir_id": f"STATE-BLIND-{pid}-{cond}",
                "condition_secret": fake_secrets[cond],
                "turns": [{
                    "turn_index": 0,
                    "user_message": "您好，我剛被診斷出第 2 型糖尿病。",
                    "assistant_response": "您好！請不用過度擔心，我們會一起協助您了解血糖控制方式。",
                }],
            })

    # Should pass without error
    validate_agy3_judge_input_contract(valid_blinded)

    # Test 1: Raw condition leaked in condition_secret
    invalid_leaked = copy.deepcopy(valid_blinded)
    invalid_leaked[0]["condition_secret"] = "A"
    with pytest.raises(ValueError, match="unblinded raw condition name leaked"):
        validate_agy3_judge_input_contract(invalid_leaked)

    # Test 2: Forbidden internal toggle leaked
    invalid_toggle = copy.deepcopy(valid_blinded)
    invalid_toggle[0]["enable_planner"] = True
    with pytest.raises(ValueError, match="internal toggle leaked"):
        validate_agy3_judge_input_contract(invalid_toggle)

    # Test 3: Pilot string leaked in value
    invalid_pilot = copy.deepcopy(valid_blinded)
    invalid_pilot[0]["notes"] = "pilot run test"
    with pytest.raises(ValueError, match="internal identifier leaked"):
        validate_agy3_judge_input_contract(invalid_pilot)

    # Test 4: Incomplete turns
    invalid_records = copy.deepcopy(valid_blinded)
    invalid_records[0]["turns"] = []
    with pytest.raises(ValueError, match="empty or non-list turns/records"):
        validate_agy3_judge_input_contract(invalid_records)


# ==============================================================================
# Part 3: STAGE 2 Cross-Workstream Fake E2E Acceptance Tests
# ==============================================================================

def test_stage2_cross_workstream_fake_e2e_pipeline(tmp_path: Path):
    """STAGE 2 Full Fake End-to-End Acceptance Pipeline.

    Orchestrates:
    WS1 Batch Controller (fake mode) -> 48 raw trajectories
    -> WS1 Blind Export (secret mapping) -> 48 blinded trajectories (leakage check)
    -> WS5 Judge CLI (fake mode) -> 48 judge evaluations
    -> WS5 Analysis CLI -> summary.json, tables, results.csv, figure.
    """
    root = tmp_path / "e2e_workstream_test"
    root.mkdir(parents=True, exist_ok=True)

    pilot_dir = root / "pilot"
    pilot_dir.mkdir(parents=True, exist_ok=True)
    pilot_summary_file = pilot_dir / "formal_pilot_summary.json"
    pilot_runs = [{
        "run_id": f"WS4-PILOT-SP-001-{c}",
        "condition": c,
        "user_id": "ws4_sp-001_a_pilot",
        "turn_count": 6,
        "termination_reason": "MAX_TURNS",
        "error": None,
    } for c in ("A", "B", "C", "D")]
    pilot_summary_file.write_text(
        json.dumps({"execution_mode": "formal_pilot", "runs": pilot_runs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    raw_dir = root / "raw_transcripts"
    blinded_dir = root / "blinded_transcripts"
    judge_raw_dir = root / "judge_raw"
    judge_results_file = judge_raw_dir / "judge_results.jsonl"
    judge_ckpt_dir = judge_raw_dir / "checkpoints"
    derived_dir = root / "derived_results"
    figures_dir = root / "figures"
    temp_mapping_file = root / "temp_frozen_mapping.json"

    # Step 1: Execute agy1 Batch Controller with offline deterministic fake runner
    def _fake_run_condition(self, profile, condition, resume=False, fake_talker_responses=None, run_suffix="BATCH"):
        pid = profile["patient_id"] if isinstance(profile, dict) else profile.patient_id
        run_id = f"WS4-{run_suffix}-{pid}-{condition}"
        run_dir = self.output_root / run_id
        state_dir = run_dir / "isolated_state"
        state_dir.mkdir(parents=True, exist_ok=True)

        config_data = {
            "run_id": run_id,
            "condition": condition,
            "patient_id": pid,
            "max_turns": 6,
            "seed": FORMAL_SEED,
            "model": "fake-model",
            "temperature": 0.0,
        }
        (state_dir / "config.json").write_text(json.dumps(config_data, ensure_ascii=False), encoding="utf-8")

        turns = []
        for i in range(6):
            t = {
                "run_id": run_id,
                "condition": condition,
                "patient_id": pid,
                "research_patient_id": pid,
                "turn_index": i,
                "user_message": f"病患第 {i+1} 輪提問",
                "assistant_response": f"衛教師第 {i+1} 輪回應",
                "called_tools": [],
                "exposed_tools": [],
            }
            if i == 5:
                t["termination_reason"] = "MAX_TURNS"
            turns.append(t)
        (state_dir / "trajectories.jsonl").write_text(
            "\n".join(json.dumps(t, ensure_ascii=False) for t in turns) + "\n",
            encoding="utf-8",
        )

        roleplay_data = {
            "run_id": run_id,
            "condition": condition,
            "patient_id": pid,
            "termination_reason": "MAX_TURNS",
            "error_metadata": None,
            "records": [{"turn": i + 1} for i in range(6)],
        }
        (run_dir / "roleplay_result.json").write_text(
            json.dumps(roleplay_data, ensure_ascii=False), encoding="utf-8"
        )

        return {
            "run_id": run_id,
            "patient_id": pid,
            "condition": condition,
            "user_id": f"ws4_{pid.lower()}_{condition.lower()}_{run_suffix.lower()}",
            "state_dir_id": "isolated_state",
            "records": [{"turn": i + 1} for i in range(6)],
            "termination_reason": "MAX_TURNS",
            "error_metadata": None,
        }

    with patch.object(RoleplayRunner, "run_condition", _fake_run_condition):
        batch_summary = run_batch(
            confirm_token=CONFIRM_FORMAL_12X4_RUN_STRING,
            output_root=raw_dir,
            pilot_summary_path=pilot_summary_file,
            skip_git_check=True,
            runner_kwargs={"patient_agent": None},
        )

    # Validate Batch Controller Output Contract
    assert batch_summary["total_trajectories"] == 48
    assert batch_summary["expected_trajectories"] == 48
    assert batch_summary["completed_trajectories"] == 48
    assert batch_summary["error_trajectories"] == 0
    validate_agy1_batch_manifest_contract(batch_summary)

    # Step 2: Generate secret mapping and export blinded transcripts
    secret_mapping = generate_frozen_mapping(output_file=temp_mapping_file)
    blind_summary = run_blind_export(
        raw_dir=raw_dir,
        mapping_file=temp_mapping_file,
        output_dir=blinded_dir,
        require_completed=True,
    )

    assert blind_summary["exported_count"] == 48
    assert blind_summary["skipped_canary"] == 0
    assert blind_summary["skipped_pilot"] == 0
    assert blind_summary["skipped_error"] == 0

    blinded_files = list(blinded_dir.glob("*.json"))
    assert len(blinded_files) == 48

    # Step 3: Deep inspection of blinded contracts (zero leaks)
    blinded_trajectories = []
    seen_blinded_ids = set()
    patient_secret_counts: dict[str, set[str]] = {}

    from llm_ablation_paper.workstream_5_judge_analysis.sanitizer import build_judge_payload

    contract_forbidden_patterns = [
        "enable_planner", "enable_dynamic_tool_gate", "enable_output_guard",
        "enable_forced_retrieval", "enable_fixed_warning_append",
        "enable_question_budget_postprocessing", "dynamic_tool_gate",
    ]

    for bf in blinded_files:
        content_text = bf.read_text(encoding="utf-8")
        traj = json.loads(content_text)
        blinded_trajectories.append(traj)

        # 1. Check mapping pairs not leaked
        for c, s in secret_mapping.items():
            assert f'"{c}": "{s}"' not in content_text
            assert f'"{c}":"{s}"' not in content_text
            assert f'"condition": "{c}"' not in content_text
            assert f'"condition":"{c}"' not in content_text

        # 2. Check forbidden ablation flags not leaked in blinded contract
        for fp in contract_forbidden_patterns:
            assert fp not in content_text

        # 3. Verify that Judge payload physically strips internal states (state_dir_id, planner_state, raw_talker_output, guard_action)
        judge_payload = build_judge_payload(traj)
        payload_str = json.dumps(judge_payload, ensure_ascii=False)
        assert "state_dir_id" not in payload_str
        assert "planner_state" not in payload_str
        assert "raw_talker_output" not in payload_str
        assert "guard_action" not in payload_str

        # 3. Check blinded IDs
        b_id = traj["run_id"]
        assert b_id.startswith("BLIND-")
        assert b_id not in seen_blinded_ids
        seen_blinded_ids.add(b_id)
        assert traj["state_dir_id"].startswith("STATE-BLIND-")

        # 4. Check opaque condition secrets
        secret = traj["condition_secret"]
        assert secret in secret_mapping.values()
        pid = traj["patient_id"]
        assert pid in EXPECTED_PATIENT_IDS
        patient_secret_counts.setdefault(pid, set()).add(secret)

        # 5. Check turns completeness
        assert len(traj["turns"]) == FORMAL_MAX_TURNS

    assert len(patient_secret_counts) == 12
    for pid, s_set in patient_secret_counts.items():
        assert len(s_set) == 4

    validate_agy3_judge_input_contract(blinded_trajectories)

    # Step 4: Run agy3 LLM Judge CLI in offline fake mode
    judge_exit_code = run_judge_cli([
        "--mode", "fake",
        "--input-path", str(blinded_dir),
        "--output-file", str(judge_results_file),
        "--checkpoint-dir", str(judge_ckpt_dir),
    ])
    assert judge_exit_code == 0
    assert judge_results_file.exists()

    eval_records = [
        json.loads(line) for line in judge_results_file.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(eval_records) == 48

    # Step 5: Run agy3 Analysis CLI to produce tables, csv, and figures
    analysis_exit_code = run_analysis_cli([
        "--trajectories-path", str(blinded_dir),
        "--judge-results-path", str(judge_results_file),
        "--output-dir", str(derived_dir),
        "--figures-dir", str(figures_dir),
        "--allow-incomplete",
    ])
    assert analysis_exit_code == 0

    # Step 6: Validate generated derived artifacts & missing!=zero invariant
    summary_file = derived_dir / "summary.json"
    table_md_file = derived_dir / "main_table.md"
    table_tex_file = derived_dir / "main_table.tex"
    results_csv_file = derived_dir / "results.csv"
    fig_file = figures_dir / "failure_distribution.png"

    assert summary_file.exists()
    assert table_md_file.exists()
    assert table_tex_file.exists()
    assert results_csv_file.exists()
    assert fig_file.exists()

    summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
    groups = summary_data.get("summary_by_group", {})
    assert len(groups) == 4
    for cond_id, grp in groups.items():
        assert cond_id in secret_mapping.values()
        assert grp.get("sample_size") == 12
        # missing != zero check: unexposed tools should be None or omitted when not triggered
        prog = grp.get("programmatic", {})
        assert prog.get("unexposed_tool_call_rate") is None or isinstance(prog.get("unexposed_tool_call_rate"), float)

    md_text = table_md_file.read_text(encoding="utf-8")
    for secret in secret_mapping.values():
        assert secret in md_text


def test_stage2_blind_export_excludes_and_rejects(tmp_path: Path):
    """Verify that blind-export rejects incomplete trajectories and excludes pilot/canary/errors."""
    raw_dir = tmp_path / "raw_runs"
    out_dir = tmp_path / "blinded_transcripts"
    map_file = tmp_path / "mapping.json"
    generate_frozen_mapping(output_file=map_file)

    def _make_run(run_id: str, term_reason: str | None, is_error: bool = False):
        r_dir = raw_dir / run_id
        s_dir = r_dir / "isolated_state"
        s_dir.mkdir(parents=True, exist_ok=True)
        (s_dir / "config.json").write_text(
            json.dumps({"run_id": run_id, "condition": "A", "patient_id": "SP-001", "max_turns": 2}),
            encoding="utf-8",
        )
        lines = [
            json.dumps({
                "run_id": run_id,
                "condition": "A",
                "patient_id": "SP-001",
                "research_patient_id": "SP-001",
                "turn_index": 0,
                "user_message": "q1",
                "assistant_response": "a1",
            }),
            json.dumps({
                "run_id": run_id,
                "condition": "A",
                "patient_id": "SP-001",
                "research_patient_id": "SP-001",
                "turn_index": 1,
                "user_message": "q2",
                "assistant_response": "a2",
                "termination_reason": term_reason,
            }),
        ]
        (s_dir / "trajectories.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (r_dir / "roleplay_result.json").write_text(
            json.dumps({
                "run_id": run_id, "condition": "A", "patient_id": "SP-001",
                "termination_reason": "ERROR" if is_error else (term_reason or "MAX_TURNS"),
            }),
            encoding="utf-8",
        )

    # Compliant completed run
    _make_run("WS4-BATCH-SP-001-A", "MAX_TURNS")
    # Canary run (should be excluded)
    _make_run("WS4-CANARY-SP-001-A", "COMMON_INPUT_BLOCK")
    # Pilot run (should be excluded)
    _make_run("WS4-PILOT-SP-001-A", "MAX_TURNS")
    # Error run (should be excluded)
    _make_run("WS4-BATCH-SP-002-A", "ERROR", is_error=True)

    summary = run_blind_export(
        raw_dir=raw_dir,
        mapping_file=map_file,
        output_dir=out_dir,
        require_completed=True,
    )
    assert summary["exported_count"] == 1
    assert summary["skipped_canary"] == 1
    assert summary["skipped_pilot"] == 1
    assert summary["skipped_error"] == 1

    # Incomplete run rejection test
    incomplete_raw = tmp_path / "incomplete_raw"
    _make_run_inc = lambda: (
        incomplete_raw.mkdir(parents=True, exist_ok=True),
        (incomplete_raw / "WS4-BATCH-INC-A" / "isolated_state").mkdir(parents=True, exist_ok=True),
        (incomplete_raw / "WS4-BATCH-INC-A" / "isolated_state" / "config.json").write_text(
            json.dumps({"run_id": "WS4-BATCH-INC-A", "condition": "A", "patient_id": "SP-001", "max_turns": 6})
        ),
        (incomplete_raw / "WS4-BATCH-INC-A" / "isolated_state" / "trajectories.jsonl").write_text(
            json.dumps({
                "run_id": "WS4-BATCH-INC-A",
                "condition": "A",
                "patient_id": "SP-001",
                "research_patient_id": "SP-001",
                "turn_index": 0,
                "user_message": "hi",
                "assistant_response": "ok",
            }) + "\n"
        ),
    )
    _make_run_inc()
    with pytest.raises(ValueError, match="is incomplete"):
        run_blind_export(
            raw_dir=incomplete_raw,
            mapping_file=map_file,
            output_dir=tmp_path / "blinded_inc",
            require_completed=True,
        )


def test_stage2_judge_and_analysis_rejects_leaks_and_violations(tmp_path: Path):
    """Verify that Judge and Analysis fail closed against leaks, duplicates, pilot, and canary."""
    judge_in = tmp_path / "judge_inputs"
    judge_in.mkdir(parents=True, exist_ok=True)
    out_file = tmp_path / "judge_results.jsonl"
    ckpt_dir = tmp_path / "checkpoints"

    def _write_single_traj(filename: str, payload: dict):
        (judge_in / filename).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    # Test 1: Pilot in input is rejected
    _write_single_traj("p1.json", {
        "run_id": "BLIND-PILOT-001",
        "patient_id": "SP-001",
        "condition_secret": "COND-1111",
        "turns": [{"turn_index": 0, "user_message": "hi", "assistant_response": "ok"}],
        "termination_reason": "MAX_TURNS",
    })
    code = run_judge_cli([
        "--mode", "fake",
        "--input-path", str(judge_in),
        "--output-file", str(out_file),
        "--checkpoint-dir", str(ckpt_dir),
    ])
    assert code != 0
    (judge_in / "p1.json").unlink()

    # Test 2: Canary in input is rejected
    _write_single_traj("c1.json", {
        "run_id": "BLIND-CANARY-001",
        "patient_id": "SP-CANARY-001",
        "condition_secret": "COND-1111",
        "turns": [{"turn_index": 0, "user_message": "hi", "assistant_response": "ok"}],
        "termination_reason": "COMMON_INPUT_BLOCK",
    })
    code = run_judge_cli([
        "--mode", "fake",
        "--input-path", str(judge_in),
        "--output-file", str(out_file),
        "--checkpoint-dir", str(ckpt_dir),
    ])
    assert code != 0
    (judge_in / "c1.json").unlink()

    # Test 3: Raw condition leak is rejected
    _write_single_traj("leak.json", {
        "run_id": "BLIND-001",
        "patient_id": "SP-001",
        "condition": "A",
        "condition_secret": "COND-1111",
        "turns": [{"turn_index": 0, "user_message": "hi", "assistant_response": "ok"}],
        "termination_reason": "MAX_TURNS",
    })
    code = run_judge_cli([
        "--mode", "fake",
        "--input-path", str(judge_in),
        "--output-file", str(out_file),
        "--checkpoint-dir", str(ckpt_dir),
    ])
    assert code != 0
    (judge_in / "leak.json").unlink()


# ==============================================================================
# Part 4: PHASE M2.2 Adversarial Cross-Workstream Acceptance Tests
# ==============================================================================

def test_adversarial_deblinding_direction_and_table_restoration(tmp_path: Path):
    """M2.2-1: Verify that deblinding inversion correctly maps opaque condition secrets back to A-D.

    Pipeline:
    1. WS1 generate_frozen_mapping creates secret mapping {"A": "COND-...", ...}.
    2. run_batch generates 48 raw trajectories (12 patients x 4 conditions).
    3. run_blind_export uses the mapping to produce 48 blinded transcripts.
    4. run_judge evaluates the 48 blinded transcripts.
    5. WS5 run_analysis receives the EXACT SAME mapping file, validates canonical format,
       inverts it (COND-... -> A-D), and produces unblinded summary and tables.
    6. Assertions:
       - summary.json summary_by_group keys are exactly {"A", "B", "C", "D"}.
       - Each group has sample_size == 12.
       - main_table.md and results.csv restore rows for A, B, C, D.
       - Proves real->opaque export + opaque->A-D inversion are 100% aligned.
    """
    root = tmp_path / "deblind_adversarial_test"
    root.mkdir(parents=True, exist_ok=True)

    pilot_dir = root / "pilot"
    pilot_dir.mkdir(parents=True, exist_ok=True)
    pilot_summary_file = pilot_dir / "formal_pilot_summary.json"
    pilot_runs = [{
        "run_id": f"WS4-PILOT-SP-001-{c}",
        "condition": c,
        "user_id": "ws4_sp-001_a_pilot",
        "turn_count": 6,
        "termination_reason": "MAX_TURNS",
        "error": None,
    } for c in ("A", "B", "C", "D")]
    pilot_summary_file.write_text(
        json.dumps({"execution_mode": "formal_pilot", "runs": pilot_runs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    raw_dir = root / "raw_transcripts"
    blinded_dir = root / "blinded_transcripts"
    judge_raw_dir = root / "judge_raw"
    judge_results_file = judge_raw_dir / "judge_results.jsonl"
    judge_ckpt_dir = judge_raw_dir / "checkpoints"
    derived_dir = root / "derived_results"
    figures_dir = root / "figures"
    map_file = root / "frozen_condition_mapping.json"

    # 1. WS1 generate_frozen_mapping
    canonical_mapping = generate_frozen_mapping(output_file=map_file)
    assert set(canonical_mapping.keys()) == {"A", "B", "C", "D"}

    # 2. Fake run_batch
    def _fake_run_condition(self, profile, condition, resume=False, fake_talker_responses=None, run_suffix="BATCH"):
        pid = profile["patient_id"] if isinstance(profile, dict) else profile.patient_id
        run_id = f"WS4-{run_suffix}-{pid}-{condition}"
        run_dir = self.output_root / run_id
        state_dir = run_dir / "isolated_state"
        state_dir.mkdir(parents=True, exist_ok=True)

        config_data = {
            "run_id": run_id,
            "condition": condition,
            "patient_id": pid,
            "max_turns": 6,
            "seed": FORMAL_SEED,
            "model": "fake-model",
            "temperature": 0.0,
        }
        (state_dir / "config.json").write_text(json.dumps(config_data, ensure_ascii=False), encoding="utf-8")

        turns = []
        for i in range(6):
            t = {
                "run_id": run_id,
                "condition": condition,
                "patient_id": pid,
                "research_patient_id": pid,
                "turn_index": i,
                "user_message": f"病患第 {i+1} 輪提問",
                "assistant_response": f"衛教師第 {i+1} 輪針對條件 {condition} 之回應",
                "called_tools": [],
                "exposed_tools": [],
            }
            if i == 5:
                t["termination_reason"] = "MAX_TURNS"
            turns.append(t)
        (state_dir / "trajectories.jsonl").write_text(
            "\n".join(json.dumps(t, ensure_ascii=False) for t in turns) + "\n",
            encoding="utf-8",
        )

        roleplay_data = {
            "run_id": run_id,
            "condition": condition,
            "patient_id": pid,
            "termination_reason": "MAX_TURNS",
            "error_metadata": None,
            "records": [{"turn": i + 1} for i in range(6)],
        }
        (run_dir / "roleplay_result.json").write_text(
            json.dumps(roleplay_data, ensure_ascii=False), encoding="utf-8"
        )

        return {
            "run_id": run_id,
            "patient_id": pid,
            "condition": condition,
            "user_id": f"ws4_{pid.lower()}_{condition.lower()}_{run_suffix.lower()}",
            "state_dir_id": "isolated_state",
            "records": [{"turn": i + 1} for i in range(6)],
            "termination_reason": "MAX_TURNS",
            "error_metadata": None,
        }

    with patch.object(RoleplayRunner, "run_condition", _fake_run_condition):
        run_batch(
            confirm_token=CONFIRM_FORMAL_12X4_RUN_STRING,
            output_root=raw_dir,
            pilot_summary_path=pilot_summary_file,
            skip_git_check=True,
            runner_kwargs={"patient_agent": None},
        )

    # 3. WS1 blind-export
    run_blind_export(
        raw_dir=raw_dir,
        mapping_file=map_file,
        output_dir=blinded_dir,
        require_completed=True,
    )

    # 4. WS5 run_judge (fake mode)
    judge_code = run_judge_cli([
        "--mode", "fake",
        "--input-path", str(blinded_dir),
        "--output-file", str(judge_results_file),
        "--checkpoint-dir", str(judge_ckpt_dir),
    ])
    assert judge_code == 0

    # 5. WS5 run_analysis WITH deblinding mapping
    analysis_code = run_analysis_cli([
        "--trajectories-path", str(blinded_dir),
        "--judge-results-path", str(judge_results_file),
        "--output-dir", str(derived_dir),
        "--figures-dir", str(figures_dir),
        "--mapping-file", str(map_file),
        "--allow-incomplete",
    ])
    assert analysis_code == 0

    # 6. Verify Deblinded Output Restores Canonical Conditions A-D
    summary_file = derived_dir / "summary.json"
    summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
    summary_by_group = summary_data.get("summary_by_group", {})

    # Groups MUST be unblinded to A, B, C, D
    assert set(summary_by_group.keys()) == {"A", "B", "C", "D"}
    for cond in ("A", "B", "C", "D"):
        assert summary_by_group[cond]["sample_size"] == 12

    # Inversion verification
    inverted = load_and_invert_condition_mapping(map_file)
    for cond, secret in canonical_mapping.items():
        assert inverted[secret] == cond

    # CSV and Markdown tables must feature A, B, C, D
    csv_text = (derived_dir / "results.csv").read_text(encoding="utf-8")
    for cond in ("A", "B", "C", "D"):
        assert f"\n{cond}," in csv_text or csv_text.startswith(f"{cond},")

    md_text = (derived_dir / "main_table.md").read_text(encoding="utf-8")
    for cond in ("A", "B", "C", "D"):
        assert f"| {cond} |" in md_text


def test_adversarial_mapping_no_overwrite_and_byte_integrity(tmp_path: Path):
    """M2.2-2: Verify mapping cannot be overwritten and preserves byte-for-byte integrity on collision."""
    map_file = tmp_path / "protected_mapping.json"

    # First generation succeeds
    m1 = generate_frozen_mapping(output_file=map_file)
    assert set(m1.keys()) == {"A", "B", "C", "D"}
    original_bytes = map_file.read_bytes()
    assert len(original_bytes) > 0

    # Second generation attempt via function MUST raise FileExistsError (Fail-Closed)
    with pytest.raises(FileExistsError, match="overwrite is strictly prohibited"):
        generate_frozen_mapping(output_file=map_file)

    # Verify byte-for-byte integrity
    assert map_file.read_bytes() == original_bytes

    # Third generation attempt via CLI MUST also fail and preserve bytes
    with pytest.raises(FileExistsError, match="overwrite is strictly prohibited"):
        formal_experiment_main(["generate-mapping", "--output-file", str(map_file)])

    assert map_file.read_bytes() == original_bytes

    # Verify CLI parser does NOT expose --overwrite option
    parser = build_parser()
    subparsers_actions = [
        action for action in parser._actions
        if isinstance(action, type(parser._subparsers._actions[0]))
    ]
    gen_parser = parser._subparsers._actions[1].choices["generate-mapping"]
    gen_options = {opt for action in gen_parser._actions for opt in action.option_strings}
    assert "--overwrite" not in gen_options


def test_adversarial_blind_export_rejects_incomplete_and_no_cli_flag(tmp_path: Path):
    """M2.2-3: Verify blind-export fails closed on incomplete trajectories and lacks --allow-incomplete flag."""
    inc_raw_dir = tmp_path / "incomplete_raw"
    run_dir = inc_raw_dir / "WS4-BATCH-INC-001-A"
    state_dir = run_dir / "isolated_state"
    state_dir.mkdir(parents=True, exist_ok=True)

    (state_dir / "config.json").write_text(
        json.dumps({"run_id": "WS4-BATCH-INC-001-A", "condition": "A", "patient_id": "SP-001", "max_turns": 6}),
        encoding="utf-8",
    )
    # Only 2 turns out of 6, termination_reason is None
    lines = [
        json.dumps({
            "run_id": "WS4-BATCH-INC-001-A",
            "condition": "A",
            "patient_id": "SP-001",
            "research_patient_id": "SP-001",
            "turn_index": 0,
            "user_message": "q1",
            "assistant_response": "a1",
        }),
        json.dumps({
            "run_id": "WS4-BATCH-INC-001-A",
            "condition": "A",
            "patient_id": "SP-001",
            "research_patient_id": "SP-001",
            "turn_index": 1,
            "user_message": "q2",
            "assistant_response": "a2",
            "termination_reason": None,
        }),
    ]
    (state_dir / "trajectories.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (run_dir / "roleplay_result.json").write_text(
        json.dumps({"run_id": "WS4-BATCH-INC-001-A", "condition": "A", "patient_id": "SP-001", "termination_reason": None}),
        encoding="utf-8",
    )

    map_file = tmp_path / "temp_map.json"
    generate_frozen_mapping(output_file=map_file)
    blind_dir = tmp_path / "blinded_out"

    # Incomplete trajectory must raise ValueError
    with pytest.raises(ValueError, match="is incomplete"):
        run_blind_export(
            raw_dir=inc_raw_dir,
            mapping_file=map_file,
            output_dir=blind_dir,
            require_completed=True,
        )

    # Calling with require_completed=False must also fail closed
    with pytest.raises(ValueError, match="strictly requires completed trajectories"):
        run_blind_export(
            raw_dir=inc_raw_dir,
            mapping_file=map_file,
            output_dir=blind_dir,
            require_completed=False,
        )

    # Verify CLI parser does NOT expose --allow-incomplete option
    parser = build_parser()
    export_parser = parser._subparsers._actions[1].choices["blind-export"]
    export_options = {opt for action in export_parser._actions for opt in action.option_strings}
    assert "--allow-incomplete" not in export_options


def test_adversarial_pilot_termination_reasons_strictness(tmp_path: Path):
    """M2.2-4: Verify check_pilot_completed_cleanly strictly enforces {PATIENT_GOAL_MET, MAX_TURNS} and error=None."""
    def _create_summary(runs_data: list[dict[str, Any]]) -> Path:
        p = tmp_path / f"pilot_{uuid.uuid4().hex[:6]}" / "formal_pilot_summary.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"execution_mode": "formal_pilot", "runs": runs_data}), encoding="utf-8")
        return p

    base_runs = [
        {"condition": "A", "termination_reason": "MAX_TURNS", "error": None},
        {"condition": "B", "termination_reason": "MAX_TURNS", "error": None},
        {"condition": "C", "termination_reason": "MAX_TURNS", "error": None},
        {"condition": "D", "termination_reason": "MAX_TURNS", "error": None},
    ]

    # Valid Case 1: All MAX_TURNS
    p_valid1 = _create_summary(base_runs)
    check_pilot_completed_cleanly(p_valid1)

    # Valid Case 2: All PATIENT_GOAL_MET
    p_valid2 = _create_summary([
        {**r, "termination_reason": "PATIENT_GOAL_MET"} for r in base_runs
    ])
    check_pilot_completed_cleanly(p_valid2)

    # Valid Case 3: Mixed MAX_TURNS and PATIENT_GOAL_MET
    mixed_runs = [
        {"condition": "A", "termination_reason": "MAX_TURNS", "error": None},
        {"condition": "B", "termination_reason": "PATIENT_GOAL_MET", "error": None},
        {"condition": "C", "termination_reason": "MAX_TURNS", "error": None},
        {"condition": "D", "termination_reason": "PATIENT_GOAL_MET", "error": None},
    ]
    p_valid3 = _create_summary(mixed_runs)
    check_pilot_completed_cleanly(p_valid3)

    # Fail Case 1: COMMON_INPUT_BLOCK (Canary must not be accepted in pilot)
    p_canary = _create_summary([
        {"condition": "A", "termination_reason": "COMMON_INPUT_BLOCK", "error": None},
        {"condition": "B", "termination_reason": "MAX_TURNS", "error": None},
        {"condition": "C", "termination_reason": "MAX_TURNS", "error": None},
        {"condition": "D", "termination_reason": "MAX_TURNS", "error": None},
    ])
    with pytest.raises(RuntimeError, match="invalid reason: 'COMMON_INPUT_BLOCK'"):
        check_pilot_completed_cleanly(p_canary)

    # Fail Case 2: ERROR termination reason
    p_error_reason = _create_summary([
        {"condition": "A", "termination_reason": "MAX_TURNS", "error": None},
        {"condition": "B", "termination_reason": "ERROR", "error": None},
        {"condition": "C", "termination_reason": "MAX_TURNS", "error": None},
        {"condition": "D", "termination_reason": "MAX_TURNS", "error": None},
    ])
    with pytest.raises(RuntimeError, match="invalid reason: 'ERROR'"):
        check_pilot_completed_cleanly(p_error_reason)

    # Fail Case 3: None termination reason
    p_none_reason = _create_summary([
        {"condition": "A", "termination_reason": "MAX_TURNS", "error": None},
        {"condition": "B", "termination_reason": None, "error": None},
        {"condition": "C", "termination_reason": "MAX_TURNS", "error": None},
        {"condition": "D", "termination_reason": "MAX_TURNS", "error": None},
    ])
    with pytest.raises(RuntimeError, match="invalid reason: None"):
        check_pilot_completed_cleanly(p_none_reason)

    # Fail Case 4: Non-null error metadata (even if reason is MAX_TURNS)
    p_err_metadata = _create_summary([
        {"condition": "A", "termination_reason": "MAX_TURNS", "error": "Transient TimeoutError"},
        {"condition": "B", "termination_reason": "MAX_TURNS", "error": None},
        {"condition": "C", "termination_reason": "MAX_TURNS", "error": None},
        {"condition": "D", "termination_reason": "MAX_TURNS", "error": None},
    ])
    with pytest.raises(RuntimeError, match="non-null error metadata"):
        check_pilot_completed_cleanly(p_err_metadata)

    # Fail Case 5: Missing conditions
    p_missing = _create_summary([
        {"condition": "A", "termination_reason": "MAX_TURNS", "error": None},
        {"condition": "B", "termination_reason": "MAX_TURNS", "error": None},
        {"condition": "C", "termination_reason": "MAX_TURNS", "error": None},
    ])
    with pytest.raises(RuntimeError, match="missing required conditions"):
        check_pilot_completed_cleanly(p_missing)


def test_adversarial_judge_live_missing_key_fails_closed_before_canary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    """M2.2-5: Verify run_judge.py live mode fails closed before canary or network calls when GEMINI_API_KEY is missing."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "")

    spy_canaries = MagicMock()
    spy_live_adapter = MagicMock()
    monkeypatch.setattr(
        "llm_ablation_paper.workstream_5_judge_analysis.run_judge.verify_canaries",
        spy_canaries,
    )
    monkeypatch.setattr(
        "llm_ablation_paper.workstream_5_judge_analysis.run_judge.live_gemini_judge_adapter",
        spy_live_adapter,
    )

    dummy_input = tmp_path / "dummy_blinded"
    dummy_input.mkdir(parents=True, exist_ok=True)
    (dummy_input / "dummy.json").write_text(json.dumps({
        "run_id": "BLIND-001", "patient_id": "SP-001", "condition_secret": "COND-1111", "turns": []
    }))

    code = run_judge_cli([
        "--mode", "live",
        "--confirm-formal-judge", FORMAL_CONFIRM_TOKEN,
        "--input-path", str(dummy_input),
        "--output-file", str(tmp_path / "judge_results.jsonl"),
        "--checkpoint-dir", str(tmp_path / "ckpts"),
    ])

    # 1. Exit code MUST indicate failure
    assert code == 1

    # 2. Canary verification MUST NOT be invoked
    assert spy_canaries.call_count == 0

    # 3. Live Gemini API adapter MUST NOT be invoked
    assert spy_live_adapter.call_count == 0

    # 4. Error message in stderr must explain missing key
    captured = capsys.readouterr()
    assert "GEMINI_API_KEY environment variable is not set" in captured.err
