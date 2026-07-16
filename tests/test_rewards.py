"""Tests for verifiable reward and surfacing-rate signals."""

from __future__ import annotations

from grapevine.rewards.reward import (
    answer_reward,
    compute_surfacing,
    exact_match_reward,
    fact_surfaced,
)
from grapevine.rollout.engine import Episode, TranscriptMessage


def _episode(required: list[str], discussion: list[tuple[int, int, str]], correct: bool) -> Episode:
    messages = [TranscriptMessage(r, a, "discussion", text) for r, a, text in discussion]
    return Episode(
        task_id="t",
        family="hidden_profile",
        question="q",
        options=["A", "B"],
        gold_answer="A",
        team_answer="A" if correct else "B",
        correct=correct,
        messages=messages,
        required_private_facts=required,
        n_agents=2,
        config={},
        usage={},
    )


def test_exact_match_reward() -> None:
    assert exact_match_reward(_episode([], [], True)) == 1.0
    assert exact_match_reward(_episode([], [], False)) == 0.0
    assert answer_reward("A", "A") == 1.0
    assert answer_reward("B", "A") == 0.0
    assert answer_reward(None, "A") == 0.0


def test_fact_surfaced_verbatim_and_fuzzy() -> None:
    fact = "Avery rewrote a flaky test suite to full reliability."
    assert fact_surfaced(fact, "I know that Avery rewrote a flaky test suite to full reliability.")
    # Paraphrase keeping most content words still counts.
    assert fact_surfaced(fact, "Avery rewrote the flaky test suite making it fully reliable")
    # Unrelated message does not.
    assert not fact_surfaced(fact, "The meeting room was on the third floor.")


def test_surfacing_rate_and_rounds() -> None:
    required = [
        "Avery led a cross-functional team of eight.",
        "Avery mentored three junior engineers to promotion.",
    ]
    # First fact surfaces in round 1, second in round 2.
    discussion = [
        (1, 0, "Avery led a cross-functional team of eight."),
        (1, 1, "Nothing much to add yet."),
        (2, 0, "Also, Avery mentored three junior engineers to promotion."),
    ]
    report = compute_surfacing(_episode(required, discussion, True))
    assert report.n_required == 2
    assert report.n_surfaced == 2
    assert report.surfacing_rate == 1.0
    assert report.first_round[required[0]] == 1
    assert report.first_round[required[1]] == 2
    assert report.rounds_to_surface == 1.5


def test_surfacing_rate_partial() -> None:
    required = [
        "Avery led a cross-functional team of eight.",
        "Avery mentored three junior engineers to promotion.",
    ]
    discussion = [(1, 0, "Avery led a cross-functional team of eight.")]
    report = compute_surfacing(_episode(required, discussion, False))
    assert report.n_surfaced == 1
    assert report.surfacing_rate == 0.5
    assert report.rounds_to_surface == 1.0


def test_surfacing_no_required_facts() -> None:
    report = compute_surfacing(_episode([], [], True))
    assert report.surfacing_rate == 0.0
    assert report.rounds_to_surface is None
