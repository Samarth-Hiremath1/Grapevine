"""Tests for experiment metrics: decoy rate, tie accounting, bootstrap CIs."""

from __future__ import annotations

from grapevine.experiments.analysis import (
    bootstrap_ci,
    paired_difference_ci,
    summarize_condition,
)
from grapevine.rollout.engine import Episode, TranscriptMessage


def _ep(
    answer: str | None,
    gold: str = "Avery",
    decoy: str = "Blair",
    was_tie: bool | None = None,
    discussion: str | None = None,
) -> Episode:
    meta: dict[str, object] = {"decoy_option": decoy}
    if was_tie is not None:
        meta["was_tie"] = was_tie
    messages = []
    if discussion is not None:
        messages.append(TranscriptMessage(1, 0, "discussion", discussion))
    return Episode(
        task_id="t",
        family="hidden_profile",
        question="q",
        options=["Avery", "Blair", "Cameron", "Devon"],
        gold_answer=gold,
        team_answer=answer,
        correct=(answer == gold),
        messages=messages,
        required_private_facts=["Avery led a cross-functional team of eight."],
        n_agents=3,
        config={},
        usage={"cost_usd": 0.01, "prompt_tokens": 100, "completion_tokens": 50, "n_calls": 4},
        metadata=meta,
    )


def test_decoy_rate_separates_decoy_from_other_wrong() -> None:
    eps = [_ep("Avery"), _ep("Blair"), _ep("Blair"), _ep("Cameron")]
    s = summarize_condition("no_communication", eps)
    assert s.n == 4
    assert s.accuracy == 0.25
    assert s.decoy_rate == 0.5  # two landed on the decoy
    assert s.other_wrong_rate == 0.25  # one wrong but not the decoy
    assert s.parse_failures == 0


def test_parse_failures_counted_separately_not_as_decoy() -> None:
    eps = [_ep(None), _ep(None), _ep("Avery"), _ep("Blair")]
    s = summarize_condition("communication", eps)
    assert s.parse_failures == 2
    assert s.parse_failure_rate == 0.5
    assert s.decoy_rate == 0.25
    assert s.accuracy == 0.25
    # A None answer must never be counted as landing on the decoy.
    assert s.other_wrong_rate == 0.0


def test_tie_metrics_reported_and_floor_is_lower() -> None:
    """Accuracy with ties scored incorrect must be <= headline accuracy."""
    eps = [
        _ep("Avery", was_tie=True),   # correct, but only via the tie-break
        _ep("Avery", was_tie=False),  # correct outright
        _ep("Blair", was_tie=True),
        _ep("Blair", was_tie=False),
    ]
    s = summarize_condition("no_communication", eps)
    assert s.tie_rate == 0.5
    assert s.accuracy == 0.5
    # Only the non-tie correct episode survives the stricter accounting.
    assert s.accuracy_ties_incorrect == 0.25
    assert s.accuracy_ties_incorrect <= s.accuracy


def test_surfacing_only_when_a_channel_exists() -> None:
    """No discussion messages -> surfacing is None, not a misleading 0.0."""
    no_channel = summarize_condition("no_communication", [_ep("Avery"), _ep("Blair")])
    assert no_channel.surfacing_rate is None

    fact = "Avery led a cross-functional team of eight."
    with_channel = summarize_condition(
        "communication", [_ep("Avery", discussion=fact), _ep("Blair", discussion="nothing")]
    )
    assert with_channel.surfacing_rate == 0.5


def test_bootstrap_ci_is_deterministic_and_brackets_the_mean() -> None:
    values = [1.0] * 30 + [0.0] * 70
    lo, hi = bootstrap_ci(values, n_resamples=2000, seed=0)
    again = bootstrap_ci(values, n_resamples=2000, seed=0)
    assert (lo, hi) == again
    assert lo < 0.30 < hi
    assert 0.0 <= lo <= hi <= 1.0


def test_bootstrap_ci_degenerate_input() -> None:
    lo, hi = bootstrap_ci([1.0] * 20, n_resamples=500, seed=0)
    assert lo == hi == 1.0


def test_paired_difference() -> None:
    a = [1.0, 1.0, 0.0, 0.0]
    b = [0.0, 0.0, 0.0, 0.0]
    mean, (lo, hi) = paired_difference_ci(a, b, n_resamples=2000, seed=0)
    assert mean == 0.5
    assert lo <= 0.5 <= hi
