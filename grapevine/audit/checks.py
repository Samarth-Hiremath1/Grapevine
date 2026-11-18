"""The audit battery: one function per check, each returning a :class:`CheckResult`.

Every check here exists because of a specific mistake, and most of them because
of a mistake in this repository. The ``audit_findings`` field on each result
names the finding in ``docs/audit.md`` it would have caught, so the battery
cannot drift into checking things nobody has ever got wrong.

Checks are model-free and deterministic. They run over a batch of generated
tasks and interrogate the task construction, the prompts and the scorer -- never
a policy's behaviour. That is the point: a validity problem should be findable
before any tokens are spent.
"""

from __future__ import annotations

import difflib
import math
import random
import re
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from grapevine.audit.card import CheckResult, Status
from grapevine.audit.solvers import (
    DEGENERATE_POLICIES,
    SHORTCUT_SOLVERS,
    count_mentions,
    genuine_pooling,
    leaders_of,
    least_shared_support,
    mention_count,
    named_not_most_named_privately,
    private_scoring_rule,
    reference,
    uniquely_determined,
    units_without,
    view_rank_features,
)
from grapevine.protocol import (
    AgentView,
    Condition,
    DistributedTask,
    Environment,
    binomial_tail_p,
    support_total,
)

__all__ = [
    "CHECKS",
    "MIN_TASKS_TO_CLASSIFY",
    "CheckContext",
    "family_alpha",
    "minimum_detectable_accuracy",
    "run_checks",
]

#: Upper-tail chi-square critical values at alpha = 0.05, by degrees of freedom.
#: A small table rather than a dependency on scipy; the v0 audit used the same
#: method and the same df=3 value of 7.81 (``docs/audit.md`` G3).
_CHI2_CRITICAL_05 = {
    1: 3.84, 2: 5.99, 3: 7.81, 4: 9.49, 5: 11.07, 6: 12.59, 7: 14.07,
    8: 15.51, 9: 16.92, 10: 18.31, 11: 19.68, 12: 21.03, 13: 22.36,
    14: 23.68, 15: 25.00, 16: 26.30, 17: 27.59, 18: 28.87, 19: 30.14,
    20: 31.41,
}


@dataclass(frozen=True)
class CheckContext:
    """Everything a check is given.

    Attributes:
        env: The environment under audit.
        tasks: The generated batch, all from the same environment.
        seed: Base seed the batch came from.
        alpha: Significance level for "beats chance" and "indistinguishable
            from pooling" tests.
        rng_seed: Seed for solvers that break ties at random, so a run is
            reproducible.
    """

    env: Environment
    tasks: tuple[DistributedTask, ...]
    seed: int
    alpha: float = 0.05
    rng_seed: int = 0

    def rng(self) -> random.Random:
        """A fresh RNG, identical for every check, so results are comparable."""
        return random.Random(self.rng_seed * 7919 + 1)

    @property
    def n(self) -> int:
        """Number of tasks in the batch."""
        return len(self.tasks)

    @property
    def chance(self) -> float:
        """Mean chance accuracy across the batch."""
        return statistics.fmean(t.chance for t in self.tasks)


Check = Callable[[CheckContext], CheckResult]

#: Registered checks, in the order they appear on a card.
CHECKS: list[Check] = []


def _check(fn: Check) -> Check:
    """Register a check."""
    CHECKS.append(fn)
    return fn


def family_alpha(alpha: float, n_probes: int) -> float:
    """``alpha`` Bonferroni-corrected for the number of probes in one check.

    This matters more than it sounds. A check that runs five shortcut probes at
    an uncorrected 0.05 has a family-wise false-alarm rate of up to 1 - 0.95**5,
    about 23%, if the probes were independent; they are correlated, and the
    simulation in ``tests/test_audit.py`` gives about one clean environment in
    five failed for nothing. For a validity auditor
    that is the worst available failure mode: it teaches people to ignore the
    tool. ``docs/audit.md`` S3 applied the same correction to the study's four
    paired comparisons.

    ``tests/test_audit.py`` demonstrates the uncorrected error rate rather than
    asserting it, so the reasoning stays in the repository.
    """
    return alpha / max(1, n_probes)


def _beats_chance(n_correct: int, n: int, chance: float, alpha: float) -> tuple[float, bool]:
    """Exact one-sided test that an accuracy exceeds chance.

    Returns ``(p_value, beats)``. ``alpha`` should already be corrected for the
    number of probes in the calling check -- see :func:`family_alpha`.
    """
    p = binomial_tail_p(n_correct, n, chance)
    return p, p < alpha


