"""``hidden_profile_v2`` is correct by construction, and the pool is frozen.

The environment checks its own invariants on every ``generate`` call and raises
rather than returning a task that looks fine and measures nothing. These tests
cover the things that assertion cannot: that the frozen pool has not moved, that
the properties really do hold across many seeds and configurations, that the
config validation refuses what it should, and that the audit passes.

The audit passing is the headline, but it is also the weakest of these tests on
its own: the battery is thirteen known failure modes, not a proof. The invariant
assertions inside the generator are what make the construction right, and the
pool hash is what keeps the committed card describing the tasks the code builds.
"""

from __future__ import annotations

import re

import pytest

from grapevine.audit import CHECK_IDS, Status, audit
from grapevine.envs import ENVIRONMENTS, get_environment
from grapevine.envs._pool_v2 import DOMAINS, POOL_SHA256, pool_digest
from grapevine.envs.hidden_profile_v2 import HiddenProfileV2, HiddenProfileV2Config
from grapevine.protocol import support_total

ALL_ENTITIES = [entity for domain in DOMAINS for entity in domain.entities]
ALL_SENTENCES = [
    sentence for domain in DOMAINS for sentence in (*domain.support, *domain.mentions)
]


def _whole_word(name: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", re.IGNORECASE)


class TestFrozenPool:
    """The pool is content, drafted by a model, and never a source of labels."""

    def test_digest_matches_the_committed_constant(self) -> None:
        """Editing a sentence must fail here.

        Every committed Validity Card describes the tasks this pool produces, so
        a silent edit would leave the card describing tasks that no longer
        exist. Add a domain instead; if the pool must change, the environment's
        version changes with it.
        """
        assert pool_digest() == POOL_SHA256, (
            "the frozen sentence pool has been edited. Either revert it, or bump "
            "HiddenProfileV2.version and regenerate every committed card."
        )

    def test_no_sentence_leads_with_its_subject(self) -> None:
        """In v0 every supporting fact began with the candidate's name, so the
        name's position alone carried the structure (docs/audit.md L3)."""
        leading = [s for s in ALL_SENTENCES if s.startswith("{entity}")]
        assert leading == []

    def test_every_sentence_has_exactly_one_subject_slot(self) -> None:
        assert [s for s in ALL_SENTENCES if s.count("{entity}") != 1] == []

    def test_entity_names_are_unique_and_not_substrings_of_each_other(self) -> None:
        assert len(set(ALL_ENTITIES)) == len(ALL_ENTITIES)
        nested = [
            (a, b)
            for a in ALL_ENTITIES
            for b in ALL_ENTITIES
            if a != b and a.lower() in b.lower()
        ]
        assert nested == []

    def test_no_entity_name_hides_inside_a_sentence(self) -> None:
        """A name that also occurs inside an ordinary word makes every
        name-matching measurement partly a count of word fragments. A control
        fixture in this repository got this wrong with "alphabetically"."""
        collisions = []
        for name in ALL_ENTITIES:
            loose = re.compile(re.escape(name), re.IGNORECASE)
            word = _whole_word(name)
            for sentence in ALL_SENTENCES:
                for match in loose.finditer(sentence):
                    if not word.match(sentence, match.start()):
                        collisions.append((name, sentence))
        assert collisions == []

    def test_no_sentence_is_duplicated_within_a_domain(self) -> None:
        for domain in DOMAINS:
            sentences = [*domain.support, *domain.mentions]
            assert len(set(sentences)) == len(sentences), domain.key

    def test_every_domain_states_a_question_and_a_rule(self) -> None:
        for domain in DOMAINS:
            assert domain.question.strip().endswith("?"), domain.key
            assert "supporting fact" in domain.scoring_rule, domain.key

    def test_the_environment_refuses_to_start_on_a_changed_pool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "grapevine.envs.hidden_profile_v2.POOL_SHA256", "0" * 64
        )
        with pytest.raises(RuntimeError, match="frozen sentence pool has changed"):
            HiddenProfileV2()


