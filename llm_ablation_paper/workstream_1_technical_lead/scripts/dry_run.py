#!/usr/bin/env python3
"""Standalone wrapper: delegates to harness.dry_run so a shallow path works.

Usage:
  python llm_ablation_paper/workstream_1_technical_lead/scripts/dry_run.py
  python llm_ablation_paper/workstream_1_technical_lead/scripts/dry_run.py --out llm_ablation_paper/artifacts/workstream_1 --patient SP-DRY-001
"""
import sys
from pathlib import Path

# Ensure project root on sys.path (scripts/ -> workstream_1_technical_lead -> llm_ablation_paper -> project root)
project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from llm_ablation_paper.workstream_1_technical_lead.harness.dry_run import main  # noqa: E402

if __name__ == "__main__":
    main()
