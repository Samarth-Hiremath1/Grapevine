"""Training rewards for distributed-information environments.

The default reward is the team's outcome: the environment's own programmatic
scorer applied to the team's final answer. It is verifiable, it needs no model,
and the audit has already fuzzed the scorer behind it.

One optional shaping term is offered, and it is **off by default** because it is
hackable by construction. An information-surfacing bonus pays a policy for
mentioning the facts the task says must be shared. That sounds like exactly the
behaviour a coordination environment wants, and it is collectable without
coordinating: one agent can recite its notes and never let the team decide.
The audit's ``reward_hacking`` check catches this with its
``recite_without_answering`` policy, so turning the term on makes the training
gate refuse to start unless ``--allow-flagged`` is passed and recorded.

That is deliberate. A shaping term is sometimes worth its risk -- sparse outcome
rewards are hard to learn from -- but the run manifest should say that the
reward it optimised was one the audit flagged, rather than leaving a reader to
discover it.

Credit-assignment helpers for a shared team reward are at the bottom. None of
them is counterfactual: difference rewards need counterfactual replay, which is
out of scope for this release.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from grapevine.protocol import DistributedTask, Environment, ScoreResult
from grapevine.rewards.reward import DEFAULT_SURFACING_THRESHOLD, fact_surfaced

__all__ = [
    "RewardBreakdown",
    "RewardConfig",
    "RewardedEnvironment",
    "score_episode",
    "shared_credit",
    "split_credit",
    "surfaced_fraction",
    "surfacing_credit",
]


@dataclass(frozen=True)
class RewardConfig:
    """How a trajectory is turned into a scalar reward.

    Attributes:
        outcome_weight: Weight on the team outcome reward, the environment's
            scorer applied to the final answer.
        surfacing_weight: Weight on the information-surfacing shaping term.
            **Default 0.** Any positive value makes the reward collectable
            without answering, which the audit gate flags.
        surfacing_threshold: Similarity threshold for counting a fact as
            surfaced in a message. The same matcher the v0 study used, which had
            precision 1.00 and recall about 0.86 against 40 labels
            (``docs/audit.md`` L5): it undercounts paraphrase.
    """

    outcome_weight: float = 1.0
    surfacing_weight: float = 0.0
    surfacing_threshold: float = DEFAULT_SURFACING_THRESHOLD

    def __post_init__(self) -> None:
        if self.outcome_weight < 0 or self.surfacing_weight < 0:
            raise ValueError("reward weights must be non-negative")
        if self.outcome_weight == 0 and self.surfacing_weight == 0:
            raise ValueError("at least one reward weight must be positive")
        if not 0.0 < self.surfacing_threshold <= 1.0:
            raise ValueError("surfacing_threshold must be in (0, 1]")

    @property
    def shaped(self) -> bool:
        """True when the reward includes any shaping term."""
        return self.surfacing_weight > 0

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready form, for run manifests."""
        return {**asdict(self), "shaped": self.shaped}

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> RewardConfig:
        """Build from a config file's ``reward`` block, rejecting unknown keys."""
        data = dict(data or {})
        known = {"outcome_weight", "surfacing_weight", "surfacing_threshold"}
        unknown = sorted(set(data) - known)
        if unknown:
            raise ValueError(f"unknown reward keys {unknown}; expected some of {sorted(known)}")
        return cls(**{k: float(v) for k, v in data.items()})


@dataclass(frozen=True)
class RewardBreakdown:
    """A reward and the parts it was built from.

    Attributes:
        outcome: The team outcome reward, from the environment's scorer.
        surfacing: The surfacing term before weighting, in ``[0, 1]``.
        total: ``outcome_weight * outcome + surfacing_weight * surfacing``.
        correct: Whether the team answer was correct.
    """

    outcome: float
    surfacing: float
    total: float
    correct: bool


def surfaced_fraction(
    task: DistributedTask,
    messages: Iterable[str],
    *,
    agent_id: int | None = None,
    threshold: float = DEFAULT_SURFACING_THRESHOLD,
) -> float:
    """Fraction of required units that appear in ``messages``.

    Args:
        task: The task.
        messages: The texts to search, typically one agent's messages.
        agent_id: Restrict to the required units this agent privately holds.
            ``None`` means every required unit in the task.
        threshold: Matcher threshold; see :class:`RewardConfig`.

    Returns:
        A value in ``[0, 1]``, or ``0.0`` when there are no units to surface.
    """
    if agent_id is None:
        wanted = set(task.required_units)
    else:
        own = {u.unit_id for u in task.views[agent_id].private}
        wanted = {u for u in task.required_units if u in own}
    if not wanted:
        return 0.0
    texts = list(messages)
    hits = sum(
        any(fact_surfaced(task.unit(uid).text, text, threshold) for text in texts)
        for uid in sorted(wanted)
    )
    return hits / len(wanted)


