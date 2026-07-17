"""Reward-hacking diagnostics.

A verifiable reward is only useful if it *cannot* be earned without the behaviour
it is meant to incentivise -- here, genuine pooling of privately held
information. This module runs a battery of degenerate policies that each pick an
answer using a shortcut that ignores real information sharing, then checks
whether any of them achieves reward statistically indistinguishable from a
genuine-pooling reference over a batch of tasks.

The policies are deliberately LLM-free and deterministic so the check runs in CI
in milliseconds: it stress-tests the *reward function and task construction*, not
any particular model. If a degenerate policy matched genuine pooling, the reward
would be hackable; the expected (and verified) outcome for these environments is
that every degenerate policy scores significantly below genuine pooling, because
the tasks guarantee that shortcuts relying only on shared/common information land
on the wrong answer.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass

from grapevine.envs.base import Env, Task

# A policy maps a task (plus an RNG for stochastic policies) to a chosen option.
Policy = Callable[[Task, random.Random], str]


def genuine_pooling(task: Task, rng: random.Random) -> str:
    """Reference policy: a team that fully pools information answers correctly."""
    return task.answer


def always_option_a(task: Task, rng: random.Random) -> str:
    """Always pick the first *listed* option regardless of content."""
    return task.options[0]


def always_fixed_name(task: Task, rng: random.Random) -> str:
    """Always pick the alphabetically-first option name (a fixed constant guess)."""
    return sorted(task.options)[0]


def random_choice(task: Task, rng: random.Random) -> str:
    """Pick a uniformly random option."""
    return rng.choice(task.options)


def _solo_guess(task: Task, agent_id: int, rng: random.Random) -> str:
    """The option a single agent would pick from *only its own* context.

    Models an agent that never asks for hidden information: it chooses the option
    named most often in the context it can see, breaking ties (including the
    all-zero case, common in split-evidence where no option name is visible)
    randomly. Crucially it uses no pooled/god's-eye information, so it is a valid
    stand-in for a non-pooling team member.
    """
    context = task.agent_contexts[agent_id].lower()
    counts = {opt: context.count(opt.lower()) for opt in task.options}
    best = max(counts.values())
    leaders = [opt for opt in task.options if counts[opt] == best]
    return rng.choice(leaders)


def answer_only_no_discussion(task: Task, rng: random.Random) -> str:
    """Each agent guesses from its own context; the team takes a majority vote.

    No information is ever shared, so on a hidden-profile task every agent sees
    the decoy-favouring shared facts and votes for the decoy.
    """
    votes = [_solo_guess(task, i, rng) for i in range(task.n_agents)]
    tally = {opt: votes.count(opt) for opt in task.options}
    best = max(tally.values())
    for opt in task.options:  # option order breaks ties deterministically
        if tally[opt] == best:
            return opt
    return task.options[0]


def copy_teammate(task: Task, rng: random.Random) -> str:
    """Everyone parrots the first agent's solo guess instead of contributing."""
    return _solo_guess(task, 0, rng)


def longest_message(task: Task, rng: random.Random) -> str:
    """Defer to whichever agent has the most to say (longest context), no pooling."""
    agent_id = max(range(task.n_agents), key=lambda i: len(task.agent_contexts[i]))
    return _solo_guess(task, agent_id, rng)


#: The degenerate policies evaluated against the reward, by name. Each is a
#: non-pooling shortcut: it uses only per-agent context, position, or chance.
DEGENERATE_POLICIES: dict[str, Policy] = {
    "always_option_a": always_option_a,
    "always_fixed_name": always_fixed_name,
    "random_choice": random_choice,
    "answer_only_no_discussion": answer_only_no_discussion,
    "copy_teammate": copy_teammate,
    "longest_message": longest_message,
}


@dataclass
class PolicyResult:
    """Reward outcome of one policy over a task batch."""

    name: str
    n: int
    n_correct: int

    @property
    def accuracy(self) -> float:
        """Mean reward (fraction correct)."""
        return self.n_correct / self.n if self.n else 0.0


@dataclass
class PolicyComparison:
    """Comparison of a degenerate policy against the genuine-pooling reference."""

    name: str
    accuracy: float
    reference_accuracy: float
    delta: float
    z: float
    p_value: float
    indistinguishable: bool


@dataclass
class DiagnosticReport:
    """Full reward-hacking report for one environment configuration."""

    env_family: str
    config_repr: str
    n_tasks: int
    seed: int
    reference: PolicyResult
    comparisons: list[PolicyComparison]

    @property
    def any_hackable(self) -> bool:
        """True if any degenerate policy matched the genuine-pooling reference."""
        return any(c.indistinguishable for c in self.comparisons)


