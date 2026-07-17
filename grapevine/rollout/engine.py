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
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from grapevine.envs.base import Task
from grapevine.rollout.client import LLMClient, Message

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

VOTE_PROMPT = (
    "{context}\n\n"
    "Full team discussion:\n{history}\n\n"
    "Cast your individual vote for the single best answer. "
    "Choose exactly one of these options: {options}.\n"
    'Respond with only a JSON object: {{"answer": "<one option exactly as written>"}}.'
)


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
    """

    n_rounds: int = 2
    aggregation: str = "aggregator"
    aggregator_index: int = 0
    max_tokens: int = 400
    temperature: float = 0.7
    final_temperature: float = 0.0

    def __post_init__(self) -> None:
        if self.n_rounds < 1:
            raise ValueError("n_rounds must be >= 1")
        if self.aggregation not in ("aggregator", "vote"):
            raise ValueError("aggregation must be 'aggregator' or 'vote'")


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

    # Snapshot usage so we can attribute cost to just this episode.
    before = [
        (c.total_prompt_tokens, c.total_completion_tokens, c.total_cost_usd, c.n_calls)
        for c in agent_clients
    ]

    messages: list[TranscriptMessage] = []

    # --- Discussion rounds --------------------------------------------------
    for round_no in range(1, cfg.n_rounds + 1):
        for agent_id in range(n_agents):
            prompt = AGENT_TURN_PROMPT.format(
                context=task.agent_contexts[agent_id],
                history=_render_history(messages),
                round_no=round_no,
                n_rounds=cfg.n_rounds,
            )
            convo = [
                Message("system", TEAM_SYSTEM_PROMPT.format(agent_id=agent_id, n_agents=n_agents)),
                Message("user", prompt),
            ]
            completion = await agent_clients[agent_id].complete(
                convo, max_tokens=cfg.max_tokens, temperature=cfg.temperature
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
                context=task.agent_contexts[agent_id],
                history=_render_history(messages),
                options=", ".join(task.options),
            )
            convo = [
                Message("system", TEAM_SYSTEM_PROMPT.format(agent_id=agent_id, n_agents=n_agents)),
                Message("user", prompt),
            ]
            completion = await agent_clients[agent_id].complete(
                convo, max_tokens=cfg.max_tokens, temperature=cfg.final_temperature
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
            context=task.agent_contexts[agg],
            history=_render_history(messages),
            options=", ".join(task.options),
        )
        convo = [
            Message("system", TEAM_SYSTEM_PROMPT.format(agent_id=agg, n_agents=n_agents)),
            Message("user", prompt),
        ]
        completion = await agent_clients[agg].complete(
            convo, max_tokens=cfg.max_tokens, temperature=cfg.final_temperature
        )
        team_answer = parse_answer(completion.text, task.options)
        messages.append(TranscriptMessage(cfg.n_rounds + 1, agg, "answer", completion.text.strip()))

    # --- Per-episode usage --------------------------------------------------
    usage = {"prompt_tokens": 0.0, "completion_tokens": 0.0, "cost_usd": 0.0, "n_calls": 0.0}
    seen: set[int] = set()
    for c, (pt, ct, cost, calls) in zip(agent_clients, before, strict=True):
        if id(c) in seen:  # avoid double counting a shared client
            continue
        seen.add(id(c))
        usage["prompt_tokens"] += c.total_prompt_tokens - pt
        usage["completion_tokens"] += c.total_completion_tokens - ct
        usage["cost_usd"] += c.total_cost_usd - cost
        usage["n_calls"] += c.n_calls - calls

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
    before = (client.total_prompt_tokens, client.total_completion_tokens, client.total_cost_usd, client.n_calls)

    prompt = AGGREGATOR_PROMPT.format(
        context="All available information:\n" + task.full_context(),
        history="(you have all information; no discussion needed)",
        options=", ".join(task.options),
    )
    convo = [
        Message("system", "You are an expert decision-maker. Reason carefully, then answer."),
        Message("user", prompt),
    ]
    completion = await client.complete(
        convo, max_tokens=cfg.max_tokens, temperature=cfg.final_temperature
    )
    team_answer = parse_answer(completion.text, task.options)
    messages = [TranscriptMessage(1, 0, "answer", completion.text.strip())]
    usage = {
        "prompt_tokens": float(client.total_prompt_tokens - before[0]),
        "completion_tokens": float(client.total_completion_tokens - before[1]),
        "cost_usd": client.total_cost_usd - before[2],
        "n_calls": float(client.n_calls - before[3]),
    }
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
