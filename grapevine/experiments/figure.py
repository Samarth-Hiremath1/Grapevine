"""Main figure for the coordination ablation.

Reads one or more run directories produced by ``grapevine.experiments.run`` and
draws accuracy and decoy rate per condition with exact Clopper-Pearson 95%
intervals. Extra
runs (for example the rule arm) are appended as further bars, and the caption
states which seeds each run covered. Writes PNG, SVG, and the source table as
CSV, so a plot never becomes separated from the numbers behind it.

Usage:
    python -m grapevine.experiments.figure --run runs/<dir>
    python -m grapevine.experiments.figure --run runs/<primary> \\
        --extra-run runs/<rule_arm> --out-dir docs/figures
"""

from __future__ import annotations

import argparse
import csv
import json
import textwrap
from pathlib import Path
from typing import Any

import matplotlib

from grapevine.experiments.analysis import clopper_pearson

matplotlib.use("Agg")  # headless: no display needed
import matplotlib.pyplot as plt  # noqa: E402

#: Display names, in the order they appear on the x-axis.
CONDITION_LABELS = {
    "full_info": "A. Full information\n(1 agent, all facts)",
    "no_communication": "B. No communication\n(3 agents, no talking)",
    "communication": "C. Instructed sharing\n(3 agents, 2 rounds)",
    "communication_neutral": "D. Neutral prompt\n(3 agents, 2 rounds)",
    "full_info_rule": "A + rule",
    "full_info_matched_rule": "A (matched) + rule",
    "no_communication_rule": "B + rule",
    "communication_rule": "C + rule",
    "communication_neutral_rule": "D + rule",
}


def load_manifest(run_dir: Path) -> dict[str, Any]:
    """Load ``manifest.json`` from a run directory."""
    path = run_dir / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"no manifest.json in {run_dir}")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def collect_rows(run_dirs: list[Path]) -> list[dict[str, Any]]:
    """Gather one row per condition across runs, in display order."""
    rows: list[dict[str, Any]] = []
    for run_dir in run_dirs:
        manifest = load_manifest(run_dir)
        seeds = manifest["resolved"]["seeds"]
        for cond, summary in manifest["summaries"].items():
            # Intervals are recomputed as Clopper-Pearson from counts, so figures
            # from older manifests (bootstrap intervals) match current ones.
            n = int(summary["n"])
            acc_ci = clopper_pearson(round(summary["accuracy"] * n), n)
            dec_ci = clopper_pearson(round(summary["decoy_rate"] * n), n)
            rows.append(
                {
                    "condition": cond,
                    "run": run_dir.name,
                    "seeds": f"{seeds[0]}-{seeds[1]}",
                    "n": summary["n"],
                    "accuracy": round(summary["accuracy"], 6),
                    "accuracy_ci_low": round(acc_ci[0], 6),
                    "accuracy_ci_high": round(acc_ci[1], 6),
                    "decoy_rate": round(summary["decoy_rate"], 6),
                    "decoy_ci_low": round(dec_ci[0], 6),
                    "decoy_ci_high": round(dec_ci[1], 6),
                    "other_wrong_rate": round(summary["other_wrong_rate"], 6),
                    "parse_failures": summary["parse_failures"],
                    "tie_rate": summary["tie_rate"],
                    "accuracy_ties_incorrect": summary["accuracy_ties_incorrect"],
                    "surfacing_rate": summary["surfacing_rate"],
                }
            )
    order = list(CONDITION_LABELS)
    rows.sort(key=lambda r: order.index(r["condition"]) if r["condition"] in order else 99)
    return rows


