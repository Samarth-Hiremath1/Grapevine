"""The audit battery is calibrated, not merely asserted.

Three things are tested here, and the second two are the ones that matter:

1. The mechanics: cards serialise, hash stably, and are deterministic by seed.
2. **Calibration.** Every environment in ``tests/fixtures/flawed_envs/`` carries
   exactly one planted defect, and the check named for it must fire. The clean
   control must pass every check. A battery that has never been shown a
   known-bad input is a battery that passes everything, and an auditor that
   passes everything launders flawed environments as checked ones.
3. **Rediscovery.** Run against the v0 ``hidden_profile`` environment, the
   battery must find the findings this repository's own hand audit found
   (``docs/audit.md``), by finding number. A miss is a bug in the battery.

Point 3 also works the other way: the battery found something the hand audit
missed, recorded as A1 in ``docs/audit.md`` and asserted below.
"""

from __future__ import annotations

import json

import pytest
from fixtures.flawed_envs import CLEAN_CONTROL, FLAWED_ENVS

from grapevine.audit import CHECK_IDS, CHECKS, Status, ValidityCard, audit, check_ids
from grapevine.audit.checks import CheckContext, run_checks
from grapevine.envs import get_environment

#: 200 tasks matches the v0 study's N and gives the binomial tests the power to
#: separate a 100%-accurate shortcut from chance beyond any doubt.
N = 200


@pytest.fixture(scope="module")
def control_card() -> ValidityCard:
    return audit(CLEAN_CONTROL, n_tasks=N, seed=0)


@pytest.fixture(scope="module")
def hidden_profile_card() -> ValidityCard:
    """The v0 environment on the seeds the committed runs used."""
    return audit(get_environment("hidden_profile"), n_tasks=N, seed=1000)


# --- 1. Mechanics ------------------------------------------------------------


class TestRegistry:
    def test_every_check_function_matches_its_result_id(self) -> None:
        """``check_<id>`` must return a result whose ``check_id`` is ``<id>``.

        CHECK_IDS is derived from function names, so without this the documented
        ids could drift from the ones cards actually carry.
        """
        tasks = tuple(CLEAN_CONTROL.generate_batch(4, 0))
        ctx = CheckContext(env=CLEAN_CONTROL, tasks=tasks, seed=0)
        for fn, declared in zip(CHECKS, CHECK_IDS, strict=True):
            assert fn(ctx).check_id == declared, fn.__name__

    def test_check_ids_are_unique_and_exposed(self) -> None:
        assert len(set(CHECK_IDS)) == len(CHECK_IDS)
        assert check_ids() == CHECK_IDS

    def test_the_documented_twelve_checks_are_present(self) -> None:
        assert set(CHECK_IDS) == {
            "leak",
            "solo_solvability",
            "full_solvability",
            "shortcuts",
            "minimality",
            "diversity",
            "balance",
            "objective",
            "condition_diff",
            "scorer_fuzz",
            "reward_hacking",
            "seed_split",
        }


