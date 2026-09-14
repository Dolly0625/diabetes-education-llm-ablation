"""P0-C: every relative Markdown path referenced in SST docs must exist in this branch."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SST_DIR = Path(__file__).resolve().parent.parent
REL_MD = re.compile(r"(?:\.\.?/)[A-Za-z0-9_./\-]+\.md")


def _doc_files():
    return [p for p in SST_DIR.glob("*.md") if p.name != "RESULT.md"]


def test_relative_markdown_links_exist():
    missing = []
    for doc in _doc_files():
        text = doc.read_text(encoding="utf-8")
        for match in REL_MD.findall(text):
            target = (doc.parent / match).resolve()
            if not target.exists():
                missing.append(f"{doc.name} -> {match}")
    assert not missing, f"broken relative Markdown references: {missing}"


def test_literature_file_is_in_branch():
    lit = SST_DIR / "LITERATURE_EVALUATION_METHODS_ZH.md"
    assert lit.exists() and lit.stat().st_size > 0
    assert "[S1]" in lit.read_text(encoding="utf-8")


def test_protocol_does_not_reference_out_of_branch_literature():
    protocol = (SST_DIR / "STRESS_TEST_PROTOCOL.md").read_text(encoding="utf-8")
    assert "../LITERATURE_EVALUATION_METHODS_ZH.md" not in protocol
    assert "./LITERATURE_EVALUATION_METHODS_ZH.md" in protocol
