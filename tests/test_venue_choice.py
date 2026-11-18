"""venue_choice is the supported environment: it passes its audit and runs end to end."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from grapevine import Status, VenueChoice, audit, get_environment
from grapevine.envs import DEFAULT_ENVIRONMENT, ENVIRONMENTS
from grapevine.rl import RewardConfig, audit_gate

SEED_RANGES = [0, 5000, 10000, 10500]


def _example_class() -> type:
    spec = importlib.util.spec_from_file_location(
        "venue_example", Path("examples/02_write_an_environment.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["venue_example"] = module
    spec.loader.exec_module(module)
    return module.VenueChoice  # type: ignore[no-any-return]


def test_registered_and_the_default() -> None:
    assert ENVIRONMENTS["venue_choice"] is VenueChoice
    assert DEFAULT_ENVIRONMENT == "venue_choice"


def test_the_package_and_the_example_are_the_same_environment() -> None:
    """The example teaches it; the package supports it. They must not drift."""
    example = _example_class()()
    package = VenueChoice()
    for seed in [0, 1, 2, 9000, 10000, 10001, 12345]:
        assert example.generate(seed) == package.generate(seed)
        task = package.generate(seed)
        assert {k: v.prompts for k, v in example.conditions(task).items()} == {
            k: v.prompts for k, v in package.conditions(task).items()
        }


@pytest.mark.parametrize("seed", SEED_RANGES)
def test_passes_its_audit_on_disjoint_seed_ranges(seed: int) -> None:
    card = audit(get_environment("venue_choice"), n_tasks=200, seed=seed)
    assert card.passed, card.flagged_checks
    assert card.get("solo_solvability").status is Status.MEASURED
    assert card.get("reward_hacking").status is Status.MEASURED


def test_the_rl_gate_admits_it_without_an_override() -> None:
    result = audit_gate(VenueChoice(), RewardConfig(), n_tasks=200)
    assert result.passed and not result.allowed_flagged


def test_the_committed_card_matches_a_fresh_audit() -> None:
    path = Path("environments/venue_choice/validity_card.json")
    committed = json.loads(path.read_text(encoding="utf-8"))
    fresh = audit(VenueChoice(), n_tasks=committed["n_tasks"], seed=committed["seed"])
    assert fresh.to_dict() == committed
    assert committed["verdict"] == "measured"