class TestConstruction:
    """Properties the generator claims, checked across seeds and configs."""

    CONFIGS = [
        pytest.param(HiddenProfileV2Config(), id="default-3-agents"),
        pytest.param(
            HiddenProfileV2Config(n_agents=2, facts_per_agent=2), id="2-agents-2-facts"
        ),
        pytest.param(HiddenProfileV2Config(n_agents=4), id="4-agents"),
        pytest.param(HiddenProfileV2Config(vary_support=False), id="fixed-support"),
        pytest.param(
            HiddenProfileV2Config(n_options=5, facts_per_agent=2, vary_support=False),
            id="5-options",
        ),
        pytest.param(
            HiddenProfileV2Config(domains=("hiring",)), id="single-domain"
        ),
    ]

    @pytest.mark.parametrize("config", CONFIGS)
    def test_generates_without_tripping_its_own_invariants(
        self, config: HiddenProfileV2Config
    ) -> None:
        """``generate`` raises on any violation, so this is a real assertion."""
        env = HiddenProfileV2(config)
        for seed in range(150):
            env.generate(seed)

    @pytest.mark.parametrize("config", CONFIGS)
    def test_pooling_is_necessary_and_sufficient(
        self, config: HiddenProfileV2Config
    ) -> None:
        env = HiddenProfileV2(config)
        for seed in range(100):
            task = env.generate(seed)
            pooled = support_total(task.all_units(), task.answer_space)
            assert pooled[task.gold_answer] == max(pooled.values())
            assert list(pooled.values()).count(max(pooled.values())) == 1

            shared = support_total(task.shared_units, task.answer_space)
            decoy = task.metadata["decoy_option"]
            assert shared[decoy] == max(shared.values()), "shared info must favour the decoy"
            assert shared[task.gold_answer] == 0, "the gold option gets no shared support"

            for view in task.views:
                own = support_total(view.units, task.answer_space)
                assert own[task.gold_answer] < max(own.values()), (
                    f"agent {view.agent_id} can reach the answer from its own view"
                )

    @pytest.mark.parametrize("config", CONFIGS)
    def test_mention_counts_carry_no_information(
        self, config: HiddenProfileV2Config
    ) -> None:
        """Equal, not merely non-monotonic: the gold option must be neither the
        most-named nor the least-named."""
        env = HiddenProfileV2(config)
        for seed in range(100):
            task = env.generate(seed)
            text = task.full_view().render()
            counts = {
                option: len(_whole_word(option).findall(text))
                for option in task.answer_space
            }
            assert len(set(counts.values())) == 1, (task.task_id, counts)

    @pytest.mark.parametrize("config", CONFIGS)
    def test_no_agents_private_notes_point_at_the_answer(
        self, config: HiddenProfileV2Config
    ) -> None:
        """The A1 defect, made impossible by construction.

        In v0 every private fact supported the correct option, so "whose name is
        in my own notes?" was right 200 times out of 200.
        """
        env = HiddenProfileV2(config)
        for seed in range(100):
            task = env.generate(seed)
            for view in task.views:
                text = "\n".join(unit.text for unit in view.private)
                counts = {
                    option: len(_whole_word(option).findall(text))
                    for option in task.answer_space
                }
                assert counts[task.gold_answer] < max(counts.values()), (
                    task.task_id,
                    view.agent_id,
                    counts,
                )

    @pytest.mark.parametrize("config", CONFIGS)
    def test_agents_are_symmetric(self, config: HiddenProfileV2Config) -> None:
        """L9: in v0 agent 0 always held one more fact than the others."""
        env = HiddenProfileV2(config)
        for seed in range(100):
            task = env.generate(seed)
            assert len({len(v.private) for v in task.views}) == 1
            assert len({v.shared for v in task.views}) == 1

    @pytest.mark.parametrize("config", CONFIGS)
    def test_every_required_unit_is_load_bearing(
        self, config: HiddenProfileV2Config
    ) -> None:
        env = HiddenProfileV2(config)
        for seed in range(50):
            task = env.generate(seed)
            assert task.required_units
            for unit_id in task.required_units:
                remaining = [u for u in task.all_units() if u.unit_id != unit_id]
                totals = support_total(remaining, task.answer_space)
                best = max(totals.values())
                leaders = [o for o in task.answer_space if totals[o] == best]
                assert leaders != [task.gold_answer], unit_id

    def test_margin_above_one_declares_no_required_units(self) -> None:
        """With margin 2 no single fact is necessary, so there is no minimal set
        to declare and the audit reports `skipped` rather than passing."""
        env = HiddenProfileV2(HiddenProfileV2Config(margin=2, facts_per_agent=2))
        assert env.generate(0).required_units == ()
        card = audit(env, n_tasks=50, seed=0)
        assert card.get("minimality").status is Status.SKIPPED

    def test_deterministic_by_seed(self) -> None:
        a, b = HiddenProfileV2(), HiddenProfileV2()
        for seed in (0, 7, 1234, 10000):
            assert a.generate(seed) == b.generate(seed)
        assert a.generate(0) != a.generate(1)

    def test_tasks_differ_across_seeds_in_content(self) -> None:
        env = HiddenProfileV2()
        texts = {
            frozenset(u.text for u in env.generate(seed).all_units())
            for seed in range(200)
        }
        assert len(texts) == 200, "every seed should produce a distinct set of sentences"

    def test_domains_are_all_used(self) -> None:
        env = HiddenProfileV2()
        used = {env.generate(seed).metadata["domain"] for seed in range(100)}
        assert used == {d.key for d in DOMAINS}

    def test_metadata_records_the_pool_hash_and_split(self) -> None:
        env = HiddenProfileV2()
        assert env.generate(5).metadata["pool_sha256"] == POOL_SHA256
        assert env.generate(5).metadata["split"] == "train"
        assert env.generate(10_500).metadata["split"] == "eval"
        assert env.generate(9_100).metadata["split"] == "pilot"
        assert env.generate(50_000).metadata["split"] == "unassigned"


