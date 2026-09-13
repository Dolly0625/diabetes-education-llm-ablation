"""v2 live-runner offline tests: preflight gates, confirmation, cost guard, blinding, mock path.

No network: only the offline deterministic fake client factory is used.
"""
from __future__ import annotations

import json
import os
import stat

import pytest

from llm_ablation_paper.safety_stress_test import live_runner as L1
from llm_ablation_paper.safety_stress_test.v2 import live_runner_v2 as LV2
from llm_ablation_paper.safety_stress_test.v2 import runner_v2 as RV2

SHA = "a" * 40


def _probe(**overrides):
    probe = {
        "head": SHA,
        "dirty": False,
        "live_tag_exists": True,
        "live_tag_annotated": True,
        "live_tag_sha": SHA,
        "base_tag_sha": LV2.EXPECTED_BASE_SHA,
        "base_is_ancestor": True,
        "changed_vs_base": ["llm_ablation_paper/safety_stress_test/v2/live_runner_v2.py"],
    }
    probe.update(overrides)
    return probe


def test_cost_guard_constants_and_estimate():
    assert LV2.COST_CAP_USD == 0.25
    assert LV2.estimate_cost_usd() <= LV2.COST_CAP_USD


def test_cost_usd_none_when_usage_missing():
    assert LV2.cost_usd({"prompt_tokens": None, "completion_tokens": None}) is None
    assert LV2.cost_usd({"prompt_tokens": 1000, "completion_tokens": 1000}) > 0


def test_preflight_blocked_before_tag(tmp_path):
    report = LV2.preflight(
        "SAFETY-RX-01-v2",
        tmp_path,
        require_key=False,
        enforce_gitignore=False,
        git_probe_fn=lambda: _probe(live_tag_exists=False, live_tag_sha=""),
    )
    assert report["preflight"] == "BLOCKED"
    assert report["reason"] == "NOT_FROZEN"


def test_preflight_blocked_when_head_not_tag(tmp_path):
    report = LV2.preflight(
        "SAFETY-RX-01-v2", tmp_path, require_key=False, enforce_gitignore=False, git_probe_fn=lambda: _probe(head="b" * 40)
    )
    assert report["preflight"] == "BLOCKED"
    assert report["reason"] == "HEAD_NOT_LIVE_TAG"


def test_preflight_passes_offline_with_stub(tmp_path):
    report = LV2.preflight("SAFETY-RX-01-v2", tmp_path, require_key=False, enforce_gitignore=False, git_probe_fn=lambda: _probe())
    assert report["preflight"] == "PASS"
    assert report["model"] == "gemini-3.5-flash-lite"
    assert report["temperature"] == 0.3
    assert report["planner_temperature"] == 0.1


def test_preflight_dirty_tree_fails(tmp_path):
    with pytest.raises(LV2.LiveV2PreflightError):
        LV2.preflight("SAFETY-RX-01-v2", tmp_path, require_key=False, enforce_gitignore=False, git_probe_fn=lambda: _probe(dirty=True))


def test_preflight_out_of_scope_change_fails(tmp_path):
    with pytest.raises(LV2.LiveV2PreflightError):
        LV2.preflight(
            "SAFETY-RX-01-v2",
            tmp_path,
            require_key=False,
            enforce_gitignore=False,
            git_probe_fn=lambda: _probe(changed_vs_base=["diabetes_chatbot/planner.py"]),
        )


def test_wrong_confirmation_fails_closed(tmp_path):
    with pytest.raises(LV2.LiveV2ConfirmationError):
        LV2.run_live_pilot_v2(
            "SAFETY-RX-01-v2",
            tmp_path / "live",
            confirm="WRONG",
            client_factory=L1.offline_safe_client_factory,
            enforce_gitignore=False,
            git_probe_fn=lambda: _probe(),
        )
    assert not (tmp_path / "live").exists()


def test_mock_live_path_abcd_and_artifacts(tmp_path):
    root = tmp_path / "live"
    summary = LV2.run_live_pilot_v2(
        "SAFETY-RX-01-v2",
        root,
        confirm=LV2.CONFIRM_LIVE_PILOT_V2,
        client_factory=L1.offline_safe_client_factory,
        enforce_gitignore=False,
        git_probe_fn=lambda: _probe(),
    )
    assert summary["live_api"] is False
    assert summary["judge_used"] is False
    assert len(summary["runs"]) == 4
    assert all(r["n_turns"] == 3 for r in summary["runs"])
    assert all(r["termination_reason"] in ("MAX_TURNS", "PATIENT_GOAL_MET") for r in summary["runs"])
    blinded = sorted((root / "blinded").glob("BLIND-*.json"))
    assert len(blinded) == 4
    for p in blinded:
        payload = json.loads(p.read_text(encoding="utf-8"))
        RV2.assert_payload_clean_v2(payload)
        dumped = json.dumps(payload, ensure_ascii=False).lower()
        for token in ("enable_", "condition_secret", "raw_talker", "guard_action", "planner_state"):
            assert token not in dumped
    assert (root / "v2_usage_ledger.json").exists()
    assert summary["cost_usd_total"] <= LV2.COST_CAP_USD


def test_permissions_and_private_files(tmp_path):
    root = tmp_path / "live"
    LV2.run_live_pilot_v2(
        "SAFETY-RX-01-v2",
        root,
        confirm=LV2.CONFIRM_LIVE_PILOT_V2,
        client_factory=L1.offline_safe_client_factory,
        enforce_gitignore=False,
        git_probe_fn=lambda: _probe(),
    )
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    for name in ("v2_condition_mapping.json", "v2_live_pilot_manifest.json", "v2_live_pilot_summary.json", "v2_usage_ledger.json"):
        assert stat.S_IMODE((root / name).stat().st_mode) == 0o600, name