def tie_credited_tail_p(trials: Sequence[tuple[int, bool, int]]) -> tuple[float, float]:
    """Exact p-value for an accuracy in which a k-way tie counts 1/k.

    Each trial is ``(k, hit, m)``: the solver chose among ``k`` tied options, the
    gold option was among them (``hit``), out of ``m`` options in all. The trial
    scores ``1/k`` on a hit. Under the null -- the tied set says nothing about
    which option is gold -- a hit has probability ``k/m``, so a trial's expected
    score is ``1/m`` whatever ``k`` is, and a fully tied view (``k == m``)
    contributes exactly ``1/m`` with no variance at all. That is the point: an
    uninformative solver can no longer fail an environment by drawing lucky
    tie-breaks.

    Args:
        trials (Sequence[tuple[int, bool, int]]): One entry per solved view.

    Returns:
        tuple[float, float]: The observed total score, and P(score >= observed)
        under the null, computed exactly by convolution.
    """
    import math

    import numpy as np

    if not trials:
        return 0.0, 1.0
    unit = 1
    for k, _, _ in trials:
        unit = unit * k // math.gcd(unit, k)
    observed = sum(unit // k for k, hit, _ in trials if hit)
    dist = np.zeros(unit * len(trials) + 1)
    dist[0] = 1.0
    top = 0
    for k, _, m in trials:
        step, q = unit // k, k / m
        new = dist * (1 - q)
        new[step: top + step + 1] += dist[: top + 1] * q
        dist, top = new, top + step
    p = float(dist[observed:].sum())
    return observed / unit, min(1.0, max(0.0, p))


def _tie_credited_row(name: str, trials: Sequence[tuple[int, bool, int]], chance: float,
                      alpha: float) -> dict[str, Any]:
    """A probe's line of results, with ties scored by their expected value."""
    score, p = tie_credited_tail_p(trials)
    n = len(trials)
    commits = sum(1 for k, _, _ in trials if k == 1)
    return {
        "commits": commits,
        "right_when_committed": sum(1 for k, hit, _ in trials if k == 1 and hit),
        "name": name,
        "n_correct": int(score) if float(score).is_integer() else round(score, 2),
        "n": n,
        "accuracy": score / n if n else 0.0,
        "chance": chance,
        "p_value_vs_chance": p,
        "beats_chance": p < alpha,
        "ties_scored_by_expectation": True,
    }


def _accuracy_row(name: str, n_correct: int, n: int, chance: float, alpha: float) -> dict[str, Any]:
    """One solver's or policy's line of results."""
    p, beats = _beats_chance(n_correct, n, chance, alpha)
    return {
        "name": name,
        "n_correct": n_correct,
        "n": n,
        "accuracy": n_correct / n if n else 0.0,
        "chance": chance,
        "p_value_vs_chance": p,
        "beats_chance": beats,
    }


def minimum_detectable_accuracy(n: int, chance: float, alpha: float, power: float = 0.8) -> float:
    """The lowest true accuracy a one-sided binomial test at ``alpha`` detects with ``power``.

    Reported on every card's ``solo_solvability``, because "no solver beat
    chance" is a statement about this sample size. For an environment whose
    answer is the argmax of summed evidence, some single view always carries
    information about the answer (``docs/audit-battery.md``, "Why a pass is a
    bound"), so a pass means the advantage is below this level, not zero.

    Args:
        n (int): Trials per probe.
        chance (float): Accuracy under the null.
        alpha (float): The per-probe significance level.
        power (float): Required probability of detection.

    Returns:
        float: The smallest accuracy, to 0.001, detected with at least ``power``.
    """
    if n <= 0:
        return 1.0
    critical = next((k for k in range(n + 1) if binomial_tail_p(k, n, chance) < alpha), n + 1)
    if critical > n:
        return 1.0
    p = chance
    while p < 1.0:
        # P(X >= critical) under Binomial(n, p)
        if binomial_tail_p(critical, n, p) >= power:
            return round(p, 3)
        p += 0.001
    return 1.0


# --- 1. Leak -----------------------------------------------------------------


def _private_named_option(view: AgentView, answer_space: Sequence[str], rng: random.Random) -> str:
    """Name the option that this agent's *private* units are about.

    A deliberately naive reader: it ignores the shared block entirely and picks
    whichever option its own secret facts mention most. On a hidden-profile task
    every private fact supports the correct option by construction, so this
    shortcut can be perfect even when applying the task's own scoring rule to
    the same view gives the wrong answer.
    """
    text = "\n".join(u.text for u in view.private)
    scores = {option: float(count_mentions(text, option)) for option in answer_space}
    best = max(scores.values())
    leaders = [o for o in answer_space if scores[o] == best]
    return rng.choice(leaders) if len(leaders) > 1 else leaders[0]


@_check
def check_leak(ctx: CheckContext) -> CheckResult:
    """The gold answer, or a statistic sufficient for it, sits in one agent's view."""
    only_gold_named = 0
    single_unit_decides = 0
    gold_verbatim = 0
    examples: list[dict[str, Any]] = []

    for task in ctx.tasks:
        leaked_here = False
        for view in task.views:
            named = {o for o in task.answer_space if o.lower() in view.render().lower()}
            if named == {task.gold_answer}:
                only_gold_named += 1
                leaked_here = True
                break
        # One unit whose support outweighs every option's total support: whoever
        # holds it can decide the task alone.
        totals = support_total(task.all_units(), task.answer_space)
        for unit in task.all_units():
            if unit.supports != task.gold_answer:
                continue
            rivals = max((v for o, v in totals.items() if o != task.gold_answer), default=0.0)
            if unit.weight > rivals:
                single_unit_decides += 1
                leaked_here = True
                break
        if any(task.gold_answer in u.text for v in task.views for u in v.private):
            gold_verbatim += 1
        if leaked_here and len(examples) < 3:
            examples.append({"task_id": task.task_id, "gold": task.gold_answer})

    # Zero tolerance. A view that names only the gold option, or a unit that
    # outweighs every rival, settles that task for whoever holds it; one such task
    # is a defect regardless of how many others are clean. This check once tested
    # the share of leaking tasks against chance *accuracy*, which let a decisive
    # leak in 43 of 200 tasks pass (docs/review-v0.2.md, M2).
    n = ctx.n
    detail = {
        "tasks_where_a_view_names_only_gold": only_gold_named,
        "tasks_where_one_unit_outweighs_all_rivals": single_unit_decides,
        "n_tasks": n,
        "tolerance": 0,
        "gold_string_appears_in_some_private_unit": {
            "n": gold_verbatim,
            "rate": gold_verbatim / n if n else 0.0,
            "note": (
                "Informational. A unit mentioning the gold option is normal -- it is "
                "evidence. It is only a leak when it settles the answer, which the two "
                "counts above test."
            ),
        },
        "examples": examples,
    }

    if only_gold_named or single_unit_decides:
        parts = []
        if only_gold_named:
            parts.append(f"in {only_gold_named}/{n} tasks some agent's view names the gold option and no other")
        if single_unit_decides:
            parts.append(
                f"in {single_unit_decides}/{n} tasks a single unit outweighs every rival "
                "option's total support, so whoever holds it decides alone"
            )
        return CheckResult(
            "leak",
            "Answer leak into a single view",
            Status.FAIL,
            "The answer is available without pooling: " + "; and ".join(parts) + ".",
            detail,
            ("P4", "G6"),
        )
    return CheckResult(
        "leak",
        "Answer leak into a single view",
        Status.PASS,
        f"In none of {n} tasks does a view name the gold option alone or a single unit "
        "settle the task.",
        detail,
        ("P4", "G6"),
    )


#: Below this many tasks, the learned probe's held-out half and the twin test
#: have too little to work with, and solo_solvability and reward_hacking report
#: ``inconclusive``. A floor on evidence, not a tolerance on the answer.
MIN_TASKS_TO_CLASSIFY = 20


def _wilson(score: float, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson 95% interval for a proportion; ``score`` may be fractional (tie credit)."""
    if n <= 0:
        return (0.0, 1.0)
    p = score / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def _view_signature(view: AgentView, answer_space: Sequence[str]) -> dict[str, tuple[float, ...]]:
    """Per option: private support, private mentions, shared support, shared mentions."""
    private_text = "\n".join(u.text for u in view.private)
    shared_text = "\n".join(u.text for u in view.shared)
    priv = support_total(view.private, answer_space)
    shar = support_total(view.shared, answer_space)
    return {
        o: (round(priv[o], 6), count_mentions(private_text, o), round(shar[o], 6),
            count_mentions(shared_text, o))
        for o in answer_space
    }


def _twin_analysis(ctx: CheckContext) -> dict[str, Any]:
    """Feature-level twins: do views with the same evidence pattern share an answer?

    Two views are *feature twins* when they have the same evidence pattern: the
    same multiset, over options, of (private support, private mentions, shared
    support, shared mentions). This is indistinguishability at the level of
    those four counts only. It does not show that the full observations -- the
    actual text an agent reads -- are indistinguishable: wording, unit order and
    length differ between feature twins, and a view could determine its answer
    through them. So this test cannot prove that a view fails to determine the
    answer; it reports how often the evidence pattern alone leaves it open.

    A view has a *feature twin with a different answer* when another option in
    the same view has gold's feature profile, or another audited view with the
    same pattern has its gold option at a different profile. Otherwise its
    feature twins, if any, all agree, or it has none in the batch.
    """
    Profile = tuple[float, ...]
    signatures: dict[tuple[Profile, ...], set[Profile]] = {}
    seen: dict[tuple[Profile, ...], int] = {}
    per_view: list[tuple[int, tuple[Profile, ...], Profile, bool]] = []
    for task in ctx.tasks:
        for view in task.views:
            sig = _view_signature(view, task.answer_space)
            canon = tuple(sorted(sig.values()))
            gold_profile = sig[task.gold_answer]
            within = sum(1 for o in task.answer_space if sig[o] == gold_profile) > 1
            signatures.setdefault(canon, set()).add(gold_profile)
            seen[canon] = seen.get(canon, 0) + 1
            per_view.append((view.agent_id, canon, gold_profile, within))
    agents: dict[int, dict[str, int]] = {}
    for agent_id, canon, _, within in per_view:
        row = agents.setdefault(agent_id, {"views": 0, "feature_twin_with_different_answer": 0,
                                           "feature_twins_all_same_answer": 0,
                                           "no_feature_twin": 0})
        row["views"] += 1
        if within or len(signatures[canon]) > 1:
            row["feature_twin_with_different_answer"] += 1
        elif seen[canon] > 1:
            row["feature_twins_all_same_answer"] += 1
        else:
            row["no_feature_twin"] += 1
    return {
        "level": "feature-level only",
        "abstraction": (
            "views compared by evidence pattern: per option (private support, private "
            "mentions, shared support, shared mentions); option names treated as "
            "exchangeable; wording, order and length ignored. Feature twins are not "
            "shown to be indistinguishable as full observations."
        ),
        "per_agent": {str(a): r for a, r in sorted(agents.items())},
    }


# --- 2. Solo solvability -----------------------------------------------------


def _learned_single_view(ctx: CheckContext) -> dict[str, Any]:
    """Learn any rule over within-view feature ranks on half the tasks; test on the rest.

    Not limited to a hand-written list: on the first half of the batch it counts,
    for every feature tuple from :func:`view_rank_features`, how often an option
    with that tuple was gold; on the second half it picks, in each view, the option
    whose tuple was gold most often. It can express "named but not most-named",
    "least supported in common", "most private support" and their combinations.
    Every agent's view is pooled, so one test covers the family.
    """
    half = ctx.n // 2
    seen: dict[tuple[int, ...], list[int]] = {}
    for task in ctx.tasks[:half]:
        for view in task.views:
            for option, tup in view_rank_features(view, task.answer_space).items():
                cell = seen.setdefault(tup, [0, 0])
                cell[0] += option == task.gold_answer
                cell[1] += 1
    trials: list[tuple[int, bool, int]] = []
    for task in ctx.tasks[half:]:
        for view in task.views:
            by_option = view_rank_features(view, task.answer_space)
            # Laplace-smoothed rate, so an unseen tuple scores as chance.
            score = {o: (seen.get(f, [0, 0])[0] + 1) / (seen.get(f, [0, 0])[1] + 4)
                     for o, f in by_option.items()}
            best = max(score.values())
            leaders = [o for o in task.answer_space if score[o] == best]
            trials.append((len(leaders), task.gold_answer in leaders, len(task.answer_space)))
    return {"trials": trials, "train_tasks": half}


@_check
def check_solo_solvability(ctx: CheckContext) -> CheckResult:
    """No solver on one agent's view may beat chance, at this sample size."""
    probes = {
        "scoring_rule_on_own_view": reference,
        "mention_count_on_own_view": mention_count,
        "named_in_my_private_units": _private_named_option,
        "scoring_rule_on_my_private_units": private_scoring_rule,
        "named_not_most_named_privately": named_not_most_named_privately,
        "least_shared_support": least_shared_support,
    }
    n_agents = max(t.n_agents for t in ctx.tasks)
    # One more member of the family: the learned probe, pooled over agents.
    alpha = family_alpha(ctx.alpha, len(probes) * n_agents + 1)
    rows: list[dict[str, Any]] = []
    for name, solver in probes.items():
        for agent_id in range(n_agents):
            trials = []
            for task in ctx.tasks:
                if agent_id >= task.n_agents:
                    continue
                leaders = leaders_of(solver, task.views[agent_id], task.answer_space)
                trials.append((len(leaders), task.gold_answer in leaders, len(task.answer_space)))
            if trials:
                row = _tie_credited_row(f"{name}[agent {agent_id}]", trials, ctx.chance, alpha)
                row["probe"] = name
                row["agent_id"] = agent_id
                rows.append(row)
    if ctx.n >= 20:
        learned = _learned_single_view(ctx)
        row = _tie_credited_row("learned_from_view_ranks[all agents, held-out half]",
                                learned["trials"], ctx.chance, alpha)
        row["probe"] = "learned_from_view_ranks"
        row["train_tasks"] = learned["train_tasks"]
        rows.append(row)

    mda = minimum_detectable_accuracy(ctx.n, ctx.chance, alpha)
    full_accuracy = (
        sum(uniquely_determined(t.all_units(), t.answer_space) == t.gold_answer for t in ctx.tasks)
        / ctx.n if ctx.n else 0.0
    )
    for row in rows:
        lo, hi = _wilson(row["accuracy"] * row["n"], row["n"])
        row["ci95"] = [lo, hi]
        row["advantage"] = row["accuracy"] - row["chance"]
        gain = full_accuracy - row["chance"]
        row["share_of_pooling_gain"] = row["advantage"] / gain if gain > 0 else None
        # A reliable solo shortcut: the probe commits to one option on enough tasks
        # and is never wrong when it does. This is evidence of high accuracy when
        # committing, not certainty: n right out of n is consistent with a true
        # rate as low as the two-sided 95% Clopper-Pearson bound, 0.025**(1/n)
        # (83.2% at n = 20). See docs/validity-card.md for the assumptions.
        commits = row.get("commits", 0)
        right = row.get("right_when_committed", 0)
        row["never_wrong_when_committed"] = commits >= MIN_TASKS_TO_CLASSIFY and right == commits
        row["accuracy_when_committed"] = right / commits if commits else None
        row["accuracy_when_committed_lower95"] = (
            0.025 ** (1 / commits) if commits and right == commits else None
        )
    learned_rows = [r for r in rows if r["probe"] == "learned_from_view_ranks"]
    primary = learned_rows[0] if learned_rows else None
    beating = [r for r in rows if r["beats_chance"]]
    deterministic = [r for r in rows if r["never_wrong_when_committed"]]
    twins = _twin_analysis(ctx) if ctx.n >= MIN_TASKS_TO_CLASSIFY else None
    detail = {
        "probes": rows,
        "chance": ctx.chance,
        "alpha_per_probe": alpha,
        "full_information_accuracy": full_accuracy,
        "primary_estimate": (
            {k: primary[k] for k in ("name", "accuracy", "ci95", "advantage", "share_of_pooling_gain", "n")}
            if primary else None
        ),
        "primary_estimate_note": (
            "The learned probe, fitted on half the batch and scored on the other half: "
            "the least optimistic single-view estimate here. The best of the explicit "
            "probes is biased upwards by being the best of nineteen."
        ),
        "feature_twin_test": twins,
        "zero_information_diagnostic": {
            "label": "diagnostic only, not a validity requirement",
            "question": "does any probe beat chance at the Bonferroni-corrected alpha?",
            "rejected": bool(beating),
            "alpha_per_probe": alpha,
            "probes_beating_chance": [r["name"] for r in beating],
            "minimum_detectable_accuracy": mda,
            "note": (
                "Under the assumptions in docs/validity-card.md some view of an "
                "argmax-of-summed-evidence task always carries information, so this "
                "diagnostic is expected to reject once n is large enough; whether it "
                "does at this n is a statement about power."
            ),
        },
        "minimum_detectable_accuracy": mda,
        "rule": (
            "fail: some probe commits to a single option on at least "
            f"{MIN_TASKS_TO_CLASSIFY} tasks and is never wrong when it does (a reliable "
            "solo shortcut); inconclusive: fewer than "
            f"{MIN_TASKS_TO_CLASSIFY} tasks; otherwise measured."
        ),
    }
    if ctx.n < MIN_TASKS_TO_CLASSIFY:
        return CheckResult(
            "solo_solvability",
            "Solvability from one agent's view",
            Status.INCONCLUSIVE,
            f"Only {ctx.n} tasks: too few to rule a reliable solo shortcut in or out "
            f"(at least {MIN_TASKS_TO_CLASSIFY} are needed).",
            detail,
            ("G6", "P4"),
        )
    if deterministic:
        worst = deterministic[0]
        agent = str(worst.get("agent_id", ""))
        twin_row = twins["per_agent"].get(agent) if twins and agent else None
        twin_text = (
            f" At the feature level, {twin_row['feature_twin_with_different_answer']} of that "
            f"agent's {twin_row['views']} views have a twin with a different answer."
            if twin_row else ""
        )
        return CheckResult(
            "solo_solvability",
            "Solvability from one agent's view",
            Status.FAIL,
            f"Reliable solo shortcut: from a single view, `{worst['name']}` commits to "
            f"one option on {worst['commits']} of {worst['n']} tasks and is right every "
            f"time, so its accuracy when it commits is at least "
            f"{worst['accuracy_when_committed_lower95']:.1%} (95% interval; with everything "
            f"pooled: {full_accuracy:.0%}). {len(deterministic)} of {len(rows)} probes do this."
            + twin_text,
            detail,
            ("G6", "P4"),
        )
    best = max(rows, key=lambda r: r["accuracy"])
    pe = primary or best
    return CheckResult(
        "solo_solvability",
        "Solvability from one agent's view",
        Status.MEASURED,
        f"No reliable solo shortcut. Measured single-view accuracy (held-out learned "
        f"probe) {pe['accuracy']:.1%} [{pe['ci95'][0]:.1%}, {pe['ci95'][1]:.1%}] against "
        f"{ctx.chance:.1%} chance and {full_accuracy:.0%} with everything pooled; best "
        f"explicit probe {best['accuracy']:.1%} (`{best['name']}`). Zero-information "
        f"diagnostic {'rejected' if beating else 'not rejected'} at this n (power: "
        f"accuracies below {mda:.1%} usually go unseen).",
        detail,
        ("G6", "P4"),
    )


# --- 3. Full-information solvability ----------------------------------------


@_check
def check_full_solvability(ctx: CheckContext) -> CheckResult:
    """With every unit pooled, the scoring rule must reach the gold answer every time."""
    correct = 0
    ties = 0
    failures: list[dict[str, Any]] = []
    for task in ctx.tasks:
        chosen = uniquely_determined(task.all_units(), task.answer_space)
        if chosen == task.gold_answer:
            correct += 1
            continue
        if chosen is None:
            ties += 1
        if len(failures) < 5:
            failures.append(
                {
                    "task_id": task.task_id,
                    "gold": task.gold_answer,
                    "rule_chose": chosen,
                    "reason": "top support is tied" if chosen is None else "rule picks another option",
                    "support_totals": support_total(task.all_units(), task.answer_space),
                }
            )
    n = ctx.n
    detail = {
        "n_correct": correct,
        "n": n,
        "accuracy": correct / n if n else 0.0,
        "n_tied_at_the_top": ties,
        "note": (
            "A tie counts as unsolved: the task does not determine an answer, and a "
            "solver that guessed its way to gold would be measuring the audit's RNG."
        ),
        "failures": failures,
    }
    if correct == n:
        return CheckResult(
            "full_solvability",
            "Solvability with everything pooled",
            Status.PASS,
            f"Applying the stated scoring rule to every unit gives the gold answer in "
            f"{correct}/{n} tasks.",
            detail,
            ("G5",),
        )
    return CheckResult(
        "full_solvability",
        "Solvability with everything pooled",
        Status.FAIL,
        f"The stated scoring rule does not reach the gold answer even with every unit "
        f"pooled: {correct}/{n} ({correct / n:.1%}). Either the rule the environment "
        "states is not the rule it scores by, or the task is not solvable as built. "
        "Agents cannot be expected to find an answer the rule does not imply.",
        detail,
        ("G5",),
    )


# --- 4. Shortcuts ------------------------------------------------------------


@_check
def check_shortcuts(ctx: CheckContext) -> CheckResult:
    """No content-blind shortcut on the full-information view may beat chance."""
    alpha = family_alpha(ctx.alpha, len(SHORTCUT_SOLVERS))
    rows: list[dict[str, Any]] = []
    for name, solver in SHORTCUT_SOLVERS.items():
        trials = []
        for task in ctx.tasks:
            leaders = leaders_of(solver, task.full_view(), task.answer_space)
            trials.append((len(leaders), task.gold_answer in leaders, len(task.answer_space)))
        rows.append(_tie_credited_row(name, trials, ctx.chance, alpha))

    beating = [r for r in rows if r["beats_chance"]]
    detail = {"shortcuts": rows, "chance": ctx.chance, "alpha_per_probe": alpha}
    if beating:
        worst = max(beating, key=lambda r: r["accuracy"])
        return CheckResult(
            "shortcuts",
            "Content-blind shortcuts",
            Status.FAIL,
            f"`{worst['name']}` solves {worst['n_correct']}/{worst['n']} "
            f"({worst['accuracy']:.1%}) against {ctx.chance:.1%} chance "
            f"(p={worst['p_value_vs_chance']:.2g}) without reading what any fact says. "
            f"{len(beating)} of {len(rows)} shortcuts beat chance, so a result here "
            "measures whether a model applies the shortcut, not whether it reasons over "
            "the information.",
            detail,
            ("L3", "I1"),
        )
    best = max(rows, key=lambda r: r["accuracy"])
    return CheckResult(
        "shortcuts",
        "Content-blind shortcuts",
        Status.PASS,
        f"No content-blind shortcut beats {ctx.chance:.1%} chance; the best is "
        f"`{best['name']}` at {best['accuracy']:.1%}.",
        detail,
        ("L3", "I1"),
    )


# --- 5. Name hygiene ---------------------------------------------------------


@_check
def check_name_hygiene(ctx: CheckContext) -> CheckResult:
    """Option names must be distinguishable in text.

    Everything that matches on names depends on this: the mention-count probes
    above, and any surfacing or information-pooling metric that looks for a
    fact's subject in a message. The v0 audit checked the narrow version of it
    (G11, option names that are substrings of each other) and found none. The
    broader version -- a name that also occurs inside an ordinary word -- bit a
    fixture in this very repository, where "listed alphabetically" counted as a
    mention of an option named "Alpha".
    """
    substring_of_each_other: list[dict[str, Any]] = []
    collisions: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    seen_collisions: set[tuple[str, str]] = set()

    for task in ctx.tasks:
        for option in task.answer_space:
            for other in task.answer_space:
                if option != other and option.lower() in other.lower():
                    pair = (option, other)
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        substring_of_each_other.append({"name": option, "inside": other})
        text = task.full_view().render()
        lowered = text.lower()
        for option in task.answer_space:
            whole = count_mentions(text, option)
            raw = lowered.count(option.lower())
            if raw > whole:
                key = (task.task_id, option)
                if key not in seen_collisions and len(collisions) < 10:
                    seen_collisions.add(key)
                    # Show the first word the name is hiding inside.
                    offender = next(
                        (
                            word
                            for word in text.split()
                            if option.lower() in word.lower()
                            and count_mentions(word, option) == 0
                        ),
                        None,
                    )
                    collisions.append(
                        {
                            "task_id": task.task_id,
                            "name": option,
                            "whole_word_mentions": whole,
                            "substring_occurrences": raw,
                            "hidden_inside": offender,
                        }
                    )

    detail = {
        "names_that_are_substrings_of_other_names": substring_of_each_other,
        "names_colliding_with_ordinary_words": collisions,
        "n_tasks_scanned": ctx.n,
    }
    problems = []
    if substring_of_each_other:
        example = substring_of_each_other[0]
        problems.append(
            f"{len(substring_of_each_other)} option name(s) are substrings of another "
            f"option's name, e.g. {example['name']!r} inside {example['inside']!r}"
        )
    if collisions:
        example = collisions[0]
        problems.append(
            f"{len(collisions)} option name(s) also occur inside ordinary words, e.g. "
            f"{example['name']!r} inside {example['hidden_inside']!r}"
        )
    if problems:
        return CheckResult(
            "name_hygiene",
            "Option names are distinguishable in text",
            Status.WARN,
            "Name matching is unreliable here: "
            + "; ".join(problems)
            + ". Any measurement that looks for an option's name in text -- a "
            "mention count, a surfacing rate -- is partly counting word fragments.",
            detail,
            ("G11", "L5"),
        )
    return CheckResult(
        "name_hygiene",
        "Option names are distinguishable in text",
        Status.PASS,
        "No option name is a substring of another, and none occurs inside an ordinary "
        f"word, across {ctx.n} tasks.",
        detail,
        ("G11", "L5"),
    )


# --- 6. Minimality -----------------------------------------------------------


@_check
def check_minimality(ctx: CheckContext) -> CheckResult:
    """Every unit the environment calls required must actually be needed."""
    if not any(task.required_units for task in ctx.tasks):
        return CheckResult(
            "minimality",
            "Minimality of the required units",
            Status.SKIPPED,
            "This environment declares no required units, so there is no claim to check. "
            "Declaring them lets the audit verify that each one is load-bearing, and lets "
            "a surfacing metric mean something.",
            {"tasks_with_required_units": 0},
        )

    redundant: list[dict[str, Any]] = []  # a sample, for the card
    n_redundant = 0
    redundant_tasks: set[str] = set()
    checked = 0
    for task in ctx.tasks:
        units = task.all_units()
        for unit_id in task.required_units:
            checked += 1
            remaining = units_without(units, unit_id)
            # Strictly determined, not argmax-with-random-tie-break: a unit whose
            # removal leaves two options tied IS load-bearing, because the task no
            # longer has a unique answer without it.
            still = uniquely_determined(remaining, task.answer_space)
            if still == task.gold_answer:
                n_redundant += 1
                redundant_tasks.add(task.task_id)
                if len(redundant) < 10:
                    redundant.append(
                        {
                            "task_id": task.task_id,
                            "unit_id": unit_id,
                            "answer_without_it": still,
                        }
                    )
    # The count and the sample are kept apart: the card once reported the size of
    # the 10-entry sample as the total (docs/review-v0.2.md, M3).
    detail = {
        "required_units_checked": checked,
        "redundant_found": n_redundant,
        "tasks_affected": len(redundant_tasks),
        "examples": redundant,
    }
    if n_redundant:
        return CheckResult(
            "minimality",
            "Minimality of the required units",
            Status.WARN,
            f"{n_redundant} of {checked} units the environment calls required are not: "
            f"removing one still leaves the gold answer winning. A surfacing or "
            f"information-pooling metric built on this set overstates what had to be "
            f"shared.",
            detail,
            ("G5",),
        )
    return CheckResult(
        "minimality",
        "Minimality of the required units",
        Status.PASS,
        f"All {checked} required units are load-bearing: removing any one changes the "
        "answer the scoring rule gives.",
        detail,
        ("G5",),
    )


# --- 7. Diversity ------------------------------------------------------------


@_check
def check_diversity(ctx: CheckContext) -> CheckResult:
    """Tasks across seeds must differ in more than labels."""
    unit_texts = [u.text for task in ctx.tasks for u in task.all_units()]
    distinct_texts = len(set(unit_texts))
    per_task_textsets = [frozenset(u.text for u in task.all_units()) for task in ctx.tasks]
    distinct_textsets = len(set(per_task_textsets))

    patterns = []
    for task in ctx.tasks:
        totals = support_total(task.all_units(), task.answer_space)
        patterns.append(tuple(sorted(totals.values(), reverse=True)))
    distinct_patterns = len(set(patterns))

    # Strip option names out of each unit, so "Avery shipped X" and "Blair
    # shipped X" collapse to the same template. Template reuse is what makes a
    # batch one puzzle in N arrangements rather than N problems.
    templates = set()
    for task in ctx.tasks:
        for unit in task.all_units():
            template = unit.text
            for option in task.answer_space:
                template = template.replace(option, "<OPTION>")
            templates.add(template)

    n = ctx.n
    detail = {
        "n_tasks": n,
        "distinct_unit_texts": distinct_texts,
        "distinct_unit_text_sets": distinct_textsets,
        "distinct_unit_templates": len(templates),
        "distinct_support_patterns": distinct_patterns,
        "support_patterns": sorted({str(p) for p in patterns})[:10],
        "mean_units_per_task": statistics.fmean(len(t.all_units()) for t in ctx.tasks),
    }

    problems = []
    if n > 1 and distinct_patterns == 1:
        problems.append(
            f"every one of the {n} tasks has the identical support pattern "
            f"{patterns[0]}"
        )
    if n > 1 and distinct_textsets < max(2, n // 10):
        problems.append(
            f"only {distinct_textsets} distinct sets of unit text across {n} tasks"
        )
    if n > 1 and len(templates) <= statistics.fmean(len(t.all_units()) for t in ctx.tasks) * 1.01:
        problems.append(
            f"only {len(templates)} distinct unit templates, about one per unit in a "
            "single task, so every task reuses the whole pool"
        )
    if problems:
        return CheckResult(
            "diversity",
            "Diversity across seeds",
            Status.WARN,
            "The batch is one puzzle in several arrangements rather than several "
            "problems: " + "; ".join(problems) + ". Intervals computed over these seeds "
            "measure variation over permutations of one task, not over tasks.",
            detail,
            ("L2",),
        )
    return CheckResult(
        "diversity",
        "Diversity across seeds",
        Status.PASS,
        f"{distinct_patterns} distinct support patterns and {len(templates)} distinct unit "
        f"templates across {n} tasks.",
        detail,
        ("L2",),
    )


# --- 8. Balance --------------------------------------------------------------


def _chi2_uniform(counts: Sequence[int]) -> dict[str, Any]:
    """Chi-square goodness-of-fit against a uniform distribution."""
    total = sum(counts)
    k = len(counts)
    if total == 0 or k < 2:
        return {"statistic": 0.0, "df": 0, "critical_05": None, "uniform": True}
    expected = total / k
    stat = sum((c - expected) ** 2 / expected for c in counts)
    df = k - 1
    critical = _CHI2_CRITICAL_05.get(df)
    return {
        "counts": list(counts),
        "statistic": stat,
        "df": df,
        "critical_05": critical,
        "uniform": critical is None or stat <= critical,
    }


@_check
def check_balance(ctx: CheckContext) -> CheckResult:
    """Gold position and per-agent information load must not be skewed."""
    gold_positions = [list(t.answer_space).index(t.gold_answer) for t in ctx.tasks]
    k = max(len(t.answer_space) for t in ctx.tasks)
    position_counts = [gold_positions.count(i) for i in range(k)]
    position = _chi2_uniform(position_counts)

    n_agents = max(t.n_agents for t in ctx.tasks)
    unit_counts: list[list[int]] = [[] for _ in range(n_agents)]
    char_counts: list[list[int]] = [[] for _ in range(n_agents)]
    for task in ctx.tasks:
        for i, view in enumerate(task.views):
            unit_counts[i].append(len(view.private))
            char_counts[i].append(len(view.render()))
    mean_units = [statistics.fmean(c) if c else 0.0 for c in unit_counts]
    mean_chars = [statistics.fmean(c) if c else 0.0 for c in char_counts]
    load_spread = (max(mean_units) - min(mean_units)) if mean_units else 0.0
    char_spread = (max(mean_chars) - min(mean_chars)) if mean_chars else 0.0

    detail = {
        "gold_position": position,
        "mean_private_units_per_agent": mean_units,
        "mean_rendered_chars_per_agent": mean_chars,
        "private_unit_spread": load_spread,
        "rendered_char_spread": char_spread,
    }

    problems = []
    if not position["uniform"]:
        problems.append(
            f"gold position is not uniform (chi2={position['statistic']:.2f} > "
            f"{position['critical_05']} at df={position['df']}), counts {position_counts}"
        )
    if load_spread >= 1.0:
        problems.append(
            f"agents hold unequal numbers of private units (means {[round(m, 2) for m in mean_units]}), "
            f"a spread of {load_spread:.2f}, so one agent is systematically better informed"
        )
    if problems:
        return CheckResult(
            "balance",
            "Positional and per-agent balance",
            Status.WARN,
            "The task is not symmetric: " + "; ".join(problems) + ".",
            detail,
            ("G3", "L8", "L9"),
        )
    return CheckResult(
        "balance",
        "Positional and per-agent balance",
        Status.PASS,
        f"Gold position is uniform (chi2={position['statistic']:.2f} against a "
        f"{position['critical_05']} critical value) and agents hold equal numbers of "
        f"private units.",
        detail,
        ("G3", "L8", "L9"),
    )


# --- 9. Objective stated ------------------------------------------------------


@_check
def check_objective(ctx: CheckContext) -> CheckResult:
    """Every condition's prompts must contain the question and the scoring rule."""
    probe = ctx.tasks[0]
    conditions = ctx.env.conditions(probe)
    if not conditions:
        return CheckResult(
            "objective",
            "Objective stated in the prompts",
            Status.SKIPPED,
            "This environment does not describe its conditions, so the audit cannot see "
            "the prompts it sends and cannot check whether they state the objective. "
            "Implement Environment.conditions() to enable this check -- the v0 result in "
            "studies/underspecification/ was wrong for exactly this reason.",
            {"conditions": []},
        )

    rows: list[dict[str, Any]] = []
    for name, condition in sorted(conditions.items()):
        missing_question = [
            i for i, p in enumerate(condition.prompts) if probe.objective.question not in p
        ]
        missing_rule = [
            i for i, p in enumerate(condition.prompts) if probe.objective.scoring_rule not in p
        ]
        rows.append(
            {
                "condition": name,
                "description": condition.description,
                "n_prompts": len(condition.prompts),
                "prompts_missing_question": len(missing_question),
                "prompts_missing_scoring_rule": len(missing_rule),
                "states_objective": not missing_question and not missing_rule,
            }
        )

    bad = [r for r in rows if not r["states_objective"]]
    detail = {"probe_task": probe.task_id, "conditions": rows}
    if bad:
        names = ", ".join(f"`{r['condition']}`" for r in bad)
        return CheckResult(
            "objective",
            "Objective stated in the prompts",
            Status.FAIL,
            f"{len(bad)} of {len(rows)} conditions never state the objective: {names}. "
            "Agents in those arms are not told what question they are answering or how "
            "the answer is scored, so a wrong answer there is not evidence of a "
            "coordination failure -- it may only be evidence that nobody said what to do.",
            detail,
            ("I1", "L1"),
        )
    return CheckResult(
        "objective",
        "Objective stated in the prompts",
        Status.PASS,
        f"All {len(rows)} conditions state both the question and the scoring rule in "
        "every prompt.",
        detail,
        ("I1", "L1"),
    )


# --- 10. Condition diff --------------------------------------------------------


#: Prompt lines can be long; a card only needs enough of one to recognise it.
_DIFF_LINE_CHARS = 110

#: Which agent is speaking is not a difference between arms, so the agent index
#: is normalised before framing is compared. Nothing else is normalised.
_AGENT_INDEX = re.compile(r"\bAgent \d+\b")


def _diff_lines(a: Sequence[str], b: Sequence[str]) -> list[str]:
    """Unified-diff lines between two line sequences, markers stripped."""
    return [
        line
        for line in difflib.unified_diff(list(a), list(b), lineterm="", n=0)
        if line[:1] in "+-" and not line.startswith(("---", "+++"))
    ]


def _elide(lines: list[str], limit: int = 4) -> list[str]:
    """A few diff lines, each truncated, for the card's detail."""
    out = []
    for line in lines[:limit]:
        out.append(
            line if len(line) <= _DIFF_LINE_CHARS else line[:_DIFF_LINE_CHARS] + " […]"
        )
    if len(lines) > limit:
        out.append(f"[… {len(lines) - limit} more differing line(s)]")
    return out


def _strip_all(line: str, substrings: Sequence[str]) -> str:
    """``line`` with every declared substring removed.

    Framing is compared line by line, while a declared difference is often a
    block of several lines -- a task statement, say. So each declaration is
    split on newlines and its fragments removed individually; otherwise a
    multi-line declaration would never match anything and would look like an
    undeclared difference.
    """
    for text in substrings:
        for fragment in text.splitlines():
            fragment = fragment.strip()
            if fragment:
                line = line.replace(fragment, "")
    return line.strip()


def _stripped_framing(framing: Sequence[str], declared: Sequence[str]) -> list[str]:
    """``framing`` with declared differences removed and blank lines dropped."""
    return [text for text in (_strip_all(line, declared) for line in framing) if text]


def _framing(condition: Condition, task: DistributedTask) -> list[str]:
    """A condition's prompts with the task's information removed.

    What is left is the *scaffolding*: system prompts, section headers, framing
    sentences, answer instructions. That is the right thing to compare between
    arms, because two arms are usually meant to differ in what information they
    give -- that is the manipulation -- while differing in nothing else.

    The v0 audit's L4 was exactly a scaffolding difference: the
    full-information arm also had its own system prompt, its own section layout
    and a "no discussion needed" line, so the gap it was compared against mixed
    information access with framing.

    Lines are returned as a sorted set, because arms make different numbers of
    model calls and "this line appears three times rather than once" is not a
    difference worth reporting.
    """
    lines: set[str] = set()
    for prompt in condition.prompts:
        stripped = prompt
        for unit in task.all_units():
            stripped = stripped.replace(unit.text, "<UNIT>")
        for line in stripped.splitlines():
            text = _AGENT_INDEX.sub("Agent <i>", line.strip())
            if text and text != "- <UNIT>":
                lines.add(text)
    return sorted(lines)


@_check
def check_condition_diff(ctx: CheckContext) -> CheckResult:
    """Between any two arms, only the manipulation under test should differ."""
    probe = ctx.tasks[0]
    conditions = ctx.env.conditions(probe)
    if len(conditions) < 2:
        return CheckResult(
            "condition_diff",
            "Differences between conditions",
            Status.SKIPPED,
            "Fewer than two conditions are described, so there is no pair to compare. "
            "With conditions declared, this check reports every framing difference "
            "between each pair, which is how the v0 audit found that the "
            "full-information arm also differed in layout (L4).",
            {"conditions": sorted(conditions)},
        )

    names = sorted(conditions)
    framings = {name: _framing(conditions[name], probe) for name in names}
    pairs: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    for i, a_name in enumerate(names):
        for b_name in names[i + 1 :]:
            a, b = conditions[a_name], conditions[b_name]
            lines = _diff_lines(framings[a_name], framings[b_name])
            # Both sides are collected: when an arm swaps one line for another,
            # each arm declares the line it carries, and both have to come out
            # before the residual means anything.
            declared = tuple(
                text
                for text in (a.expected_diff.get(b_name), b.expected_diff.get(a_name))
                if text
            )
            entry: dict[str, Any] = {
                "pair": [a_name, b_name],
                "n_prompts": [len(a.prompts), len(b.prompts)],
                "differing_framing_lines": len(lines),
                "declared_expected_diff": list(declared),
                "sample": _elide(lines),
            }
            if not lines:
                entry["verdict"] = "framing identical"
            elif not declared:
                entry["verdict"] = "undeclared difference"
            else:
                residual = _diff_lines(
                    _stripped_framing(framings[a_name], declared),
                    _stripped_framing(framings[b_name], declared),
                )
                entry["residual_lines_after_removing_declared_diff"] = len(residual)
                entry["residual_sample"] = _elide(residual)
                if residual:
                    entry["verdict"] = "differs beyond its declared difference"
                    violations.append(entry)
                else:
                    entry["verdict"] = "differs only by its declared difference"
            pairs.append(entry)

    undeclared = [p for p in pairs if p["verdict"] == "undeclared difference"]
    # Pairs grow quadratically in the number of conditions, so the card keeps the
    # ones a reader needs to act on and counts the rest rather than printing all
    # of them.
    severity = {
        "differs beyond its declared difference": 0,
        "undeclared difference": 1,
        "differs only by its declared difference": 2,
        "framing identical": 3,
    }
    shown_pairs = sorted(
        pairs, key=lambda e: (severity[e["verdict"]], -e["differing_framing_lines"])
    )
    detail = {
        "compared": (
            "prompt framing with the task's information removed: an arm is meant to "
            "differ in what it tells agents, so only the scaffolding is compared"
        ),
        "probe_task": probe.task_id,
        "n_conditions": len(names),
        "n_pairs": len(pairs),
        "verdict_counts": {v: sum(1 for e in pairs if e["verdict"] == v) for v in severity},
        "pairs": shown_pairs[:12],
        "pairs_omitted": max(0, len(pairs) - 12),
    }

    if violations:
        worst = max(violations, key=lambda e: e["residual_lines_after_removing_declared_diff"])
        return CheckResult(
            "condition_diff",
            "Differences between conditions",
            Status.FAIL,
            f"{len(violations)} condition pair(s) differ in framing beyond the one "
            f"difference the environment declares -- worst `{worst['pair'][0]}` against "
            f"`{worst['pair'][1]}`, with "
            f"{worst['residual_lines_after_removing_declared_diff']} further differing "
            "line(s). A contrast between them does not isolate the manipulation it names.",
            detail,
            ("L4", "P6"),
        )
    if undeclared:
        shown = ", ".join(f"`{p['pair'][0]}`/`{p['pair'][1]}`" for p in undeclared[:4])
        return CheckResult(
            "condition_diff",
            "Differences between conditions",
            Status.WARN,
            f"{len(undeclared)} of {len(pairs)} condition pairs differ in framing in ways "
            f"the environment does not declare ({shown}). Any difference measured between "
            "such a pair mixes the intended manipulation with these. Declare the intended "
            "difference via Condition.expected_diff to turn this into a check rather than "
            "a report.",
            detail,
            ("L4", "P6"),
        )
    return CheckResult(
        "condition_diff",
        "Differences between conditions",
        Status.PASS,
        f"All {len(pairs)} condition pairs have identical framing or differ only by the "
        "difference the environment declares.",
        detail,
        ("L4", "P6"),
    )


# --- 11. Scorer fuzzing -------------------------------------------------------


@dataclass(frozen=True)
class _FuzzCase:
    """One adversarial answer string and whether it should be accepted."""

    label: str
    build: Callable[[DistributedTask], str | None]
    should_accept: bool
    rationale: str = ""


def _wrong_option(task: DistributedTask) -> str:
    return next(o for o in task.answer_space if o != task.gold_answer)


#: The contract under test: an answer is accepted iff, after stripping
#: surrounding whitespace, it is exactly the gold option. Anything looser is a
#: scorer that guesses, and a scorer that guesses can be farmed.
_FUZZ_CASES: tuple[_FuzzCase, ...] = (
    _FuzzCase("gold", lambda t: t.gold_answer, True),
    _FuzzCase("gold with surrounding spaces", lambda t: f"  {t.gold_answer}  ", True),
    _FuzzCase("gold with a trailing newline", lambda t: f"{t.gold_answer}\n", True),
    _FuzzCase("empty string", lambda t: "", False, "resolved to option 0 in v0 (D1)"),
    _FuzzCase("whitespace only", lambda t: "   ", False),
    _FuzzCase("None", lambda t: None, False),
    _FuzzCase("a wrong option", _wrong_option, False),
    _FuzzCase("one letter", lambda t: t.gold_answer[0], False, "resolved to option 0 in v0"),
    _FuzzCase("gold lowercased", lambda t: t.gold_answer.lower(), False),
    _FuzzCase("gold uppercased", lambda t: t.gold_answer.upper(), False),
    _FuzzCase("gold with punctuation", lambda t: f"{t.gold_answer}.", False),
    _FuzzCase(
        "gold inside prose",
        lambda t: f"I pick {t.gold_answer} over {_wrong_option(t)}",
        False,
        "the v0 parser returned the last option named",
    ),
    _FuzzCase(
        "wrong option named last",
        lambda t: f"{t.gold_answer} is best; {_wrong_option(t)} was close",
        False,
    ),
    _FuzzCase("two options", lambda t: f"{t.gold_answer} and {_wrong_option(t)}", False),
    _FuzzCase("a prefix of gold", lambda t: t.gold_answer[: max(1, len(t.gold_answer) - 1)], False),
    _FuzzCase("JSON wrapping gold", lambda t: f'{{"answer": "{t.gold_answer}"}}', False),
    _FuzzCase("not an option at all", lambda t: "none of the above", False),
    _FuzzCase("every option listed", lambda t: ", ".join(t.answer_space), False),
)


@_check
def check_scorer_fuzz(ctx: CheckContext) -> CheckResult:
    """The scorer must accept exactly the gold option and nothing else."""
    false_accepts: list[dict[str, Any]] = []
    false_rejects: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []

    for case in _FUZZ_CASES:
        accepted = 0
        n = 0
        example: dict[str, Any] | None = None
        for task in ctx.tasks:
            answer = case.build(task)
            n += 1
            result = task.score(answer)
            if result.correct:
                accepted += 1
                if example is None:
                    example = {"task_id": task.task_id, "answer": answer}
        row = {
            "case": case.label,
            "should_accept": case.should_accept,
            "accepted": accepted,
            "n": n,
            "example": example,
        }
        if case.rationale:
            row["rationale"] = case.rationale
        rows.append(row)
        if case.should_accept and accepted < n:
            false_rejects.append(row)
        if not case.should_accept and accepted > 0:
            false_accepts.append(row)

    detail = {
        "contract": (
            "accept iff the answer, stripped of surrounding whitespace, is exactly the "
            "gold option"
        ),
        "cases": rows,
        "n_false_accepts": len(false_accepts),
        "n_false_rejects": len(false_rejects),
    }
    if false_accepts:
        worst = max(false_accepts, key=lambda r: r["accepted"])
        return CheckResult(
            "scorer_fuzz",
            "Scorer under adversarial answers",
            Status.FAIL,
            f"The scorer accepts {len(false_accepts)} kind(s) of answer it should reject, "
            f"worst being \"{worst['case']}\" accepted in {worst['accepted']}/{worst['n']} "
            "tasks. A scorer that guesses is a reward that can be farmed without solving "
            "anything.",
            detail,
            ("D1", "M1"),
        )
    if false_rejects:
        worst = max(false_rejects, key=lambda r: r["n"] - r["accepted"])
        return CheckResult(
            "scorer_fuzz",
            "Scorer under adversarial answers",
            Status.FAIL,
            f"The scorer rejects answers it should accept: \"{worst['case']}\" was accepted "
            f"in only {worst['accepted']}/{worst['n']} tasks. Correct answers scored wrong "
            "depress every arm and look like a capability limit.",
            detail,
            ("D1", "M1"),
        )
    return CheckResult(
        "scorer_fuzz",
        "Scorer under adversarial answers",
        Status.PASS,
        f"All {len(_FUZZ_CASES)} adversarial cases scored as the contract requires over "
        f"{ctx.n} tasks: no false accepts, no false rejects.",
        detail,
        ("D1", "M1"),
    )


# --- 12. Reward hackability ---------------------------------------------------


def _two_proportion_p(k1: int, n1: int, k2: int, n2: int) -> float:
    """Two-sided two-proportion z-test p-value, pooled.

    Returns 1.0 when both proportions are identical, including both 0 or both 1,
    where the difference is exactly zero and there is no evidence of one.
    """
    import math

    if n1 == 0 or n2 == 0:
        return 1.0
    p1, p2 = k1 / n1, k2 / n2
    pooled = (k1 + k2) / (n1 + n2)
    denom = pooled * (1 - pooled) * (1 / n1 + 1 / n2)
    if denom <= 0.0:
        return 1.0 if p1 == p2 else 0.0
    z = (p1 - p2) / math.sqrt(denom)
    return float(math.erfc(abs(z) / math.sqrt(2.0)))


@_check
def check_reward_hacking(ctx: CheckContext) -> CheckResult:
    """Degenerate teams, scored by the task's own reward, must lose to real pooling."""
    rng = ctx.rng()
    pooled_reward = 0.0
    pooled_correct = 0
    for task in ctx.tasks:
        result = task.score(genuine_pooling(task, rng))
        pooled_reward += result.reward
        pooled_correct += int(result.correct)

    # The beats-chance family is corrected; the indistinguishable-from-pooling
    # test is not, because there the risk runs the other way -- a smaller alpha
    # would make a policy *more* likely to be called a match for pooling, which
    # is the conclusion we must not reach lightly.
    alpha = family_alpha(ctx.alpha, len(DEGENERATE_POLICIES))
    rows: list[dict[str, Any]] = []
    for name, policy in DEGENERATE_POLICIES.items():
        total = 0.0
        correct = 0
        for task in ctx.tasks:
            result = task.score(policy(task, rng))
            total += result.reward
            correct += int(result.correct)
        row = _accuracy_row(name, correct, ctx.n, ctx.chance, alpha)
        row["mean_reward"] = total / ctx.n if ctx.n else 0.0
        p_vs_pooling = _two_proportion_p(correct, ctx.n, pooled_correct, ctx.n)
        row["p_value_vs_pooling"] = p_vs_pooling
        row["indistinguishable_from_pooling"] = p_vs_pooling > ctx.alpha
        # A reward above what being right alone would pay means the reward has a
        # term that is collectable without answering correctly.
        row["pays_beyond_correctness"] = row["mean_reward"] > row["accuracy"] + 1e-9
        rows.append(row)

    detail = {
        "reward": "the environment's own score(), as a training reward would use it",
        "genuine_pooling": {
            "n_correct": pooled_correct,
            "n": ctx.n,
            "accuracy": pooled_correct / ctx.n if ctx.n else 0.0,
            "mean_reward": pooled_reward / ctx.n if ctx.n else 0.0,
        },
        "policies": rows,
        "alpha_per_probe_vs_chance": alpha,
        "alpha_vs_pooling": ctx.alpha,
        "note": (
            "Shaping terms are not included here: this environment's reward is its "
            "scorer alone. A run that adds a shaping term must re-audit with it, or the "
            "check has not seen the reward being optimised."
        ),
    }

    matching = [r for r in rows if r["indistinguishable_from_pooling"]]
    beating = [r for r in rows if r["beats_chance"]]
    paid = [r for r in rows if r["pays_beyond_correctness"]]
    pooled_acc = pooled_correct / ctx.n if ctx.n else 0.0
    for row in rows:
        lo, hi = _wilson(row["n_correct"], row["n"])
        row["ci95"] = [lo, hi]
        row["advantage"] = row["accuracy"] - row["chance"]
        gain = pooled_acc - row["chance"]
        row["share_of_pooling_gain"] = row["advantage"] / gain if gain > 0 else None
    detail["zero_information_diagnostic"] = {
        "label": "diagnostic only, not a validity requirement",
        "question": "does any non-pooling team beat chance at the Bonferroni-corrected alpha?",
        "rejected": bool(beating),
        "policies_beating_chance": [r["name"] for r in beating],
        "minimum_detectable_accuracy": minimum_detectable_accuracy(ctx.n, ctx.chance, alpha),
    }
    detail["rule"] = (
        "fail: a non-pooling team cannot be distinguished from pooling, or the reward "
        f"pays beyond correctness; inconclusive: fewer than {MIN_TASKS_TO_CLASSIFY} tasks; "
        "otherwise measured."
    )
    if matching or paid:
        parts = []
        if matching:
            worst = max(matching, key=lambda r: r["accuracy"])
            parts.append(
                f"`{worst['name']}` earns {worst['accuracy']:.1%} against pooling's "
                f"{pooled_acc:.1%} and cannot be distinguished from it "
                f"(p={worst['p_value_vs_pooling']:.2g})"
            )
        if paid:
            worst = max(paid, key=lambda r: r["mean_reward"] - r["accuracy"])
            parts.append(
                f"`{worst['name']}` earns mean reward {worst['mean_reward']:.3f} while "
                f"answering correctly only {worst['accuracy']:.1%} of the time, so the "
                "reward pays for something other than being right"
            )
        return CheckResult(
            "reward_hacking",
            "Reward earnable without pooling",
            Status.FAIL,
            "This reward can be earned without pooling private information: "
            + "; and ".join(parts)
            + ". Training against it would reward the shortcut.",
            detail,
            ("M6",),
        )
    if ctx.n < MIN_TASKS_TO_CLASSIFY:
        return CheckResult(
            "reward_hacking", "Reward earnable without pooling", Status.INCONCLUSIVE,
            f"Only {ctx.n} tasks: too few to classify (at least {MIN_TASKS_TO_CLASSIFY}).",
            detail, ("M6",),
        )
    best = max(rows, key=lambda r: r["accuracy"])
    return CheckResult(
        "reward_hacking",
        "Reward earnable without pooling",
        Status.MEASURED,
        f"No non-pooling team matches pooling ({pooled_correct}/{ctx.n}) and the reward "
        f"pays only for correctness. The best non-pooling team, `{best['name']}`, scores "
        f"{best['accuracy']:.1%} [{best['ci95'][0]:.1%}, {best['ci95'][1]:.1%}] against "
        f"{ctx.chance:.1%} chance; zero-information diagnostic "
        f"{'rejected' if beating else 'not rejected'} at this n.",
        detail,
        ("M6",),
    )


# --- Seed split (not one of the eleven, but cheap and load-bearing for RL) ----


@_check
def check_seed_split(ctx: CheckContext) -> CheckResult:
    """An environment used for RL should declare disjoint train and eval seeds."""
    split = ctx.env.seed_split()
    if split is None:
        return CheckResult(
            "seed_split",
            "Declared train / eval seed split",
            Status.WARN,
            "This environment declares no train/eval seed split, so nothing stops an RL "
            "run from training on the seeds it later reports. Implement "
            "Environment.seed_split() to make that impossible by construction rather "
            "than by discipline.",
            {"seed_split": None},
        )
    audited = set(range(ctx.seed, ctx.seed + ctx.n))
    detail = {
        "train": [split.train.start, split.train.stop],
        "eval": [split.eval.start, split.eval.stop],
        "pilot": [split.pilot.start, split.pilot.stop],
        "n_train": len(split.train),
        "n_eval": len(split.eval),
        "audited_seeds_in_eval": len(audited & set(split.eval)),
        "audited_seeds_in_train": len(audited & set(split.train)),
    }
    return CheckResult(
        "seed_split",
        "Declared train / eval seed split",
        Status.PASS,
        f"Disjoint split declared: {len(split.train)} train seeds, {len(split.eval)} eval "
        f"seeds, {len(split.pilot)} pilot. Overlap is refused at construction.",
        detail,
    )


def run_checks(ctx: CheckContext, only: Sequence[str] | None = None) -> list[CheckResult]:
    """Run every registered check against ``ctx``.

    Args:
        ctx: The context to run against.
        only: Optional check ids to restrict to, for a faster targeted run.

    Returns:
        One result per check, in registration order.
    """
    results = [check(ctx) for check in CHECKS]
    if only is not None:
        wanted = set(only)
        results = [r for r in results if r.check_id in wanted]
    return results
