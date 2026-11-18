"""The environment protocol refuses malformed tasks at construction.

Every validation here exists so a problem surfaces where it is cheap -- when the
task is built -- rather than as a confusing audit result or, worse, a published
number.
"""

from __future__ import annotations

import pytest

from grapevine.protocol import (
    AgentView,
    DistributedTask,
    Environment,
    InfoUnit,
    Objective,
    SeedSplit,
    binomial_tail_p,
    exact_match,
    support_total,
)

OPTIONS = ("Alpha", "Bravo", "Delta", "Gamma")


def _unit(uid: str, supports: str | None = None, weight: float = 1.0) -> InfoUnit:
    return InfoUnit(uid, f"Sentence for {uid}.", supports, weight)


def _task(**overrides: object) -> DistributedTask:
    shared = (_unit("s0", "Bravo"),)
    kwargs: dict[str, object] = {
        "task_id": "t-0",
        "objective": Objective(question="Who?", scoring_rule="Most support wins."),
        "answer_space": OPTIONS,
        "gold_answer": "Alpha",
        "views": (
            AgentView(0, shared, (_unit("a0", "Alpha"),)),
            AgentView(1, shared, (_unit("a1", "Alpha"),)),
        ),
        "required_units": ("a0", "a1"),
    }
    kwargs.update(overrides)
    return DistributedTask(**kwargs)  # type: ignore[arg-type]


class TestObjective:
    def test_requires_a_question(self) -> None:
        with pytest.raises(ValueError, match="question"):
            Objective(question="  ", scoring_rule="Most support wins.")

    def test_requires_a_scoring_rule(self) -> None:
        """An environment that cannot say how it scores cannot tell agents what to do."""
        with pytest.raises(ValueError, match="scoring_rule"):
            Objective(question="Who?", scoring_rule="")

    def test_statement_contains_both_halves(self) -> None:
        objective = Objective(question="Who wins?", scoring_rule="Most support.")
        assert "Who wins?" in objective.statement()
        assert "Most support." in objective.statement()


class TestTaskValidation:
    def test_gold_must_be_an_option(self) -> None:
        with pytest.raises(ValueError, match="not in answer_space"):
            _task(gold_answer="Nobody")

    def test_answer_space_needs_two_options(self) -> None:
        with pytest.raises(ValueError, match="at least 2 options"):
            _task(answer_space=("Alpha",), gold_answer="Alpha")

    def test_answer_space_rejects_duplicates(self) -> None:
        with pytest.raises(ValueError, match="duplicate options"):
            _task(answer_space=("Alpha", "Alpha", "Bravo"))

    def test_needs_at_least_two_views(self) -> None:
        """One view is a baseline condition, not a distributed task."""
        shared = (_unit("s0", "Bravo"),)
        with pytest.raises(ValueError, match="at least 2 agent views"):
            _task(views=(AgentView(0, shared, (_unit("a0", "Alpha"),)),), required_units=())

    def test_rejects_duplicate_unit_ids(self) -> None:
        shared = (_unit("s0", "Bravo"),)
        with pytest.raises(ValueError, match="duplicate unit ids"):
            _task(
                views=(
                    AgentView(0, shared, (_unit("dup", "Alpha"),)),
                    AgentView(1, shared, (_unit("dup", "Alpha"),)),
                ),
                required_units=(),
            )

    def test_rejects_shared_units_that_are_not_shared(self) -> None:
        """Units every agent holds go in `shared`; anything else is private."""
        with pytest.raises(ValueError, match="shared units differ"):
            _task(
                views=(
                    AgentView(0, (_unit("s0", "Bravo"),), (_unit("a0", "Alpha"),)),
                    AgentView(1, (_unit("s1", "Bravo"),), (_unit("a1", "Alpha"),)),
                ),
                required_units=(),
            )

    def test_rejects_unknown_required_units(self) -> None:
        with pytest.raises(ValueError, match="unknown units"):
            _task(required_units=("nope",))

    def test_rejects_support_for_a_non_option(self) -> None:
        shared = (_unit("s0", "Bravo"),)
        with pytest.raises(ValueError, match="which is not an option"):
            _task(
                views=(
                    AgentView(0, shared, (_unit("a0", "Zulu"),)),
                    AgentView(1, shared, (_unit("a1", "Alpha"),)),
                ),
                required_units=(),
            )

    def test_rejects_an_empty_unit(self) -> None:
        with pytest.raises(ValueError, match="empty text"):
            InfoUnit("u", "", None)