def score_episode(
    config: RewardConfig,
    task: DistributedTask,
    team_answer: str | None,
    surfacing_messages: Sequence[str],
    *,
    surfacing_agent: int | None = None,
) -> RewardBreakdown:
    """Combine outcome and shaping into one reward.

    Args:
        config: Reward weights.
        task: The task the episode ran on.
        team_answer: The parsed team answer, or ``None``.
        surfacing_messages: Messages the surfacing term is computed over.
        surfacing_agent: Restrict the surfacing term to this agent's own
            required units; ``None`` uses all of them.
    """
    result: ScoreResult = task.score(team_answer)
    surfacing = (
        surfaced_fraction(
            task,
            surfacing_messages,
            agent_id=surfacing_agent,
            threshold=config.surfacing_threshold,
        )
        if config.shaped
        else 0.0
    )
    total = config.outcome_weight * result.reward + config.surfacing_weight * surfacing
    return RewardBreakdown(
        outcome=result.reward, surfacing=surfacing, total=total, correct=result.correct
    )


class RewardedEnvironment(Environment):
    """An environment whose scorer is replaced by a training reward.

    This is how the audit sees the reward a run will actually optimise. The
    battery's ``reward_hacking`` check scores degenerate policies with each
    task's scorer; wrapping the environment makes that scorer the training
    reward, shaping term included, so a hackable term is caught before training
    rather than discovered after.

    Everything else -- name, version, seed split, conditions -- is forwarded, so
    the card describes the same environment the run trains on.
    """

    def __init__(self, env: Environment, reward: RewardConfig) -> None:
        """Wrap ``env`` so its tasks are scored by ``reward``."""
        self.inner = env
        self.reward = reward
        self.name = env.name
        self.version = env.version

    def generate(self, seed: int) -> DistributedTask:
        """The wrapped environment's task, scored by the training reward."""
        from dataclasses import replace

        task = self.inner.generate(seed)
        inner_scorer = task.scorer
        reward = self.reward

        def training_reward(answer: str | None, scored: DistributedTask) -> ScoreResult:
            base = inner_scorer(answer, scored)
            surfacing = (
                surfaced_fraction(
                    scored, [answer or ""], threshold=reward.surfacing_threshold
                )
                if reward.shaped
                else 0.0
            )
            total = reward.outcome_weight * base.reward + reward.surfacing_weight * surfacing
            return ScoreResult(
                base.answer,
                base.correct,
                total,
                {**dict(base.detail), "surfacing": surfacing, "training_reward": total},
            )

        return replace(task, scorer=training_reward)

    def seed_split(self) -> Any:
        """Forwarded."""
        return self.inner.seed_split()

    def conditions(self, task: DistributedTask) -> Any:
        """Forwarded."""
        return self.inner.conditions(task)

    def config_summary(self) -> Mapping[str, Any]:
        """The wrapped environment's config, plus the reward being audited."""
        return {**dict(self.inner.config_summary()), "training_reward": self.reward.to_dict()}


# --- Shared-team credit -------------------------------------------------------


def shared_credit(team_reward: float, n_agents: int) -> tuple[float, ...]:
    """Every agent receives the full team reward.

    The usual choice for a cooperative task, and the one ``grapevine.rl`` uses:
    every agent is trained toward the same outcome. It assigns no blame, so an
    agent that contributed nothing is rewarded like one that carried the team.
    """
    return tuple(team_reward for _ in range(n_agents))


def split_credit(team_reward: float, n_agents: int) -> tuple[float, ...]:
    """The team reward divided equally. A rescaling of :func:`shared_credit`."""
    return tuple(team_reward / n_agents for _ in range(n_agents))


def surfacing_credit(
    team_reward: float,
    task: DistributedTask,
    messages_by_agent: Mapping[int, Sequence[str]],
    *,
    threshold: float = DEFAULT_SURFACING_THRESHOLD,
) -> tuple[float, ...]:
    """Divide the team reward in proportion to what each agent surfaced.

    Each agent's share is the fraction of its own required units it surfaced,
    normalised across agents. An agent that surfaced nothing gets nothing; if
    nobody surfaced anything, credit falls back to an equal split.

    A heuristic, not a counterfactual: it does not ask whether the team would
    have failed without an agent's contribution, and it inherits the surfacing
    matcher's undercounting of paraphrase. It is also exactly the signal the
    surfacing shaping term exposes, so it carries the same hackability risk when
    used as a reward rather than as a diagnostic.
    """
    raw = [
        surfaced_fraction(
            task, messages_by_agent.get(agent_id, ()), agent_id=agent_id, threshold=threshold
        )
        for agent_id in range(task.n_agents)
    ]
    total = sum(raw)
    if total == 0:
        return split_credit(team_reward, task.n_agents)
    return tuple(team_reward * share / total for share in raw)
