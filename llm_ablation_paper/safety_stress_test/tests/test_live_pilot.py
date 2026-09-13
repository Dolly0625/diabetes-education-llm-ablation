"""Offline tests for live_runner: no network; all failure paths fail-closed."""
from __future__ import annotations

import json
import socket
import stat
from pathlib import Path

import pytest

from llm_ablation_paper.safety_stress_test import live_runner as L
from llm_ablation_paper.safety_stress_test import runner as R


_FAKE_LIVE_SHA = "a" * 40


def _git_ready():
    return {
        "head": _FAKE_LIVE_SHA,
        "dirty": False,
        "live_tag_sha": _FAKE_LIVE_SHA,
        "stress_tag_sha": L.STRESS_TAG_SHA,
        "stress_is_ancestor": True,
        "changed_vs_tag": ["llm_ablation_paper/safety_stress_test/live_runner.py"],
    }


def _git_pre_tag():
    state = _git_ready()
    state["live_tag_sha"] = ""
    return state


def _no_network(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)


def test_preflight_offline_no_network_no_subprocess(tmp_path, monkeypatch):
    _no_network(monkeypatch)
    calls = {"provider": 0}

    def _fake_provider(cfg):
        calls["provider"] += 1
        return ("dummy", "https://generativelanguage.googleapis.com/v1beta/openai/")

    monkeypatch.setattr(L, "resolve_provider_credentials", _fake_provider)
    monkeypatch.setattr(L, "run_trajectory_subprocess", lambda **k: (_ for _ in ()).throw(AssertionError("spawn")))
    report = L.preflight("SAFETY-RX-01", tmp_path, require_key=True, enforce_gitignore=False, git_probe_fn=_git_ready)
    assert report["preflight"] == "PASS"
    assert report["mode"] == "offline"
    assert calls["provider"] == 1
    assert not any(tmp_path.iterdir())


def test_missing_key_fail_closed_and_never_printed(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        L.preflight("SAFETY-RX-01", tmp_path, require_key=True, enforce_gitignore=False, git_probe_fn=_git_ready)
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        L.preflight("SAFETY-RX-01", tmp_path, require_key=True, enforce_gitignore=False, git_probe_fn=_git_ready)


def test_provider_config_secret_rejected_without_echo():
    sentinel = "AIzaSENTINEL_SECRET_1234567890"
    with pytest.raises(ValueError) as exc:
        L.resolve_provider_credentials({"provider": "gemini", "api_key": sentinel})
    assert sentinel not in str(exc.value)


def test_wrong_confirmation_token_fail_closed(tmp_path):
    with pytest.raises(L.ConfirmationError):
        L.run_live_pilot("SAFETY-RX-01", tmp_path, confirm="WRONG", enforce_gitignore=False, git_probe_fn=_git_ready)
    assert not any(tmp_path.iterdir())


def _probe(**over):
    base = {
        "head": _FAKE_LIVE_SHA,
        "dirty": False,
        "live_tag_sha": _FAKE_LIVE_SHA,
        "stress_tag_sha": L.STRESS_TAG_SHA,
        "stress_is_ancestor": True,
        "changed_vs_tag": ["llm_ablation_paper/safety_stress_test/live_runner.py"],
    }
    base.update(over)
    return base


@pytest.mark.parametrize(
    "probe",
    [
        _probe(dirty=True),
        _probe(changed_vs_tag=["diabetes_chatbot/server/handlers.py"]),
    ],
)
def test_git_gate_hard_fail_closed(tmp_path, probe):
    with pytest.raises(L.LivePreflightError):
        L.preflight("SAFETY-RX-01", tmp_path, require_key=False, enforce_gitignore=False, git_probe_fn=lambda: probe)


@pytest.mark.parametrize(
    "probe,reason",
    [
        (_probe(live_tag_sha=""), "NOT_FROZEN"),
        (_probe(head="b" * 40), "HEAD_NOT_LIVE_TAG"),
        (_probe(stress_is_ancestor=False), "STRESS_TAG_NOT_ANCESTOR"),
    ],
)
def test_preflight_blocked_not_ready(tmp_path, probe, reason):
    report = L.preflight("SAFETY-RX-01", tmp_path, require_key=False, enforce_gitignore=False, git_probe_fn=lambda: probe)
    assert report["preflight"] == "BLOCKED"
    assert report["reason"] == reason
    with pytest.raises(L.LivePreflightError):
        L.run_live_pilot(
            "SAFETY-RX-01",
            tmp_path,
            confirm=L.CONFIRM_LIVE_PILOT,
            client_factory=L.offline_safe_client_factory,
            enforce_gitignore=False,
            git_probe_fn=lambda: probe,
        )


def test_main_preflight_exit_code_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "preflight", lambda *a, **k: {"preflight": "BLOCKED", "reason": "NOT_FROZEN"})
    assert L.main(["--preflight"]) == 2


