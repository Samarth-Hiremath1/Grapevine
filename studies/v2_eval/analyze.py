"""The pre-registered analysis for the ``hidden_profile_v2`` eval.

    python -m studies.v2_eval.analyze studies/v2_eval/runs/<primary-run>

This is the script the pre-registration names, committed before any data
exists. It is run once on the primary run, and whatever it prints is the
result.

It refuses three things, by raising rather than warning:

* a run containing synthetic episodes (``CLAUDE.md`` rule 2: a results table
  containing one must fail to build);
* a pilot run (a pilot checks the plumbing and the truncation rate; it is not a
  result);
* an incomplete run presented as complete. An incomplete primary run can still
  be analysed with ``--incomplete``, and the output says so in its first line.

Per cell it reports accuracy with an exact Clopper-Pearson interval, parse
failures, truncations and decoy choices. Then the seven pre-registered paired
contrasts per model, aligned by task id, each with a paired-bootstrap 95%
interval and a Bonferroni-adjusted interval for the family of seven.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from grapevine.experiments.analysis import bootstrap_ci, clopper_pearson
from studies.v2_eval.design import CELLS, DESIGN

#: The pre-registered contrasts, as (label, cell a, cell b), read as a - b.
CONTRASTS: tuple[tuple[str, tuple[str, str], tuple[str, str]], ...] = (
    ("objective effect, full_info", ("full_info", "stated"), ("full_info", "unstated")),
    ("objective effect, no_communication",
     ("no_communication", "stated"), ("no_communication", "unstated")),
    ("objective effect, communication",
     ("communication", "stated"), ("communication", "unstated")),
    ("communication - no_communication, stated",
     ("communication", "stated"), ("no_communication", "stated")),
    ("full_info - communication, stated", ("full_info", "stated"), ("communication", "stated")),
    ("communication - no_communication, unstated",
     ("communication", "unstated"), ("no_communication", "unstated")),
    ("full_info - communication, unstated",
     ("full_info", "unstated"), ("communication", "unstated")),
)


class SyntheticDataError(ValueError):
    """Raised when a results table would include a synthetic episode."""


def load_run(run_dir: Path, *, allow_incomplete: bool = False) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load a run, refusing anything that must not become a result.

    Raises:
        SyntheticDataError: If the run is synthetic.
        ValueError: If it is a pilot, or incomplete without ``allow_incomplete``.
    """
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("synthetic"):
        raise SyntheticDataError(
            f"{run_dir.name} is synthetic (scripted client). A results table containing a "
            "synthetic episode must not be built (CLAUDE.md rule 2)."
        )
    if manifest.get("phase") != "primary":
        raise ValueError(
            f"{run_dir.name} is a {manifest.get('phase')} run. A pilot checks the plumbing; "
            "only the primary run is analysed as a result."
        )
    if not manifest.get("complete") and not allow_incomplete:
        raise ValueError(
            f"{run_dir.name} is incomplete ({manifest.get('episodes_completed')}/"
            f"{manifest.get('episodes_expected')} episodes; stopped: "
            f"{manifest.get('stopped_early')}). Pass --incomplete to analyse it as such."
        )
    episodes = [
        json.loads(line)
        for line in (run_dir / "episodes.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return manifest, episodes


def cell_summary(episodes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Accuracy and failure counts for one cell."""
    n = len(episodes)
    k = sum(bool(e["correct"]) for e in episodes)
    lo, hi = clopper_pearson(k, n) if n else (float("nan"), float("nan"))
    return {
        "n": n,
        "correct": k,
        "accuracy": k / n if n else float("nan"),
        "ci95": [lo, hi],
        "parse_failures": sum(bool(e["parse_failure"]) for e in episodes),
        "truncated": sum(bool(e["truncated"]) for e in episodes),
        "chose_decoy": sum(e["answer"] == e["decoy"] for e in episodes),
        "ties": sum(bool(e.get("tie")) for e in episodes),
    }


def paired_contrast(
    a: Mapping[str, Mapping[str, Any]],
    b: Mapping[str, Mapping[str, Any]],
    *,
    n_contrasts: int,
) -> dict[str, Any]:
    """Mean paired difference in correctness, aligned by task id.

    Raises:
        ValueError: If the two cells were not run on the same tasks. Positional
            pairing after a dropped episode misaligned pairs in v0
            (``docs/audit.md`` D2); here mismatched task sets are refused.
    """
    if set(a) != set(b):
        raise ValueError(
            f"cells cover different tasks ({len(set(a) ^ set(b))} differ); refusing to pair"
        )
    ids = sorted(a)
    diffs = [float(a[i]["correct"]) - float(b[i]["correct"]) for i in ids]
    mean = sum(diffs) / len(diffs) if diffs else float("nan")
    return {
        "n_paired": len(diffs),
        "mean_difference": mean,
        "ci95": list(bootstrap_ci(
            diffs, n_resamples=DESIGN.bootstrap_resamples, seed=DESIGN.bootstrap_seed
        )),
        "ci_bonferroni": list(bootstrap_ci(
            diffs,
            n_resamples=DESIGN.bootstrap_resamples,
            seed=DESIGN.bootstrap_seed,
            alpha=0.05 / n_contrasts,
        )),
        "bonferroni_family_size": n_contrasts,
    }


def analyze(run_dir: Path, *, allow_incomplete: bool = False) -> dict[str, Any]:
    """Every pre-registered number for one primary run."""
    manifest, episodes = load_run(run_dir, allow_incomplete=allow_incomplete)
    result: dict[str, Any] = {
        "run": run_dir.name,
        "complete": manifest.get("complete"),
        "models": manifest["models"],
        "cost_usd": manifest.get("total_cost_usd"),
        "truncated_calls": manifest.get("truncated_calls"),
        "chance": 1.0 / 4,
        "cells": {},
        "contrasts": {},
    }
    for model in manifest["models"]:
        by_cell: dict[tuple[str, str], dict[str, Any]] = {}
        for cell in CELLS:
            rows = [e for e in episodes if e["model"] == model
                    and (e["condition"], e["objective"]) == cell]
            by_cell[cell] = {e["task_id"]: e for e in rows}
            result["cells"].setdefault(model, {})[f"{cell[0]}/{cell[1]}"] = cell_summary(rows)
        result["contrasts"][model] = {
            label: paired_contrast(by_cell[a], by_cell[b], n_contrasts=len(CONTRASTS))
            for label, a, b in CONTRASTS
        }
    return result


def markdown(result: Mapping[str, Any]) -> str:
    """The result as tables."""
    def pct(x: float) -> str:
        return f"{x * 100:.1f}%"

    lines = [f"# hidden_profile_v2 eval: {result['run']}", ""]
    if not result["complete"]:
        lines += ["**INCOMPLETE RUN.** Read every number below as partial.", ""]
    for model in result["models"]:
        lines += [f"## {model}", "", "| Condition | Objective stated | Objective not stated |",
                  "|---|---|---|"]
        for condition in ("full_info", "no_communication", "communication"):
            cells = []
            for objective in ("stated", "unstated"):
                c = result["cells"][model][f"{condition}/{objective}"]
                cells.append(
                    f"{c['correct']}/{c['n']} · {pct(c['accuracy'])} "
                    f"[{pct(c['ci95'][0])}, {pct(c['ci95'][1])}]"
                )
            lines.append(f"| {condition} | {cells[0]} | {cells[1]} |")
        lines += ["", "| Contrast | Mean | 95% | Bonferroni |", "|---|---:|---:|---:|"]
        for label, c in result["contrasts"][model].items():
            lines.append(
                f"| {label} | {c['mean_difference'] * 100:+.1f} | "
                f"[{c['ci95'][0] * 100:+.1f}, {c['ci95'][1] * 100:+.1f}] | "
                f"[{c['ci_bonferroni'][0] * 100:+.1f}, {c['ci_bonferroni'][1] * 100:+.1f}] |"
            )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Analyse one primary run and write ``results.json`` and ``results.md`` into it."""
    parser = argparse.ArgumentParser(prog="python -m studies.v2_eval.analyze")
    parser.add_argument("run_dir")
    parser.add_argument("--incomplete", action="store_true",
                        help="analyse an incomplete run; the output says so")
    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir)
    result = analyze(run_dir, allow_incomplete=args.incomplete)
    (run_dir / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    text = markdown(result)
    (run_dir / "results.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
