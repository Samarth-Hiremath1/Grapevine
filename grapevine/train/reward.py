"""Reward function for GRPO: verifiable team reward around a generated message.

During GRPO the policy model generates candidate messages for agent 0's opening
turn. For each candidate we run the *rest* of the multi-agent rollout -- the
other agents' turns and the final aggregation -- using an auxiliary client, then
score the episode with the exact-match verifiable reward. The generated tokens
therefore causally determine the reward through a genuine multi-agent rollout,
which is exactly the signal GRPO optimises.

The auxiliary client is pluggable: a :class:`~grapevine.train.hf_client.LocalHFClient`
(the model itself, frozen) for real runs, or a fast deterministic
:class:`~grapevine.rollout.client.ScriptedClient` for the CPU smoke test.
"""

from __future__ import annotations

import asyncio

from grapevine.envs.base import Task
from grapevine.rollout.client import LLMClient, Message
from grapevine.rollout.engine import (
    AGENT_TURN_PROMPT,
    AGGREGATOR_PROMPT,
    TEAM_SYSTEM_PROMPT,
    RolloutConfig,
    TranscriptMessage,
    _render_history,
    parse_answer,
)


async def _run_seeded_episode(
    task: Task,
    seed_message: str,
    aux_client: LLMClient,
    cfg: RolloutConfig,
) -> str | None:
    """Run a rollout with agent 0's first message fixed to ``seed_message``.

    Agents ``1..n-1`` (and any later rounds) are produced by ``aux_client``; the
    aggregator likewise. Returns the parsed team answer (or ``None``).
    """
    n_agents = task.n_agents
    messages: list[TranscriptMessage] = [
        TranscriptMessage(1, 0, "discussion", seed_message.strip())
    ]

    # Remaining agents in round 1.
    for agent_id in range(1, n_agents):
        completion = await aux_client.complete(
            _turn_messages(task, agent_id, messages, 1, cfg.n_rounds),
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
        )
        messages.append(TranscriptMessage(1, agent_id, "discussion", completion.text.strip()))

    # Any further rounds: all agents via the auxiliary client.
    for round_no in range(2, cfg.n_rounds + 1):
        for agent_id in range(n_agents):
            completion = await aux_client.complete(
                _turn_messages(task, agent_id, messages, round_no, cfg.n_rounds),
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature,
            )
            messages.append(
                TranscriptMessage(round_no, agent_id, "discussion", completion.text.strip())
            )

    # Aggregation.
    agg = cfg.aggregator_index
    prompt = AGGREGATOR_PROMPT.format(
        context=task.agent_contexts[agg],
        history=_render_history(messages),
        options=", ".join(task.options),
    )
    convo = [
        Message("system", TEAM_SYSTEM_PROMPT.format(agent_id=agg, n_agents=n_agents)),
        Message("user", prompt),
    ]
    completion = await aux_client.complete(
        convo, max_tokens=cfg.max_tokens, temperature=cfg.final_temperature
    )
    return parse_answer(completion.text, task.options)


def _turn_messages(
    task: Task, agent_id: int, history: list[TranscriptMessage], round_no: int, n_rounds: int
) -> list[Message]:
    prompt = AGENT_TURN_PROMPT.format(
        context=task.agent_contexts[agent_id],
        history=_render_history(history),
        round_no=round_no,
        n_rounds=n_rounds,
    )
    return [
        Message("system", TEAM_SYSTEM_PROMPT.format(agent_id=agent_id, n_agents=task.n_agents)),
        Message("user", prompt),
    ]


async def _team_rewards_async(
    tasks: list[Task],
    completions: list[str],
    aux_client: LLMClient,
    cfg: RolloutConfig,
) -> list[float]:
    answers = await asyncio.gather(
        *(
            _run_seeded_episode(task, completion, aux_client, cfg)
            for task, completion in zip(tasks, completions, strict=True)
        )
    )
    return [1.0 if ans == task.answer else 0.0 for task, ans in zip(tasks, answers, strict=True)]


def team_reward_for_completions(
    tasks: list[Task],
    completions: list[str],
    aux_client: LLMClient,
    cfg: RolloutConfig | None = None,
) -> list[float]:
    """Compute the verifiable team reward for each ``(task, completion)`` pair.

    Args:
        tasks: One task per completion (repeated across a GRPO group).
        completions: Generated agent-0 opening messages.
        aux_client: Client that plays the remaining agents and the aggregator.
        cfg: Rollout configuration.

    Returns:
        A list of rewards in ``{0.0, 1.0}``.
    """
    cfg = cfg or RolloutConfig()
    return asyncio.run(_team_rewards_async(tasks, completions, aux_client, cfg))
