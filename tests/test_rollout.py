"""Tests for the rollout engine, answer parsing, and cost tracking.

Uses the offline ScriptedClient so no network or API key is needed.
"""

from __future__ import annotations

from grapevine.envs.hidden_profile import HiddenProfileConfig, HiddenProfileEnv
from grapevine.rollout.client import Message, Pricing, ScriptedClient
from grapevine.rollout.engine import (
    RolloutConfig,
    parse_answer,
    run_episode,
    run_single_agent,
)


def test_parse_answer_json() -> None:
    options = ["Avery", "Blair", "Cameron"]
    assert parse_answer('{"answer": "Blair"}', options) == "Blair"
    assert parse_answer('I think {"answer":"cameron"} is best', options) == "Cameron"


def test_parse_answer_freeform_and_none() -> None:
    options = ["Avery", "Blair", "Cameron"]
    assert parse_answer("My final pick is Avery.", options) == "Avery"
    assert parse_answer("no option named here", options) is None


def test_parse_answer_last_mentioned_on_conflict() -> None:
    options = ["Avery", "Blair"]
    # Both appear; the later mention wins.
    assert parse_answer("Maybe Avery, but actually Blair.", options) == "Blair"


async def test_run_episode_correct_when_aggregator_picks_gold() -> None:
    env = HiddenProfileEnv(HiddenProfileConfig())
    task = env.generate(0)

    def responder(messages: list[Message]) -> str:
        user = messages[-1].content
        if "JSON object" in user:  # final answer turn
            return f'{{"answer": "{task.answer}"}}'
        return "Here is a fact I hold."

    client = ScriptedClient(responder, price=Pricing(0.001, 0.002))
    episode = await run_episode(task, client, RolloutConfig(n_rounds=2))
    assert episode.correct is True
    assert episode.team_answer == task.answer
    # 2 rounds * n_agents discussion + 1 aggregation call.
    expected_calls = 2 * task.n_agents + 1
    assert episode.usage["n_calls"] == expected_calls
    assert episode.usage["cost_usd"] > 0.0
    assert len(episode.messages) == expected_calls


async def test_run_episode_vote_mode() -> None:
    env = HiddenProfileEnv(HiddenProfileConfig())
    task = env.generate(3)
    wrong = next(o for o in task.options if o != task.answer)

    def responder(messages: list[Message]) -> str:
        user = messages[-1].content
        if "vote" in user.lower():
            return f'{{"answer": "{wrong}"}}'
        return "Sharing what I know."

    client = ScriptedClient(responder)
    episode = await run_episode(task, client, RolloutConfig(n_rounds=1, aggregation="vote"))
    assert episode.team_answer == wrong
    assert episode.correct is False


async def test_single_agent_sees_full_context() -> None:
    env = HiddenProfileEnv(HiddenProfileConfig())
    task = env.generate(1)
    captured: dict[str, str] = {}

    def responder(messages: list[Message]) -> str:
        captured["ctx"] = messages[-1].content
        return f'{{"answer": "{task.answer}"}}'

    client = ScriptedClient(responder)
    episode = await run_single_agent(task, client)
    assert episode.correct is True
    assert episode.n_agents == 1
    # Every required private fact is present in the single-agent context.
    for fact in task.required_private_facts:
        assert fact in captured["ctx"]
