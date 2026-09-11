"""Pure SHA-256 fingerprint helpers for the WS1 freeze candidate.

Read-only: these helpers only read prompt/tool constants and compute hashes.
They do not change runtime behavior, and patient input data is never hashed.
"""
from __future__ import annotations

import hashlib
import inspect
import json


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def talker_base_prompt_sha256() -> str:
    from diabetes_chatbot.prompts import NURSE_SYSTEM_PROMPT

    return _sha256_text(NURSE_SYSTEM_PROMPT)


def talker_prompt_template_bundle_sha256() -> str:
    from diabetes_chatbot.prompts import NURSE_SYSTEM_PROMPT, build_nurse_system_prompt

    payload = {
        "nurse_system_prompt": NURSE_SYSTEM_PROMPT,
        "build_nurse_system_prompt_source": inspect.getsource(build_nurse_system_prompt),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_text(canonical)


def planner_system_prompt_sha256() -> str:
    from diabetes_chatbot.planner import PLANNER_SYSTEM_PROMPT

    return _sha256_text(PLANNER_SYSTEM_PROMPT)


def canonical_tool_schema_sha256() -> str:
    from .config import compute_tool_snapshot_sha

    return compute_tool_snapshot_sha()