def write_source_table(rows: list[dict[str, Any]], out_csv: Path) -> None:
    """Write the exact numbers behind the figure to ``out_csv``."""
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _caption(rows: list[dict[str, Any]], primary: dict[str, Any]) -> str:
    model = primary["config"]["model"]["name"]
    n_rounds = primary["resolved"]["rollout"]["n_rounds"]
    seed_groups: dict[str, list[str]] = {}
    for r in rows:
        short = CONDITION_LABELS.get(r["condition"], r["condition"]).split("\n")[0]
        seed_groups.setdefault(r["seeds"], []).append(short.split(".")[0].strip())
    if len(seed_groups) == 1:
        seed_text = "All conditions ran on identical task seeds."
    else:
        seed_text = " ".join(
            f"{', '.join(names)}: seeds {seeds}." for seeds, names in seed_groups.items()
        )
    has_rule = any(r["condition"].endswith("_rule") for r in rows)
    rule_text = (
        " A-D never saw the task question or scoring rule; the '+ rule' bars show both."
        if has_rule
        else ""
    )
    text = (
        f"Hidden-profile tasks, {model}. Bars show the proportion of episodes ending on "
        "the correct candidate and on the decoy (the candidate favoured by the facts every "
        f"agent already shares). Discussion conditions use {n_rounds} rounds; C and D differ "
        f"only in whether the prompt instructs fact-sharing.{rule_text} Error bars are "
        f"exact Clopper-Pearson 95% intervals. {seed_text}"
    )
    return "\n".join(textwrap.wrap(text, 150))