class TestTaskViews:
    def test_full_view_holds_every_unit_once(self) -> None:
        task = _task()
        full = task.full_view()
        assert {u.unit_id for u in full.units} == {"s0", "a0", "a1"}
        assert full.agent_id == -1

    def test_all_units_counts_shared_once(self) -> None:
        task = _task()
        assert [u.unit_id for u in task.all_units()] == ["s0", "a0", "a1"]

    def test_unit_lookup_raises_on_unknown(self) -> None:
        with pytest.raises(KeyError, match="no unit"):
            _task().unit("missing")

    def test_render_labels_shared_and_private_separately(self) -> None:
        """An agent that cannot tell which facts are already common cannot know
        what is worth saying."""
        rendered = _task().views[0].render()
        assert "Facts known to everyone:" in rendered
        assert "Facts only you know:" in rendered

    def test_chance_is_one_over_the_option_count(self) -> None:
        assert _task().chance == pytest.approx(0.25)


class TestExactMatch:
    def test_accepts_gold_and_tolerates_surrounding_whitespace(self) -> None:
        task = _task()
        for answer in ("Alpha", "  Alpha  ", "Alpha\n"):
            assert task.score(answer).correct, answer

    @pytest.mark.parametrize(
        "answer",
        [
            None,
            "",
            "   ",
            "Bravo",
            "A",
            "alpha",
            "ALPHA",
            "Alpha.",
            "I pick Alpha over Bravo",
            '{"answer": "Alpha"}',
            "Alpha and Bravo",
            "none of the above",
        ],
    )
    def test_rejects_everything_else(self, answer: str | None) -> None:
        """The v0 parser resolved several of these to an option, biasing toward
        whatever was listed first (docs/audit.md D1)."""
        assert not _task().score(answer).correct

    def test_reward_mirrors_correctness(self) -> None:
        task = _task()
        assert task.score("Alpha").reward == 1.0
        assert task.score("Bravo").reward == 0.0

    def test_result_carries_a_reason(self) -> None:
        assert "reason" in exact_match("Bravo", _task()).detail


class TestSupportTotal:
    def test_sums_weights_and_ignores_distractors(self) -> None:
        units = [_unit("a", "Alpha", 2.0), _unit("b", "Alpha"), _unit("c", None), _unit("d", "Bravo")]
        totals = support_total(units, OPTIONS)
        assert totals == {"Alpha": 3.0, "Bravo": 1.0, "Delta": 0.0, "Gamma": 0.0}


class TestSeedSplit:
    def test_refuses_overlapping_train_and_eval(self) -> None:
        """Enforced in code, not by convention: CLAUDE.md rule 4."""
        with pytest.raises(ValueError, match="train and eval seeds overlap"):
            SeedSplit(train=range(0, 100), eval=range(50, 150))

    def test_refuses_a_pilot_overlapping_the_primary_seeds(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            SeedSplit(train=range(0, 100), eval=range(100, 200), pilot=range(150, 160))

    def test_accepts_disjoint_ranges(self) -> None:
        split = SeedSplit(train=range(0, 100), eval=range(1000, 1100), pilot=range(500, 510))
        assert split.holds_out(1050)
        assert not split.holds_out(50)


class TestEnvironmentDefaults:
    def test_generate_batch_uses_consecutive_seeds(self) -> None:
        class Counting(Environment):
            name = "counting"

            def generate(self, seed: int) -> DistributedTask:
                return _task(task_id=f"counting-{seed}", metadata={"seed": seed})

        tasks = Counting().generate_batch(3, 10)
        assert [t.task_id for t in tasks] == ["counting-10", "counting-11", "counting-12"]

    def test_generate_batch_rejects_a_negative_count(self) -> None:
        class Tiny(Environment):
            name = "tiny"

            def generate(self, seed: int) -> DistributedTask:
                return _task()

        with pytest.raises(ValueError, match="non-negative"):
            Tiny().generate_batch(-1, 0)

    def test_optional_hooks_default_to_nothing_declared(self) -> None:
        """Defaults must make the audit say `skipped`, never `pass`."""

        class Bare(Environment):
            name = "bare"

            def generate(self, seed: int) -> DistributedTask:
                return _task()

        env = Bare()
        assert env.seed_split() is None
        assert env.conditions(_task()) == {}


class TestBinomialTailP:
    def test_certainty_gives_a_tiny_p_value(self) -> None:
        assert binomial_tail_p(200, 200, 0.25) < 1e-100

    def test_chance_performance_is_not_significant(self) -> None:
        assert binomial_tail_p(50, 200, 0.25) > 0.4

    def test_handles_degenerate_inputs(self) -> None:
        assert binomial_tail_p(0, 0, 0.25) == 1.0
        assert binomial_tail_p(0, 10, 0.25) == pytest.approx(1.0)


def test_the_package_version_has_one_source_of_truth() -> None:
    """``__version__`` and the distribution metadata must agree; cards record it."""
    import tomllib
    from pathlib import Path

    import grapevine

    meta = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert meta["name"] == "grapevine-mas"
    assert grapevine.__version__ == meta["version"]
