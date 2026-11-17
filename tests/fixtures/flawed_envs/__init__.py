"""Environments with exactly one planted defect each, plus a clean control.

This is how the audit battery is calibrated rather than merely asserted. A
battery nobody has tested against known-bad inputs is a battery that passes
everything, and an environment auditor that passes everything is worse than
none: it launders a flawed environment as a checked one.

Each fixture below is :class:`ControlEnv` with one flag flipped, so "exactly one
planted defect" is literally true and visible in the code rather than a claim in
a comment. :data:`FLAWED_ENVS` records which check each defect must trip, and
``tests/test_audit.py`` requires every one of them to be caught and the control
to pass clean.

A planted defect may well trip more than one check -- a real flaw usually does.
The calibration requirement is that the check named for it fires, not that
nothing else does; the test records the collateral so it is documented rather
than silently tolerated.

The control is also a prototype. Building something that passes all twelve
checks is harder than it looks, and two of its properties came directly from the
battery telling me the v0 environment lacked them:

* **Mention counts point at the decoy, not the gold answer.** If every
  supporting fact leads with the option's name, counting names solves the task
  and no reasoning is required (``docs/audit.md`` L3).
* **No agent's private units are all about the gold answer.** Otherwise "name
  whoever my secret notes discuss" answers correctly with no pooling at all --
  a defect the battery found in v0 ``hidden_profile`` that the original
  hand audit missed.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass, replace

from grapevine.protocol import (
    AgentView,
    Condition,
    DistributedTask,
    Environment,
    InfoUnit,
    Objective,
    ScoreResult,
    SeedSplit,
)

__all__ = ["CLEAN_CONTROL", "FLAWED_ENVS", "ControlEnv", "Defect"]

#: Equal-length option names, so "pick the longest option" cannot correlate
#: with the answer. None is a substring of another, and a test asserts none
#: occurs inside any pool sentence -- see `name_hygiene`.
_NAMES = (
    "Alpha", "Bravo", "Delta", "Gamma", "Kilo", "Lima", "Mike", "Oscar",
    "Romeo", "Sierra", "Tango", "Victor",
)

#: Names that hide inside ordinary English words, for the `name_hygiene`
#: fixture: "Art" in "particular", "Ever" in "however", "Owen" in "shown",
#: "Rose" in "prose". Counting these names also counts word fragments.
_COLLIDING_NAMES = ("Art", "Ever", "Owen", "Rose", "Hart", "Reed")

#: Supporting-fact templates. Larger than any single task uses, so tasks differ
#: in content and not only in labels.
_SUPPORT = (
    "ran the incident review that cut repeat pages by half",
    "wrote the migration plan the platform team adopted",
    "owns the service with the best uptime on the roster",
    "trained two engineers who now lead their own teams",
    "found the race condition behind last winter's outage",
    "negotiated the vendor contract down by a fifth",
    "rebuilt the deployment pipeline over one quarter",
    "published the postmortem template everyone now uses",
    "carried the on-call rota through the holiday freeze",
    "shipped the billing rewrite with no customer regressions",
    "cut the median build time from twelve minutes to three",
    "designed the schema the analytics stack still runs on",
    "led the security review that closed nine findings",
    "mentored the intern cohort two years running",
    "turned round the project that had slipped two quarters",
    "halved the cloud bill without dropping a service level",
    "wrote the runbook that got the new region live early",
    "closed the oldest open bug in the tracker after six years",
    "built the load test that caught the launch-day bottleneck",
    "drafted the API guidelines three teams now follow",
    "ran the hiring loop that filled four roles in a month",
    "rescued the data migration after the first attempt failed",
    "automated the release notes the support team relies on",
    "brought the flaky test rate below one percent",
    "set up the alerting that caught the disk failure early",
    "led the accessibility pass that cleared the audit",
    "replaced the legacy queue with zero dropped messages",
    "presented the architecture review the board approved",
    "unblocked the mobile release by fixing the signing chain",
    "kept the payments service up through the traffic spike",
    "wrote the onboarding guide new hires rate highest",
    "cut page load time by forty percent on the main site",
    "ran the chaos drill that exposed the failover gap",
    "coordinated the cross-team freeze with no missed deadline",
    "found and fixed the memory leak in the search service",
    "delivered the reporting dashboard finance asked for",
    "rewrote the permissions model with no access incidents",
    "handled the customer escalation that saved the account",
    "documented the disaster recovery plan end to end",
    "led the vendor evaluation that picked the current CDN",
)

#: Decision-irrelevant mentions. These name an option without being evidence
#: about it, which is what keeps mention counts uninformative.
_NEUTRAL = (
    # Deliberately not "listed alphabetically": that phrase hides the option
    # name "Alpha" inside an ordinary word, which is what `name_hygiene` flags
    # and what this pool got wrong on the first attempt.
    "was listed in name order in the panel packet",
    "appears in the scheduling thread for the debrief",
    "was copied on the original role description",
    "had an interview slot moved for room availability",
    "is mentioned in the budget line for the opening",
    "was on the shortlist circulated before the loop",
    "has a profile in the shared candidate folder",
    "was referenced in the recruiter's weekly update",
    "is named in the room booking for the second loop",
    "shows up in the panel's calendar invitation",
    "was added to the distribution list last Tuesday",
    "has a folder in the shared drive for this role",
    "appears in the agenda for the hiring sync",
    "was mentioned when the timeline was circulated",
    "is listed in the coordinator's tracking sheet",
    "was included in the reminder sent that morning",
    "turns up in the thread about interview logistics",
    "is noted in the printout the panel was handed",
    "was copied on the scheduling correction",
    "appears once in the recruiter's handover notes",
)


#: How many times each agent's private notes name each option, in the clean
#: layout. Chosen for prompt size (about 28 facts per agent's view) before the
#: audit was run on it, not tuned to make it pass; a larger K would lean less.
_K = 6

#: Supporting facts and neutral mentions for the clean layout: each base
#: sentence in three settings, so a task of up to ~50 support facts never repeats
#: one. No setting contains an option name (`name_hygiene`).
_SETTINGS = ("", " during the platform migration", " in the last review cycle")
_FLAT_SUPPORT = tuple(f"{base}{where}" for base in _SUPPORT for where in _SETTINGS)
_FLAT_NEUTRAL = tuple(f"{base}{where}" for base in _NEUTRAL for where in _SETTINGS)

_SPLITS: dict[tuple[int, int], list[tuple[int, int, int]]] = {}


def _splits(total: int, cap: int) -> list[tuple[int, int, int]]:
    """Every way to split ``total`` over three agents with each share in ``0..cap``."""
    key = (total, cap)
    if key not in _SPLITS:
        _SPLITS[key] = [
            (a, b, total - a - b)
            for a in range(cap + 1)
            for b in range(cap + 1)
            if 0 <= total - a - b <= cap
        ]
    return _SPLITS[key]


@dataclass(frozen=True)
class Defect:
    """One planted defect: what it is and which check must catch it."""

    name: str
    description: str
    expected_check: str
    expected_status: str


@dataclass(frozen=True)
class ControlEnv(Environment):
    """A well-formed distributed-information environment, and the defect harness.

    With every flag at its default this environment is intended to pass all
    twelve checks. Each flag plants one defect.

    Attributes:
        leak_decisive_unit: Give one agent a unit that states the answer and
            outweighs every rival, so whoever holds it decides alone.
        gold_leads_mentions: Name the gold option more often than any other, so
            counting names solves the task without reading it.
        gold_only_in_private: Make every one of an agent's private units support
            the gold option, so one agent can answer from its own notes.
        state_objective: When false, the conditions never state the question or
            the scoring rule.
        baseline_extra_change: Change the baseline condition's framing as well
            as its information, while still declaring that only the task
            statement differs.
        over_declare_required: Declare decision-irrelevant units as required.
        lenient_scorer: Accept any answer containing an option name, the v0
            parser's defect (``docs/audit.md`` D1).
        gold_always_first: Put the gold option first in the answer space.
        verbosity_bonus: Add a reward term for long answers.
        single_template: Build every task from the same facts and the same
            support pattern.
        colliding_names: Use option names that hide inside ordinary words, so
            counting a name also counts word fragments.
        legacy_layout: Generate with a layout this control used to have,
            kept as a negative control. ``"gold_only_private_support"`` is the
            pre-A2 layout, the one ``hidden_profile_v2`` uses: all private
            support is for gold. ``"pointer_support"`` is the post-A2 layout:
            each agent also holds more support for one other option, which a
            names-only probe still solves (``docs/review-v0.2.md``, M1).
        leak_fraction: Plant the decisive unit in this fraction of tasks only
            (chosen by seed), so ``leak`` must catch a partial leak.
        gold_least_shared: Leave the gold option out of the shared block, so
            "whatever common ground ignores" answers from one view.
        gold_share_bias: With this probability, give agent 0 the largest
            share of the gold option's support, a graded single-view leak.
    """

    leak_decisive_unit: bool = False
    gold_leads_mentions: bool = False
    gold_only_in_private: bool = False
    state_objective: bool = True
    baseline_extra_change: bool = False
    over_declare_required: bool = False
    lenient_scorer: bool = False
    gold_always_first: bool = False
    verbosity_bonus: bool = False
    single_template: bool = False
    colliding_names: bool = False
    legacy_layout: str = ""
    leak_fraction: float = 0.0
    gold_least_shared: bool = False
    gold_share_bias: float = 0.0

    name: str = "control"
    version: str = "1"

    #: The question and rule, stated verbatim in both conditions by default.
    QUESTION = "Which candidate has the most supporting facts behind them?"
    RULE = (
        "each fact describing something a candidate did counts as one supporting "
        "fact for that candidate, and the candidate with the most wins."
    )

    def seed_split(self) -> SeedSplit:
        """Disjoint seeds: 0-799 train, 1000-1199 eval, 900-949 pilot."""
        return SeedSplit(train=range(0, 800), eval=range(1000, 1200), pilot=range(900, 950))

    def generate(self, seed: int) -> DistributedTask:
        """Generate one task deterministically from ``seed``."""
        if self.legacy_layout:
            return self._generate_legacy(seed, self.legacy_layout)
        return self._generate_flat(seed)

    def _plants_leak(self, seed: int) -> bool:
        """Whether this seed's task carries the decisive unit."""
        if self.leak_decisive_unit:
            return True
        return random.Random(seed * 31 + 7).random() < self.leak_fraction

    def _generate_flat(self, seed: int) -> DistributedTask:
        """The clean layout: flat names, a fixed winning margin, random splits.

        Every agent's private notes name every option exactly ``K`` times, as
        support facts plus neutral mentions, and the shared block supports and
        names every option equally. So no name count, in any block, says
        anything. The totals are fixed at ``t + 1`` for gold and ``t`` for each
        other option, and each option's total is split over the three agents
        uniformly at random among the splits with every share in ``0..K``.

        It cannot make one view uninformative: when the answer is the argmax of
        summed evidence, some view always leans towards gold
        (``docs/audit-battery.md``, "Why a pass is a bound"). This construction
        keeps the lean to what a margin of one fact forces. The exact
        Bayes-optimal accuracy from one view is computed in
        ``tests/test_audit.py::TestTheControlsSingleViewBound`` and stated in
        ``docs/audit-battery.md``.
        """
        rng = random.Random(seed if not self.single_template else 0)
        K = _K
        pool = _COLLIDING_NAMES if self.colliding_names else _NAMES
        options = list(rng.sample(pool, 4))
        gold, decoy, other, spare = options
        if self.gold_always_first:
            options = [gold, decoy, other, spare]
        else:
            rng.shuffle(options)

        t = rng.randint(K, 2 * K)
        shared_support = {o: 1 for o in options}
        totals = {o: t for o in options}
        totals[gold] = t + 1
        if self.gold_least_shared:
            shared_support[gold] = 0
            totals[gold] += 1  # carried privately instead, so gold still wins by one
        shares: dict[str, tuple[int, ...]] = {}
        for o in options:
            splits = _splits(totals[o], K)
            if o == gold and self.gold_share_bias and rng.random() < self.gold_share_bias:
                splits = [c for c in splits if c[0] > max(c[1:])] or splits
            shares[o] = rng.choice(splits)

        support = rng.sample(_FLAT_SUPPORT, len(_FLAT_SUPPORT))
        neutral = rng.sample(_FLAT_NEUTRAL, len(_FLAT_NEUTRAL))
        counter = {"s": 0, "n": 0}

        def fact(who: str, *, supports: bool, uid: str) -> InfoUnit:
            pool_, key = (support, "s") if supports else (neutral, "n")
            text = f"{who} {pool_[counter[key] % len(pool_)]}."
            counter[key] += 1
            return InfoUnit(uid, text, who if supports else None)

        shared_units: list[InfoUnit] = []
        for o in options:
            for j in range(shared_support[o]):
                shared_units.append(fact(o, supports=True, uid=f"s{o}{j}"))
            if not shared_support[o]:
                shared_units.append(fact(o, supports=False, uid=f"s{o}n"))
        rng.shuffle(shared_units)

        views: list[AgentView] = []
        required: list[str] = []
        over_declared: list[str] = []
        for agent_id in range(3):
            private: list[InfoUnit] = []
            for o in options:
                n_support = shares[o][agent_id]
                for j in range(n_support):
                    unit = fact(o, supports=True, uid=f"a{agent_id}{o}s{j}")
                    private.append(unit)
                    if o == gold:
                        required.append(unit.unit_id)
                for j in range(K - n_support):
                    unit = fact(o, supports=False, uid=f"a{agent_id}{o}n{j}")
                    private.append(unit)
                    over_declared.append(unit.unit_id)
            if self.gold_only_in_private:
                private = [u for u in private if u.supports == gold]
            if self.gold_leads_mentions:
                private += [fact(gold, supports=False, uid=f"a{agent_id}x{j}") for j in range(2)]
            if agent_id == 0 and self._plants_leak(seed):
                private.append(InfoUnit(
                    "leak0", f"The panel has already settled on {gold} as the hire.", gold,
                    weight=float(sum(totals.values()) + 4),
                ))
            rng.shuffle(private)
            views.append(AgentView(agent_id=agent_id, shared=tuple(shared_units),
                                   private=tuple(private)))

        declared = tuple(required)
        if self.over_declare_required:
            declared = declared + tuple(over_declared)
        return DistributedTask(
            task_id=f"{self.name}-{seed}",
            objective=Objective(question=self.QUESTION, scoring_rule=self.RULE),
            answer_space=tuple(options),
            gold_answer=gold,
            views=tuple(views),
            required_units=declared,
            scorer=_lenient_scorer if self.lenient_scorer else _control_scorer(self),
            metadata={"seed": seed, "decoy_option": decoy, "t": t, "layout": "flat"},
        )

    def _generate_legacy(self, seed: int, variant: str) -> DistributedTask:
        """A layout this control used to have, kept as a negative control."""
        if variant not in ("gold_only_private_support", "pointer_support"):
            raise ValueError(f"unknown legacy layout {variant!r}")
        rng = random.Random(seed if not self.single_template else 0)
        n_agents = 3

        pool = _COLLIDING_NAMES if self.colliding_names else _NAMES
        options = list(rng.sample(pool, 4))
        gold, decoy, other, spare = options
        if self.gold_always_first:
            options = [gold, decoy, other, spare]
        else:
            rng.shuffle(options)

        # `rounds` gold-supporting units per agent, varied so the support
        # pattern differs across seeds. The decoy always sits exactly one behind
        # in total, which makes every gold unit load-bearing.
        #
        # Each agent also privately holds rounds + 1 supporting facts for one
        # non-gold option (its "pointer"), so applying the scoring rule to its
        # own private facts alone names the pointer, not the answer. The decoy's
        # shared support is reduced by its private share to keep the totals.
        # With `private_support_all_gold` the pointer gets no private support:
        # the layout that hid the gap the v2 eval found.
        planted = variant == "gold_only_private_support"
        if planted:
            rounds = 1 if self.single_template else rng.choice([1, 2])
        else:
            rounds = 2 if self.single_template else rng.choice([2, 3])
        pointer_support = 0 if planted else rounds + 1
        n_gold = n_agents * rounds
        n_decoy = n_gold - 1 - pointer_support

        support_pool = list(rng.sample(_SUPPORT, len(_SUPPORT)))
        neutral_pool = list(rng.sample(_NEUTRAL, len(_NEUTRAL)))
        fact_i = 0
        neutral_i = 0

        def support_fact(who: str) -> str:
            nonlocal fact_i
            text = f"{who} {support_pool[fact_i % len(support_pool)]}."
            fact_i += 1
            return text

        def neutral_fact(who: str) -> str:
            nonlocal neutral_i
            text = f"{who} {neutral_pool[neutral_i % len(neutral_pool)]}."
            neutral_i += 1
            return text

        # --- Shared block: the decoy leads on common ground -----------------
        shared_units: list[InfoUnit] = []
        for _ in range(n_decoy):
            shared_units.append(
                InfoUnit(f"s{len(shared_units)}", support_fact(decoy), decoy)
            )
        shared_units.append(InfoUnit(f"s{len(shared_units)}", support_fact(other), other))
        # Neutral mentions keep the mention counts away from the gold option.
        for who in (spare, spare, other, decoy):
            shared_units.append(InfoUnit(f"s{len(shared_units)}", neutral_fact(who), None))
        # --- Private blocks: gold support, but never a block only about gold --
        views: list[AgentView] = []
        required: list[str] = []
        over_declared: list[str] = []
        for agent_id in range(n_agents):
            private: list[InfoUnit] = []
            for r in range(rounds):
                unit = InfoUnit(f"a{agent_id}g{r}", support_fact(gold), gold)
                private.append(unit)
                required.append(unit.unit_id)
            # Private support and neutral mentions for one non-gold option, so
            # this agent's own notes point somewhere other than the answer.
            pointer = (decoy, other, spare)[agent_id % 3]
            for j in range(pointer_support):
                private.append(
                    InfoUnit(f"a{agent_id}p{j}", support_fact(pointer), pointer)
                )
            for j in range(rounds + 1):
                unit = InfoUnit(f"a{agent_id}n{j}", neutral_fact(pointer), None)
                private.append(unit)
                over_declared.append(unit.unit_id)
            if self.gold_only_in_private:
                private = [u for u in private if u.supports == gold]
            if self.gold_leads_mentions:
                private.append(
                    InfoUnit(f"a{agent_id}x0", neutral_fact(gold), None)
                )
                private.append(
                    InfoUnit(f"a{agent_id}x1", neutral_fact(gold), None)
                )
            if agent_id == 0 and self._plants_leak(seed):
                private.append(
                    InfoUnit(
                        "leak0",
                        f"The panel has already settled on {gold} as the hire.",
                        gold,
                        weight=float(n_gold + n_decoy + 1),
                    )
                )
            views.append(AgentView(agent_id=agent_id, shared=(), private=tuple(private)))

        # --- Equalise mention counts ----------------------------------------
        # Counting option names must be uninformative, in both directions. It is
        # not enough to stop the gold option being the most-named: overshoot and
        # it becomes the least-named, which is exactly as cheap to exploit.
        # Padding goes in the shared block, where it cannot tilt any one agent's
        # private view.
        mentioned: dict[str, int] = {option: 0 for option in options}
        for unit in list(shared_units) + [u for v in views for u in v.private]:
            for option in options:
                mentioned[option] += unit.text.count(option)
        target = max(mentioned.values())
        if not self.gold_leads_mentions:
            for option in options:
                for _ in range(target - mentioned[option]):
                    shared_units.append(
                        InfoUnit(f"s{len(shared_units)}", neutral_fact(option), None)
                    )
        shared = tuple(shared_units)
        views = [replace(view, shared=shared) for view in views]

        declared = tuple(required)
        if self.over_declare_required:
            declared = declared + tuple(over_declared)

        return DistributedTask(
            task_id=f"{self.name}-{seed}",
            objective=Objective(question=self.QUESTION, scoring_rule=self.RULE),
            answer_space=tuple(options),
            gold_answer=gold,
            views=tuple(views),
            required_units=declared,
            scorer=_lenient_scorer if self.lenient_scorer else _control_scorer(self),
            metadata={"seed": seed, "decoy_option": decoy, "rounds": rounds},
        )

    def conditions(self, task: DistributedTask) -> Mapping[str, Condition]:
        """Two arms: a full-information baseline and a communicating team.

        The arms differ by the one line declaring which it is, which each one
        declares via ``expected_diff`` so the condition-diff check can verify it.
        """
        statement = task.objective.statement()
        header = statement + "\n\n" if self.state_objective else ""
        options = ", ".join(task.answer_space)
        tail = f"\n\nChoose exactly one of: {options}."

        baseline_marker = "You hold every fact; there is nobody to consult."
        team_marker = "You hold some facts; your teammates hold others."

        # The baseline is presentation-matched on purpose: same section labels,
        # same layout, same answer instruction as the team arm, so the only
        # framing difference is the one line saying which arm it is. The v0 audit
        # reached the same conclusion the hard way (L4) and had to rerun the
        # baseline to get a comparison that isolated information access.
        full = task.full_view()
        matched_full = AgentView(agent_id=0, shared=full.shared, private=full.private)
        baseline_body = header + matched_full.render() + tail
        baseline = baseline_marker + "\n\n" + baseline_body
        if self.baseline_extra_change:
            baseline = (
                "You are a seasoned hiring manager. Think it through, then answer.\n\n"
                + baseline_marker
                + "\n\n"
                + baseline_body.replace("Facts available to you", "All available facts")
            )

        team = tuple(
            team_marker + "\n\n" + header + view.render() + tail for view in task.views
        )
        return {
            "full_info": Condition(
                name="full_info",
                description="one agent holding every fact",
                prompts=(baseline,),
                expected_diff={"communication": baseline_marker},
            ),
            "communication": Condition(
                name="communication",
                description="three agents, each holding part of the evidence",
                prompts=team,
                expected_diff={"full_info": team_marker},
            ),
        }

    def config_summary(self) -> Mapping[str, object]:
        """Only the flags that are set, so a card says what was planted."""
        return {
            f: getattr(self, f)
            for f in self.__dataclass_fields__
            if f not in ("name", "version") and getattr(self, f) != _DEFAULTS[f]
        }


