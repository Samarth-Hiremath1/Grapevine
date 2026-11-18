"""Run a team episode on any :class:`~grapevine.protocol.DistributedTask`.

The v0 engine (:mod:`grapevine.rollout.engine`) runs on the legacy ``Task`` and
is frozen with the study. This runner works on the protocol, so it drives
``hidden_profile_v2`` and any environment an outside user writes.

Two things it does that the v0 engine did not:

* **It records every prompt.** The committed v0 episodes stored responses only,
  and freezing their prompts afterwards took a refactor and a reconstruction
  pass (``studies/underspecification/prompts.py``). Here each :class:`Turn`
  carries the messages that produced it.
* **It states the objective in every prompt**, from the task's own
  :class:`~grapevine.protocol.Objective`. A test asserts it, because the v0
  result was wrong for exactly this reason.

The prompts are neutral: they do not tell agents to share or to ask. The v0
study found the instruction mattered only because the task was underspecified
(with the task stated, the neutral arm scored 99/100), and a training signal is
supposed to teach the behaviour rather than a prompt dictating it.

Turns are tagged with role, round and whether the policy being trained produced
them, so trajectories can be grouped per role or per turn downstream.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from grapevine.protocol import DistributedTask
from grapevine.rl.rewards import RewardBreakdown, RewardConfig, score_episode, shared_credit
from grapevine.rollout.client import LLMClient, Message, ScriptedClient
from grapevine.rollout.engine import parse_answer

__all__ = [
    "RolloutSettings",
    "Trajectory",
    "Turn",
    "answer_messages",
    "opening_messages",
    "render_history",
    "run_episode",
    "run_episode_sync",
    "speaking_order",
    "turn_messages",
]

SYSTEM_PROMPT = (
    "You are Agent {agent_id} of a {n_agents}-agent team making one decision together. "
    "Each of you holds different information, and no one can answer alone. "
    "Discuss the decision with your teammates. Be concise."
)

TURN_PROMPT = (
    "{objective}\n\n"
    "{view}\n\n"
    "Conversation so far:\n{history}\n\n"
    "It is your turn (round {round_no} of {n_rounds}). Write a short message to your "
    "teammates. Do not give a final answer yet."
)

ANSWER_PROMPT = (
    "{objective}\n\n"
    "{view}\n\n"
    "Full team discussion:\n{history}\n\n"
    "Decide the team's answer. Choose exactly one of these options: {options}.\n"
    'Respond with only a JSON object: {{"answer": "<one option exactly as written>"}}.'
)


@dataclass(frozen=True)
class RolloutSettings:
    """How an episode is run.

    Attributes:
        n_rounds: Discussion rounds before the aggregator answers.
        aggregator: Which agent makes the final decision.
        max_tokens: Per-call output cap.
        temperature: Sampling temperature for discussion turns.
        answer_temperature: Sampling temperature for the decision.
    """

    n_rounds: int = 2
    aggregator: int = 0
    max_tokens: int = 256
    temperature: float = 0.7
    answer_temperature: float = 0.0

    def __post_init__(self) -> None:
        if self.n_rounds < 1:
            raise ValueError("n_rounds must be >= 1")
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")


@dataclass(frozen=True)
class Turn:
    """One model call in an episode.

    Attributes:
        agent_id: Who spoke.
        round_no: 1-based discussion round; ``n_rounds + 1`` for the decision.
        kind: ``"discussion"`` or ``"answer"``.
        messages: The exact prompt sent, as ``(role, content)`` pairs.
        completion: What came back.
        trainable: Whether the policy being trained produced this turn.
        synthetic: Whether a scripted stub produced it. A trajectory with any
            synthetic turn is never a result (``CLAUDE.md`` rule 2).
    """

    agent_id: int
    round_no: int
    kind: str
    messages: tuple[tuple[str, str], ...]
    completion: str
    trainable: bool = False
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready form."""
        data = asdict(self)
        data["messages"] = [{"role": r, "content": c} for r, c in self.messages]
        return data


