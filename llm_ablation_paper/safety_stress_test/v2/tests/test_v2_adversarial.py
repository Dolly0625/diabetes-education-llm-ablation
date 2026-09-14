"""v2 adversarial fail-closed tests: mapping, fingerprint, state, canary, leakage, blocks, denominators."""
from __future__ import annotations

from pathlib import Path

import pytest

from llm_ablation_paper.safety_stress_test import runner as R1
from llm_ablation_paper.safety_stress_test.v2 import analysis_v2 as A2
from llm_ablation_paper.safety_stress_test.v2 import runner_v2 as RV2
from llm_ablation_paper.safety_stress_test.v2 import validate_v2 as V2
from llm_ablation_paper.workstream_1_technical_lead.harness.isolation import ensure_state_dir_empty


def test_none_mapping_hard_fails():
    with pytest.raises(R1.FrozenConfigError):
        R1.resolve_stress_mapping(None)


def test_wrong_mapping_hard_fails():
    with pytest.raises(ValueError):
        R1.resolve_stress_mapping({"A": "X", "B": "X", "C": "Y", "D": "Z"})


def test_tampered_frozen_fingerprint_hard_fails(monkeypatch):
    monkeypatch.setitem(R1.FROZEN_FINGERPRINTS, "talker_base_prompt_sha256", "0" * 64)
    with pytest.raises(R1.FrozenConfigError):
        R1.verify_frozen_fingerprints()


def test_contaminated_state_dir_hard_fails(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "trajectories.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(FileExistsError):
        ensure_state_dir_empty(state, resume=False, run_id="r")


def test_canary_mixed_into_main_hard_fails():
    with pytest.raises(R1.CanaryMixingError):
        R1.assert_main_batch_is_clean([{"run_id": "CANARY-INJ-DIRECT-abc", "patient_id": "SP-CANARY"}])


def test_payload_leak_hard_fails():
    with pytest.raises(RV2.V2LeakError):
        RV2.assert_payload_clean_v2(
            {
                "blinded_run_id": "BLIND-12345678",
                "patient_id": "SAFETY-RX-01-v2",
                "turns": [],
                "reference_facts": [],
                "condition_secret": "x",
            }
        )
    with pytest.raises(RV2.V2LeakError):
        RV2.assert_payload_clean_v2(
            {
                "blinded_run_id": "BLIND-12345678",
                "patient_id": "SAFETY-RX-01-v2",
                "turns": [{"turn": 1, "enable_output_guard": True}],
                "reference_facts": [],
            }
        )


def test_unknown_cf_code_hard_fails():
    bad = {
        "blinded_run_id": "BLIND-12345678",
        "taxonomy_version": "sst-taxonomy-v2",
        "critical_failure": True,
        "failure_types": ["CF_NEW_RISK"],
        "factual_state_errors": [],
        "quality_failures": [],
        "escalations": [],
        "scores": {"safety": 0, "tool_use": 2, "state_consistency": 2, "dialogue_planning": 2, "helpfulness": 2},
        "evidence": [{"turn": 1, "reason": "x"}],
        "confidence": "LOW",
    }
    with pytest.raises(V2.V2ValidationError):
        V2.judge_payload_invariants(bad, expected_blinded_run_id="BLIND-12345678")


def test_incomplete_block_hard_fails():
    runs = [{"set": "main_safety", "case_id": "SAFETY-RX-01-v2", "condition": c} for c in ("A", "B", "C")]
    with pytest.raises(RV2.V2BlockError):
        RV2.assert_complete_blocks_v2(runs, [{"case_id": "SAFETY-RX-01-v2"}], [], [])


def test_denominator_zero_is_null_not_zero():
    cell = A2._pct(0, 0)
    assert cell["n"] == 0
    assert cell["rate"] is None
    assert cell["wilson_95"] == [None, None]


def test_mapping_is_test_only_and_not_persisted():
    assert R1.MAPPING_MODE == "TEST_ONLY_FIXED"
    frozen = R1.REPO_ROOT / "artifacts" / "frozen_config" / "frozen_condition_mapping.json"
    assert not frozen.exists()
