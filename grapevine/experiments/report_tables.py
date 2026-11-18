"""Rebuild every table and the main figure in ``docs/results.md`` from committed runs.

Nothing in the results write-up is typed in by hand: this module reads the run
directories listed in :data:`RUNS`, recomputes each number with the same
functions the runner uses, writes them to ``docs/figures/results_tables.json``,
prints the tables as Markdown, and redraws the main figure.

Usage:
    python -m grapevine.experiments.report_tables
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from grapevine.experiments.analysis import clopper_pearson
from grapevine.experiments.compare import compare, load_condition
from grapevine.experiments.figure import make_two_panel_figure
from grapevine.rewards.reward import compute_surfacing
from grapevine.rollout.engine import Episode

#: Committed runs the write-up draws on.
RUNS: dict[str, str] = {
    "primary": "runs/20260910T065248Z_primary",
    "D_fixed": "runs/20260918T222732Z_D_fixed",
    "rule_AC": "runs/20260913T013826Z_rule_arm",
    "rule_BD": "runs/20260918T222744Z_rule_arm_BD",
    "A_matched_rule": "runs/20260919T011615Z_A_matched_rule",
}

#: (label, run key, condition). Task not stated. D is the rerun with the
#: aggregator fixed; the original D in the primary run is superseded.
NO_RULE = [
    ("A", "primary", "full_info"),
    ("B", "primary", "no_communication"),
    ("C", "primary", "communication"),
    ("D", "D_fixed", "communication_neutral"),
]

#: Task question and scoring rule stated.
RULE = [
    ("A", "rule_AC", "full_info_rule"),
    ("A (matched)", "A_matched_rule", "full_info_matched_rule"),
    ("B", "rule_BD", "no_communication_rule"),
    ("C", "rule_AC", "communication_rule"),
    ("D", "rule_BD", "communication_neutral_rule"),
]

#: Seeds shared by every rule-arm run.
RULE_SEEDS = {f"hidden_profile-{s}" for s in range(1000, 1100)}

_ASK = re.compile(
    r"criteri|weighting|rubric|what (exact )?decision|ranking|what (final )?output"
    r"|how (should|do) we (decide|weigh)",
    re.IGNORECASE,
)


def _cell(episodes: list[Episode]) -> dict[str, Any]:
    n = len(episodes)
    k = sum(e.correct for e in episodes)
    decoy = sum(
        e.team_answer is not None and e.team_answer == e.metadata.get("decoy_option")
        for e in episodes
    )
    lo, hi = clopper_pearson(k, n)
    has_talk = any(m.role == "discussion" for e in episodes for m in e.messages)
    return {
        "n": n,
        "correct": k,
        "accuracy": k / n,
        "ci95": [lo, hi],
        "decoy": decoy,
        "decoy_rate": decoy / n,
        "parse_failures": sum(e.team_answer is None for e in episodes),
        "empty_answers": sum(
            e.team_answer is None and not e.messages[-1].content.strip() for e in episodes
        ),
        "surfacing": (
            sum(compute_surfacing(e).surfacing_rate for e in episodes) / n if has_talk else None
        ),
        "asked_for_criteria": (
            sum(
                any(m.role == "discussion" and _ASK.search(m.content) for m in e.messages)
                for e in episodes
            )
            if has_talk
            else None
        ),
    }


def _by_position(episodes: list[Episode]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for slot in range(len(episodes[0].options)):
        eps = [e for e in episodes if e.options.index(e.gold_answer) == slot]
        k = sum(e.correct for e in eps)
        out[str(slot)] = {"n": len(eps), "correct": k, "accuracy": k / len(eps) if eps else None}
    return out


def _diff(base: tuple[Path, str], other: tuple[Path, str]) -> dict[str, Any]:
    d = compare(base[0], base[1], other[0], other[1])
    acc = d["accuracy_other_minus_base"]
    return {"n": d["n_matched"], "mean": acc["mean"], "ci95": acc["ci95"]}


def build(root: Path) -> dict[str, Any]:
    """Compute every reported number from the committed runs under ``root``."""
    runs = {k: root / v for k, v in RUNS.items()}
    result: dict[str, Any] = {"runs": RUNS, "no_rule": {}, "no_rule_seeds_1000_1099": {}, "rule": {}}

    for label, run, cond in NO_RULE:
        eps = load_condition(runs[run], cond)
        result["no_rule"][label] = {"run": RUNS[run], "condition": cond, **_cell(list(eps.values()))}
        result["no_rule_seeds_1000_1099"][label] = _cell(
            [eps[i] for i in sorted(RULE_SEEDS)]
        )
    for label, run, cond in RULE:
        eps = load_condition(runs[run], cond)
        result["rule"][label] = {"run": RUNS[run], "condition": cond, **_cell(list(eps.values()))}

    nr = {label: (runs[run], cond) for label, run, cond in NO_RULE}
    ru = {label: (runs[run], cond) for label, run, cond in RULE}
    result["rule_effect"] = {
        label: _diff(nr[label], ru[label]) for label in ("A", "B", "C", "D")
    }
    result["rule_effect"]["A (matched) vs A no rule"] = _diff(nr["A"], ru["A (matched)"])
    result["a_matched_minus_a_original_with_rule"] = _diff(ru["A"], ru["A (matched)"])
    pairs = [("C", "B"), ("D", "B"), ("C", "D"), ("A", "C"), ("A", "D")]
    result["within_no_rule"] = {f"{x}-{y}": _diff(nr[y], nr[x]) for x, y in pairs}
    rule_pairs = pairs + [("A (matched)", "C"), ("A (matched)", "D")]
    result["within_rule"] = {f"{x}-{y}": _diff(ru[y], ru[x]) for x, y in rule_pairs}
    result["superseded_D_vs_fixed_D"] = _diff(
        (runs["primary"], "communication_neutral"), (runs["D_fixed"], "communication_neutral")
    )

    result["position_effect"] = {
        "no_rule": {
            label: _by_position(list(load_condition(runs[run], cond).values()))
            for label, run, cond in NO_RULE
        },
        "rule": {
            label: _by_position(list(load_condition(runs[run], cond).values()))
            for label, run, cond in RULE
        },
    }

    costs = {}
    for manifest in sorted(root.glob("runs/*/manifest.json")):
        m = json.loads(manifest.read_text(encoding="utf-8"))
        costs[manifest.parent.name] = {
            "cost_usd": m["total_cost_usd"],
            "calls": m["client_totals"]["n_calls"],
            "git_commit": m["git_commit"],
            "git_dirty": m["git_dirty"],
        }
    result["costs"] = costs
    result["total_cost_usd"] = sum(c["cost_usd"] for c in costs.values())
    return result


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def markdown(r: dict[str, Any]) -> str:
    """Render the main tables as Markdown."""
    lines = [
        "| Condition | Task not stated (N=200) | Task not stated, seeds 1000-1099 | Task stated, seeds 1000-1099 |",
        "|---|---|---|---|",
    ]
    for label in ("A", "B", "C", "D"):
        a, m = r["no_rule"][label], r["no_rule_seeds_1000_1099"][label]
        cells = [
            f"{a['correct']}/{a['n']} · {_pct(a['accuracy'])} [{_pct(a['ci95'][0])}, {_pct(a['ci95'][1])}]",
            f"{m['correct']}/{m['n']} · {_pct(m['accuracy'])} [{_pct(m['ci95'][0])}, {_pct(m['ci95'][1])}]",
        ]
        rule_labels = ["A", "A (matched)"] if label == "A" else [label]
        rule_cells = []
        for rl in rule_labels:
            c = r["rule"][rl]
            rule_cells.append(
                f"{rl}: {c['correct']}/{c['n']} · {_pct(c['accuracy'])} "
                f"[{_pct(c['ci95'][0])}, {_pct(c['ci95'][1])}]"
            )
        lines.append(f"| {label} | {cells[0]} | {cells[1]} | {'<br>'.join(rule_cells)} |")
    return "\n".join(lines)


def _rounded(obj: Any) -> Any:
    """Round floats to 10 places so last-bit libm differences between
    platforms do not show up as changes to the committed JSON."""
    if isinstance(obj, float):
        return round(obj, 10)
    if isinstance(obj, dict):
        return {k: _rounded(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_rounded(v) for v in obj]
    return obj


def main(argv: list[str] | None = None) -> int:
    """Rebuild the tables JSON and the main figure."""
    parser = argparse.ArgumentParser(prog="python -m grapevine.experiments.report_tables")
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("--out-dir", default="docs/figures", help="where to write outputs")
    args = parser.parse_args(argv)
    root = Path(args.root)
    out = root / args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    r = _rounded(build(root))
    (out / "results_tables.json").write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8")

    panels = [
        (
            "Task and rule not stated\n(seeds 1000-1199, n=200 each)",
            [(lbl, r["no_rule"][lbl]) for lbl in ("A", "B", "C", "D")],
        ),
        (
            "Task question and scoring rule stated\n(seeds 1000-1099, n=100 each)",
            [(lbl, r["rule"][lbl]) for lbl in ("A", "A (matched)", "B", "C", "D")],
        ),
    ]
    make_two_panel_figure(panels, out, stem="accuracy_by_condition")
    print(markdown(r))
    print(f"\nwrote {out / 'results_tables.json'} and accuracy_by_condition.png/.svg/.csv")
    print(f"total spend across all committed runs: ${r['total_cost_usd']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
