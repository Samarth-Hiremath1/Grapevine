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
        private_support_all_gold: Give agents private support for the gold
            option only, the layout ``hidden_profile_v2`` uses. Scoring one's
            own private facts then names the answer, even though name counts
            are equalised (``studies/v2_eval/h1_investigation.md``).
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
    private_support_all_gold: bool = False

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
        planted = self.private_support_all_gold
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
            if self.leak_decisive_unit and agent_id == 0:
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
    "private_support_all_gold": (
        ControlEnv(name="flawed_private_support", private_support_all_gold=True),
        Defect(
            "private_support_all_gold",
            "every private supporting fact favours the gold option, so an agent that "
            "scores only its own private facts answers alone, though name counts are equal",
            "solo_solvability",
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