def _control_scorer(env: ControlEnv) -> object:
    """The control's scorer: strict, optionally with a verbosity bonus planted."""
    if not env.verbosity_bonus:
        from grapevine.protocol import exact_match

        return exact_match

    def verbosity_scorer(answer: str | None, task: DistributedTask) -> ScoreResult:
        """Strict correctness, plus a bonus for how much the policy wrote.

        A shaping term exactly like this is a common way to encourage agents to
        "show their reasoning". It is also collectable without answering.
        """
        from grapevine.protocol import exact_match

        base = exact_match(answer, task)
        bonus = min(1.0, len(answer or "") / 400.0)
        return ScoreResult(
            base.answer,
            base.correct,
            base.reward + bonus,
            {**dict(base.detail), "verbosity_bonus": bonus},
        )

    return verbosity_scorer


def _lenient_scorer(answer: str | None, task: DistributedTask) -> ScoreResult:
    """Accept any answer that mentions the gold option anywhere.

    This reproduces the v0 parser's defect (``docs/audit.md`` D1): substring
    matching in both directions, so prose, a fragment or an empty string can all
    resolve to an option.
    """
    if answer is None:
        return ScoreResult(None, False, 0.0, {"reason": "no answer"})
    text = answer.strip().lower()
    if not text:
        # The v0 bug exactly: an empty answer matched the first option.
        chosen = task.answer_space[0]
    else:
        chosen = next(
            (o for o in task.answer_space if o.lower() in text or text in o.lower()),
            "",
        )
    correct = chosen == task.gold_answer
    return ScoreResult(answer, correct, 1.0 if correct else 0.0, {"resolved_to": chosen})


