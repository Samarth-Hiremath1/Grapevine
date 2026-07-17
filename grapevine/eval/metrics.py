"""Evaluation metrics for distributed-team vs single-agent conditions.

The headline comparison is between two conditions run on the same tasks:

* the **distributed team** (information split across agents), and
* a **single agent with the full context** (the accuracy ceiling).

From these we report team accuracy, single-agent accuracy, the gap-closure
percentage (how far the team climbs from chance toward the ceiling), and the
mean private-fact surfacing rate that explains *why* the team lands where it
does.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean

from grapevine.rewards.reward import compute_surfacing
from grapevine.rollout.engine import Episode


@dataclass
class EvalMetrics:
    """Aggregate metrics over a set of episodes.

    Attributes:
        n_tasks: Number of team episodes aggregated.
        team_accuracy: Fraction of team episodes with the correct answer.
        single_agent_accuracy: Fraction of single-agent full-context episodes
            correct (the upper bound); ``None`` if not provided.
        chance_accuracy: Mean ``1 / n_options`` over the team episodes.
        gap_closure: Fraction of the chance-to-ceiling gap the team closes,
            ``(team - chance) / (single - chance)``; ``None`` when it cannot be
            computed (no single-agent condition, or a degenerate denominator).
        surfacing_rate: Mean private-fact surfacing rate over team episodes.
        team_cost_usd: Total USD cost of the team episodes.
        single_cost_usd: Total USD cost of the single-agent episodes.
    """

    n_tasks: int
    team_accuracy: float
    single_agent_accuracy: float | None
    chance_accuracy: float
    gap_closure: float | None
    surfacing_rate: float
    team_cost_usd: float
    single_cost_usd: float


def _accuracy(episodes: list[Episode]) -> float:
    if not episodes:
        return 0.0
    return fmean(1.0 if e.correct else 0.0 for e in episodes)


def _cost(episodes: list[Episode]) -> float:
    return sum(float(e.usage.get("cost_usd", 0.0)) for e in episodes)


def compute_metrics(
    team_episodes: list[Episode],
    single_episodes: list[Episode] | None = None,
    surfacing_threshold: float = 0.7,
) -> EvalMetrics:
    """Aggregate metrics from team (and optionally single-agent) episodes.

    Args:
        team_episodes: Distributed-team episodes.
        single_episodes: Single-agent full-context episodes on the same tasks.
        surfacing_threshold: Fuzzy-match threshold for the surfacing metric.

    Returns:
        The aggregated :class:`EvalMetrics`.
    """
    if not team_episodes:
        raise ValueError("team_episodes must be non-empty")

    team_acc = _accuracy(team_episodes)
    chance = fmean(1.0 / len(e.options) for e in team_episodes if e.options)
    surfacing = fmean(
        compute_surfacing(e, surfacing_threshold).surfacing_rate for e in team_episodes
    )

    single_acc: float | None = None
    gap_closure: float | None = None
    single_cost = 0.0
    if single_episodes:
        single_acc = _accuracy(single_episodes)
        single_cost = _cost(single_episodes)
        denom = single_acc - chance
        if denom > 1e-9:
            gap_closure = (team_acc - chance) / denom

    return EvalMetrics(
        n_tasks=len(team_episodes),
        team_accuracy=team_acc,
        single_agent_accuracy=single_acc,
        chance_accuracy=chance,
        gap_closure=gap_closure,
        surfacing_rate=surfacing,
        team_cost_usd=_cost(team_episodes),
        single_cost_usd=single_cost,
    )


def metrics_markdown(metrics: EvalMetrics, title: str = "Evaluation") -> str:
    """Render :class:`EvalMetrics` as a small Markdown table."""
    def pct(x: float | None) -> str:
        return "n/a" if x is None else f"{x * 100:.1f}%"

    lines = [
        f"## {title}",
        "",
        f"- Tasks: **{metrics.n_tasks}**",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Distributed-team accuracy | {pct(metrics.team_accuracy)} |",
        f"| Single-agent full-context accuracy (ceiling) | {pct(metrics.single_agent_accuracy)} |",
        f"| Chance accuracy | {pct(metrics.chance_accuracy)} |",
        f"| Gap-closure | {pct(metrics.gap_closure)} |",
        f"| Private-fact surfacing rate | {pct(metrics.surfacing_rate)} |",
        f"| Team cost (USD) | ${metrics.team_cost_usd:.4f} |",
        f"| Single-agent cost (USD) | ${metrics.single_cost_usd:.4f} |",
    ]
    return "\n".join(lines)
