"""Paired comparison of conditions across two runs, matched by task id.

The within-run paired differences in ``manifest.json`` only cover conditions run
together. Arms run separately on overlapping seeds (the rule arm) are compared
here instead: only task ids present in both runs are used, and the number
matched is reported.

Usage:
    python -m grapevine.experiments.compare \\
        --base runs/<primary> --base-cond communication \\
        --other runs/<rule_arm> --other-cond communication_rule \\
        --base-ref-cond full_info --other-ref-cond full_info_rule

With the two ``-ref-cond`` flags it also reports how the gap between the
reference condition and the compared condition changes between runs, e.g. how
the A - C gap moves when the rule is shown.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from grapevine.experiments.analysis import bootstrap_ci, paired_difference_ci
from grapevine.rewards.reward import compute_surfacing
from grapevine.rollout.engine import Episode, load_transcript


def load_condition(run_dir: Path, condition: str) -> dict[str, Episode]:
    """Load one condition's episodes from a run directory, keyed by task id."""
    path = run_dir / f"episodes_{condition}.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"no {path.name} in {run_dir}")
    episodes = (Episode.from_dict(d) for d in load_transcript(path))
    return {e.task_id: e for e in episodes}


def _correct(episodes: list[Episode]) -> list[float]:
    return [1.0 if e.correct else 0.0 for e in episodes]


def _decoy(episodes: list[Episode]) -> list[float]:
    return [
        1.0
        if e.team_answer is not None and e.team_answer == e.metadata.get("decoy_option")
        else 0.0
        for e in episodes
    ]


def _summary(episodes: list[Episode]) -> dict[str, Any]:
    acc = _correct(episodes)
    dec = _decoy(episodes)
    surfacing: float | None = None
    if any(m.role == "discussion" for e in episodes for m in e.messages):
        surfacing = sum(compute_surfacing(e).surfacing_rate for e in episodes) / len(episodes)
    return {
        "n": len(episodes),
        "accuracy": sum(acc) / len(acc),
        "accuracy_ci95": list(bootstrap_ci(acc, seed=0)),
        "decoy_rate": sum(dec) / len(dec),
        "decoy_rate_ci95": list(bootstrap_ci(dec, seed=1)),
        "parse_failures": sum(1 for e in episodes if e.team_answer is None),
        "surfacing_rate": surfacing,
    }


def compare(
    base_dir: Path,
    base_cond: str,
    other_dir: Path,
    other_cond: str,
    base_ref_cond: str | None = None,
    other_ref_cond: str | None = None,
) -> dict[str, Any]:
    """Compare ``other_cond`` in ``other_dir`` against ``base_cond`` in ``base_dir``.

    Differences are ``other - base`` on the tasks both runs contain, with paired
    bootstrap 95% intervals. If both reference conditions are given, the result
    also includes the change in the gap ``ref - cond`` between the two runs,
    bootstrapped per task, restricted to tasks present in all four.
    """
    base = load_condition(base_dir, base_cond)
    other = load_condition(other_dir, other_cond)
    ids = sorted(set(base) & set(other))
    if not ids:
        raise ValueError("the two runs share no task ids")

    b = [base[i] for i in ids]
    o = [other[i] for i in ids]
    acc_mean, acc_ci = paired_difference_ci(_correct(o), _correct(b), seed=0)
    dec_mean, dec_ci = paired_difference_ci(_decoy(o), _decoy(b), seed=1)

    result: dict[str, Any] = {
        "n_matched": len(ids),
        "task_ids": [ids[0], ids[-1]],
        "base": {"run": str(base_dir), "condition": base_cond, **_summary(b)},
        "other": {"run": str(other_dir), "condition": other_cond, **_summary(o)},
        "accuracy_other_minus_base": {"mean": acc_mean, "ci95": list(acc_ci)},
        "decoy_rate_other_minus_base": {"mean": dec_mean, "ci95": list(dec_ci)},
    }

    if base_ref_cond and other_ref_cond:
        base_ref = load_condition(base_dir, base_ref_cond)
        other_ref = load_condition(other_dir, other_ref_cond)
        gap_ids = [i for i in ids if i in base_ref and i in other_ref]
        base_gap = [
            (1.0 if base_ref[i].correct else 0.0) - (1.0 if base[i].correct else 0.0)
            for i in gap_ids
        ]
        other_gap = [
            (1.0 if other_ref[i].correct else 0.0) - (1.0 if other[i].correct else 0.0)
            for i in gap_ids
        ]
        change, change_ci = paired_difference_ci(other_gap, base_gap, seed=2)
        result["gap_change"] = {
            "definition": (
                f"({other_ref_cond} - {other_cond}) minus ({base_ref_cond} - {base_cond}), "
                "accuracy, per task"
            ),
            "n_matched": len(gap_ids),
            "base_gap": sum(base_gap) / len(base_gap),
            "other_gap": sum(other_gap) / len(other_gap),
            "change": change,
            "ci95": list(change_ci),
        }
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="python -m grapevine.experiments.compare",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--base", required=True, help="baseline run directory")
    parser.add_argument("--base-cond", required=True, help="condition in the baseline run")
    parser.add_argument("--other", required=True, help="run directory to compare")
    parser.add_argument("--other-cond", required=True, help="condition in the other run")
    parser.add_argument("--base-ref-cond", default=None, help="reference condition, baseline run")
    parser.add_argument("--other-ref-cond", default=None, help="reference condition, other run")
    parser.add_argument("--out", default=None, help="write the result as JSON to this path")
    args = parser.parse_args(argv)

    result = compare(
        Path(args.base),
        args.base_cond,
        Path(args.other),
        args.other_cond,
        args.base_ref_cond,
        args.other_ref_cond,
    )
    text = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
