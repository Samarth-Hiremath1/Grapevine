"""Async multi-agent rollout engine.

An episode runs ``n_agents`` agents over ``n_rounds`` of discussion. In each
round every agent produces one message given its own private context plus the
full shared history of messages produced so far. After the final round the team
answer is produced either by a designated aggregator agent or by majority vote.

The engine is deliberately agnostic to where completions come from: it takes an
:class:`~grapevine.rollout.client.LLMClient` (one shared client, or one per
agent), so the same code path is used for API evaluation, offline scripted
tests, and on-policy generation during GRPO training.

Every episode is captured as a fully structured :class:`Episode` that serialises
to a single JSONL line, including every message and per-episode cost/usage.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from grapevine.envs.base import Task
from grapevine.rollout.client import Completion, LLMClient, Message

TEAM_SYSTEM_PROMPT = (
    "You are Agent {agent_id} of a {n_agents}-agent team solving a problem together. "
    "Each teammate holds different private information, and no one can answer alone. "
    "Your job is to actively SHARE the specific facts you hold and ASK teammates for "
    "information you are missing, then reason over everything the team has surfaced. "
    "State concrete facts verbatim rather than vague summaries. Be concise."
)

AGENT_TURN_PROMPT = (
    "{context}\n\n"
    "Conversation so far:\n{history}\n\n"
    "It is your turn (round {round_no} of {n_rounds}). Write a short message to your "
    "teammates: share the specific facts you hold that are relevant, and ask for any "
    "information you still need. Do not state a final answer yet."
)

AGGREGATOR_PROMPT = (
    "{context}\n\n"
    "Full team discussion:\n{history}\n\n"
    "Based on everything the team surfaced, decide the single best answer. "
    "Choose exactly one of these options: {options}.\n"
    'Respond with only a JSON object: {{"answer": "<one option exactly as written>"}}.'
)

#: Condition D. Identical to TEAM_SYSTEM_PROMPT for the first two sentences, then
#: replaces the explicit share/ask instruction with a neutral framing. Isolates
#: how much of condition C's performance comes from being told to pool.
NEUTRAL_SYSTEM_PROMPT = (
    "You are Agent {agent_id} of a {n_agents}-agent team solving a problem together. "
    "Each teammate holds different private information, and no one can answer alone. "
    "Discuss the decision with your teammates. Be concise."
)

#: Condition D turn prompt: the C turn prompt with the "share the specific facts
#: you hold / ask for any information you still need" directive removed.
NEUTRAL_TURN_PROMPT = (
    "{context}\n\n"
    "Conversation so far:\n{history}\n\n"
    "It is your turn (round {round_no} of {n_rounds}). Write a short message to your "
    "teammates. Do not state a final answer yet."
)

SOLO_SYSTEM_PROMPT = (
    "You are Agent {agent_id} of a {n_agents}-agent group. Each member holds different "
    "private information. You must decide ALONE: there is no discussion, you cannot ask "
    "anyone anything, and you will never see what the others hold. Reason carefully over "
    "the information you have and commit to the best answer you can."
)

NO_COMM_PROMPT = (
    "{context}\n\n"
    "You are deciding alone, with no discussion.\n"
    "Choose exactly one of these options: {options}.\n"
    'Respond with only a JSON object: {{"answer": "<one option exactly as written>"}}.'
)

VOTE_PROMPT = (
    "{context}\n\n"
    "Full team discussion:\n{history}\n\n"
    "Cast your individual vote for the single best answer. "
    "Choose exactly one of these options: {options}.\n"
    'Respond with only a JSON object: {{"answer": "<one option exactly as written>"}}.'
)


#: Shown only in the rule arm (``show_task=True``). States the task's question and
#: the rule grading uses. Conditions A-D never saw either.
TASK_STATEMENT = (
    "Task: {question}\n"
    "Decision rule: the strongest candidate is the one with the most supporting facts. "
    "Each fact describing a candidate's strengths counts as one supporting fact for "
    "that candidate."
)


def _with_task(context: str, task: Task, show_task: bool) -> str:
    """Prepend the task statement to a prompt context when ``show_task`` is set."""
    if not show_task:
        return context
    return f"{TASK_STATEMENT.format(question=task.question)}\n\n{context}"


@dataclass
class RolloutConfig:
    """Configuration for a rollout episode.

    Attributes:
        n_rounds: Number of discussion rounds before the team answers.
        aggregation: ``"aggregator"`` (a designated agent decides) or ``"vote"``
            (each agent votes; majority wins, ties broken by option order).
        aggregator_index: Which agent aggregates when ``aggregation="aggregator"``.
        max_tokens: Max tokens per model call.
        temperature: Sampling temperature for discussion turns.
        final_temperature: Sampling temperature for the answer/vote turn.
        prompt_style: ``"instructed"`` (condition C) tells agents to share their
            facts and ask for what they are missing; ``"neutral"`` (condition D)
            gives the same task framing without that directive. Everything else
            about the rollout is unchanged.
        show_task: When True, every prompt starts with :data:`TASK_STATEMENT` (the
            task question plus the scoring rule). Off by default, which keeps
            prompts byte-identical to those used for the four-condition run.
    """

    n_rounds: int = 2
    aggregation: str = "aggregator"
    aggregator_index: int = 0
    max_tokens: int = 400
    temperature: float = 0.7
    final_temperature: float = 0.0
    prompt_style: str = "instructed"
    show_task: bool = False

    def __post_init__(self) -> None:
        if self.n_rounds < 1:
            raise ValueError("n_rounds must be >= 1")
        if self.aggregation not in ("aggregator", "vote"):
            raise ValueError("aggregation must be 'aggregator' or 'vote'")
        if self.prompt_style not in ("instructed", "neutral"):
            raise ValueError("prompt_style must be 'instructed' or 'neutral'")

    def discussion_prompts(self) -> tuple[str, str]:
        """Return ``(system_prompt, turn_prompt)`` templates for this style."""
        if self.prompt_style == "neutral":
            return NEUTRAL_SYSTEM_PROMPT, NEUTRAL_TURN_PROMPT
        return TEAM_SYSTEM_PROMPT, AGENT_TURN_PROMPT


@dataclass
class TranscriptMessage:
    """One message in an episode transcript."""

    round_no: int
    agent_id: int
    role: str  # "discussion" | "answer" | "vote"
    content: str


@dataclass
class Episode:
    """A completed rollout episode, serialisable to one JSONL line."""

    task_id: str
    family: str
    question: str
    options: list[str]
    gold_answer: str
    team_answer: str | None
    correct: bool
    messages: list[TranscriptMessage]
    required_private_facts: list[str]
    n_agents: int
    config: dict[str, Any]
    usage: dict[str, float]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-ready dict."""
        data = asdict(self)
        return data

    def to_jsonl(self) -> str:
        """Serialise to a single JSON line."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Episode:
        """Reconstruct an :class:`Episode` from :meth:`to_dict` output."""
        messages = [
            TranscriptMessage(
                round_no=int(m["round_no"]),
                agent_id=int(m["agent_id"]),
                role=str(m["role"]),
                content=str(m["content"]),
            )
            for m in data.get("messages", [])
        ]
        return cls(
            task_id=data["task_id"],
            family=data.get("family", "unknown"),
            question=data["question"],
            options=list(data["options"]),
            gold_answer=data["gold_answer"],
            team_answer=data.get("team_answer"),
            correct=bool(data["correct"]),
            messages=messages,
            required_private_facts=list(data.get("required_private_facts", [])),
            n_agents=int(data.get("n_agents", 0)),
            config=dict(data.get("config", {})),
            usage=dict(data.get("usage", {})),
            metadata=dict(data.get("metadata", {})),
        )


def _render_history(messages: list[TranscriptMessage]) -> str:
    """Render the discussion so far as plain text for the next prompt."""
    if not messages:
        return "(no messages yet)"
    lines = []
    for m in messages:
        if m.role == "discussion":
            lines.append(f"Agent {m.agent_id}: {m.content}")
    return "\n".join(lines) if lines else "(no messages yet)"


def parse_answer(text: str, options: list[str]) -> str | None:
    """Extract the chosen option from a model response.

    Tries, in order: a ``{"answer": ...}`` JSON object, then an exact
    case-insensitive option match anywhere in the text. Returns ``None`` if no
    option can be identified.
    """
    # 1) JSON object with an "answer" field.
    for match in re.finditer(r"\{[^{}]*\}", text, re.DOTALL):
        try:
            obj = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "answer" in obj:
            candidate = str(obj["answer"]).strip()
            resolved = _match_option(candidate, options)
            if resolved is not None:
                return resolved
    # 2) Any option string appearing verbatim (case-insensitive).
    lowered = text.lower()
    hits = [opt for opt in options if opt.lower() in lowered]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        # Prefer the last-mentioned option (closest to a concluding statement).
        positions = {opt: lowered.rfind(opt.lower()) for opt in hits}
        return max(positions, key=lambda o: positions[o])
    return None


def _match_option(candidate: str, options: list[str]) -> str | None:
    """Resolve a raw answer string to one of ``options`` (exact/substring)."""
    for opt in options:
        if candidate.lower() == opt.lower():
            return opt
    for opt in options:
        if opt.lower() in candidate.lower() or candidate.lower() in opt.lower():
            return opt
    return None


def _majority_vote(votes: list[str | None], options: list[str]) -> str | None:
    """Return the majority option, breaking ties by option order."""
    tally = {opt: 0 for opt in options}
    for v in votes:
        if v in tally:
            tally[v] += 1
    best = max(tally.values())
    if best == 0:
        return None
    for opt in options:  # option order breaks ties deterministically
        if tally[opt] == best:
            return opt
    return None


class _UsageAccumulator:
    """Accumulates token/cost usage for exactly one episode.

    Usage must be summed from the completions this episode actually received,
    not by diffing the client's running totals before and after. A single client
    is normally shared by many episodes running concurrently, and every ``await``
    lets those episodes interleave, so a before/after diff silently absorbs other
    episodes' tokens. (Measured: four concurrent episodes each reported 13-16
    calls when the true figure was 4.)
    """

    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cost_usd = 0.0
        self.n_calls = 0

    def add(self, completion: Completion) -> Completion:
        """Record ``completion`` against this episode and return it unchanged."""
        self.prompt_tokens += completion.prompt_tokens
        self.completion_tokens += completion.completion_tokens
        self.cost_usd += completion.cost_usd
        self.n_calls += 1
        return completion

    def as_dict(self) -> dict[str, float]:
        """Return the accumulated usage in the Episode.usage shape."""
        return {
            "prompt_tokens": float(self.prompt_tokens),
            "completion_tokens": float(self.completion_tokens),
            "cost_usd": self.cost_usd,
            "n_calls": float(self.n_calls),
        }


def _clients_for(
    clients: LLMClient | list[LLMClient], n_agents: int
) -> list[LLMClient]:
    """Normalise a single client or a per-agent list into a per-agent list."""
    if isinstance(clients, list):
        if len(clients) != n_agents:
            raise ValueError(f"expected {n_agents} clients, got {len(clients)}")
        return clients
    return [clients] * n_agents


async def run_episode(
    task: Task,
    clients: LLMClient | list[LLMClient],
    config: RolloutConfig | None = None,
) -> Episode:
    """Run one multi-agent episode on ``task`` and return the :class:`Episode`.

    Args:
        task: The task to solve.
        clients: One shared :class:`LLMClient`, or one per agent.
        config: Rollout configuration; defaults to :class:`RolloutConfig`.

    Returns:
        A fully populated :class:`Episode` including every message, the parsed
        team answer, correctness, and per-episode token/cost usage.
    """
    cfg = config or RolloutConfig()
    n_agents = task.n_agents
    agent_clients = _clients_for(clients, n_agents)

    usage_acc = _UsageAccumulator()
    messages: list[TranscriptMessage] = []
    system_tmpl, turn_tmpl = cfg.discussion_prompts()

    # --- Discussion rounds --------------------------------------------------
    for round_no in range(1, cfg.n_rounds + 1):
        for agent_id in range(n_agents):
            prompt = turn_tmpl.format(
                context=_with_task(task.agent_contexts[agent_id], task, cfg.show_task),
                history=_render_history(messages),
                round_no=round_no,
                n_rounds=cfg.n_rounds,
            )
            convo = [
                Message("system", system_tmpl.format(agent_id=agent_id, n_agents=n_agents)),
                Message("user", prompt),
            ]
            completion = usage_acc.add(
                await agent_clients[agent_id].complete(
                    convo, max_tokens=cfg.max_tokens, temperature=cfg.temperature
                )
            )
            messages.append(
                TranscriptMessage(round_no, agent_id, "discussion", completion.text.strip())
            )

    # --- Final answer -------------------------------------------------------
    team_answer: str | None
    if cfg.aggregation == "vote":
        votes: list[str | None] = []
        for agent_id in range(n_agents):
            prompt = VOTE_PROMPT.format(
                context=_with_task(task.agent_contexts[agent_id], task, cfg.show_task),
                history=_render_history(messages),
                options=", ".join(task.options),
            )
            convo = [
                Message("system", TEAM_SYSTEM_PROMPT.format(agent_id=agent_id, n_agents=n_agents)),
                Message("user", prompt),
            ]
            completion = usage_acc.add(
                await agent_clients[agent_id].complete(
                    convo, max_tokens=cfg.max_tokens, temperature=cfg.final_temperature
                )
            )
            vote = parse_answer(completion.text, task.options)
            votes.append(vote)
            messages.append(
                TranscriptMessage(cfg.n_rounds + 1, agent_id, "vote", completion.text.strip())
            )
        team_answer = _majority_vote(votes, task.options)
    else:
        agg = cfg.aggregator_index
        prompt = AGGREGATOR_PROMPT.format(
            context=_with_task(task.agent_contexts[agg], task, cfg.show_task),
            history=_render_history(messages),
            options=", ".join(task.options),
        )
        convo = [
            Message("system", TEAM_SYSTEM_PROMPT.format(agent_id=agg, n_agents=n_agents)),
            Message("user", prompt),
        ]
        completion = usage_acc.add(
            await agent_clients[agg].complete(
                convo, max_tokens=cfg.max_tokens, temperature=cfg.final_temperature
            )
        )
        team_answer = parse_answer(completion.text, task.options)
        messages.append(TranscriptMessage(cfg.n_rounds + 1, agg, "answer", completion.text.strip()))

    usage = usage_acc.as_dict()

    return Episode(
        task_id=task.task_id,
        family=str(task.metadata.get("family", "unknown")),
        question=task.question,
        options=task.options,
        gold_answer=task.answer,
        team_answer=team_answer,
        correct=(team_answer == task.answer),
        messages=messages,
        required_private_facts=task.required_private_facts,
        n_agents=n_agents,
        config=asdict(cfg),
        usage=usage,
    )


def tally_votes(
    votes: list[str | None], options: list[str], tie_break_seed: str
) -> tuple[str | None, bool, dict[str, int]]:
    """Aggregate independent votes into a group answer.

    The tie-break rule is fixed in advance (see ``docs/methodology.md``): among
    the options sharing the top vote count, one is chosen uniformly at random by
    an RNG seeded from ``tie_break_seed`` (the task id). This is deterministic
    and reproducible, and unbiased with respect to the correct answer -- unlike
    "first option in the list", which would interact with option ordering.

    Votes that failed to parse (``None``) are recorded but excluded from the
    tally, so a refusal never counts toward any option.

    Args:
        votes: One vote per agent; ``None`` for an unparseable response.
        options: The task's answer options.
        tie_break_seed: Stable string used to seed the tie-break RNG.

    Returns:
        ``(answer, was_tie, tally)``. ``answer`` is ``None`` only when no vote
        parsed at all. ``was_tie`` is True when two or more options shared the
        top count.
    """
    tally = {opt: 0 for opt in options}
    for vote in votes:
        if vote in tally:
            tally[vote] += 1
    top = max(tally.values())
    if top == 0:
        return None, False, tally
    leaders = [opt for opt in options if tally[opt] == top]
    was_tie = len(leaders) > 1
    if not was_tie:
        return leaders[0], False, tally
    rng = random.Random(tie_break_seed)
    return rng.choice(leaders), True, tally


async def run_no_communication(
    task: Task,
    clients: LLMClient | list[LLMClient],
    config: RolloutConfig | None = None,
) -> Episode:
    """Run the no-communication condition: agents answer independently, then vote.

    Each agent sees only its own private context and never sees any other
    agent's context or output -- there is no shared message history at all. The
    group answer is the majority vote, with ties resolved by :func:`tally_votes`.

    This isolates the effect of *distributing* information from the effect of
    *communicating* about it: compared against the communication condition, the
    only thing that changes is whether agents can talk.

    The per-agent calls use ``final_temperature`` (the same setting every other
    condition uses for an answer-producing turn), and each agent's vote plus the
    tally, tie flag, and parse-failure count are recorded in ``metadata``.
    """
    cfg = config or RolloutConfig()
    n_agents = task.n_agents
    agent_clients = _clients_for(clients, n_agents)
    usage_acc = _UsageAccumulator()

    messages: list[TranscriptMessage] = []
    votes: list[str | None] = []

    for agent_id in range(n_agents):
        prompt = NO_COMM_PROMPT.format(
            context=_with_task(task.agent_contexts[agent_id], task, cfg.show_task),
            options=", ".join(task.options),
        )
        convo = [
            Message("system", SOLO_SYSTEM_PROMPT.format(agent_id=agent_id, n_agents=n_agents)),
            Message("user", prompt),
        ]
        completion = usage_acc.add(
            await agent_clients[agent_id].complete(
                convo, max_tokens=cfg.max_tokens, temperature=cfg.final_temperature
            )
        )
        vote = parse_answer(completion.text, task.options)
        votes.append(vote)
        messages.append(TranscriptMessage(1, agent_id, "vote", completion.text.strip()))

    team_answer, was_tie, tally = tally_votes(votes, task.options, task.task_id)
    n_parse_failures = sum(1 for v in votes if v is None)

    return Episode(
        task_id=task.task_id,
        family=str(task.metadata.get("family", "unknown")),
        question=task.question,
        options=task.options,
        gold_answer=task.answer,
        team_answer=team_answer,
        correct=(team_answer == task.answer),
        messages=messages,
        required_private_facts=task.required_private_facts,
        n_agents=n_agents,
        config=asdict(cfg),
        usage=usage_acc.as_dict(),
        metadata={
            "condition": "no_communication",
            "votes": votes,
            "vote_tally": tally,
            "was_tie": was_tie,
            "n_parse_failures": n_parse_failures,
        },
    )


async def run_single_agent(
    task: Task,
    client: LLMClient,
    config: RolloutConfig | None = None,
) -> Episode:
    """Run the single-agent, full-information upper-bound condition.

    One agent is shown the union of every fact (``task.full_context()``) and
    answers directly, with no discussion. Used as the accuracy ceiling in
    evaluation.
    """
    cfg = config or RolloutConfig()
    usage_acc = _UsageAccumulator()

    prompt = AGGREGATOR_PROMPT.format(
        context=_with_task(
            "All available information:\n" + task.full_context(), task, cfg.show_task
        ),
        history="(you have all information; no discussion needed)",
        options=", ".join(task.options),
    )
    convo = [
        Message("system", "You are an expert decision-maker. Reason carefully, then answer."),
        Message("user", prompt),
    ]
    completion = usage_acc.add(
        await client.complete(
            convo, max_tokens=cfg.max_tokens, temperature=cfg.final_temperature
        )
    )
    team_answer = parse_answer(completion.text, task.options)
    messages = [TranscriptMessage(1, 0, "answer", completion.text.strip())]
    usage = usage_acc.as_dict()
    return Episode(
        task_id=task.task_id,
        family=str(task.metadata.get("family", "unknown")),
        question=task.question,
        options=task.options,
        gold_answer=task.answer,
        team_answer=team_answer,
        correct=(team_answer == task.answer),
        messages=messages,
        required_private_facts=task.required_private_facts,
        n_agents=1,
        config=asdict(cfg),
        usage=usage,
        metadata={"condition": "single_agent_full_context"},
    )


class TranscriptWriter:
    """Append-only JSONL writer for episodes (one JSON object per line)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8")

    def write(self, episode: Episode) -> None:
        """Write one episode as a JSONL line and flush."""
        self._fh.write(episode.to_jsonl() + "\n")
        self._fh.flush()

    def close(self) -> None:
        """Close the underlying file handle."""
        self._fh.close()

    def __enter__(self) -> TranscriptWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def load_transcript(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSONL transcript file into a list of episode dicts."""
    episodes: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                episodes.append(json.loads(line))
    return episodes