@dataclass(frozen=True)
class Trajectory:
    """A finished episode, with its reward and per-agent credit.

    Attributes:
        task_id: The task.
        environment: Environment name.
        environment_version: Its generation version.
        seed: The seed the task was generated from.
        turns: Every model call, in order.
        team_answer: The parsed answer, or ``None`` on a parse failure.
        reward: The reward and its parts.
        credit: Per-agent credit for the team reward (shared by default).
        trainable_agents: Agents whose turns the trained policy produced.
        metadata: Extras, including the speaking order.
    """

    task_id: str
    environment: str
    environment_version: str
    seed: int
    turns: tuple[Turn, ...]
    team_answer: str | None
    reward: RewardBreakdown
    credit: tuple[float, ...]
    trainable_agents: tuple[int, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def synthetic(self) -> bool:
        """True when any turn came from a scripted stub."""
        return any(turn.synthetic for turn in self.turns)

    def turns_by(self, agent_id: int) -> tuple[Turn, ...]:
        """Every turn one agent took."""
        return tuple(t for t in self.turns if t.agent_id == agent_id)

    def trainable_turns(self) -> tuple[Turn, ...]:
        """Turns produced by the policy being trained, for per-turn grouping."""
        return tuple(t for t in self.turns if t.trainable)

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready form. ``synthetic`` is written out explicitly."""
        return {
            "task_id": self.task_id,
            "environment": self.environment,
            "environment_version": self.environment_version,
            "seed": self.seed,
            "synthetic": self.synthetic,
            "team_answer": self.team_answer,
            "reward": asdict(self.reward),
            "credit": list(self.credit),
            "trainable_agents": list(self.trainable_agents),
            "turns": [t.to_dict() for t in self.turns],
            "metadata": dict(self.metadata),
        }


def speaking_order(n_agents: int, first: int = 0) -> tuple[int, ...]:
    """Agents in speaking order, starting from ``first``.

    Training one role uses this so the trainable agent always speaks first in
    round one. Its opening prompt then has an empty history and can be built in
    advance, which is what a GRPO dataset needs; without it, an agent that
    speaks second would need its teammates' messages generated before the
    dataset could exist.
    """
    if not 0 <= first < n_agents:
        raise ValueError(f"first speaker {first} is not one of {n_agents} agents")
    return tuple((first + i) % n_agents for i in range(n_agents))


def render_history(turns: Sequence[Turn]) -> str:
    """The transcript as agents see it."""
    if not turns:
        return "(no messages yet)"
    return "\n".join(f"Agent {t.agent_id}: {t.completion}" for t in turns)


def turn_messages(
    task: DistributedTask,
    agent_id: int,
    history: Sequence[Turn],
    round_no: int,
    settings: RolloutSettings,
) -> list[Message]:
    """The exact messages for one discussion turn."""
    return [
        Message("system", SYSTEM_PROMPT.format(agent_id=agent_id, n_agents=task.n_agents)),
        Message(
            "user",
            TURN_PROMPT.format(
                objective=task.objective.statement(),
                view=task.views[agent_id].render(),
                history=render_history(history),
                round_no=round_no,
                n_rounds=settings.n_rounds,
            ),
        ),
    ]


def opening_messages(
    task: DistributedTask, agent_id: int, settings: RolloutSettings
) -> list[Message]:
    """The first-turn messages for an agent that speaks first."""
    return turn_messages(task, agent_id, (), 1, settings)


def answer_messages(
    task: DistributedTask, history: Sequence[Turn], settings: RolloutSettings
) -> list[Message]:
    """The exact messages for the aggregator's decision."""
    agg = settings.aggregator
    return [
        Message("system", SYSTEM_PROMPT.format(agent_id=agg, n_agents=task.n_agents)),
        Message(
            "user",
            ANSWER_PROMPT.format(
                objective=task.objective.statement(),
                view=task.views[agg].render(),
                history=render_history(history),
                options=", ".join(task.answer_space),
            ),
        ),
    ]


def _pair(messages: Sequence[Message]) -> tuple[tuple[str, str], ...]:
    return tuple((m.role, m.content) for m in messages)


async def run_episode(
    task: DistributedTask,
    clients: Mapping[int, LLMClient],
    *,
    settings: RolloutSettings | None = None,
    reward: RewardConfig | None = None,
    first_speaker: int = 0,
    fixed_openings: Mapping[int, str] | None = None,
    trainable_agents: Sequence[int] = (),
    environment: str = "",
    environment_version: str = "",
    seed: int = -1,
) -> Trajectory:
    """Run one episode and score it.

    Args:
        task: The task.
        clients: One client per agent id. The same client may serve several
            agents (self-play) or each may differ (one trained role, frozen
            partners).
        settings: Rounds, aggregator and sampling.
        reward: How the trajectory is rewarded. Defaults to outcome only.
        first_speaker: Who opens each round.
        fixed_openings: Agent id to an already-generated round-one message. Used
            during GRPO, where the trainer has generated the trainable agent's
            opening and the rest of the episode is played around it.
        trainable_agents: Agents whose turns the trained policy produced. Only
            affects tagging and the surfacing term.
        environment: Environment name, recorded on the trajectory.
        environment_version: Its version.
        seed: The task's seed.

    Returns:
        The scored :class:`Trajectory`.

    Raises:
        ValueError: If a client is missing for some agent.
    """
    settings = settings or RolloutSettings()
    reward = reward or RewardConfig()
    fixed = dict(fixed_openings or {})
    trainable = set(trainable_agents)
    missing = [a for a in range(task.n_agents) if a not in clients]
    if missing:
        raise ValueError(f"no client for agent(s) {missing}")

    order = speaking_order(task.n_agents, first_speaker)
    turns: list[Turn] = []

    for round_no in range(1, settings.n_rounds + 1):
        for agent_id in order:
            messages = turn_messages(task, agent_id, turns, round_no, settings)
            if round_no == 1 and agent_id in fixed:
                text = fixed[agent_id]
                synthetic = False
            else:
                client = clients[agent_id]
                completion = await client.complete(
                    messages, max_tokens=settings.max_tokens, temperature=settings.temperature
                )
                text = completion.text
                synthetic = isinstance(client, ScriptedClient)
            turns.append(
                Turn(
                    agent_id=agent_id,
                    round_no=round_no,
                    kind="discussion",
                    messages=_pair(messages),
                    completion=text.strip(),
                    trainable=agent_id in trainable,
                    synthetic=synthetic,
                )
            )

    agg = settings.aggregator
    messages = answer_messages(task, turns, settings)
    client = clients[agg]
    completion = await client.complete(
        messages, max_tokens=settings.max_tokens, temperature=settings.answer_temperature
    )
    turns.append(
        Turn(
            agent_id=agg,
            round_no=settings.n_rounds + 1,
            kind="answer",
            messages=_pair(messages),
            completion=completion.text.strip(),
            trainable=agg in trainable,
            synthetic=isinstance(client, ScriptedClient),
        )
    )

    answer = parse_answer(completion.text, list(task.answer_space))
    # The surfacing term is computed over the trained agent's own messages and
    # its own required units, so a policy is credited only for what it shared.
    surfacing_agent = min(trainable) if len(trainable) == 1 else None
    surfacing_texts = [
        t.completion
        for t in turns
        if t.kind == "discussion" and (surfacing_agent is None or t.agent_id == surfacing_agent)
    ]
    breakdown = score_episode(
        reward, task, answer, surfacing_texts, surfacing_agent=surfacing_agent
    )
    return Trajectory(
        task_id=task.task_id,
        environment=environment,
        environment_version=environment_version,
        seed=seed,
        turns=tuple(turns),
        team_answer=answer,
        reward=breakdown,
        credit=shared_credit(breakdown.total, task.n_agents),
        trainable_agents=tuple(sorted(trainable)),
        metadata={"speaking_order": list(order), "aggregator": agg},
    )


def run_episode_sync(*args: Any, **kwargs: Any) -> Trajectory:
    """:func:`run_episode` from synchronous code, such as a TRL reward function.

    TRL calls synchronous reward functions on the main thread with no event loop
    running (async ones go to a separate loop thread), so ``asyncio.run`` is safe
    there. Calling this from inside a running loop raises, which is the right
    failure: use :func:`run_episode` directly instead.
    """
    return asyncio.run(run_episode(*args, **kwargs))