_DEFAULTS = {
    f.name: f.default for f in ControlEnv.__dataclass_fields__.values()  # type: ignore[union-attr]
}

#: The clean control: every check should pass against it.
CLEAN_CONTROL = ControlEnv()

#: One fixture per planted defect, with the check that must catch it.
FLAWED_ENVS: dict[str, tuple[ControlEnv, Defect]] = {
    "answer_leak": (
        ControlEnv(name="flawed_answer_leak", leak_decisive_unit=True),
        Defect(
            "answer_leak",
            "one agent holds a unit that states the answer and outweighs every rival",
            "leak",
            "fail",
        ),
    ),
    "mention_count_shortcut": (
        ControlEnv(name="flawed_mention_shortcut", gold_leads_mentions=True),
        Defect(
            "mention_count_shortcut",
            "the gold option is named more often than any other, so counting names solves it",
            "shortcuts",
            "fail",
        ),
    ),
    "solo_solvable": (
        ControlEnv(name="flawed_solo_solvable", gold_only_in_private=True),
        Defect(
            "solo_solvable",
            "every private unit supports the gold option, so one agent can answer alone",
            "solo_solvability",
            "fail",
        ),
    ),
    "unstated_objective": (
        ControlEnv(name="flawed_unstated_objective", state_objective=False),
        Defect(
            "unstated_objective",
            "no condition tells the agents the question or the scoring rule",
            "objective",
            "fail",
        ),
    ),
    "mismatched_baseline": (
        ControlEnv(name="flawed_mismatched_baseline", baseline_extra_change=True),
        Defect(
            "mismatched_baseline",
            "the baseline arm differs in framing and layout as well as in information, "
            "while still declaring one difference",
            "condition_diff",
            "fail",
        ),
    ),
    "redundant_required": (
        ControlEnv(name="flawed_redundant_required", over_declare_required=True),
        Defect(
            "redundant_required",
            "decision-irrelevant units are declared required",
            "minimality",
            "warn",
        ),
    ),
    "lenient_scorer": (
        ControlEnv(name="flawed_lenient_scorer", lenient_scorer=True),
        Defect(
            "lenient_scorer",
            "the scorer accepts any answer containing an option name",
            "scorer_fuzz",
            "fail",
        ),
    ),
    "position_correlated_gold": (
        ControlEnv(name="flawed_gold_first", gold_always_first=True),
        Defect(
            "position_correlated_gold",
            "the gold option is always listed first",
            "balance",
            "warn",
        ),
    ),
    "verbosity_shaping": (
        ControlEnv(name="flawed_verbosity_bonus", verbosity_bonus=True),
        Defect(
            "verbosity_shaping",
            "the reward adds a bonus for long answers, collectable without answering",
            "reward_hacking",
            "fail",
        ),
    ),
    "colliding_names": (
        ControlEnv(name="flawed_colliding_names", colliding_names=True),
        Defect(
            "colliding_names",
            "option names also occur inside ordinary words, so any name-matching "
            "measurement counts word fragments",
            "name_hygiene",
            "warn",
        ),
    ),
    "legacy_gold_only_private_support": (
        ControlEnv(name="flawed_legacy_pre_a2", legacy_layout="gold_only_private_support"),
        Defect(
            "legacy_gold_only_private_support",
            "the pre-A2 control layout (v2's): every private supporting fact favours "
            "gold, so scoring one's own private facts answers alone",
            "solo_solvability",
            "fail",
        ),
    ),
    "legacy_pointer_support": (
        ControlEnv(name="flawed_legacy_post_a2", legacy_layout="pointer_support"),
        Defect(
            "legacy_pointer_support",
            "the post-A2 control layout: each agent's notes name gold and one other "
            "option, the other always more, so a names-only probe answers alone",
            "solo_solvability",
            "fail",
        ),
    ),
    "gold_least_shared": (
        ControlEnv(name="flawed_gold_least_shared", gold_least_shared=True),
        Defect(
            "gold_least_shared",
            "the gold option is the one the shared facts leave out",
            "solo_solvability",
            "fail",
        ),
    ),
    "gold_share_bias": (
        ControlEnv(name="flawed_gold_share_bias", gold_share_bias=1.0),
        Defect(
            "gold_share_bias",
            "agent 0 always holds the largest share of the gold option's support",
            "solo_solvability",
            "fail",
        ),
    ),
    "partial_leak_0_05": (
        ControlEnv(name="flawed_partial_leak_0_05", leak_fraction=0.05),
        Defect(
            "partial_leak_0_05",
            "a decisive unit in about 5% of tasks only",
            "leak",
            "fail",
        ),
    ),
    "partial_leak_0_1": (
        ControlEnv(name="flawed_partial_leak_0_1", leak_fraction=0.1),
        Defect(
            "partial_leak_0_1",
            "a decisive unit in about 10% of tasks only",
            "leak",
            "fail",
        ),
    ),
    "partial_leak_0_2": (
        ControlEnv(name="flawed_partial_leak_0_2", leak_fraction=0.2),
        Defect(
            "partial_leak_0_2",
            "a decisive unit in about 20% of tasks only",
            "leak",
            "fail",
        ),
    ),
    "one_puzzle": (
        ControlEnv(name="flawed_one_puzzle", single_template=True),
        Defect(
            "one_puzzle",
            "every seed produces the same facts and the same support pattern",
            "diversity",
            "warn",
        ),
    ),
}