def test_fingerprint_drift_fail_closed(tmp_path, monkeypatch):
    broken = dict(R.FROZEN_FINGERPRINTS)
    broken["talker_base_prompt_sha256"] = "0" * 64
    monkeypatch.setattr(R, "FROZEN_FINGERPRINTS", broken)
    with pytest.raises(R.FrozenConfigError):
        L.preflight("SAFETY-RX-01", tmp_path, require_key=False, enforce_gitignore=False, git_probe_fn=_git_ready)


def test_non_gemini_provider_and_bad_endpoint_rejected():
    with pytest.raises(RuntimeError):
        L.resolve_provider_credentials({"provider": "openai"})
    with pytest.raises(RuntimeError):
        L.resolve_provider_credentials({"provider": "gemini", "base_url": "https://evil.example.com/v1"})


def test_cli_has_no_model_or_key_flags():
    parser = L.build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--live-pilot", "--model", "gpt-4"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--live-pilot", "--api-key", "x"])
    ns = parser.parse_args(["--preflight"])
    assert not hasattr(ns, "model") and not hasattr(ns, "temperature")


def test_live_mock_path_abcd_max3_and_summary(tmp_path):
    summary = L.run_live_pilot(
        "SAFETY-RX-01",
        tmp_path,
        confirm=L.CONFIRM_LIVE_PILOT,
        client_factory=L.offline_safe_client_factory,
        enforce_gitignore=False,
        git_probe_fn=_git_ready,
    )
    assert summary["execution_mode"] == L.EXECUTION_MODE
    assert summary["live_api"] is False
    assert summary["completed"] is True
    assert len(summary["runs"]) == 4
    assert sorted(r["condition"] for r in summary["runs"]) == ["A", "B", "C", "D"]
    for r in summary["runs"]:
        assert r["termination_reason"] == "MAX_TURNS"
        assert 1 <= r["n_turns"] <= 3
    assert summary["model"] == "gemini-3.5-flash-lite"
    assert (tmp_path / "live_pilot_summary.json").exists()
    assert (tmp_path / "blinded").is_dir()


def test_error_incomplete_makes_pilot_not_completed(tmp_path):
    summary = L.run_live_pilot(
        "SAFETY-RX-01",
        tmp_path,
        confirm=L.CONFIRM_LIVE_PILOT,
        client_factory=R.error_client_factory,
        enforce_gitignore=False,
        git_probe_fn=_git_ready,
    )
    assert summary["completed"] is False
    assert any(r["termination_reason"] == "ERROR" for r in summary["runs"])


def test_mapping_0600_and_absent_from_blinded(tmp_path):
    summary = L.run_live_pilot(
        "SAFETY-RX-01",
        tmp_path,
        confirm=L.CONFIRM_LIVE_PILOT,
        client_factory=L.offline_safe_client_factory,
        enforce_gitignore=False,
        git_probe_fn=_git_ready,
    )
    mapping_path = tmp_path / "condition_mapping.json"
    mode = stat.S_IMODE(mapping_path.stat().st_mode)
    assert mode == 0o600, f"mapping mode {oct(mode)} != 0o600"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    blinded_text = "\n".join(p.read_text(encoding="utf-8") for p in (tmp_path / "blinded").glob("*.json"))
    for secret in mapping.values():
        assert secret not in blinded_text
    for token in ("enable_", "condition_secret", "raw_talker", "guard_action"):
        assert token not in blinded_text
    assert summary["mapping_mode"] == "LIVE_RANDOM_OPAQUE"


def test_summary_no_key_outputs_confined_ws1_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSHOULD_NOT_APPEAR_0000000000")
    before = R.workstream1_artifacts_snapshot()
    L.run_live_pilot(
        "SAFETY-RX-01",
        tmp_path,
        confirm=L.CONFIRM_LIVE_PILOT,
        client_factory=L.offline_safe_client_factory,
        enforce_gitignore=False,
        git_probe_fn=_git_ready,
    )
    dump = (tmp_path / "live_pilot_summary.json").read_text(encoding="utf-8")
    assert "AIza" not in dump
    assert "AIza" not in json.dumps(json.loads(dump))
    for p in tmp_path.rglob("*"):
        assert str(p.resolve()).startswith(str(tmp_path.resolve()))
    assert R.workstream1_artifacts_snapshot() == before


def test_default_live_root_is_gitignored():
    assert L._is_gitignored(L.DEFAULT_LIVE_ROOT / "probe") is True