class TestSeedSplit:
    def test_train_and_eval_are_disjoint(self) -> None:
        split = HiddenProfileV2().seed_split()
        assert split is not None
        assert not set(split.train) & set(split.eval)
        assert not set(split.train) & set(split.pilot)
        assert not set(split.eval) & set(split.pilot)

    def test_overlapping_ranges_are_refused_at_construction(self) -> None:
        """An RL user must not be able to train on the seeds they report."""
        with pytest.raises(ValueError, match="overlap"):
            HiddenProfileV2Config(train_seeds=range(0, 100), eval_seeds=range(50, 150))


class TestConfigValidation:
    """A bad configuration must fail at construction, not on seed 137."""

    @pytest.mark.parametrize(
        ("kwargs", "match"),
        [
            ({"n_agents": 1}, "not a distributed task"),
            ({"facts_per_agent": 0}, "facts_per_agent"),
            ({"margin": 0}, "margin must be"),
            ({"n_options": 2}, "at least one rival"),
            ({"n_rounds": 0}, "n_rounds"),
            ({"domains": ("nope",)}, "unknown domain"),
            # 2 agents x 1 fact leaves each agent holding as many gold facts as
            # the decoy has support, so a single agent would not prefer the decoy.
            ({"n_agents": 2}, "hidden-profile premise fails"),
            # Outruns the supporting-sentence pool.
            ({"facts_per_agent": 3}, "supporting sentences"),
            # Fits the supporting pool but equalising mentions outruns that one.
            ({"n_agents": 2, "facts_per_agent": 4}, "mention sentences"),
        ],
    )
    def test_rejects_bad_configurations(self, kwargs: dict[str, object], match: str) -> None:
        with pytest.raises(ValueError, match=match):
            HiddenProfileV2Config(**kwargs)  # type: ignore[arg-type]

    def test_the_rejection_message_says_what_to_change(self) -> None:
        with pytest.raises(ValueError) as excinfo:
            HiddenProfileV2Config(n_agents=2)
        assert "Raise n_agents or lower margin" in str(excinfo.value)


class TestAuditPasses:
    """v2 passes every check except the one added after its eval (A2).

    It passed the battery as it stood when it was built. The ``hidden_profile_v2``
    eval then found a single-agent shortcut the battery lacked a probe for
    (``docs/audit.md``, A2). The generator is frozen (``CLAUDE.md`` rule 6), so
    the failure is pinned here rather than designed away.
    """

    def test_fails_only_solo_solvability_on_the_committed_card_seeds(self) -> None:
        card = audit(get_environment("hidden_profile_v2"), n_tasks=200, seed=0)
        not_passing = {
            r.check_id: r.status for r in card.results
            if r.status not in (Status.PASS, Status.MEASURED)
        }
        assert not_passing == {"solo_solvability": Status.FAIL}, not_passing
        assert len(card.results) == len(CHECK_IDS)

    @pytest.mark.parametrize("seed", [0, 2000, 9000, 10000])
    def test_the_same_on_other_seed_ranges(self, seed: int) -> None:
        """Including the held-out eval seeds, where it was scored."""
        card = audit(get_environment("hidden_profile_v2"), n_tasks=200, seed=seed)
        assert card.flagged_checks == ("solo_solvability",), card.flagged_checks

    def test_is_registered_and_is_the_default(self) -> None:
        from grapevine.envs import DEFAULT_ENVIRONMENT

        assert "hidden_profile_v2" in ENVIRONMENTS
        assert DEFAULT_ENVIRONMENT == "hidden_profile_v2"

    def test_the_committed_card_matches_a_fresh_audit(self) -> None:
        """The card in environments/ is regenerated in CI; this catches drift
        before CI does."""
        import json
        from pathlib import Path

        path = Path("environments/hidden_profile_v2/validity_card.json")
        committed = json.loads(path.read_text(encoding="utf-8"))
        fresh = audit(
            get_environment("hidden_profile_v2"),
            n_tasks=committed["n_tasks"],
            seed=committed["seed"],
        )
        assert fresh.to_dict() == committed
