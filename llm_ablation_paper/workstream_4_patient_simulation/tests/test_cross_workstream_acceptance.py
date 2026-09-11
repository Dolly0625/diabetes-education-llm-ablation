"""WS4 Cross-Workstream Acceptance Tests (STAGE 1: Specifications and Fake Fixtures).

This test module verifies the cross-workstream contracts between:
- Workstream 4 (Patient Simulation / agy2)
- Workstream 1 (Batch Controller / agy1)
- Workstream 5 (LLM Judge & Analysis / agy3)

In STAGE 1, all tests run strictly offline with fake deterministic fixtures.
No external APIs are called, and no real condition mapping secrets are inspected.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

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
from llm_ablation_paper.workstream_4_patient_simulation.scripts.run_patient_simulation import (
    DeterministicPatientAgent,
    FAKE_TALKER_RESPONSES,
    RoleplayRunner,
    TERMINATION_REASONS,
    load_profiles,
    run_input_block_canary,
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

        # Seed pairing
        if seed != FORMAL_SEED:
            raise ValueError(f"trajectory {run_id} seed {seed} does not match FORMAL_SEED {FORMAL_SEED}")

        # Unique identity & state isolation
        if not run_id or run_id in run_ids:
            raise ValueError(f"duplicate or missing run_id: {run_id}")
        run_ids.add(run_id)

        if not user_id or user_id in user_ids:
            raise ValueError(f"duplicate or missing user_id: {user_id}")
        user_ids.add(user_id)

        if not state_dir or state_dir in state_dirs:
            raise ValueError(f"duplicate or missing state_dir: {state_dir}")
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
# Part 3: STAGE 2 Placeholder
# ==============================================================================

def test_stage2_e2e_fake_cross_workstream_acceptance_placeholder():
    """STAGE 2 Placeholder.

    This test marks the integration point for PHASE M2.1 STAGE 2.
    Once the project manager (PM) notifies that main contains the merged:
    - agy1 (Batch Controller)
    - agy3 (LLM Judge CLI)

    STAGE 2 will execute the full end-to-end fake test:
      agy1 Batch Controller (fake mode) -> 48 raw + 48 blinded transcripts
      -> agy3 Judge CLI (fake mode) -> judge results & statistical analysis.
    """
    stage2_ready = False  # Set to True in STAGE 2 when agy1 and agy3 modules exist in main
    if not stage2_ready:
        pytest.skip(
            "STAGE 2: Awaiting PM notification that main includes agy1 Batch Controller and agy3 Judge CLI."
        )
