"""Tests for the split-evidence multi-hop generator."""

from __future__ import annotations

import re

import pytest

from grapevine.envs.split_evidence import SplitEvidenceConfig, SplitEvidenceEnv

_HOP_RE = re.compile(r"From (Station \w{3}), the active route continues to (Station \w{3})\.")

CONFIGS = [
    SplitEvidenceConfig(),
    SplitEvidenceConfig(n_agents=4, n_shared_facts=3, n_private_facts_per_agent=2, n_distractors=5),
    SplitEvidenceConfig(n_agents=2, n_shared_facts=0, n_private_facts_per_agent=1, n_distractors=0),
    SplitEvidenceConfig(
        n_agents=6, n_shared_facts=10, n_private_facts_per_agent=3, n_distractors=8, n_options=6
    ),
]


@pytest.mark.parametrize("cfg", CONFIGS)
def test_answer_is_unique_terminal_of_chain(cfg: SplitEvidenceConfig) -> None:
    """Following the true hops from the start yields exactly the stored answer."""
    env = SplitEvidenceEnv(cfg)
    for seed in range(25):
        task = env.generate(seed)
        edges: dict[str, str] = {}
        for fact in task.required_private_facts:
            match = _HOP_RE.match(fact)
            assert match is not None
            edges[match.group(1)] = match.group(2)
        cur = task.metadata["start"]
        steps = 0
        while cur in edges and steps <= cfg.n_agents + 1:
            cur = edges[cur]
            steps += 1
        assert steps == cfg.n_agents, "must take exactly one hop per agent"
        assert cur == task.answer
        assert task.answer in task.options
        assert len(task.options) == cfg.n_options


@pytest.mark.parametrize("cfg", CONFIGS)
def test_each_agent_holds_exactly_one_hop(cfg: SplitEvidenceConfig) -> None:
    """Every agent context contains exactly one of the required hops."""
    env = SplitEvidenceEnv(cfg)
    for seed in range(20):
        task = env.generate(seed)
        assert len(task.required_private_facts) == cfg.n_agents
        required = set(task.required_private_facts)
        for facts in task.metadata["private_facts"]:
            assert len(facts) == cfg.n_private_facts_per_agent
            assert sum(1 for f in facts if f in required) == 1


@pytest.mark.parametrize("cfg", CONFIGS)
def test_no_single_agent_can_answer(cfg: SplitEvidenceConfig) -> None:
    """No individual agent context contains the whole chain."""
    env = SplitEvidenceEnv(cfg)
    for seed in range(20):
        task = env.generate(seed)
        for ctx in task.agent_contexts:
            present = sum(1 for f in task.required_private_facts if f in ctx)
            assert present < cfg.n_agents, "a single agent should not hold all hops"


@pytest.mark.parametrize("cfg", CONFIGS)
def test_fact_strings_are_unique(cfg: SplitEvidenceConfig) -> None:
    env = SplitEvidenceEnv(cfg)
    for seed in range(10):
        task = env.generate(seed)
        all_facts = list(task.metadata["shared_facts"])
        for facts in task.metadata["private_facts"]:
            all_facts.extend(facts)
        assert len(all_facts) == len(set(all_facts))


def test_determinism_under_seed() -> None:
    env = SplitEvidenceEnv()
    assert env.generate(5).to_json() == env.generate(5).to_json()
    assert env.generate(5).to_json() != env.generate(6).to_json()


def test_invalid_config_rejected() -> None:
    with pytest.raises(ValueError):
        SplitEvidenceConfig(n_agents=1)
    with pytest.raises(ValueError):
        SplitEvidenceConfig(n_options=1)
