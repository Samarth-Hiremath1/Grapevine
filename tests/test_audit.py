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
from grapevine.audit.checks import CheckContext, family_alpha, run_checks
from grapevine.envs import get_environment
from grapevine.protocol import binomial_tail_p

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

    def test_the_documented_checks_are_present(self) -> None:
        """Pinned so adding a check is a deliberate, documented act.

        ``docs/audit-battery.md`` lists these, and a check added without
        updating that page fails here.
        """
        assert set(CHECK_IDS) == {
            "leak",
            "solo_solvability",
            "full_solvability",
            "shortcuts",
            "name_hygiene",
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
        ran = [r.status for r in control_card.results]
        worst = max((st for st in ran if st is not Status.SKIPPED), key=lambda st: st.rank)
        assert control_card.verdict is worst
        assert control_card.passed == (Status.FAIL not in ran)
        assert set(control_card.flagged_checks) == {
            r.check_id for r in control_card.results if r.status is Status.FAIL
        }

    def test_skipped_never_counts_as_passing(self) -> None:
        """An environment that declares nothing must not look checked."""
        card = audit(get_environment("split_evidence"), n_tasks=20, seed=0)
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


class TestMultiplicity:
    """A check that runs several probes must correct for running several probes.

    This is not a nicety. Five shortcut probes at an uncorrected alpha of 0.05
    fail roughly one clean environment in four, and a validity auditor that
    cries wolf that often is one people learn to ignore. ``docs/audit.md`` S3
    applied the same correction to the study's four paired comparisons.
    """

    def test_alpha_is_divided_by_the_number_of_probes(self) -> None:
        assert family_alpha(0.05, 5) == pytest.approx(0.01)
        assert family_alpha(0.05, 1) == pytest.approx(0.05)
        assert family_alpha(0.05, 0) == pytest.approx(0.05)

    def test_uncorrected_alpha_would_fail_clean_environments(self) -> None:
        """Demonstrated rather than asserted from theory.

        Simulates five probes that are genuinely at chance over 200 tasks and
        counts how often at least one clears an uncorrected 0.05. The answer is
        around one run in five; with the correction it is around one in twenty.
        """
        import random

        rng = random.Random(20261115)
        n, trials, n_probes = 200, 2000, 5
        uncorrected = corrected = 0
        for _ in range(trials):
            p_values = [
                binomial_tail_p(sum(rng.random() < 0.25 for _ in range(n)), n, 0.25)
                for _ in range(n_probes)
            ]
            uncorrected += any(p < 0.05 for p in p_values)
            corrected += any(p < family_alpha(0.05, n_probes) for p in p_values)
        assert uncorrected / trials > 0.12, uncorrected / trials
        assert corrected / trials < 0.06, corrected / trials

    def test_the_correction_is_recorded_on_the_card(self) -> None:
        """A reader must be able to see which threshold was used."""
        card = audit(CLEAN_CONTROL, n_tasks=50, seed=0)
        assert card.get("shortcuts").detail["alpha_per_probe"] < 0.05
        assert card.get("solo_solvability").detail["alpha_per_probe"] < 0.05
        assert card.get("reward_hacking").detail["alpha_per_probe_vs_chance"] < 0.05

    def test_the_correction_does_not_hide_a_real_shortcut(self) -> None:
        """v0's name counting solved 200/200; no correction could mask that."""
        card = audit(get_environment("hidden_profile"), n_tasks=200, seed=1000)
        assert card.get("shortcuts").status is Status.FAIL


# --- 2. Calibration ----------------------------------------------------------


#: The two checks whose "beats chance" test is limited by sample size, not by
#: what they look for: some single view always leans towards the answer of an
#: argmax-of-summed-evidence task (docs/audit-battery.md, "Why a pass is a bound").
POWER_LIMITED = {"solo_solvability", "reward_hacking"}

#: Probes and policies that read which facts are support -- the content the task
#: is about. The unavoidable lean shows up only through these.
READS_SUPPORT = {
    "scoring_rule_on_own_view", "scoring_rule_on_my_private_units", "learned_from_view_ranks",
}
LEAN_POLICIES = {"no_discussion_majority", "copy_agent_zero", "defer_to_largest_view"}
DISJOINT_SEEDS = [0, 5000, 10000, 20000]


class TestCleanControl:
    """The control is as clean as an additive hidden profile can be, and no cleaner.

    It used to be required to pass every check. That cannot be guaranteed once
    the battery has probes good enough to see the single-view lean every such
    task has; what can be required is everything below.
    """

    @pytest.mark.parametrize("seed", DISJOINT_SEEDS)
    def test_every_check_passes_and_the_advantage_is_measured(self, seed: int) -> None:
        """The overall verdict is the same on every seed range: measured, never fail."""
        card = audit(CLEAN_CONTROL, n_tasks=N, seed=seed)
        not_passing = {r.check_id: r.status.value for r in card.results
                       if r.status is not Status.PASS and r.check_id not in POWER_LIMITED}
        assert not_passing == {}, not_passing
        for check in POWER_LIMITED:
            assert card.get(check).status is Status.MEASURED, card.get(check).summary
        assert card.verdict is Status.MEASURED and card.passed

    @pytest.mark.parametrize("seed", DISJOINT_SEEDS)
    def test_only_the_irreducible_lean_is_ever_detected(self, seed: int) -> None:
        """No names-only or shared-block probe, and no layout policy, ever fires."""
        card = audit(CLEAN_CONTROL, n_tasks=N, seed=seed)
        solo = {r["probe"] for r in card.get("solo_solvability").detail["probes"] if r["beats_chance"]}
        assert solo <= READS_SUPPORT, solo
        hacking = set(card.get("reward_hacking").detail["zero_information_diagnostic"]["policies_beating_chance"])
        assert hacking <= LEAN_POLICIES, hacking

    def test_control_is_deterministic_by_seed(self) -> None:
        env = CLEAN_CONTROL
        assert env.generate(7) == env.generate(7)
        assert env.generate(7) != env.generate(8)


class TestTheControlsSingleViewBound:
    """What one agent can do alone in the control, computed exactly and checked."""

    def test_the_exact_bound(self) -> None:
        from fixtures.flawed_envs import _K

        from studies.battery_calibration.bound import exact_single_view_bayes

        bound = exact_single_view_bayes(_K, list(range(_K, 2 * _K + 1)))
        assert bound == pytest.approx(0.2976, abs=5e-4)

    def test_the_generator_matches_the_bound(self) -> None:
        """Own-view scoring rule over 9,000 views lands on the Bayes bound."""
        from grapevine.protocol import support_total

        hits, n = 0.0, 0
        for seed in range(20000, 23000):
            task = CLEAN_CONTROL.generate(seed)
            for view in task.views:
                totals = support_total(view.private, task.answer_space)
                top = max(totals.values())
                leaders = [o for o in task.answer_space if totals[o] == top]
                hits += (task.gold_answer in leaders) / len(leaders)
                n += 1
        assert hits / n == pytest.approx(0.2976, abs=0.015)

    def test_more_tasks_sharpen_the_estimate_without_changing_the_status(self) -> None:
        """At n=2000 the zero-information diagnostic rejects; the status does not move."""
        small = audit(CLEAN_CONTROL, n_tasks=200, seed=100000).get("solo_solvability")
        large = audit(CLEAN_CONTROL, n_tasks=2000, seed=100000).get("solo_solvability")
        assert small.status is large.status is Status.MEASURED
        assert large.detail["zero_information_diagnostic"]["rejected"]
        assert large.detail["minimum_detectable_accuracy"] < 0.2976
        lo, hi = large.detail["primary_estimate"]["ci95"]
        assert lo < 0.2976 + 0.02 and hi > 0.2976 - 0.02
        assert hi - lo < small.detail["primary_estimate"]["ci95"][1] - small.detail["primary_estimate"]["ci95"][0]


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


class TestMinimalityCounts:
    """The card reports the total, not the size of its 10-entry sample (review M3)."""

    def test_the_count_is_not_capped_by_the_sample(self) -> None:
        from grapevine.audit.solvers import uniquely_determined, units_without

        flawed, _ = FLAWED_ENVS["redundant_required"]
        result = audit(flawed, n_tasks=50, seed=0).get("minimality")
        expected = sum(
            uniquely_determined(units_without(t.all_units(), uid), t.answer_space) == t.gold_answer
            for t in flawed.generate_batch(50, seed=0)
            for uid in t.required_units
        )
        assert expected > 10
        assert result.detail["redundant_found"] == expected
        assert result.summary.startswith(f"{expected} of ")
        assert len(result.detail["examples"]) == 10


#: The probes solo_solvability had before the v2 eval found A2.
PRE_A2_PROBES = {"scoring_rule_on_own_view", "mention_count_on_own_view", "named_in_my_private_units"}
#: ...and before the external review (docs/review-v0.2.md, M1).
PRE_REVIEW_PROBES = PRE_A2_PROBES | {"scoring_rule_on_my_private_units"}


class TestTheReviewsFindings:
    """Regression tests for docs/review-v0.2.md M1 (names-only) and M2 (partial leak)."""

    @pytest.mark.parametrize("seed", DISJOINT_SEEDS)
    def test_the_names_only_layout_is_caught_and_only_by_the_new_probes(self, seed: int) -> None:
        flawed, _ = FLAWED_ENVS["legacy_pointer_support"]
        result = audit(flawed, n_tasks=N, seed=seed).get("solo_solvability")
        assert result.status is Status.FAIL
        rows = {r["name"]: r for r in result.detail["probes"]}
        for agent_id in range(3):
            assert rows[f"named_not_most_named_privately[agent {agent_id}]"]["n_correct"] == N
        pre = [r for r in result.detail["probes"] if r["probe"] in PRE_REVIEW_PROBES]
        assert not any(r["beats_chance"] for r in pre), "a pre-review probe now catches it"

    def test_the_43_of_200_leak_fails_and_is_counted(self) -> None:
        import random as _random

        flawed, _ = FLAWED_ENVS["partial_leak_0_2"]
        planted = sum(_random.Random(s * 31 + 7).random() < 0.2 for s in range(N))
        assert planted == 43
        leak = audit(flawed, n_tasks=N, seed=0).get("leak")
        assert leak.status is Status.FAIL
        assert leak.detail["tasks_where_one_unit_outweighs_all_rivals"] == planted

    @pytest.mark.parametrize("fraction", ["0_05", "0_1", "0_2"])
    @pytest.mark.parametrize("seed", DISJOINT_SEEDS)
    def test_every_dose_fails_on_every_seed_range(self, fraction: str, seed: int) -> None:
        flawed, _ = FLAWED_ENVS[f"partial_leak_{fraction}"]
        assert audit(flawed, n_tasks=N, seed=seed).get("leak").status is Status.FAIL

    def test_a_single_leaking_task_fails(self) -> None:
        """Zero tolerance: one decisive unit in one task is a defect."""
        from fixtures.flawed_envs import ControlEnv

        seeds = [s for s in range(5000) if __import__("random").Random(s * 31 + 7).random() < 0.001]
        assert seeds, "no seed plants the leak at this fraction"
        leak = audit(ControlEnv(leak_fraction=0.001), n_tasks=200, seed=seeds[0]).get("leak")
        assert leak.status is Status.FAIL
        assert leak.detail["tasks_where_one_unit_outweighs_all_rivals"] >= 1


class TestTheGapTheV2EvalFound:
    """A2: a private-only scoring rule, missed by the battery until a model used it.

    Recorded in ``docs/audit.md`` and ``studies/v2_eval/h1_investigation.md``.
    """

    def test_only_the_new_probe_catches_the_planted_layout(self) -> None:
        """Every probe the battery had before A2 reports clean on this layout."""
        flawed, _ = FLAWED_ENVS["legacy_gold_only_private_support"]
        result = audit(flawed, n_tasks=100, seed=0).get("solo_solvability")
        assert result.status is Status.FAIL
        beating = {r["probe"] for r in result.detail["probes"] if r["beats_chance"]}
        assert "scoring_rule_on_my_private_units" in beating
        assert not beating & PRE_A2_PROBES, beating

    def test_hidden_profile_v2_fails_on_it(self) -> None:
        """v2 passed the battery as it stood; it does not pass this probe.

        v2's generator is frozen (``CLAUDE.md`` rule 6), so the failure stays
        on its card rather than being designed away.
        """
        env = get_environment("hidden_profile_v2")
        result = audit(env, n_tasks=100, seed=env.seed_split().eval[0]).get("solo_solvability")
        assert result.status is Status.FAIL
        rows = {r["name"]: r for r in result.detail["probes"]}
        for agent_id in range(3):
            assert rows[f"scoring_rule_on_my_private_units[agent {agent_id}]"]["n_correct"] == 100
        old = [r for r in result.detail["probes"] if r["probe"] in PRE_A2_PROBES]
        assert not any(r["beats_chance"] for r in old)


class TestSplitEvidenceIsARealPositiveControl:
    """``split_evidence`` failed for real, before any of this existed."""

    def test_the_leak_check_reproduces_the_hand_count(self) -> None:
        """docs/decisions.md: the gold answer appeared in some agent's context
        in 100 of 100 generated tasks."""
        card = audit(get_environment("split_evidence"), n_tasks=100, seed=0)
        leak = card.get("leak")
        assert leak.status is Status.FAIL
        assert leak.detail["tasks_where_a_view_names_only_gold"] == 100

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
        rows = {r["name"]: r for r in result.detail["policies"]}
        assert rows["no_discussion_majority"]["accuracy"] > 0.4
        # A large measured advantage, not a match for pooling: reward_hacking reports
        # it as measured, and the environment fails on what causes it -- the leak.
        assert result.status is Status.MEASURED
        assert result.detail["zero_information_diagnostic"]["rejected"]
        assert card.get("leak").status is Status.FAIL


class TestClassification:
    """Confirmed failures, measured advantages and insufficient evidence are told apart."""

    def test_v0_and_v2_are_reliable_solo_shortcuts(self) -> None:
        for name in ("hidden_profile", "hidden_profile_v2"):
            result = audit(get_environment(name), n_tasks=N, seed=0).get("solo_solvability")
            assert result.status is Status.FAIL, name
            assert result.summary.startswith("Reliable solo shortcut")
            # At the feature level, no view has a twin with a different answer.
            assert result.detail["feature_twin_test"]["per_agent"]["0"]["feature_twin_with_different_answer"] == 0

    def test_the_control_is_a_measured_advantage(self) -> None:
        result = audit(CLEAN_CONTROL, n_tasks=N, seed=0).get("solo_solvability")
        assert result.status is Status.MEASURED
        twins = result.detail["feature_twin_test"]["per_agent"]
        assert result.detail["feature_twin_test"]["level"] == "feature-level only"
        for agent in ("0", "1", "2"):
            # For most views, the evidence pattern alone leaves the answer open: a
            # feature twin with a different gold option exists. Feature-level only.
            assert twins[agent]["feature_twin_with_different_answer"] > 0.8 * twins[agent]["views"]
        estimate = result.detail["primary_estimate"]
        for key in ("accuracy", "ci95", "advantage", "share_of_pooling_gain", "n"):
            assert key in estimate
        assert result.detail["zero_information_diagnostic"]["label"].startswith("diagnostic only")

    def test_a_graded_leak_is_measured_not_failed(self) -> None:
        flawed, _ = FLAWED_ENVS["gold_share_bias"]
        result = audit(flawed, n_tasks=N, seed=0).get("solo_solvability")
        assert result.status is Status.MEASURED
        assert result.detail["zero_information_diagnostic"]["rejected"]

    def test_a_conditional_shortcut_is_a_failure(self) -> None:
        """Right whenever it commits, even if it cannot commit on every task."""
        flawed, _ = FLAWED_ENVS["solo_solvable"]
        result = audit(flawed, n_tasks=N, seed=0).get("solo_solvability")
        assert result.status is Status.FAIL
        rows = [r for r in result.detail["probes"] if r["never_wrong_when_committed"]]
        assert any(r["commits"] < r["n"] for r in rows)

    def test_too_few_tasks_is_inconclusive(self) -> None:
        card = audit(CLEAN_CONTROL, n_tasks=10, seed=0)
        assert card.get("solo_solvability").status is Status.INCONCLUSIVE
        assert card.get("reward_hacking").status is Status.INCONCLUSIVE
        assert card.passed

    def test_the_impossibility_identity_holds_on_the_control(self) -> None:
        """Sum over views of gold's lean equals gold's lead in the pooled total.

        The argument in docs/validity-card.md rests on this identity: if every view's
        lean were zero in expectation, gold's expected lead over the average option
        would be zero, but it is positive by construction.
        """
        from grapevine.protocol import support_total

        lean_sum = lead = 0.0
        for seed in range(30000, 31000):
            task = CLEAN_CONTROL.generate(seed)
            opts = task.answer_space
            for view in task.views:
                p = support_total(view.private, opts)
                lean_sum += p[task.gold_answer] - sum(p.values()) / len(opts)
            shared = support_total(task.views[0].shared, opts)
            lean_sum += shared[task.gold_answer] - sum(shared.values()) / len(opts)
            total = support_total(task.all_units(), opts)
            lead += total[task.gold_answer] - sum(total.values()) / len(opts)
        assert lean_sum == pytest.approx(lead)
        assert lead / 1000 == pytest.approx(0.75)
