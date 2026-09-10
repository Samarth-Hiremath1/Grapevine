"""Main figure for the coordination ablation.

Reads a run directory produced by ``grapevine.experiments.run`` and draws
accuracy by condition with bootstrap 95% intervals, alongside the decoy rate so
the mechanism is visible in the same picture. Writes PNG, SVG, and the source
table as CSV into the run directory, so a plot never becomes separated from the
numbers behind it.

Usage:
    python -m grapevine.experiments.figure --run runs/<dir>
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless: no display needed
import matplotlib.pyplot as plt  # noqa: E402

#: Display names, in the order they appear on the x-axis.
CONDITION_LABELS = {
    "full_info": "A. Full information\n(1 agent, all facts)",
    "no_communication": "B. No communication\n(3 agents, no talking)",
    "communication": "C. Instructed sharing\n(3 agents, 2 rounds)",
    "communication_neutral": "D. Neutral prompt\n(3 agents, 2 rounds)",
}


def load_manifest(run_dir: Path) -> dict[str, Any]:
    """Load ``manifest.json`` from a run directory."""
    path = run_dir / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"no manifest.json in {run_dir}")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def write_source_table(manifest: dict[str, Any], out_csv: Path) -> list[dict[str, Any]]:
    """Write the exact numbers behind the figure to ``out_csv`` and return them."""
    rows: list[dict[str, Any]] = []
    for cond, summary in manifest["summaries"].items():
        rows.append(
            {
                "condition": cond,
                "n": summary["n"],
                "accuracy": round(summary["accuracy"], 6),
                "accuracy_ci_low": round(summary["accuracy_ci"][0], 6),
                "accuracy_ci_high": round(summary["accuracy_ci"][1], 6),
                "decoy_rate": round(summary["decoy_rate"], 6),
                "decoy_ci_low": round(summary["decoy_rate_ci"][0], 6),
                "decoy_ci_high": round(summary["decoy_rate_ci"][1], 6),
                "other_wrong_rate": round(summary["other_wrong_rate"], 6),
                "parse_failures": summary["parse_failures"],
                "tie_rate": summary["tie_rate"],
                "accuracy_ties_incorrect": summary["accuracy_ties_incorrect"],
                "surfacing_rate": summary["surfacing_rate"],
            }
        )
    order = [c for c in CONDITION_LABELS if c in {r["condition"] for r in rows}]
    rows.sort(key=lambda r: order.index(r["condition"]))
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def make_figure(run_dir: Path) -> tuple[Path, Path, Path]:
    """Draw the main figure for ``run_dir``. Returns (png, svg, csv) paths."""
    manifest = load_manifest(run_dir)
    csv_path = run_dir / "figure_data.csv"
    rows = write_source_table(manifest, csv_path)

    chance = manifest["resolved"]["chance_accuracy"]
    n_rounds = manifest["resolved"]["rollout"]["n_rounds"]
    model = manifest["config"]["model"]["name"]

    labels = [
        f'{CONDITION_LABELS.get(r["condition"], r["condition"])}\nn={r["n"]}'
        for r in rows
    ]
    acc = [r["accuracy"] for r in rows]
    acc_err_lo = [r["accuracy"] - r["accuracy_ci_low"] for r in rows]
    acc_err_hi = [r["accuracy_ci_high"] - r["accuracy"] for r in rows]
    decoy = [r["decoy_rate"] for r in rows]
    decoy_err_lo = [r["decoy_rate"] - r["decoy_ci_low"] for r in rows]
    decoy_err_hi = [r["decoy_ci_high"] - r["decoy_rate"] for r in rows]


    x = range(len(rows))
    width = 0.36
    fig, ax = plt.subplots(figsize=(10.0, 5.6))

    ax.bar(
        [i - width / 2 for i in x],
        acc,
        width,
        yerr=[acc_err_lo, acc_err_hi],
        capsize=4,
        label="Correct answer",
        color="#2b6cb0",
    )
    ax.bar(
        [i + width / 2 for i in x],
        decoy,
        width,
        yerr=[decoy_err_lo, decoy_err_hi],
        capsize=4,
        label="Chose the decoy",
        color="#c05621",
    )

    ax.axhline(
        chance,
        linestyle="--",
        linewidth=1.2,
        color="#4a5568",
        label=f"Chance ({chance*100:.0f}%)",
    )

    ax.set_ylim(0, 1.0)
    ax.set_ylabel("Proportion of episodes")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_title("Distributing information across agents on hidden-profile tasks")
    ax.legend(loc="upper right", frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)

    for i, (a, d, hi_a, hi_d) in enumerate(
        zip(acc, decoy, acc_err_hi, decoy_err_hi, strict=True)
    ):
        # Sit the value label just above each error bar so they never overlap.
        ax.text(i - width / 2, a + hi_a + 0.03, f"{a*100:.0f}%", ha="center", fontsize=9)
        ax.text(i + width / 2, d + hi_d + 0.03, f"{d*100:.0f}%", ha="center", fontsize=9)

    caption = (
        f"Hidden-profile tasks, {model}. Bars show the proportion of episodes ending on the "
        f"correct candidate and on the decoy\n(the candidate favoured by the facts every agent "
        f"already shares). Condition C uses {n_rounds} discussion rounds. Error bars are "
        f"percentile\nbootstrap 95% intervals over episodes. All conditions ran on identical "
        f"task seeds."
    )
    fig.text(0.5, 0.005, caption, ha="center", fontsize=8, color="#2d3748")
    fig.tight_layout(rect=(0, 0.09, 1, 1))

    png = run_dir / "accuracy_by_condition.png"
    svg = run_dir / "accuracy_by_condition.svg"
    fig.savefig(png, dpi=200)
    fig.savefig(svg)
    plt.close(fig)
    return png, svg, csv_path


def main(argv: list[str] | None = None) -> int:
    """Build the main figure for a run directory."""
    parser = argparse.ArgumentParser(
        prog="python -m grapevine.experiments.figure", description=__doc__
    )
    parser.add_argument("--run", required=True, help="run directory containing manifest.json")
    args = parser.parse_args(argv)
    png, svg, csv_path = make_figure(Path(args.run))
    print(f"wrote {png}")
    print(f"wrote {svg}")
    print(f"wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
