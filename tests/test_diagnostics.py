"""Tests for the reward-hacking diagnostics."""

from __future__ import annotations

from grapevine.diagnostics.hacking import (
    _two_proportion_z,
    answer_only_no_discussion,
    diagnose,
    report_markdown,
    run_policy,
)
from grapevine.envs.hidden_profile import HiddenProfileConfig, HiddenProfileEnv
from grapevine.envs.split_evidence import SplitEvidenceConfig, SplitEvidenceEnv


def test_two_proportion_z_identical_is_indistinguishable() -> None:
    z, p = _two_proportion_z(10, 100, 10, 100)
    assert z == 0.0
    assert p == 1.0


def test_two_proportion_z_detects_difference() -> None:
    z, p = _two_proportion_z(5, 100, 95, 100)
    assert p < 0.001


def test_no_discussion_policy_lands_on_decoy_for_hidden_profile() -> None:
    """The no-discussion majority-vote policy should pick the decoy, not gold."""
    env = HiddenProfileEnv(HiddenProfileConfig())
    import random

    rng = random.Random(0)
    n_decoy = 0
    for seed in range(50):
        task = env.generate(seed)
        choice = answer_only_no_discussion(task, rng)
        if choice == task.metadata["decoy_option"]:
            n_decoy += 1
    # Every agent sees the decoy-favouring shared facts, so with no pooling the
    # team overwhelmingly votes for the decoy (and therefore fails the reward).
    assert n_decoy >= 45


def test_hidden_profile_reward_not_hackable() -> None:
    env = HiddenProfileEnv(HiddenProfileConfig())
    report = diagnose(env, n_tasks=200, seed=0)
    assert report.reference.accuracy == 1.0
    assert not report.any_hackable, "no degenerate policy should match genuine pooling"
    # The shared-only policy in particular should be far below the reference.
    shared = next(c for c in report.comparisons if c.name == "answer_only_no_discussion")
    assert shared.accuracy < 0.5
    md = report_markdown(report)
    assert "PASS" in md


def test_split_evidence_reward_not_hackable() -> None:
    env = SplitEvidenceEnv(SplitEvidenceConfig())
    report = diagnose(env, n_tasks=200, seed=0)
    assert not report.any_hackable


def test_run_policy_counts_correctly() -> None:
    env = HiddenProfileEnv(HiddenProfileConfig())
    # A policy that always returns the gold answer scores 100%.
    result = run_policy(env, lambda t, rng: t.answer, 20, seed=1)
    assert result.n_correct == 20
    assert result.accuracy == 1.0