class TestCard:
    def test_json_round_trips_and_names_its_schema(self, control_card: ValidityCard) -> None:
        payload = json.loads(control_card.to_json())
        assert payload["schema"] == "grapevine.validity_card/1"
        assert payload["environment"] == "control"
        assert len(payload["results"]) == len(CHECK_IDS)

    def test_markdown_states_the_verdict_and_every_check(
        self, control_card: ValidityCard
    ) -> None:
        markdown = control_card.to_markdown()
        assert "Validity Card" in markdown
        for check_id in CHECK_IDS:
            assert f"`{check_id}`" in markdown

    def test_hash_is_stable_across_rebuilds_but_not_across_content(self) -> None:
        a = audit(CLEAN_CONTROL, n_tasks=20, seed=0)
        b = audit(CLEAN_CONTROL, n_tasks=20, seed=0)
        c = audit(CLEAN_CONTROL, n_tasks=20, seed=50)
        assert a.content_hash() == b.content_hash()
        assert a.content_hash() != c.content_hash()

    def test_verdict_is_the_worst_status_that_ran(self, control_card: ValidityCard) -> None:
        assert control_card.verdict is Status.PASS
        assert control_card.passed
        assert control_card.flagged_checks == ()

    def test_skipped_never_counts_as_passing(self) -> None:
        """An environment that declares nothing must not look checked."""
        from grapevine.envs import get_environment as _get

        card = audit(_get("split_evidence"), n_tasks=20, seed=0)
        objective = card.get("objective")
        assert objective.status is Status.SKIPPED
        assert "cannot" in objective.summary.lower()
        assert objective.status is not Status.PASS

    def test_get_raises_on_an_unknown_check(self, control_card: ValidityCard) -> None:
        with pytest.raises(KeyError, match="no check"):
            control_card.get("nope")

    def test_only_restricts_the_card(self) -> None:
        card = audit(CLEAN_CONTROL, n_tasks=20, seed=0, only=("leak", "shortcuts"))
        assert {r.check_id for r in card.results} == {"leak", "shortcuts"}

    def test_rejects_a_non_positive_task_count(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            audit(CLEAN_CONTROL, n_tasks=0)

    def test_every_check_cites_the_finding_it_came_from(self) -> None:
        """A check nobody has ever needed is a check that will drift.

        ``seed_split`` is the one exception: it guards a future RL mistake rather
        than a past one.
        """
        tasks = tuple(CLEAN_CONTROL.generate_batch(4, 0))
        results = run_checks(CheckContext(env=CLEAN_CONTROL, tasks=tasks, seed=0))
        uncited = [r.check_id for r in results if not r.audit_findings]
        assert uncited == ["seed_split"]


# --- 2. Calibration ----------------------------------------------------------


class TestCleanControl:
    def test_control_passes_every_check(self, control_card: ValidityCard) -> None:
        """If this ever fails, fix the control before trusting any other result."""
        not_passing = {
            r.check_id: (r.status.value, r.summary) for r in control_card.results
            if r.status is not Status.PASS
        }
        assert not_passing == {}, f"control no longer clean: {not_passing}"

    def test_control_is_deterministic_by_seed(self) -> None:
        env = CLEAN_CONTROL
        assert env.generate(7) == env.generate(7)
        assert env.generate(7) != env.generate(8)


@pytest.mark.parametrize("fixture_name", sorted(FLAWED_ENVS), ids=sorted(FLAWED_ENVS))
def test_every_planted_flaw_is_flagged(fixture_name: str) -> None:
    """The check named for a planted defect must fire at the declared severity.

    A planted defect may trip other checks too -- a real flaw usually does, and
    a leak really does also make a task solo-solvable. What is required is that
    the check responsible for it catches it.
    """
    env, defect = FLAWED_ENVS[fixture_name]
    card = audit(env, n_tasks=N, seed=0)
    result = card.get(defect.expected_check)
    assert result.status.value == defect.expected_status, (
        f"planted defect '{defect.name}' ({defect.description}) should make "
        f"`{defect.expected_check}` report {defect.expected_status}, "
        f"got {result.status.value}: {result.summary}"
    )


@pytest.mark.parametrize("fixture_name", sorted(FLAWED_ENVS), ids=sorted(FLAWED_ENVS))
def test_every_flawed_fixture_differs_from_the_control(fixture_name: str) -> None:
    """Each fixture is the control with one flag flipped, and only one."""
    env, _ = FLAWED_ENVS[fixture_name]
    flipped = [
        f
        for f in env.__dataclass_fields__
        if f not in ("name", "version") and getattr(env, f) != getattr(CLEAN_CONTROL, f)
    ]
    assert len(flipped) == 1, f"{fixture_name} flips {flipped}, expected exactly one"


def test_a_flawed_card_reports_its_planted_flag() -> None:
    """A card records the configuration it audited, so a reader can see the defect."""
    env, _ = FLAWED_ENVS["lenient_scorer"]
    card = audit(env, n_tasks=20, seed=0)
    assert card.config.get("lenient_scorer") is True


# --- 3. Rediscovery of the v0 findings ---------------------------------------


class TestRediscoversTheV0Audit:
    """Each test names the finding in ``docs/audit.md`` it reproduces."""

    def test_l3_name_counting_solves_the_task(self, hidden_profile_card: ValidityCard) -> None:
        """L3 / I1.3: counting name mentions picked the correct answer in 200/200."""
        result = hidden_profile_card.get("shortcuts")
        assert result.status is Status.FAIL
        rows = {r["name"]: r for r in result.detail["shortcuts"]}
        assert rows["mention_count"]["n_correct"] == N
        assert rows["mention_count"]["accuracy"] == 1.0
        assert "L3" in result.audit_findings

    def test_i1_the_objective_never_reached_the_models(
        self, hidden_profile_card: ValidityCard
    ) -> None:
        """I1 / L1: no prompt in conditions A-D stated the question or the rule.

        This is the finding that made the v0 headline wrong, so it is the one the
        battery most has to catch.
        """
        result = hidden_profile_card.get("objective")
        assert result.status is Status.FAIL
        rows = {r["condition"]: r for r in result.detail["conditions"]}
        for condition in (
            "full_info",
            "no_communication",
            "communication",
            "communication_neutral",
        ):
            assert not rows[condition]["states_objective"], condition
            assert rows[condition]["prompts_missing_question"] > 0
            assert rows[condition]["prompts_missing_scoring_rule"] > 0
        # And the rule arm, which fixed it, states both.
        for condition in ("communication_rule", "full_info_rule", "no_communication_rule"):
            assert rows[condition]["states_objective"], condition

    def test_l2_the_batch_is_one_puzzle_in_200_arrangements(
        self, hidden_profile_card: ValidityCard
    ) -> None:
        """L2: all 200 tasks share the support pattern (6, 5, 1, 0) and 12 sentences."""
        result = hidden_profile_card.get("diversity")
        assert result.status is Status.WARN
        assert result.detail["distinct_support_patterns"] == 1
        assert "L2" in result.audit_findings

    def test_l9_agent_zero_is_better_informed(
        self, hidden_profile_card: ValidityCard
    ) -> None:
        """L9: distractors are dealt round-robin, so agent 0 always holds one more."""
        result = hidden_profile_card.get("balance")
        assert result.status is Status.WARN
        means = result.detail["mean_private_units_per_agent"]
        assert means[0] > means[1], means
        assert "L9" in result.audit_findings

    def test_l4_the_baseline_arm_differs_in_framing_too(
        self, hidden_profile_card: ValidityCard
    ) -> None:
        """L4: condition A had its own system prompt, headers and framing line.

        Asserted on the framings directly rather than on the card's pair list,
        which is capped at the pairs a reader needs to act on. The point is the
        specific text L4 named, not the pair's position in that list.
        """
        from grapevine.audit.checks import _diff_lines, _framing

        result = hidden_profile_card.get("condition_diff")
        assert result.status is Status.WARN
        assert "L4" in result.audit_findings

        env = get_environment("hidden_profile")
        task = env.generate(1000)
        conditions = env.conditions(task)
        baseline = _framing(conditions["full_info"], task)
        team = _framing(conditions["communication"], task)
        differing = "\n".join(_diff_lines(baseline, team))

        # The exact strings L4 reported as present in A and absent from B/C/D.
        assert "You are an expert decision-maker" in differing
        assert "All available information:" in differing
        assert "(you have all information; no discussion needed)" in differing
        # And the shared/private headers the team arms use and A did not.
        assert "Facts known to the whole committee:" in differing

    def test_the_rule_arms_differ_only_by_the_task_statement(
        self, hidden_profile_card: ValidityCard
    ) -> None:
        """The study's central claim, as the audit sees it.

        Each ``_rule`` arm declares that the task statement is its only
        difference from the arm it mirrors, and the check verifies it rather than
        taking the declaration on trust.
        """
        result = hidden_profile_card.get("condition_diff")
        verdicts = result.detail["verdict_counts"]
        assert verdicts["differs beyond its declared difference"] == 0
        assert verdicts["differs only by its declared difference"] == 5

    def test_g3_gold_position_is_uniform(self, hidden_profile_card: ValidityCard) -> None:
        """G3 (clean): gold position was uniform over 5,000 seeds, chi2 = 1.31."""
        position = hidden_profile_card.get("balance").detail["gold_position"]
        assert position["uniform"], position
        assert position["critical_05"] == 7.81

    def test_g5_pooling_solves_it_and_every_required_fact_is_needed(
        self, hidden_profile_card: ValidityCard
    ) -> None:
        """G5 (clean): 0 invariant violations over the 200 primary seeds."""
        assert hidden_profile_card.get("full_solvability").status is Status.PASS
        assert hidden_profile_card.get("full_solvability").detail["n_correct"] == N
        minimality = hidden_profile_card.get("minimality")
        assert minimality.status is Status.PASS
        assert minimality.detail["redundant_found"] == 0

    def test_d1_is_fixed_so_the_scorer_check_passes(
        self, hidden_profile_card: ValidityCard
    ) -> None:
        """D1 was fixed in the audit branch; the check that would catch it passes.

        Calibration for this check lives in the ``lenient_scorer`` fixture, which
        reproduces D1's exact behaviour and must fail.
        """
        assert hidden_profile_card.get("scorer_fuzz").status is Status.PASS
        flawed, _ = FLAWED_ENVS["lenient_scorer"]
        assert audit(flawed, n_tasks=20, seed=0).get("scorer_fuzz").status is Status.FAIL

    def test_a1_a_new_finding_the_hand_audit_missed(
        self, hidden_profile_card: ValidityCard
    ) -> None:
        """A1: every private fact supports the gold option.

        So "name whoever my own secret notes discuss" answers correctly from a
        single agent's view, with no pooling at all. The hand audit tested solo
        solvability by applying the task's scoring rule to one view (G6, 0/200)
        and did not try the broader class of solvers. Recorded in
        ``docs/audit.md`` under "Found later, by the battery".
        """
        result = hidden_profile_card.get("solo_solvability")
        assert result.status is Status.FAIL
        rows = {r["name"]: r for r in result.detail["probes"]}
        for agent_id in range(3):
            row = rows[f"named_in_my_private_units[agent {agent_id}]"]
            assert row["n_correct"] == N, row
        # The hand audit's own probe still reports clean, which is why it missed it.
        for agent_id in range(3):
            row = rows[f"scoring_rule_on_own_view[agent {agent_id}]"]
            assert not row["beats_chance"], row


class TestSplitEvidenceIsARealPositiveControl:
    """``split_evidence`` failed for real, before any of this existed."""

    def test_the_leak_check_reproduces_the_hand_count(self) -> None:
        """docs/decisions.md: the gold answer appeared in some agent's context
        in 100 of 100 generated tasks."""
        card = audit(get_environment("split_evidence"), n_tasks=100, seed=0)
        leak = card.get("leak")
        assert leak.status is Status.FAIL
        assert leak.detail["only_gold_named_in_a_view"]["n_correct"] == 100

    def test_it_is_solvable_by_one_agent_alone(self) -> None:
        """Which is why condition B built on it would not have measured pooling."""
        card = audit(get_environment("split_evidence"), n_tasks=100, seed=0)
        assert card.get("solo_solvability").status is Status.FAIL

    def test_the_old_diagnostic_finding_is_reproduced(self) -> None:
        """docs/decisions.md recorded a no-discussion policy scoring 0.557 here
        against roughly chance on hidden_profile. The battery agrees: the reward
        is earnable without discussion."""
        card = audit(get_environment("split_evidence"), n_tasks=100, seed=0)
        result = card.get("reward_hacking")
        assert result.status is Status.FAIL
        rows = {r["name"]: r for r in result.detail["policies"]}
        assert rows["no_discussion_majority"]["accuracy"] > 0.4