def make_figure(
    run_dir: Path, extra_runs: list[Path] | None = None, out_dir: Path | None = None
) -> tuple[Path, Path, Path]:
    """Draw the main figure. Returns (png, svg, csv) paths."""
    run_dirs = [run_dir, *(extra_runs or [])]
    out = out_dir or run_dir
    out.mkdir(parents=True, exist_ok=True)
    rows = collect_rows(run_dirs)
    csv_path = out / "figure_data.csv"
    write_source_table(rows, csv_path)

    primary = load_manifest(run_dir)
    chance = primary["resolved"]["chance_accuracy"]

    labels = [
        f'{CONDITION_LABELS.get(r["condition"], r["condition"])}\nn={r["n"]}' for r in rows
    ]
    acc = [r["accuracy"] for r in rows]
    acc_err_lo = [r["accuracy"] - r["accuracy_ci_low"] for r in rows]
    acc_err_hi = [r["accuracy_ci_high"] - r["accuracy"] for r in rows]
    decoy = [r["decoy_rate"] for r in rows]
    decoy_err_lo = [r["decoy_rate"] - r["decoy_ci_low"] for r in rows]
    decoy_err_hi = [r["decoy_ci_high"] - r["decoy_rate"] for r in rows]

    x = range(len(rows))
    width = 0.36
    fig, ax = plt.subplots(figsize=(max(10.0, 2.1 * len(rows)), 6.0))

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
        chance, linestyle="--", linewidth=1.2, color="#4a5568", label=f"Chance ({chance*100:.0f}%)"
    )

    if any(r["condition"].endswith("_rule") for r in rows):
        first_rule = next(i for i, r in enumerate(rows) if r["condition"].endswith("_rule"))
        ax.axvline(first_rule - 0.5, color="#a0aec0", linewidth=1.0, linestyle=":")

    # Headroom so a 100% bar's value label does not collide with the title.
    ax.set_ylim(0, 1.14)
    ax.set_yticks([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_ylabel("Proportion of episodes")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_title("Distributing information across agents on hidden-profile tasks")
    ax.legend(loc="upper right", frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)

    for i, (a, d, hi_a, hi_d) in enumerate(zip(acc, decoy, acc_err_hi, decoy_err_hi, strict=True)):
        ax.text(i - width / 2, a + hi_a + 0.03, f"{a*100:.0f}%", ha="center", fontsize=9)
        ax.text(i + width / 2, d + hi_d + 0.03, f"{d*100:.0f}%", ha="center", fontsize=9)

    fig.text(0.5, 0.005, _caption(rows, primary), ha="center", fontsize=8, color="#2d3748")
    fig.tight_layout(rect=(0, 0.1, 1, 1))

    png = out / "accuracy_by_condition.png"
    svg = out / "accuracy_by_condition.svg"
    fig.savefig(png, dpi=200)
    fig.savefig(svg)
    plt.close(fig)
    return png, svg, csv_path


#: Axis labels for the two-panel figure, keyed by table label.
PANEL_LABELS = {
    "A": "A\nfull info,\n1 agent",
    "A (matched)": "A\nfull info,\nmatched prompt",
    "B": "B\n3 agents,\nno talking",
    "C": "C\n3 agents,\ntold to share",
    "D": "D\n3 agents,\nneutral prompt",
}


def make_two_panel_figure(
    panels: list[tuple[str, list[tuple[str, dict[str, Any]]]]],
    out_dir: Path,
    stem: str = "accuracy_by_condition",
) -> tuple[Path, Path, Path]:
    """Accuracy per condition, one panel per framing, exact 95% intervals.

    ``panels`` is a list of ``(panel title, [(label, cell), ...])`` where each
    cell has ``accuracy``, ``ci95``, ``n`` and ``correct``. Writes PNG, SVG and
    a CSV of the plotted numbers.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{stem}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["panel", "condition", "correct", "n", "accuracy", "ci_low", "ci_high"])
        for title, cells in panels:
            for label, c in cells:
                writer.writerow(
                    [title.split("\n")[0], label, c["correct"], c["n"],
                     round(c["accuracy"], 6), round(c["ci95"][0], 6), round(c["ci95"][1], 6)]
                )

    widths = [len(cells) for _, cells in panels]
    fig, axes = plt.subplots(
        1, len(panels), figsize=(12.5, 5.6), sharey=True,
        gridspec_kw={"width_ratios": widths},
    )
    for ax, (title, cells) in zip(axes, panels, strict=True):
        x = list(range(len(cells)))
        acc = [c["accuracy"] for _, c in cells]
        lo = [c["accuracy"] - c["ci95"][0] for _, c in cells]
        hi = [c["ci95"][1] - c["accuracy"] for _, c in cells]
        ax.bar(x, acc, 0.62, yerr=[lo, hi], capsize=4, color="#2b6cb0")
        ax.axhline(0.25, linestyle="--", linewidth=1.1, color="#4a5568")
        for i, (a, h) in enumerate(zip(acc, hi, strict=True)):
            ax.text(i, a + h + 0.025, f"{a * 100:.1f}%", ha="center", fontsize=9)
        ax.set_xticks(x)
        ax.set_xticklabels([PANEL_LABELS.get(lbl, lbl) for lbl, _ in cells], fontsize=8.5)
        ax.set_title(title, fontsize=10)
        ax.set_ylim(0, 1.12)
        ax.set_yticks([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("Accuracy (share of episodes correct)")
    axes[0].text(
        -0.44, 0.30, "chance 25%", ha="left", va="bottom", fontsize=8.5,
        color="#1a202c", bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.5},
    )
    fig.suptitle(
        "Hidden-profile tasks, gpt-5.6-luna: accuracy with and without the task stated",
        fontsize=11,
    )
    caption = (
        "Error bars are exact Clopper-Pearson 95% intervals. B, C and D split the facts across "
        "three agents; C and D discuss for 2 rounds, C's prompt tells agents to share facts and "
        "D's does not. A (matched) gives one agent every fact in the same layout and framing as "
        "B-D; original A uses a different prompt. Every wrong answer in every condition was the "
        "decoy option. Left: primary run and the D rerun; right: rule-arm runs."
    )
    fig.text(0.5, 0.01, "\n".join(textwrap.wrap(caption, 165)), ha="center", fontsize=8,
             color="#2d3748")
    fig.tight_layout(rect=(0, 0.08, 1, 0.95))
    png, svg = out_dir / f"{stem}.png", out_dir / f"{stem}.svg"
    fig.savefig(png, dpi=200)
    fig.savefig(svg)
    plt.close(fig)
    return png, svg, csv_path


def main(argv: list[str] | None = None) -> int:
    """Build the main figure."""
    parser = argparse.ArgumentParser(
        prog="python -m grapevine.experiments.figure",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--run", required=True, help="primary run directory")
    parser.add_argument(
        "--extra-run", action="append", default=[], help="additional run to append (repeatable)"
    )
    parser.add_argument(
        "--out-dir", default=None, help="where to write outputs (default: the primary run dir)"
    )
    args = parser.parse_args(argv)
    png, svg, csv_path = make_figure(
        Path(args.run),
        [Path(p) for p in args.extra_run],
        Path(args.out_dir) if args.out_dir else None,
    )
    print(f"wrote {png}")
    print(f"wrote {svg}")
    print(f"wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
