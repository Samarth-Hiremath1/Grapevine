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


def test_leaks_the_gold_answer_into_one_agents_view() -> None:
    """The defect that keeps this family unregistered, asserted rather than described.

    The final hop names the terminal station, which is the gold answer, so
    whichever agent holds that hop can answer with no pooling at all. This is
    the check `docs/decisions.md` ran by hand over 100 tasks.
    """
    env = SplitEvidenceEnv()
    leaked = sum(
        any(task.answer in context for context in task.agent_contexts)
        for task in env.generate_batch(100, 0)
    )
    assert leaked == 100, "if this family stops leaking, re-register it and update the reason"


def test_unregistered_so_nothing_can_run_it() -> None:
    """The family is importable but unreachable by name.

    Step 4 of the v0.2 plan either fixes the leak or deletes the family. Until
    then nothing that resolves a family by name may hand one out, or a condition
    built on it would silently not measure pooling.
    """
    from grapevine.envs import REGISTRY, UNREGISTERED, unavailable_reason

    assert SplitEvidenceEnv.family not in REGISTRY
    assert SplitEvidenceEnv.family in UNREGISTERED
    assert "leaks the gold answer" in (unavailable_reason(SplitEvidenceEnv.family) or "")
    assert unavailable_reason("hidden_profile") is None


def test_cli_refuses_it_with_the_reason() -> None:
    """``grapevine gen split_evidence`` explains itself instead of failing blankly."""
    from grapevine.cli import main

    with pytest.raises(SystemExit) as excinfo:
        main(["gen", "split_evidence", "--n", "1"])
    assert "leaks the gold answer" in str(excinfo.value)


def test_experiment_runner_refuses_it_with_the_reason(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The experiment runner refuses it at config-load time, not mid-run."""
    import yaml

    from grapevine.experiments.run import load_config

    config = tmp_path / "bad.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "model": {"name": "gpt-5.6-luna"},
                "env": {"family": "split_evidence"},
                "rollout": {},
                "run": {"n_episodes": 1, "seed_start": 0},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="leaks the gold answer"):
        load_config(config)
