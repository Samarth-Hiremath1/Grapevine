"""Tests for the no-communication condition and its tie-break rule.

The no-communication arm is the experiment's key control, so the properties that
make it a valid control are asserted here: agents are genuinely isolated, and the
tie-break is deterministic and unbiased with respect to the correct answer.
"""

from __future__ import annotations

import random

from grapevine.envs.hidden_profile import HiddenProfileConfig, HiddenProfileEnv
from grapevine.rollout.client import Message, ScriptedClient
from grapevine.rollout.engine import RolloutConfig, run_no_communication, tally_votes


def test_agents_are_isolated_no_shared_state() -> None:
    """Each agent must see only its own context: no history, no teammate output."""
    env = HiddenProfileEnv(HiddenProfileConfig())
    task = env.generate(0)
    seen_prompts: list[str] = []

    def responder(messages: list[Message]) -> str:
        seen_prompts.append(messages[-1].content)
        return f'{{"answer": "{task.options[0]}"}}'

    client = ScriptedClient(responder)
    import asyncio

    asyncio.run(run_no_communication(task, client, RolloutConfig()))

    assert len(seen_prompts) == task.n_agents
    private = task.metadata["private_facts"]
    for i, prompt in enumerate(seen_prompts):
        # Agent i's own private facts are present...
        for fact in private[i]:
            assert fact in prompt
        # ...and no other agent's private facts are.
        for j, facts in enumerate(private):
            if j == i:
                continue
            for fact in facts:
                assert fact not in prompt, f"agent {i} saw agent {j}'s private fact"
        # No discussion history leaked in.
        assert "Conversation so far" not in prompt
        assert "Full team discussion" not in prompt


def test_tally_votes_clear_majority() -> None:
    options = ["A", "B", "C", "D"]
    answer, was_tie, tally = tally_votes(["B", "B", "C"], options, "task-1")
    assert answer == "B"
    assert was_tie is False
    assert tally == {"A": 0, "B": 2, "C": 1, "D": 0}


def test_tally_votes_tie_is_flagged_and_deterministic() -> None:
    """A three-way split is flagged as a tie and resolves identically every time."""
    options = ["A", "B", "C", "D"]
    first, was_tie, _ = tally_votes(["A", "B", "C"], options, "task-7")
    assert was_tie is True
    for _ in range(20):
        again, _, _ = tally_votes(["A", "B", "C"], options, "task-7")
        assert again == first, "tie-break must be deterministic for a given task id"
    assert first in {"A", "B", "C"}


def test_tie_break_is_unbiased_across_tasks() -> None:
    """Across many task ids the tie-break spreads roughly evenly over the leaders.

    Guards against a rule that systematically favours one position (e.g. always
    taking the first listed option), which would entangle the tie-break with
    option ordering.
    """
    options = ["A", "B", "C", "D"]
    counts = {"A": 0, "B": 0, "C": 0}
    for i in range(600):
        pick, was_tie, _ = tally_votes(["A", "B", "C"], options, f"hidden_profile-{i}")
        assert was_tie
        counts[pick] += 1
    # Uniform would be 200 each; allow a generous band for sampling noise.
    for opt, n in counts.items():
        assert 140 < n < 260, f"tie-break looks biased toward/against {opt}: {counts}"


def test_unparseable_votes_excluded_and_counted() -> None:
    """A refusal counts toward no option and is reported as a parse failure."""
    env = HiddenProfileEnv(HiddenProfileConfig())
    task = env.generate(2)

    def responder(messages: list[Message]) -> str:
        return "I cannot determine an answer from this information."

    import asyncio

    ep = asyncio.run(run_no_communication(task, ScriptedClient(responder), RolloutConfig()))
    assert ep.metadata["n_parse_failures"] == task.n_agents
    assert ep.team_answer is None
    assert ep.correct is False
    assert all(v == 0 for v in ep.metadata["vote_tally"].values())


def test_records_votes_and_usage() -> None:
    env = HiddenProfileEnv(HiddenProfileConfig())
    task = env.generate(5)
    gold = task.answer

    def responder(messages: list[Message]) -> str:
        return f'{{"answer": "{gold}"}}'

    import asyncio

    ep = asyncio.run(run_no_communication(task, ScriptedClient(responder), RolloutConfig()))
    assert ep.metadata["condition"] == "no_communication"
    assert ep.metadata["votes"] == [gold] * task.n_agents
    assert ep.correct is True
    # One call per agent, no discussion turns.
    assert ep.usage["n_calls"] == task.n_agents
    assert len(ep.messages) == task.n_agents


def test_tie_break_matches_documented_rule() -> None:
    """The rule is: seeded uniform choice among tied leaders, seeded by task id."""
    options = ["A", "B", "C", "D"]
    votes = ["A", "B", "C"]
    got, _, _ = tally_votes(votes, options, "task-xyz")
    leaders = ["A", "B", "C"]
    expected = random.Random("task-xyz").choice(leaders)
    assert got == expected
