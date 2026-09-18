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


def test_parse_answer_multiple_options_fails_loudly() -> None:
    options = ["Avery", "Blair"]
    # Both appear and there is no JSON answer: refuse to guess.
    assert parse_answer("Maybe Avery, but actually Blair.", options) is None


#: (name, model output, what a careful reader would take it to mean, what the
#: parser must return). The parser may fail loudly (None) on an answer a human
#: could read, but it must never return an option the text does not choose.
ADVERSARIAL_ANSWERS = [
    ("clean JSON", '{"answer": "Blair"}', "Blair", "Blair"),
    ("empty JSON answer", '{"answer": ""}', None, None),
    ("single letter", '{"answer": "A"}', None, None),
    ("single lowercase letter", '{"answer": "e"}', None, None),
    ("refusal", "I cannot determine an answer.", None, None),
    ("none fit", "None of the candidates is clearly best.", None, None),
    ("reject then pick", "Not Avery. I choose Blair.", "Blair", None),
    ("pick then reject", "I choose Blair. Actually no, Avery.", "Avery", None),
    ("pick then mention", "Blair is best; Avery was close.", "Blair", None),
    ("two named, no verdict", "It is between Avery and Blair.", None, None),
    ("fenced JSON", '```json\n{"answer": "Devon"}\n```', "Devon", "Devon"),
    ("lowercase", '{"answer": "devon"}', "Devon", "Devon"),
    ("trailing period", '{"answer": "Devon."}', "Devon", "Devon"),
    ("option inside a longer word", "Averyone agrees on Cameron.", "Cameron", "Cameron"),
    ("all four listed", "Options: Avery, Blair, Cameron, Devon.", None, None),
    ("nested JSON", '{"result": {"answer": "Blair"}}', "Blair", "Blair"),
    ("answer under another key", '{"choice": "Blair"}', "Blair", "Blair"),
    ("JSON answer is a sentence", '{"answer": "I pick Blair over Avery"}', "Blair", None),
]


def test_parse_answer_adversarial_never_returns_a_wrong_option() -> None:
    """Regression test for audit finding D1.

    The old parser matched substrings in both directions, so an empty or
    one-letter answer resolved to the first option, and free text took the
    last-mentioned option. 7 of these 18 cases used to return a wrong option.
    """
    options = ["Avery", "Blair", "Cameron", "Devon"]
    for name, text, meant, expected in ADVERSARIAL_ANSWERS:
        got = parse_answer(text, options)
        assert got in (meant, None), f"{name}: returned {got!r}, text means {meant!r}"
        assert got == expected, f"{name}: returned {got!r}, expected {expected!r}"


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


async def test_per_episode_usage_is_not_corrupted_by_concurrency() -> None:
    """Concurrent episodes sharing one client must each report only their own usage.

    Regression test: usage was previously computed by diffing the client's running
    totals before and after an episode. Because every ``await`` lets other
    episodes interleave, each episode absorbed the others' tokens (four
    concurrent episodes reported 13-16 calls apiece instead of 4).
    """
    import asyncio

    from grapevine.rollout.client import Completion, LLMClient, Pricing

    class YieldingClient(LLMClient):
        """Client that awaits, so concurrent episodes genuinely interleave."""

        def __init__(self) -> None:
            super().__init__("yielding")
            self.price = Pricing(0.001, 0.001)

        async def complete(
            self, messages: list[Message], *, max_tokens: int = 512, temperature: float = 0.7
        ) -> Completion:
            await asyncio.sleep(0.005)
            completion = Completion("ok", 10, 5, self.price.cost(10, 5))
            self._record(completion)
            return completion

    env = HiddenProfileEnv(HiddenProfileConfig())
    tasks = env.generate_batch(4, seed=0)
    client = YieldingClient()
    cfg = RolloutConfig(n_rounds=1)

    episodes = await asyncio.gather(*(run_episode(t, client, cfg) for t in tasks))

    expected_calls = tasks[0].n_agents + 1  # 1 round of discussion + aggregation
    for ep in episodes:
        assert ep.usage["n_calls"] == expected_calls
        assert ep.usage["prompt_tokens"] == 10 * expected_calls
    # Per-episode usage must sum to the client's own total, with no double count.
    assert sum(e.usage["n_calls"] for e in episodes) == client.n_calls


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


