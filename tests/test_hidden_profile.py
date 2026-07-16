"""Tests for the hidden-profile generator.

These cover the three defining properties of a hidden profile (shared facts bias
toward a wrong option, the correct option wins only with full pooling, and every
required private fact is necessary) plus determinism and fact splitting.
"""

from __future__ import annotations

import pytest

from grapevine.envs.hidden_profile import HiddenProfileConfig, HiddenProfileEnv

CONFIGS = [
    HiddenProfileConfig(),
    HiddenProfileConfig(n_agents=4, n_shared_facts=12, n_private_facts_per_agent=3, n_options=5),
    HiddenProfileConfig(n_agents=2, n_shared_facts=8, n_private_facts_per_agent=1, n_options=2),
    HiddenProfileConfig(
        n_agents=5, n_shared_facts=20, n_private_facts_per_agent=4, n_distractors=10, n_options=6
    ),
]


@pytest.mark.parametrize("cfg", CONFIGS)
def test_shared_facts_favor_wrong_option(cfg: HiddenProfileConfig) -> None:
    """Among shared facts alone, the decoy (a wrong option) must strictly lead."""
    env = HiddenProfileEnv(cfg)
    for seed in range(25):
        task = env.generate(seed)
        ssup = task.metadata["shared_support"]
        correct = task.metadata["correct_option"]
        decoy = task.metadata["decoy_option"]
        assert decoy != correct
        best = max(ssup.values())
        assert ssup[decoy] == best
        assert list(ssup.values()).count(best) == 1, "shared leader must be unique"
        assert ssup[correct] < ssup[decoy], "correct option must trail on shared info"


@pytest.mark.parametrize("cfg", CONFIGS)
def test_correct_option_wins_with_full_pooling(cfg: HiddenProfileConfig) -> None:
    """With every fact pooled, the correct option must be the unique winner."""
    env = HiddenProfileEnv(cfg)
    for seed in range(25):
        task = env.generate(seed)
        sup = task.metadata["support"]
        correct = task.metadata["correct_option"]
        assert task.answer == correct
        best = max(sup.values())
        assert sup[correct] == best
        assert list(sup.values()).count(best) == 1, "overall winner must be unique"


@pytest.mark.parametrize("cfg", CONFIGS)
def test_every_required_private_fact_is_necessary(cfg: HiddenProfileConfig) -> None:
    """Dropping any single required private fact must undo the correct option's lead."""
    env = HiddenProfileEnv(cfg)
    n_required = cfg.n_agents * cfg.n_private_facts_per_agent
    for seed in range(25):
        task = env.generate(seed)
        assert len(task.required_private_facts) == n_required
        sup = task.metadata["support"]
        correct = task.metadata["correct_option"]
        others_max = max(v for k, v in sup.items() if k != correct)
        # Each required fact contributes +1 to the correct option; removing one
        # must make the correct option no longer a strict winner.
        assert sup[correct] - 1 <= others_max


@pytest.mark.parametrize("cfg", CONFIGS)
def test_facts_are_actually_split(cfg: HiddenProfileConfig) -> None:
    """Required facts live in private contexts, not in the shared block."""
    env = HiddenProfileEnv(cfg)
    for seed in range(10):
        task = env.generate(seed)
        shared = set(task.metadata["shared_facts"])
        for fact in task.required_private_facts:
            assert fact not in shared, "a required fact leaked into shared info"
        # Each required fact appears in exactly one agent's context.
        for fact in task.required_private_facts:
            holders = [i for i, ctx in enumerate(task.agent_contexts) if fact in ctx]
            assert len(holders) == 1


@pytest.mark.parametrize("cfg", CONFIGS)
def test_fact_strings_are_unique(cfg: HiddenProfileConfig) -> None:
    """No two facts (shared or private) share the same string."""
    env = HiddenProfileEnv(cfg)
    for seed in range(10):
        task = env.generate(seed)
        all_facts = list(task.metadata["shared_facts"])
        for facts in task.metadata["private_facts"]:
            all_facts.extend(facts)
        assert len(all_facts) == len(set(all_facts))


def test_determinism_under_seed() -> None:
    """The same seed yields byte-identical tasks; different seeds differ."""
    env = HiddenProfileEnv()
    assert env.generate(11).to_json() == env.generate(11).to_json()
    assert env.generate(11).to_json() != env.generate(12).to_json()


def test_batch_uses_consecutive_seeds() -> None:
    """generate_batch matches per-seed generate calls."""
    env = HiddenProfileEnv()
    batch = env.generate_batch(4, seed=100)
    assert [t.task_id for t in batch] == [f"hidden_profile-{s}" for s in range(100, 104)]


def test_invalid_config_rejected() -> None:
    """n_shared_facts too small to seat the decoy lead is rejected."""
    with pytest.raises(ValueError):
        HiddenProfileConfig(n_agents=4, n_shared_facts=2, n_private_facts_per_agent=3)
    with pytest.raises(ValueError):
        HiddenProfileConfig(n_agents=1)