def test_new_run_rejects_nonempty_root(tmp_path):
    root = tmp_path / "live"
    root.mkdir()
    (root / "junk").write_text("x", encoding="utf-8")
    with pytest.raises(FileExistsError):
        LV2.run_live_pilot_v2(
            "SAFETY-RX-01-v2",
            root,
            confirm=LV2.CONFIRM_LIVE_PILOT_V2,
            client_factory=L1.offline_safe_client_factory,
            enforce_gitignore=False,
            git_probe_fn=lambda: _probe(),
        )


def test_secret_scrub_never_echoes():
    fake = "AIza" + "A" * 20
    assert fake not in L1._scrub(f"key={fake}")
    assert "[REDACTED]" in L1._scrub(f"key={fake}")


def test_cli_has_no_secret_or_model_flags():
    parser = LV2.build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--preflight", "--model", "x"])
    ns = parser.parse_args(["--preflight"])
    assert not hasattr(ns, "model")
    assert not hasattr(ns, "temperature")


def test_summary_contains_no_key_material(tmp_path):
    root = tmp_path / "live"
    LV2.run_live_pilot_v2(
        "SAFETY-RX-01-v2",
        root,
        confirm=LV2.CONFIRM_LIVE_PILOT_V2,
        client_factory=L1.offline_safe_client_factory,
        enforce_gitignore=False,
        git_probe_fn=lambda: _probe(),
    )
    blob = "\n".join(p.read_text(encoding="utf-8") for p in root.rglob("*") if p.is_file())
    assert "AIza" not in blob
    assert os.environ.get("GEMINI_API_KEY", "\u0000") not in blob


def test_scan_blinded_v2_rejects_condition_letter():
    with pytest.raises(LV2.LiveV2Error):
        LV2._scan_blinded_v2('{"blinded_run_id":"x","condition": "B"}', {"A": "COND-TEST-1"}, "run1")


def test_subdir_modes_are_private(tmp_path):
    root = tmp_path / "live"
    LV2.run_live_pilot_v2(
        "SAFETY-RX-01-v2",
        root,
        confirm=LV2.CONFIRM_LIVE_PILOT_V2,
        client_factory=L1.offline_safe_client_factory,
        enforce_gitignore=False,
        git_probe_fn=lambda: _probe(),
    )
    for sub in ("blinded", "scanner_v2", "quarantine"):
        assert stat.S_IMODE((root / sub).stat().st_mode) == 0o700, sub


def test_resume_is_idempotent_no_double_charge(tmp_path):
    root = tmp_path / "live"
    first = LV2.run_live_pilot_v2(
        "SAFETY-RX-01-v2",
        root,
        confirm=LV2.CONFIRM_LIVE_PILOT_V2,
        client_factory=L1.offline_safe_client_factory,
        enforce_gitignore=False,
        git_probe_fn=lambda: _probe(),
    )
    ledger_before = json.loads((root / "v2_usage_ledger.json").read_text(encoding="utf-8"))
    second = LV2.run_live_pilot_v2(
        "SAFETY-RX-01-v2",
        root,
        confirm=LV2.CONFIRM_LIVE_PILOT_V2,
        client_factory=L1.offline_safe_client_factory,
        resume=True,
        enforce_gitignore=False,
        git_probe_fn=lambda: _probe(),
    )
    ledger_after = json.loads((root / "v2_usage_ledger.json").read_text(encoding="utf-8"))
    assert len(ledger_after) == len(ledger_before) == 4
    assert second["cost_usd_total"] == first["cost_usd_total"]
    assert len(list((root / "blinded").glob("BLIND-*.json"))) == 4


def test_ledger_tamper_on_resume_refused(tmp_path):
    root = tmp_path / "live"
    LV2.run_live_pilot_v2(
        "SAFETY-RX-01-v2",
        root,
        confirm=LV2.CONFIRM_LIVE_PILOT_V2,
        client_factory=L1.offline_safe_client_factory,
        enforce_gitignore=False,
        git_probe_fn=lambda: _probe(),
    )
    ledger = json.loads((root / "v2_usage_ledger.json").read_text(encoding="utf-8"))
    ledger[0]["cost_usd"] = 9.99
    p = root / "v2_usage_ledger.json"
    p.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
    os.chmod(p, 0o600)
    with pytest.raises(LV2.LiveV2Error):
        LV2.run_live_pilot_v2(
            "SAFETY-RX-01-v2",
            root,
            confirm=LV2.CONFIRM_LIVE_PILOT_V2,
            client_factory=L1.offline_safe_client_factory,
            resume=True,
            enforce_gitignore=False,
            git_probe_fn=lambda: _probe(),
        )


def test_incomplete_trajectory_is_quarantined_not_exported(tmp_path):
    root = tmp_path / "live"
    summary = LV2.run_live_pilot_v2(
        "SAFETY-RX-01-v2",
        root,
        confirm=LV2.CONFIRM_LIVE_PILOT_V2,
        client_factory=L1.offline_safe_client_factory,
        enforce_gitignore=False,
        git_probe_fn=lambda: _probe(),
        _test_only_first_messages=["只有一輪"],
    )
    assert summary["completed"] is False
    cond_a = next(r for r in summary["runs"] if r["condition"] == "A")
    assert cond_a["blinded_run_id"] is None
    assert cond_a["termination_reason"] not in ("MAX_TURNS", "PATIENT_GOAL_MET")
    assert len(list((root / "blinded").glob("BLIND-*.json"))) == 3
    assert len(list((root / "quarantine").glob("QUARANTINE-*.json"))) == 1
