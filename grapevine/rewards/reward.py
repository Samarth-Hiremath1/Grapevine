"""Verifiable reward and auxiliary transcript signals.

The primary reward is intentionally simple and hard to game by construction: a
team earns ``1.0`` iff its selected option exactly matches the task's gold
answer, and ``0.0`` otherwise. Because the environments guarantee the answer is
only derivable once every required private fact is surfaced, this exact-match
reward is a genuine verifiable signal for whether the team pooled information.

Alongside the reward we compute *diagnostic* signals from the transcript -- the
private-fact surfacing rate and rounds-to-surface -- which are not part of the
reward but reveal whether reward was earned through real information pooling.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from grapevine.rollout.engine import Episode, TranscriptMessage

_WORD_RE = re.compile(r"[a-z0-9]+")

# Function words carry little identifying signal for whether a specific fact was
# shared, so they are excluded from the content-overlap match.
_STOPWORDS = frozenset(
    {
        "a", "an", "the", "to", "of", "and", "or", "in", "on", "at", "for", "with",
        "by", "is", "was", "were", "be", "been", "it", "its", "as", "that", "this",
        "has", "had", "have", "who", "whom", "from", "into", "their", "they", "them",
    }
)

DEFAULT_SURFACING_THRESHOLD = 0.7


def exact_match_reward(episode: Episode) -> float:
    """Return ``1.0`` if the team answer exactly matches the gold answer.

    Matching is delegated to the episode's ``correct`` flag, which the rollout
    engine sets via exact option comparison.
    """
    return 1.0 if episode.correct else 0.0


def answer_reward(team_answer: str | None, gold_answer: str) -> float:
    """Exact-match reward from a raw ``(team_answer, gold_answer)`` pair."""
    return 1.0 if team_answer is not None and team_answer == gold_answer else 0.0


def _normalize(text: str) -> str:
    """Lowercase and collapse to a space-separated token string."""
    return " ".join(_WORD_RE.findall(text.lower()))


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _content_tokens(text: str) -> list[str]:
    return [t for t in _WORD_RE.findall(text.lower()) if t not in _STOPWORDS]


def fact_surfaced(
    fact: str, message: str, threshold: float = DEFAULT_SURFACING_THRESHOLD
) -> bool:
    """Return whether ``fact`` has been surfaced in ``message``.

    A fact counts as surfaced if any of the following holds:

    * its normalized form is a substring of the normalized message (verbatim or
      near-verbatim sharing);
    * a fraction ``>= threshold`` of the fact's *content* tokens (stopwords
      removed) appear in the message (reordering / passive voice / light
      paraphrase);
    * the overall character-level similarity of the two normalized strings is
      ``>= threshold`` (catches minor word-form changes).

    The metric targets the verbatim-to-near-verbatim fact sharing that the agent
    system prompt explicitly encourages; it is a diagnostic proxy, not a full
    entailment check.

    Args:
        fact: The required private fact string.
        message: A single conversation message.
        threshold: Similarity threshold in ``[0, 1]``.
    """
    norm_fact = _normalize(fact)
    norm_msg = _normalize(message)
    if not norm_fact:
        return False
    if norm_fact in norm_msg:
        return True
    fact_content = _content_tokens(fact)
    if fact_content:
        msg_content_set = set(_content_tokens(message))
        contained = sum(1 for t in fact_content if t in msg_content_set)
        if contained / len(fact_content) >= threshold:
            return True
    ratio = difflib.SequenceMatcher(None, norm_fact, norm_msg).ratio()
    return ratio >= threshold


@dataclass
class SurfacingReport:
    """Per-episode summary of which required facts were surfaced, and when.

    Attributes:
        n_required: Number of required private facts.
        n_surfaced: How many were surfaced during discussion.
        surfacing_rate: ``n_surfaced / n_required`` (0 if there are no required
            facts).
        first_round: Map from each required fact to the 1-based round in which it
            was first surfaced, or ``None`` if never surfaced.
        rounds_to_surface: Mean first-surface round over the facts that surfaced
            (``None`` if none surfaced).
    """

    n_required: int
    n_surfaced: int
    surfacing_rate: float
    first_round: dict[str, int | None] = field(default_factory=dict)
    rounds_to_surface: float | None = None


def _discussion_messages(messages: list[TranscriptMessage]) -> list[TranscriptMessage]:
    """Messages that count for surfacing: discussion and vote turns, not the
    aggregator's final answer (which merely restates a conclusion)."""
    return [m for m in messages if m.role in ("discussion", "vote")]


def compute_surfacing(episode: Episode, threshold: float = DEFAULT_SURFACING_THRESHOLD) -> SurfacingReport:
    """Compute the surfacing report for one episode.

    Scans discussion messages in round order and records, for each required
    private fact, the first round in which it was surfaced by any agent.
    """
    required = episode.required_private_facts
    n_required = len(required)
    first_round: dict[str, int | None] = {fact: None for fact in required}

    for message in sorted(_discussion_messages(episode.messages), key=lambda m: m.round_no):
        for fact in required:
            if first_round[fact] is None and fact_surfaced(fact, message.content, threshold):
                first_round[fact] = message.round_no

    surfaced_rounds = [r for r in first_round.values() if r is not None]
    n_surfaced = len(surfaced_rounds)
    surfacing_rate = n_surfaced / n_required if n_required else 0.0
    mean_round = sum(surfaced_rounds) / n_surfaced if n_surfaced else None

    return SurfacingReport(
        n_required=n_required,
        n_surfaced=n_surfaced,
        surfacing_rate=surfacing_rate,
        first_round=first_round,
        rounds_to_surface=mean_round,
    )


def auxiliary_signals(episode: Episode, threshold: float = DEFAULT_SURFACING_THRESHOLD) -> dict[str, float]:
    """Return a flat dict of auxiliary signals for logging/aggregation."""
    report = compute_surfacing(episode, threshold)
    return {
        "reward": exact_match_reward(episode),
        "surfacing_rate": report.surfacing_rate,
        "n_surfaced": float(report.n_surfaced),
        "n_required": float(report.n_required),
        "rounds_to_surface": (
            report.rounds_to_surface if report.rounds_to_surface is not None else float("nan")
        ),
    }