def test_model_parameter_detection() -> None:
    """GPT-5 and o-series need max_completion_tokens and reject explicit temperature."""
    from grapevine.rollout.client import (
        OpenAICompatibleClient,
        supports_temperature,
        uses_max_completion_tokens,
    )

    assert uses_max_completion_tokens("gpt-5.6-luna")
    assert uses_max_completion_tokens("o3-mini")
    assert not uses_max_completion_tokens("gpt-4o-mini")

    assert not supports_temperature("gpt-5.6-luna")
    assert supports_temperature("gpt-4o-mini")

    new = OpenAICompatibleClient("gpt-5.6-luna", api_key="x")
    assert new.token_param == "max_completion_tokens"
    assert new.supports_temperature is False

    old = OpenAICompatibleClient("gpt-4o-mini", api_key="x")
    assert old.token_param == "max_tokens"
    assert old.supports_temperature is True

    # Explicit override wins over detection.
    forced = OpenAICompatibleClient("gpt-5.6-luna", api_key="x", token_param="max_tokens")
    assert forced.token_param == "max_tokens"


async def test_task_statement_only_shown_when_requested() -> None:
    """The rule arm shows the question and scoring rule; default prompts do not.

    Defaults must stay byte-identical to what produced the committed four-condition
    run, and A and C must receive exactly the same statement text.
    """
    from grapevine.rollout.engine import AGGREGATOR_PROMPT, TASK_STATEMENT

    env = HiddenProfileEnv(HiddenProfileConfig())
    task = env.generate(1006)
    statement = TASK_STATEMENT.format(question=task.question)

    def capture() -> tuple[list[str], ScriptedClient]:
        seen: list[str] = []

        def responder(messages: list[Message]) -> str:
            seen.append(messages[-1].content)
            return f'{{"answer": "{task.answer}"}}'

        return seen, ScriptedClient(responder)

    seen_a, client_a = capture()
    await run_single_agent(task, client_a, RolloutConfig())
    seen_c, client_c = capture()
    await run_episode(task, client_c, RolloutConfig(n_rounds=1))
    assert seen_a[0] == AGGREGATOR_PROMPT.format(
        context="All available information:\n" + task.full_context(),
        history="(you have all information; no discussion needed)",
        options=", ".join(task.options),
    )
    for prompt in seen_a + seen_c:
        assert "Decision rule" not in prompt
        assert task.question not in prompt

    seen_a, client_a = capture()
    await run_single_agent(task, client_a, RolloutConfig(show_task=True))
    seen_c, client_c = capture()
    await run_episode(task, client_c, RolloutConfig(n_rounds=1, show_task=True))
    assert len(seen_a) == 1
    assert len(seen_c) == task.n_agents + 1  # one discussion round plus aggregation
    for prompt in seen_a + seen_c:
        assert prompt.startswith(statement + "\n\n")


async def test_aggregator_system_prompt_follows_prompt_style() -> None:
    """Every call in a neutral-style episode, including aggregation, gets the neutral
    system prompt; instructed-style episodes keep the team prompt throughout.

    Regression test for audit finding L11: the aggregation branch used to send
    TEAM_SYSTEM_PROMPT regardless of prompt_style.
    """
    from grapevine.rollout.engine import NEUTRAL_SYSTEM_PROMPT, TEAM_SYSTEM_PROMPT

    env = HiddenProfileEnv(HiddenProfileConfig())
    task = env.generate(1006)

    for style, template in (("neutral", NEUTRAL_SYSTEM_PROMPT), ("instructed", TEAM_SYSTEM_PROMPT)):
        systems: list[str] = []

        def responder(messages: list[Message], systems: list[str] = systems) -> str:
            systems.append(messages[0].content)
            return f'{{"answer": "{task.answer}"}}'

        await run_episode(task, ScriptedClient(responder), RolloutConfig(n_rounds=1, prompt_style=style))
        assert len(systems) == task.n_agents + 1
        allowed = {template.format(agent_id=i, n_agents=task.n_agents) for i in range(task.n_agents)}
        assert all(s in allowed for s in systems), f"{style}: a call used the wrong system prompt"
