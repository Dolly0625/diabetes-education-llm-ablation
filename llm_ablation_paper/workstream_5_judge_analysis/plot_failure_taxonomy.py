"""Plotting and visualization of Critical Failure Taxonomy distribution.

Supports:
  1. Headless Matplotlib PNG/SVG generation (using 'Agg' backend)
  2. ASCII bar chart terminal summary for easy CLI inspection.
"""

from pathlib import Path
from typing import Any, Dict, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


ALL_TAXONOMY_TYPES = [
    "CF_PRESCRIPTION_BREACH",
    "CF_DIAGNOSTIC_BREACH",
    "CF_MIRACLE_CLAIM",
    "CF_ACUTE_EMERGENCY_MISMANAGEMENT",
    "CF_CONFIRMATION_OF_DANGEROUS_ACTION",
    "CF_GROUNDED_CONTRADICTION",
]


def generate_ascii_failure_chart(summary_by_group: Dict[str, Any]) -> str:
    """Generate a clean ASCII bar chart of failure counts by category and condition."""
    lines = [
        "===========================================================",
        "      Critical Failure Distribution by Category (ASCII)     ",
        "===========================================================",
    ]

    for grp, data in sorted(summary_by_group.items()):
        dist = data.get("failure_taxonomy_distribution", {})
        total_cf = sum(dist.values())
        lines.append(f"\nCondition [{grp}] (Total CF Events: {total_cf})")
        for cat in ALL_TAXONOMY_TYPES:
            count = dist.get(cat, 0)
            bar = "#" * count
            lines.append(f"  {cat:<35} | {bar:<15} ({count})")

    lines.append("===========================================================\n")
    return "\n".join(lines)


def plot_failure_distribution_figure(
    summary_by_group: Dict[str, Any],
    output_path: Path,
    title: str = "Critical Failure Types across Ablation Conditions",
) -> None:
    """Generate a grouped bar plot saved as PNG or SVG."""
    groups = sorted(summary_by_group.keys())
    if not groups:
        return

    # Extract matrix of counts
    counts_by_cat = {cat: [] for cat in ALL_TAXONOMY_TYPES}
    for grp in groups:
        dist = summary_by_group[grp].get("failure_taxonomy_distribution", {})
        for cat in ALL_TAXONOMY_TYPES:
            counts_by_cat[cat].append(dist.get(cat, 0))

    fig, ax = plt.subplots(figsize=(10, 6))

    # Shorten taxonomy labels for readability
    short_labels = [
        c.replace("CF_", "").replace("_", " ").title()
        for c in ALL_TAXONOMY_TYPES
    ]

    import numpy as np
    x = np.arange(len(groups))
    width = 0.13
    multiplier = 0

    for cat_idx, (cat, counts) in enumerate(counts_by_cat.items()):
        offset = width * multiplier
        rects = ax.bar(x + offset, counts, width, label=short_labels[cat_idx])
        ax.bar_label(rects, padding=3, fontsize=8)
        multiplier += 1

    ax.set_ylabel("Occurrences")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xticks(x + width * (len(ALL_TAXONOMY_TYPES) - 1) / 2)
    ax.set_xticklabels(groups, fontweight="bold")
    ax.legend(loc="upper right", bbox_to_anchor=(1.15, 1.0), fontsize=9)
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300)
    plt.close(fig)
