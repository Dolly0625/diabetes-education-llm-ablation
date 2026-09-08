"""Isolation helpers for harness."""
from __future__ import annotations
from pathlib import Path
import tempfile
import uuid
import json


def make_isolated_state_dir(base: Path | str | None, run_id: str) -> Path:
    """Create isolated state directory for a run. Returns Path."""
    if base is None:
        base_path = Path(tempfile.gettempdir()) / "ablation_harness"
    else:
        base_path = Path(base)
    run_dir = base_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def clear_session_cache() -> None:
    """Clear handlers._SESSION_CACHE to ensure isolation."""
    try:
        from diabetes_chatbot.server import handlers as h
        h._SESSION_CACHE.clear()
    except Exception:
        pass
    try:
        import diabetes_chatbot.server.handlers as h2
        if hasattr(h2, "_SESSION_CACHE"):
            h2._SESSION_CACHE.clear()
    except Exception:
        pass
    try:
        from diabetes_chatbot.server import ablation_core
        pass
    except Exception:
        pass


def get_patient_file_for_state(state_dir: Path | str, user_id: str) -> Path:
    """Return patient file path under state_dir for given user_id. Sanitize user_id."""
    sd = Path(state_dir)
    sd.mkdir(parents=True, exist_ok=True)
    safe_user = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in user_id)
    if not safe_user:
        safe_user = f"user_{uuid.uuid4().hex[:8]}"
    return sd / f"{safe_user}.json"


def ensure_state_dir_empty(
    state_dir: Path | str,
    resume: bool = False,
    run_id: str | None = None,
    condition: str | None = None,
    patient_id: str | None = None,
) -> None:
    """Validate state directory cleanliness or verify exact match for resume.

    If config.json, trajectories.jsonl, or non-empty checkpoints directory exists:
      - If resume=False: reject unconditionally by raising FileExistsError.
      - If resume=True: verify that run_id, condition, and patient_id match existing state.
        Raise ValueError on any mismatch.
    """
    sd = Path(state_dir)
    sd.mkdir(parents=True, exist_ok=True)
    has_config = (sd / "config.json").exists()
    has_traj = (sd / "trajectories.jsonl").exists()
    has_checkpoints = (sd / "checkpoints").exists() and any((sd / "checkpoints").iterdir())

    if has_config or has_traj or has_checkpoints:
        if not resume:
            raise FileExistsError(
                f"state_dir {sd} already contains config.json/trajectories.jsonl/checkpoints; "
                "resume=False rejects reuse. Pass resume=True to resume or use a new directory."
            )

        # resume=True: check exact consistency of run_id, condition, patient_id
        if has_config:
            try:
                cfg = json.loads((sd / "config.json").read_text(encoding="utf-8"))
                if run_id is not None and cfg.get("run_id") and cfg.get("run_id") != run_id:
                    raise ValueError(f"Resume run_id mismatch: existing {cfg.get('run_id')!r} != {run_id!r}")
                if condition is not None and cfg.get("condition") and cfg.get("condition") != condition:
                    raise ValueError(f"Resume condition mismatch: existing {cfg.get('condition')!r} != {condition!r}")
            except (ValueError, FileExistsError):
                raise
            except Exception:
                pass

        summary_file = sd / "summary.json"
        if summary_file.exists():
            try:
                summ = json.loads(summary_file.read_text(encoding="utf-8"))
                if run_id is not None and summ.get("run_id") and summ.get("run_id") != run_id:
                    raise ValueError(f"Resume run_id mismatch in summary: existing {summ.get('run_id')!r} != {run_id!r}")
                if condition is not None and summ.get("condition") and summ.get("condition") != condition:
                    raise ValueError(f"Resume condition mismatch in summary: existing {summ.get('condition')!r} != {condition!r}")
                if patient_id is not None and summ.get("patient_id") and summ.get("patient_id") != patient_id:
                    raise ValueError(f"Resume patient_id mismatch in summary: existing {summ.get('patient_id')!r} != {patient_id!r}")
            except (ValueError, FileExistsError):
                raise
            except Exception:
                pass

        if has_traj and patient_id is not None:
            try:
                lines = (sd / "trajectories.jsonl").read_text(encoding="utf-8").strip().splitlines()
                if lines:
                    first_turn = json.loads(lines[0])
                    ex_pid = first_turn.get("patient_id")
                    if ex_pid and ex_pid != patient_id:
                        raise ValueError(f"Resume patient_id mismatch in trajectory: existing {ex_pid!r} != {patient_id!r}")
            except (ValueError, FileExistsError):
                raise
            except Exception:
                pass
