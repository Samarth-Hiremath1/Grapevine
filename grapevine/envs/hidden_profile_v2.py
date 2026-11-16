"""``hidden_profile_v2``: a hidden-profile environment built to pass its own audit.

Same paradigm as v0 (Stasser & Titus, 1985): the facts every agent already
shares favour a decoy, the facts that make the right option correct are split
one cluster per agent, and the right option only overtakes once all of them are
pooled. What changed is everything the battery found wrong with v0, and each
difference below is traceable to a finding in ``docs/audit.md``.

**Name counting does not work, in either direction** (L3). No sentence leads
with its subject, and every option is named the same number of times in the
full-information view. Decision-irrelevant *mention* sentences -- scheduling,
paperwork, logistics -- pad the counts to equality. Merely stopping the gold
option being the most-named is not enough: overshoot and it becomes the
least-named, which is exactly as cheap to exploit.

**No agent can answer from its own view** (A1). In v0 every private fact
supported the correct option, so "whose name is in my own notes?" was right 200
times out of 200 with no pooling at all. Here each agent's private block also
carries mention sentences about one *non-gold* option, more of them than it has
gold-supporting facts, so its own notes point the wrong way. Applying the
scoring rule to a single view gives the decoy, as it should.

**Tasks differ in more than labels** (L2). Three domains, each with sixteen
supporting and twelve mention sentences, and the number of supporting facts and
the rival options' support both vary by seed, so the support pattern is not one
shape repeated.

**The objective is stated by default** (I1). ``Objective.statement()`` -- the
question *and* the scoring rule -- goes at the top of every prompt in every
condition. ``state_objective=False`` exists only to demonstrate the check that
would catch its absence.

**Agents are symmetric** (L9). Every agent holds the same number of private
units and the same shared block. No agent is systematically better informed.

**Conditions differ by one declared line** (L4). The full-information baseline
is presentation-matched to the team conditions: same section labels, same
layout, same answer instruction. The only framing difference between any two
arms is the single line saying which arm it is, and each arm declares that line
so ``condition_diff`` verifies it rather than taking it on trust.

**Train and eval seeds are declared here** (not a v0 finding, but an RL one).
An RL user cannot train on the seeds they later report, because the split is a
property of the environment rather than of whoever is running it.

Gold labels come from this generator's construction -- support counts it chose
-- and never from a model. The sentence pool was drafted by a model, which
``grapevine/envs/_pool_v2.py`` says plainly, and is frozen and hashed.

The committed Validity Card is ``environments/hidden_profile_v2/validity_card.md``.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from grapevine.envs._pool_v2 import DOMAINS, POOL_SHA256, Domain, pool_digest
from grapevine.protocol import (
    AgentView,
    Condition,
    DistributedTask,
    Environment,
    InfoUnit,
    Objective,
    SeedSplit,
    support_total,
)

__all__ = ["HiddenProfileV2", "HiddenProfileV2Config"]

#: The one line that differs between conditions. Each arm declares its own, and
#: the condition-diff check strips both before looking for anything else.
_MARKERS: dict[str, str] = {
    "full_info": "You hold every fact relevant to this decision; there is nobody to consult.",
    "no_communication": (
        "You hold only part of the evidence and must decide alone: there is no discussion, "
        "and you will never see what the others hold."
    ),
    "communication": (
        "You hold only part of the evidence; your teammates hold the rest, and you can "
        "talk to them before deciding."
    ),
}

_CONDITION_DESCRIPTIONS: dict[str, str] = {
    "full_info": "one agent holding every fact, laid out exactly as the team arms are",
    "no_communication": "every agent decides alone, with no channel",
    "communication": "agents discuss before one of them answers",
}

#: Every prompt in every condition has this shape. Only ``{marker}`` differs
#: between arms; the objective, the context layout and the answer instruction
#: are byte-identical.
_PROMPT = (
    "{marker}\n\n"
    "{objective}"
    "{context}\n\n"
    "Choose exactly one of these options: {options}.\n"
    'Respond with only a JSON object: {{"answer": "<one option exactly as written>"}}.'
)


@dataclass(frozen=True)
class HiddenProfileV2Config:
    """Configuration for :class:`HiddenProfileV2`.

    Attributes:
        n_agents: Number of agents the evidence is split across. At least 2.
        facts_per_agent: Gold-supporting facts each agent privately holds. The
            pooled total is ``n_agents * facts_per_agent``, so every agent holds
            something the team needs and no agent is favoured.
        margin: How far the gold option leads the decoy once everything is
            pooled. **Leave this at 1** unless you know why not: at 1 every
            gold-supporting fact is individually necessary, which is what makes
            ``required_units`` a genuinely minimal set and a surfacing metric
            meaningful. At 2 or more no single fact is required, so the
            environment declares no required units and the minimality check
            reports ``skipped`` rather than passing on a claim it cannot verify.
        n_options: Number of options. At least 3, so there is a rival besides
            the decoy.
        n_rounds: Discussion rounds, for consumers that run episodes. The
            generator does not use it; it is recorded so an RL config and a run
            manifest agree on one value.
        vary_support: Vary the pooled gold support (and so the support pattern)
            across seeds. On by default: without it every task has the same
            shape, which is what made the v0 batch one puzzle in 200
            arrangements.
        state_objective: Put the question and the scoring rule at the top of
            every prompt. **On by default.** Turning it off is only useful for
            demonstrating the check that catches its absence.
        domains: Which domains to draw from, by key. Empty means all of them.
        train_seeds: Seeds available for training.
        eval_seeds: Seeds held out for evaluation.
        pilot_seeds: Seeds for a pilot. Disjointness from the other two is
            enforced in code, not by convention.
    """

    n_agents: int = 3
    facts_per_agent: int = 1
    margin: int = 1
    n_options: int = 4
    n_rounds: int = 2
    vary_support: bool = True
    state_objective: bool = True
    domains: tuple[str, ...] = ()
    train_seeds: range = field(default_factory=lambda: range(0, 8000))
    eval_seeds: range = field(default_factory=lambda: range(10000, 11000))
    pilot_seeds: range = field(default_factory=lambda: range(9000, 9200))

    def __post_init__(self) -> None:
        if self.n_agents < 2:
            raise ValueError("n_agents must be >= 2: one agent is not a distributed task")
        if self.facts_per_agent < 1:
            raise ValueError("facts_per_agent must be >= 1 so every agent holds something needed")
        if self.margin < 1:
            raise ValueError("margin must be >= 1 so the gold option strictly wins once pooled")
        if self.n_options < 3:
            raise ValueError("n_options must be >= 3: gold, a decoy, and at least one rival")
        if self.n_rounds < 1:
            raise ValueError("n_rounds must be >= 1")
        known = {domain.key for domain in DOMAINS}
        unknown = sorted(set(self.domains) - known)
        if unknown:
            raise ValueError(f"unknown domain(s) {unknown}; available: {sorted(known)}")
        # Validate the hardest constraint for every support level a seed could
        # draw, so a bad config fails at construction rather than on some seed.
        for multiplier in self._multipliers():
            gold = self.n_agents * self.facts_per_agent * multiplier
            decoy = gold - self.margin
            per_agent = self.facts_per_agent * multiplier
            if decoy < 1:
                raise ValueError(
                    f"margin={self.margin} leaves the decoy {decoy} supporting facts at "
                    f"gold support {gold}; it needs at least 1 to lead before discussion"
                )
            if decoy <= per_agent:
                raise ValueError(
                    f"with gold support {gold} over {self.n_agents} agents each holds "
                    f"{per_agent} supporting fact(s), which is not fewer than the decoy's "
                    f"{decoy}. A single agent would then not prefer the decoy, so the "
                    "hidden-profile premise fails. Raise n_agents or lower margin."
                )
            if decoy < self.n_options - 2:
                raise ValueError(
                    f"the decoy's {decoy} supporting facts cannot be split into "
                    f"{self.n_options - 2} distinct smaller totals for the remaining "
                    "options; lower n_options or raise facts_per_agent"
                )
            # Content budget. Equalising mention counts needs, in the worst
            # case, `gold + per_agent` mention sentences for one subject: the
            # gold option is named once per supporting fact, and each agent adds
            # one more mention of a non-gold option than it has gold facts.
            # Checked here so an over-ambitious config fails on construction
            # rather than on whichever seed first runs the pool dry.
            available = self._smallest_pools()
            if gold > available[0]:
                raise ValueError(
                    f"gold support {gold} exceeds the {available[0]} supporting sentences "
                    "available in the smallest selected domain; lower facts_per_agent, "
                    "set vary_support=False, or add a domain with a larger pool"
                )
            if gold + per_agent > available[1]:
                raise ValueError(
                    f"equalising mention counts at gold support {gold} would need "
                    f"{gold + per_agent} mention sentences for one subject, but the "
                    f"smallest selected domain has {available[1]}. Lower facts_per_agent, "
                    "set vary_support=False, or add a domain with a larger pool."
                )
        for name_a, a in (("train", self.train_seeds), ("eval", self.eval_seeds)):
            for name_b, b in (("eval", self.eval_seeds), ("pilot", self.pilot_seeds)):
                if name_a != name_b and set(a) & set(b):
                    raise ValueError(f"{name_a} and {name_b} seed ranges overlap")
        if set(self.train_seeds) & set(self.pilot_seeds):
            raise ValueError("train and pilot seed ranges overlap")

    def _smallest_pools(self) -> tuple[int, int]:
        """``(support, mention)`` sentence counts of the smallest selected domain."""
        selected = [d for d in DOMAINS if not self.domains or d.key in self.domains]
        return (
            min(len(d.support) for d in selected),
            min(len(d.mentions) for d in selected),
        )

    def _multipliers(self) -> tuple[int, ...]:
        """Support multipliers a seed may draw. ``(1,)`` when not varying."""
        return (1, 2) if self.vary_support else (1,)


class HiddenProfileV2(Environment):
    """Hidden-profile tasks that pass the validity battery.

    See the module docstring for which v0 finding each design choice answers.
    """

    name = "hidden_profile_v2"
    version = "2"

    def __init__(self, config: HiddenProfileV2Config | None = None) -> None:
        """Create the environment.

        Args:
            config: Configuration. The default is 3 agents, 1 gold-supporting
                fact each, margin 1, 4 options, all three domains.

        Raises:
            RuntimeError: If the frozen sentence pool has been edited without
                its digest being updated.
        """
        self.config = config or HiddenProfileV2Config()
        actual = pool_digest()
        if actual != POOL_SHA256:
            raise RuntimeError(
                "the frozen sentence pool has changed: "
                f"expected {POOL_SHA256}, got {actual}. Every committed run and "
                "Validity Card describes the tasks the old pool produced, so either "
                "revert the edit or publish a new environment version."
            )

    def seed_split(self) -> SeedSplit:
        """The declared train / eval / pilot split, so RL cannot train on eval."""
        return SeedSplit(
            train=self.config.train_seeds,
            eval=self.config.eval_seeds,
            pilot=self.config.pilot_seeds,
        )

    def _domains(self) -> tuple[Domain, ...]:
        """The domains this configuration draws from."""
        if not self.config.domains:
            return DOMAINS
        return tuple(d for d in DOMAINS if d.key in self.config.domains)

    def generate(self, seed: int) -> DistributedTask:
        """Generate one task deterministically from ``seed``.

        Raises:
            ValueError: If a constructed task violates any of the invariants the
                environment claims. This should be impossible; it is checked
                anyway, because a silently invalid task is how v0 went wrong.
        """
        cfg = self.config
        rng = random.Random(seed)
        domain = rng.choice(self._domains())

        options = list(rng.sample(domain.entities, cfg.n_options))
        gold, decoy = rng.sample(options, 2)
        rivals = [o for o in options if o not in (gold, decoy)]
        rng.shuffle(options)

        multiplier = rng.choice(cfg._multipliers())
        per_agent = cfg.facts_per_agent * multiplier
        gold_support = cfg.n_agents * per_agent
        decoy_support = gold_support - cfg.margin
        rival_support = sorted(rng.sample(range(decoy_support), len(rivals)), reverse=True)

        # Sentence selection. A template reused for a different subject is a
        # different sentence, so uniqueness only needs the (template, subject)
        # pair to be fresh. But three suppliers all "doing the integration in
        # two weeks" reads like a template exercise, so a rolling cursor hands
        # out an unused template first and only falls back to reusing one with a
        # new subject when the pool is exhausted.
        support_order = rng.sample(domain.support, len(domain.support))
        mention_order = rng.sample(domain.mentions, len(domain.mentions))
        cursors = {"support": 0, "mention": 0}
        used: set[tuple[str, str]] = set()
        counter = {"n": 0}

        def _unit(entity: str, *, supports: bool) -> InfoUnit:
            kind = "support" if supports else "mention"
            pool = support_order if supports else mention_order
            start = cursors[kind]
            for offset in range(len(pool)):
                index = (start + offset) % len(pool)
                if (pool[index], entity) not in used:
                    used.add((pool[index], entity))
                    cursors[kind] = (index + 1) % len(pool)
                    counter["n"] += 1
                    return InfoUnit(
                        unit_id=f"u{counter['n']:03d}",
                        text=pool[index].format(entity=entity),
                        supports=entity if supports else None,
                    )
            raise ValueError(
                f"domain {domain.key!r} has only {len(pool)} {kind} sentences, all of "
                f"which are already used for {entity!r}: this configuration needs a "
                "larger pool"
            )

        # --- Shared block: every non-gold supporting fact -------------------
        # The gold option gets no shared support, so before anyone speaks the
        # decoy leads on common ground. That is the hidden profile.
        shared_units: list[InfoUnit] = [_unit(decoy, supports=True) for _ in range(decoy_support)]
        for rival, count in zip(rivals, rival_support, strict=True):
            shared_units.extend(_unit(rival, supports=True) for _ in range(count))

        # --- Private blocks -------------------------------------------------
        # Each agent holds `per_agent` gold-supporting facts, plus one more
        # mention sentence about a single non-gold option than that, so its own
        # notes point away from the answer (A1).
        non_gold = [decoy, *rivals]
        views: list[AgentView] = []
        required: list[str] = []
        for agent_id in range(cfg.n_agents):
            private = [_unit(gold, supports=True) for _ in range(per_agent)]
            required.extend(u.unit_id for u in private)
            pointer = non_gold[agent_id % len(non_gold)]
            private.extend(_unit(pointer, supports=False) for _ in range(per_agent + 1))
            rng.shuffle(private)
            views.append(AgentView(agent_id=agent_id, shared=(), private=tuple(private)))

        # --- Equalise mention counts ----------------------------------------
        # Counting option names must be uninformative in both directions, so
        # every option ends up named the same number of times. Padding goes in
        # the shared block, where it cannot tilt any one agent's private view.
        named: dict[str, int] = dict.fromkeys(options, 0)
        for unit in [*shared_units, *(u for v in views for u in v.private)]:
            for option in options:
                named[option] += unit.text.count(option)
        target = max(named.values())
        for option in options:
            shared_units.extend(
                _unit(option, supports=False) for _ in range(target - named[option])
            )

        rng.shuffle(shared_units)
        shared = tuple(shared_units)
        views = [replace(view, shared=shared) for view in views]

        task = DistributedTask(
            task_id=f"{self.name}-{seed}",
            objective=Objective(question=domain.question, scoring_rule=domain.scoring_rule),
            answer_space=tuple(options),
            gold_answer=gold,
            views=tuple(views),
            # With margin > 1 no single fact is individually necessary, so there
            # is no minimal required set to declare and the audit says `skipped`
            # rather than passing on an unverifiable claim.
            required_units=tuple(required) if cfg.margin == 1 else (),
            metadata={
                "family": self.name,
                "version": self.version,
                "seed": seed,
                "domain": domain.key,
                "subject": domain.subject,
                "decoy_option": decoy,
                "gold_support": gold_support,
                "decoy_support": decoy_support,
                "n_rounds": cfg.n_rounds,
                "pool_sha256": POOL_SHA256,
                "mentions_per_option": target,
                "split": self._split_of(seed),
            },
        )
        self._assert_invariants(task, gold_support, decoy_support, per_agent)
        return task

    def _split_of(self, seed: int) -> str:
        """Which declared seed range ``seed`` falls in."""
        if seed in self.config.eval_seeds:
            return "eval"
        if seed in self.config.pilot_seeds:
            return "pilot"
        if seed in self.config.train_seeds:
            return "train"
        return "unassigned"

    def _assert_invariants(
        self,
        task: DistributedTask,
        gold_support: int,
        decoy_support: int,
        per_agent: int,
    ) -> None:
        """Check every property this environment claims, and raise on any failure.

        These are the same properties the audit checks, verified here as well so
        a broken configuration fails at generation rather than producing tasks
        that look fine and measure nothing.
        """
        tid = task.task_id
        options = task.answer_space
        gold = task.gold_answer

        def _unique_leader(units: Any, label: str) -> str:
            totals = support_total(units, options)
            best = max(totals.values())
            leaders = [o for o in options if totals[o] == best]
            if len(leaders) != 1:
                raise ValueError(f"{tid}: {label} support is tied between {leaders}")
            return leaders[0]

        if _unique_leader(task.all_units(), "pooled") != gold:
            raise ValueError(f"{tid}: pooled support does not uniquely favour the gold option")
        decoy = str(task.metadata["decoy_option"])
        if _unique_leader(task.shared_units, "shared-only") != decoy:
            raise ValueError(
                f"{tid}: shared information does not uniquely favour the decoy, so this "
                "is not a hidden profile"
            )

        for view in task.views:
            own = support_total(view.units, options)
            if max(own.values()) == own[gold]:
                raise ValueError(
                    f"{tid}: agent {view.agent_id} can reach the gold option by applying "
                    "the scoring rule to its own view"
                )
            private_named = {o: sum(u.text.count(o) for u in view.private) for o in options}
            if private_named[gold] >= max(private_named.values()):
                raise ValueError(
                    f"{tid}: agent {view.agent_id}'s private units name the gold option "
                    "at least as often as any other, so its own notes point at the answer"
                )

        private_counts = {len(v.private) for v in task.views}
        if len(private_counts) != 1:
            raise ValueError(f"{tid}: agents hold different numbers of private units")

        full_text = task.full_view().render()
        named = {o: full_text.count(o) for o in options}
        if len(set(named.values())) != 1:
            raise ValueError(
                f"{tid}: option mention counts are not equal ({named}), so counting names "
                "carries information about the answer"
            )

        rivals_best = max(
            (v for o, v in support_total(task.all_units(), options).items() if o != gold),
            default=0.0,
        )
        for unit in task.all_units():
            if unit.supports == gold and unit.weight > rivals_best:
                raise ValueError(
                    f"{tid}: unit {unit.unit_id} alone outweighs every rival option, so "
                    "whoever holds it decides the task without pooling"
                )

        if task.required_units:
            for unit_id in task.required_units:
                remaining = [u for u in task.all_units() if u.unit_id != unit_id]
                totals = support_total(remaining, options)
                best = max(totals.values())
                leaders = [o for o in options if totals[o] == best]
                if leaders == [gold]:
                    raise ValueError(
                        f"{tid}: required unit {unit_id} is not load-bearing; the gold "
                        "option still wins without it"
                    )
            if len(task.required_units) != gold_support:
                raise ValueError(f"{tid}: required_units should name all {gold_support} gold facts")

        texts = [u.text for u in task.all_units()]
        if len(set(texts)) != len(texts):
            raise ValueError(f"{tid}: duplicate unit text")
        if decoy_support <= per_agent:
            raise ValueError(f"{tid}: decoy support {decoy_support} does not exceed {per_agent}")

    def conditions(self, task: DistributedTask) -> Mapping[str, Condition]:
        """The three arms, differing by exactly one declared line each.

        The full-information baseline is presentation-matched: it renders the
        pooled units in the same two blocks an agent sees, with the same labels,
        the same answer instruction and the same objective. v0's baseline was
        not, so any gap measured against it mixed information access with
        framing (L4), and the baseline had to be rerun.
        """
        objective = (
            task.objective.statement() + "\n\n" if self.config.state_objective else ""
        )
        options = ", ".join(task.answer_space)

        def _prompt(marker: str, context: str) -> str:
            return _PROMPT.format(
                marker=marker, objective=objective, context=context, options=options
            )

        full = task.full_view()
        # agent_id 0 rather than -1 so the section labels match the team arms.
        matched = AgentView(agent_id=0, shared=full.shared, private=full.private)

        prompts: dict[str, tuple[str, ...]] = {
            "full_info": (_prompt(_MARKERS["full_info"], matched.render()),),
            "no_communication": tuple(
                _prompt(_MARKERS["no_communication"], view.render()) for view in task.views
            ),
            "communication": tuple(
                _prompt(_MARKERS["communication"], view.render()) for view in task.views
            ),
        }
        return {
            name: Condition(
                name=name,
                description=_CONDITION_DESCRIPTIONS[name],
                prompts=prompts[name],
                # Every other arm differs from this one by this arm's marker.
                expected_diff={other: _MARKERS[name] for other in _MARKERS if other != name},
            )
            for name in _MARKERS
        }

    def config_summary(self) -> Mapping[str, Any]:
        """Configuration recorded on the Validity Card."""
        cfg = self.config
        return {
            "n_agents": cfg.n_agents,
            "facts_per_agent": cfg.facts_per_agent,
            "margin": cfg.margin,
            "n_options": cfg.n_options,
            "n_rounds": cfg.n_rounds,
            "vary_support": cfg.vary_support,
            "state_objective": cfg.state_objective,
            "domains": list(cfg.domains) or [d.key for d in DOMAINS],
            "pool_sha256": POOL_SHA256,
        }