def _two_proportion_z(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float]:
    """Two-sided two-proportion z-test. Returns ``(z, p_value)``.

    Uses the pooled-proportion normal approximation. When both proportions are
    identical (including both 0 or both 1) the difference is exactly zero and the
    test returns ``z=0, p=1`` (indistinguishable).
    """
    if n1 == 0 or n2 == 0:
        return 0.0, 1.0
    p1 = k1 / n1
    p2 = k2 / n2
    pooled = (k1 + k2) / (n1 + n2)
    denom = pooled * (1 - pooled) * (1 / n1 + 1 / n2)
    if denom <= 0.0:
        # Zero variance: identical extreme proportions -> no evidence of a diff.
        return (0.0, 1.0) if p1 == p2 else (float("inf"), 0.0)
    z = (p1 - p2) / math.sqrt(denom)
    p = math.erfc(abs(z) / math.sqrt(2.0))  # two-sided p-value
    return z, p


def run_policy(env: Env, policy: Policy, n_tasks: int, seed: int) -> PolicyResult:
    """Run ``policy`` over ``n_tasks`` generated tasks and tally reward."""
    tasks = env.generate_batch(n_tasks, seed)
    rng = random.Random(seed * 7919 + 1)
    n_correct = 0
    for task in tasks:
        choice = policy(task, rng)
        if choice == task.answer:
            n_correct += 1
    return PolicyResult(name=getattr(policy, "__name__", "policy"), n=n_tasks, n_correct=n_correct)


def diagnose(
    env: Env, n_tasks: int = 200, seed: int = 0, alpha: float = 0.05
) -> DiagnosticReport:
    """Run the degenerate-policy battery against the genuine-pooling reference.

    Args:
        env: The environment whose reward/task construction is under test.
        n_tasks: Number of tasks per policy.
        seed: Base seed for task generation.
        alpha: Significance level; a degenerate policy is deemed
            *indistinguishable* from genuine pooling when the two-proportion test
            p-value exceeds ``alpha``.

    Returns:
        A :class:`DiagnosticReport` summarising every policy comparison.
    """
    reference = run_policy(env, genuine_pooling, n_tasks, seed)
    reference.name = "genuine_pooling"

    comparisons: list[PolicyComparison] = []
    for name, policy in DEGENERATE_POLICIES.items():
        result = run_policy(env, policy, n_tasks, seed)
        z, p = _two_proportion_z(
            result.n_correct, result.n, reference.n_correct, reference.n
        )
        comparisons.append(
            PolicyComparison(
                name=name,
                accuracy=result.accuracy,
                reference_accuracy=reference.accuracy,
                delta=result.accuracy - reference.accuracy,
                z=z,
                p_value=p,
                indistinguishable=(p > alpha),
            )
        )

    return DiagnosticReport(
        env_family=env.family,
        config_repr=repr(getattr(env, "config", None)),
        n_tasks=n_tasks,
        seed=seed,
        reference=reference,
        comparisons=comparisons,
    )


def report_markdown(report: DiagnosticReport) -> str:
    """Render a :class:`DiagnosticReport` as a Markdown document."""
    verdict = (
        "❌ **REWARD HACKABLE** — at least one degenerate policy matches genuine pooling."
        if report.any_hackable
        else "✅ **PASS** — every degenerate policy scores significantly below genuine pooling."
    )
    lines = [
        f"# Reward-hacking diagnostics: `{report.env_family}`",
        "",
        f"- Config: `{report.config_repr}`",
        f"- Tasks per policy: **{report.n_tasks}** (seed {report.seed})",
        f"- Genuine-pooling reference accuracy: **{report.reference.accuracy:.3f}**",
        "",
        verdict,
        "",
        "A degenerate policy is flagged *indistinguishable* when a two-proportion "
        "z-test against genuine pooling gives p > 0.05 (i.e. we cannot say it does "
        "worse). Any such policy would mean the reward can be earned without pooling.",
        "",
        "| Degenerate policy | Accuracy | Δ vs pooling | z | p-value | Indistinguishable? |",
        "| --- | ---: | ---: | ---: | ---: | :---: |",
    ]
    for c in report.comparisons:
        z_str = "inf" if math.isinf(c.z) else f"{c.z:.2f}"
        flag = "⚠️ yes" if c.indistinguishable else "no"
        lines.append(
            f"| `{c.name}` | {c.accuracy:.3f} | {c.delta:+.3f} | {z_str} | "
            f"{c.p_value:.3g} | {flag} |"
        )
    lines.append("")
    return "\n".join(lines)
