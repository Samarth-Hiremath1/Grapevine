"""Exploratory follow-up to the external review (``docs/review-v0.2.md``).

    python -m studies.v2_eval.review_followup            # regenerate
    python -m studies.v2_eval.review_followup --check    # verify; CI runs this

**Not pre-registered.** Nothing here changes a pre-registered number or reading;
it re-derives the review's findings from committed runs and the generators, so
the numbers the response quotes are reproducible (``CLAUDE.md`` rule 1).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import random
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from grapevine import Environment, audit, get_environment
from grapevine.audit.solvers import count_mentions
from grapevine.experiments.analysis import bootstrap_ci
from grapevine.protocol import DistributedTask, support_total
from grapevine.rewards.reward import fact_surfaced
from studies.v2_eval.design import DESIGN, ENVIRONMENT

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "studies/v2_eval/runs/20261116T091238Z_primary"
OUT_PATH = Path(__file__).resolve().parent / "review_followup.md"
MODELS = ("gpt-5.6-luna", "gpt-6-luna", "gpt-4o-mini")


def _episodes() -> list[dict[str, Any]]:
    lines = (RUN / "episodes.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _cell(eps: Sequence[dict[str, Any]], model: str, condition: str, objective: str) -> dict[str, Any]:
    return {e["task_id"]: e for e in eps
            if e["model"] == model and e["condition"] == condition and e["objective"] == objective}


def h3_detail() -> dict[str, Any]:
    """Discordant pairs, truncations among them, McNemar, and bootstrap-seed sensitivity.

    Returns:
        dict[str, Any]: Per model, for ``full_info - communication``, objective stated.
    """
    eps = _episodes()
    out: dict[str, Any] = {}
    for model in MODELS:
        a = _cell(eps, model, "full_info", "stated")
        b = _cell(eps, model, "communication", "stated")
        only_full = sorted(t for t in a if a[t]["correct"] and not b[t]["correct"])
        only_comm = sorted(t for t in a if b[t]["correct"] and not a[t]["correct"])
        failed_to_answer = [t for t in only_full if b[t]["truncated"] or b[t]["parse_failure"]]
        n, k = len(only_full) + len(only_comm), min(len(only_full), len(only_comm))
        p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2**n) if n else 1.0
        diffs = [float(a[t]["correct"]) - float(b[t]["correct"]) for t in sorted(a)]
        lower = {
            seed: bootstrap_ci(diffs, n_resamples=DESIGN.bootstrap_resamples, seed=seed,
                               alpha=0.05 / 7)[0]
            for seed in (DESIGN.bootstrap_seed, 1, 2, 3)
        }
        out[model] = {
            "only_full": len(only_full), "only_comm": len(only_comm),
            "only_full_comm_failed_to_answer": len(failed_to_answer),
            "failed_task_ids": failed_to_answer, "mcnemar_p": p,
            "bonferroni_lower_by_seed": {str(s): v for s, v in lower.items()},
        }
    return out


def surfacing() -> dict[str, Any]:
    """Correct communication episodes in which agents 1 and 2 did not surface all their gold facts.

    Uses the repository's ``fact_surfaced`` at its default threshold, whose recall
    was about 0.86 on v0 (``docs/audit.md`` L5), so this over-counts misses.

    Returns:
        dict[str, Any]: Per model, objective stated.
    """
    eps = _episodes()
    out: dict[str, Any] = {}
    for model in MODELS:
        rows = [e for e in _cell(eps, model, "communication", "stated").values() if e["correct"]]
        missing = 0
        for e in rows:
            task = ENVIRONMENT.generate(e["seed"])
            said = {a: " ".join(t["completion"] or "" for t in e["turns"]
                                if t["agent"] == a and t["kind"] == "discussion") for a in (1, 2)}
            if not all(fact_surfaced(u.text, said[a]) for a in (1, 2)
                       for u in task.views[a].private if u.supports == task.gold_answer):
                missing += 1
        out[model] = {"correct": len(rows), "not_all_gold_surfaced": missing}
    return out


def _probe_counts(env: Environment, seeds: range) -> dict[str, list[int]]:
    rng = random.Random(0)
    c = {"named_not_most_named": [0, 0], "least_shared_support": [0, 0],
         "full_info_most_named_in_private_block": [0, 0]}
    for seed in seeds:
        task: DistributedTask = env.generate(seed)
        opts = task.answer_space
        text = "\n".join(u.text for u in task.full_view().private)
        named = {o: count_mentions(text, o) for o in opts}
        top = max(named.values())
        c["full_info_most_named_in_private_block"][0] += (
            rng.choice([o for o in opts if named[o] == top]) == task.gold_answer)
        c["full_info_most_named_in_private_block"][1] += 1
        for view in task.views:
            text = "\n".join(u.text for u in view.private)
            named = {o: count_mentions(text, o) for o in opts}
            top = max(named.values())
            pool = [o for o in opts if 0 < named[o] < top] or list(opts)
            c["named_not_most_named"][0] += rng.choice(pool) == task.gold_answer
            c["named_not_most_named"][1] += 1
            shared = support_total(view.shared, opts)
            low = min(shared.values())
            c["least_shared_support"][0] += rng.choice([o for o in opts if shared[o] == low]) == task.gold_answer
            c["least_shared_support"][1] += 1
    return c


def probes() -> dict[str, Any]:
    """Single-view probes outside the battery, on v2, the clean control and the example.

    Returns:
        dict[str, Any]: Per environment, ``[correct, n]`` for each probe.
    """
    sys.path.insert(0, str(ROOT / "tests"))
    from fixtures.flawed_envs import (  # type: ignore[import-not-found]
        CLEAN_CONTROL,
        FLAWED_ENVS,
    )

    spec = importlib.util.spec_from_file_location("venue_example", ROOT / "examples/02_write_an_environment.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["venue_example"] = module
    spec.loader.exec_module(module)
    legacy, _ = FLAWED_ENVS["legacy_pointer_support"]
    return {
        "hidden_profile_v2 (eval 10000-10199)": _probe_counts(get_environment("hidden_profile_v2"), range(10000, 10200)),
        "control as reviewed (eval 1000-1199)": _probe_counts(legacy, range(1000, 1200)),
        "control now (eval 1000-1199)": _probe_counts(CLEAN_CONTROL, range(1000, 1200)),
        "venue_choice now (eval 10000-10199)": _probe_counts(module.VenueChoice(), range(10000, 10200)),
    }


def partial_leak() -> list[dict[str, Any]]:
    """The audit's verdict when a decisive leak is planted in a fraction of tasks.

    Returns:
        list[dict[str, Any]]: One row per leak fraction.
    """
    sys.path.insert(0, str(ROOT / "tests"))
    from fixtures.flawed_envs import ControlEnv

    clean, leaky = ControlEnv(), ControlEnv(leak_decisive_unit=True)

    class Partial(Environment):
        name = "partial_leak"
        version = "1"

        def __init__(self, frac: float) -> None:
            self.frac = frac

        def _pick(self, seed: int) -> Any:
            return leaky if random.Random(seed * 31 + 7).random() < self.frac else clean

        def generate(self, seed: int) -> DistributedTask:
            task: DistributedTask = self._pick(seed).generate(seed)
            return task

        def conditions(self, task: DistributedTask) -> Any:
            return clean.conditions(task)

        def seed_split(self) -> Any:
            return clean.seed_split()

    rows = []
    for frac in (0.1, 0.2, 0.3):
        card = audit(Partial(frac), n_tasks=200, seed=0)
        leaked = sum(random.Random(s * 31 + 7).random() < frac for s in range(200))
        rows.append({"fraction": frac, "leaky_tasks": leaked, "verdict": card.verdict.value,
                     "leak": card.get("leak").status.value,
                     "solo_solvability": card.get("solo_solvability").status.value})
    return rows


def markdown() -> str:
    """Every follow-up number, as a report.

    Returns:
        str: Markdown text.
    """
    h3, surf, pr, leak = h3_detail(), surfacing(), probes(), partial_leak()
    lines = [
        "# Review follow-up (exploratory, not pre-registered)",
        "",
        "Generated by `python -m studies.v2_eval.review_followup`. Do not edit by hand.",
        "Re-derives the findings of `docs/review-v0.2.md` from committed runs and the",
        "generators. Nothing here is a pre-registered result.",
        "",
        "## H3 contrast in detail (`full_info - communication`, objective stated)",
        "",
        "| Model | Only full_info correct | Only communication correct | ...of the former, communication truncated or unparsed | Exact McNemar p (two-sided) | Bonferroni lower bound, bootstrap seeds 20261115 / 1 / 2 / 3 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for m, r in h3.items():
        lows = " / ".join(f"{v * 100:+.1f}" for v in r["bonferroni_lower_by_seed"].values())
        lines.append(f"| {m} | {r['only_full']} | {r['only_comm']} | "
                     f"{r['only_full_comm_failed_to_answer']} | {r['mcnemar_p']:.3f} | {lows} |")
    lines += ["", "## Was the information pooled? (communication, objective stated)", "",
              "| Model | Correct episodes | ...in which agents 1 and 2 did not surface every gold fact they held |",
              "|---|---:|---:|"]
    for m, r in surf.items():
        lines.append(f"| {m} | {r['correct']} | {r['not_all_gold_surfaced']} |")
    lines += ["", "`fact_surfaced` had recall about 0.86 on v0, so this over-counts misses.", "",
              "## Single-view probes outside the battery", "",
              "Chance is 25%. `full_info_most_named_in_private_block` reads the full-information",
              "prompt's \"Facts only you know\" block. \"As reviewed\" is the control's layout at",
              "the time of the review, kept as the negative control `legacy_pointer_support`;",
              "\"now\" is the layout that replaced it. The example as reviewed is at commit",
              "`f9491cf` (`examples/02_write_an_environment.py`).", "",
              "| Environment | Probe | Correct |", "|---|---|---:|"]
    for env, counts in pr.items():
        for probe, (k, n) in counts.items():
            lines.append(f"| {env} | `{probe}` | {k}/{n} |")
    lines += ["", "## A decisive leak in a fraction of tasks, under the current battery", "",
              "At the time of the review, the 0.1 and 0.2 rows passed `leak` (`docs/review-v0.2.md`, M2).",
              "The check is now zero-tolerance.", "",
              "| Fraction | Tasks with a decisive unit | Verdict | `leak` | `solo_solvability` |",
              "|---:|---:|---|---|---|"]
    for r in leak:
        lines.append(f"| {r['fraction']} | {r['leaky_tasks']}/200 | {r['verdict']} | {r['leak']} | {r['solo_solvability']} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Regenerate the report, or verify it with ``--check``.

    Args:
        argv (list[str] | None): Command-line arguments.

    Returns:
        int: Exit code.
    """
    parser = argparse.ArgumentParser(prog="python -m studies.v2_eval.review_followup")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    text = markdown()
    if args.check:
        same = OUT_PATH.exists() and OUT_PATH.read_text(encoding="utf-8") == text
        print("review_followup.md " + ("unchanged" if same else "has drifted"))
        return 0 if same else 1
    OUT_PATH.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
