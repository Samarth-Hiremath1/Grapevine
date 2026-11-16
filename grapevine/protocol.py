"""The environment protocol: the one interface you implement to use Grapevine.

A Grapevine environment generates *distributed-information* tasks: tasks where
no single agent holds enough to answer, and the answer only becomes derivable
once information held by different agents is pooled. That premise is what makes
a coordination claim meaningful, and it is also what quietly breaks — an answer
leaks into one agent's view, a content-blind shortcut solves the task, the
objective is never stated. ``grapevine audit`` checks for exactly those
failures, and it can only do so against a task that describes itself.

So the protocol is deliberately a little more explicit than "a prompt and a gold
string". It asks for:

* **Information units** (:class:`InfoUnit`) rather than one blob of text per
  agent, so the audit can remove a unit and ask whether the answer changes.
* **An objective** (:class:`Objective`): the question *and* the scoring rule.
  The v0 case study in ``studies/underspecification/`` exists because neither
  reached the models, which produced a coordination failure that was not one.
* **A programmatic scorer**: :meth:`DistributedTask.score` must decide
  correctness without a model, so the audit can fuzz it and so a reward is
  verifiable.
* **Deterministic generation** from a seed, with the train and eval seed split
  declared by the environment rather than by whoever is training.

The minimum to implement is :class:`Environment` with
:meth:`Environment.generate`. Everything else has a usable default.

Example:
    A two-agent task where neither agent can answer alone::

        import random

        from grapevine import AgentView, DistributedTask, Environment, InfoUnit, Objective

        class Relay(Environment):
            name = "relay"
            version = "1"

            def generate(self, seed: int) -> DistributedTask:
                rng = random.Random(seed)
                options = ("north", "south", "east", "west")
                gold = rng.choice(options)
                # Each agent holds one vote for gold. Neither majority nor
                # either agent alone decides it; both votes are needed.
                units = [
                    InfoUnit(f"u{i}", f"Scout {i} reported the train heading {gold}.", gold)
                    for i in range(2)
                ]
                decoy = rng.choice([o for o in options if o != gold])
                return DistributedTask(
                    task_id=f"relay-{seed}",
                    objective=Objective(
                        question="Which way did the train go?",
                        scoring_rule="The direction with the most scout reports.",
                    ),
                    answer_space=options,
                    gold_answer=gold,
                    views=tuple(
                        AgentView(
                            agent_id=i,
                            shared=(InfoUnit("s0", f"One early report said {decoy}.", decoy),),
                            private=(units[i],),
                        )
                        for i in range(2)
                    ),
                    required_units=("u0", "u1"),
                )
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "AgentView",
    "Condition",
    "DistributedTask",
    "Environment",
    "InfoUnit",
    "Objective",
    "ScoreResult",
    "Scorer",
    "SeedSplit",
    "binomial_tail_p",
    "exact_match",
    "support_total",
]


@dataclass(frozen=True)
class InfoUnit:
    """One atomic piece of information an agent can hold and share.

    Units rather than free text are what let the audit reason about a task:
    minimality removes one unit at a time, the leak check looks for a unit that
    settles the answer on its own, and the diversity check counts distinct unit
    text across seeds.

    Attributes:
        unit_id: Unique within a task. Stable across regenerations of the same
            seed.
        text: The sentence an agent sees and may share.
        supports: The option this unit is evidence for, or ``None`` for a
            decision-irrelevant distractor. Must be in the task's answer space
            when set.
        weight: How much evidence the unit carries for ``supports``. The default
            scoring rule sums weights per option.
    """

    unit_id: str
    text: str
    supports: str | None = None
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.unit_id:
            raise ValueError("unit_id must be non-empty")
        if not self.text:
            raise ValueError(f"unit {self.unit_id!r} has empty text")

    @property
    def is_distractor(self) -> bool:
        """True when the unit supports no option."""
        return self.supports is None


@dataclass(frozen=True)
class Objective:
    """What the team is asked, and how its answer is scored.

    Both halves are required, and :meth:`statement` is what an environment
    should put in front of a model. An evaluation that withholds either can
    produce a coordination failure that disappears once they are stated: see
    ``studies/underspecification/``.

    Attributes:
        question: The question posed to the team.
        scoring_rule: How a correct answer is determined, in the same words a
            model could act on. Not "accuracy" -- the actual rule, e.g. "the
            strongest candidate is the one with the most supporting facts".
    """

    question: str
    scoring_rule: str

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ValueError("objective.question must be non-empty")
        if not self.scoring_rule.strip():
            raise ValueError(
                "objective.scoring_rule must be non-empty: an environment that "
                "cannot state how it scores cannot tell its agents what to do"
            )

    def statement(self) -> str:
        """The objective as a block to place at the top of a prompt."""
        return f"Task: {self.question}\nDecision rule: {self.scoring_rule}"


@dataclass(frozen=True)
class AgentView:
    """What one agent holds at the start of an episode.

    Attributes:
        agent_id: Zero-based index, or ``-1`` for the synthetic full-information
            view returned by :meth:`DistributedTask.full_view`.
        shared: Units every agent holds. Must be identical across the views of
            one task; the audit validates this.
        private: Units only this agent holds.
    """

    agent_id: int
    shared: tuple[InfoUnit, ...] = ()
    private: tuple[InfoUnit, ...] = ()

    @property
    def units(self) -> tuple[InfoUnit, ...]:
        """Every unit this agent holds, shared first."""
        return self.shared + self.private

    def render(self) -> str:
        """The view as the text an agent is shown.

        Shared and private units are labelled separately, because an agent that
        cannot tell which of its facts the others already have cannot know what
        is worth saying.
        """
        blocks = []
        if self.shared:
            blocks.append(
                "Facts known to everyone:\n" + "\n".join(f"- {u.text}" for u in self.shared)
            )
        if self.private:
            label = "Facts available to you" if self.agent_id < 0 else "Facts only you know"
            blocks.append(f"{label}:\n" + "\n".join(f"- {u.text}" for u in self.private))
        return "\n\n".join(blocks)


@dataclass(frozen=True)
class ScoreResult:
    """The outcome of scoring one answer.

    Attributes:
        answer: The answer as scored, or ``None`` if nothing was parsed.
        correct: Whether it counts as correct.
        reward: Scalar reward, ``1.0``/``0.0`` for the default exact-match
            scorer. This is what RL optimises, so it is kept separate from
            ``correct`` for scorers that award partial credit.
        detail: Scorer-specific explanation, included in audit output.
    """

    answer: str | None
    correct: bool
    reward: float
    detail: Mapping[str, Any] = field(default_factory=dict)


#: A scorer decides correctness programmatically, with no model in the loop.
#: It receives the answer exactly as parsed -- possibly ``None`` -- and the task.
Scorer = Callable[[str | None, "DistributedTask"], ScoreResult]


def exact_match(answer: str | None, task: DistributedTask) -> ScoreResult:
    """Accept an answer only when it is exactly one option, and that option is gold.

    Surrounding whitespace is stripped; nothing else is forgiven. No substring
    matching, no case folding, no "the answer is X" extraction. Parsing a
    model's prose into an option is the harness's job, and a scorer that also
    guesses is a scorer that can be hacked: in the v0 audit a lenient matcher
    resolved ``""``, ``"A"`` and ``"y"`` to the first option, a silent bias
    toward whatever was listed first (``docs/audit.md`` D1).

    Args:
        answer: The parsed answer, or ``None``.
        task: The task being scored.

    Returns:
        A :class:`ScoreResult`. ``reward`` is 1.0 for a correct answer, else 0.0.
    """
    if answer is None:
        return ScoreResult(None, False, 0.0, {"reason": "no answer parsed"})
    stripped = answer.strip()
    if stripped not in task.answer_space:
        return ScoreResult(
            answer, False, 0.0, {"reason": "not exactly one option", "stripped": stripped}
        )
    correct = stripped == task.gold_answer
    return ScoreResult(
        answer, correct, 1.0 if correct else 0.0, {"reason": "exact option match"}
    )


@dataclass(frozen=True)
class Condition:
    """One experimental arm, and the prompts it sends.

    The audit uses conditions for two checks it cannot otherwise run: whether
    each arm actually states the objective, and what differs between a pair of
    arms beyond the manipulation under test. Both were real v0 findings.

    Only the *opening* prompts are rendered. Later turns embed a transcript that
    does not exist before a rollout, and the two checks do not need one.

    Attributes:
        name: Short identifier, e.g. ``"no_communication"``.
        description: One line on what the arm manipulates.
        prompts: The opening prompt for each model call the arm makes, in call
            order, with system and user text joined as it reaches the model.
        expected_diff: Maps another condition's name to the single substring
            that should be the *only* difference from it. The condition-diff
            check fails when anything else differs. Pairs left undeclared are
            reported rather than failed.
    """

    name: str
    description: str
    prompts: tuple[str, ...]
    expected_diff: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SeedSplit:
    """Disjoint seed ranges for training and evaluation.

    Declared by the environment, not by whoever is training, so an RL run cannot
    accidentally train on the tasks it reports. :meth:`validate` is called on
    construction and refuses any overlap.

    Attributes:
        train: Seeds available for training.
        eval: Seeds held out for evaluation.
        pilot: Seeds for a pilot, disjoint from both. Pre-registration requires
            pilot and primary seeds to be disjoint and enforced in code, not by
            convention (``CLAUDE.md`` rule 4).
    """

    train: range
    eval: range
    pilot: range = range(0)

    def __post_init__(self) -> None:
        named = (("train", self.train), ("eval", self.eval), ("pilot", self.pilot))
        for i, (name_a, a) in enumerate(named):
            for name_b, b in named[i + 1 :]:
                overlap = set(a) & set(b)
                if overlap:
                    raise ValueError(
                        f"{name_a} and {name_b} seeds overlap in "
                        f"{len(overlap)} place(s), e.g. {min(overlap)}"
                    )

    def holds_out(self, seed: int) -> bool:
        """True when ``seed`` is an evaluation seed."""
        return seed in self.eval


@dataclass(frozen=True)
class DistributedTask:
    """One distributed-information task.

    Attributes:
        task_id: Unique and stable for a given environment and seed.
        objective: The question and the scoring rule.
        answer_space: The options; the team selects exactly one.
        gold_answer: The correct option, from the environment's own
            construction. Never a model's label (``CLAUDE.md`` rule 8).
        views: One view per agent, in agent order. At least two -- a task only
            one agent can see is not distributed.
        required_units: Ids of the units that must all be pooled for the answer
            to be derivable. Empty when the environment does not claim a minimal
            set, which makes the minimality check report ``skipped``.
        scorer: How an answer is scored. Defaults to :func:`exact_match`.
        metadata: Environment-specific extras. Never needed for scoring.
    """

    task_id: str
    objective: Objective
    answer_space: tuple[str, ...]
    gold_answer: str
    views: tuple[AgentView, ...]
    required_units: tuple[str, ...] = ()
    scorer: Scorer = exact_match
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.answer_space) < 2:
            raise ValueError(f"{self.task_id}: answer_space needs at least 2 options")
        if len(set(self.answer_space)) != len(self.answer_space):
            raise ValueError(f"{self.task_id}: answer_space has duplicate options")
        if self.gold_answer not in self.answer_space:
            raise ValueError(
                f"{self.task_id}: gold_answer {self.gold_answer!r} is not in answer_space"
            )
        if len(self.views) < 2:
            raise ValueError(
                f"{self.task_id}: a distributed task needs at least 2 agent views; "
                "a single-agent view is a baseline condition, not a task"
            )
        ids = [u.unit_id for v in self.views for u in v.private] + [
            u.unit_id for u in self.views[0].shared
        ]
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            raise ValueError(f"{self.task_id}: duplicate unit ids {sorted(duplicates)}")
        shared = self.views[0].shared
        for view in self.views[1:]:
            if view.shared != shared:
                raise ValueError(
                    f"{self.task_id}: agent {view.agent_id}'s shared units differ from "
                    "agent 0's. Units every agent holds go in `shared`; anything else "
                    "is private to an agent."
                )
        known = set(ids)
        unknown = [u for u in self.required_units if u not in known]
        if unknown:
            raise ValueError(f"{self.task_id}: required_units names unknown units {unknown}")
        for unit in self.all_units():
            if unit.supports is not None and unit.supports not in self.answer_space:
                raise ValueError(
                    f"{self.task_id}: unit {unit.unit_id!r} supports "
                    f"{unit.supports!r}, which is not an option"
                )

    @property
    def n_agents(self) -> int:
        """Number of agents the task is distributed across."""
        return len(self.views)

    @property
    def shared_units(self) -> tuple[InfoUnit, ...]:
        """The units every agent holds."""
        return self.views[0].shared

    def all_units(self) -> tuple[InfoUnit, ...]:
        """Every unit in the task: shared once, then each agent's private units."""
        return self.shared_units + tuple(u for v in self.views for u in v.private)

    def unit(self, unit_id: str) -> InfoUnit:
        """Look up a unit by id.

        Raises:
            KeyError: If no unit has that id.
        """
        for unit in self.all_units():
            if unit.unit_id == unit_id:
                return unit
        raise KeyError(f"{self.task_id}: no unit {unit_id!r}")

    def full_view(self) -> AgentView:
        """The single-agent, full-information view: every unit, once.

        Used for the full-information baseline and for the solvability checks.
        Its ``agent_id`` is ``-1``, since no agent in the task holds it.
        """
        return AgentView(
            agent_id=-1,
            shared=self.shared_units,
            private=tuple(u for v in self.views for u in v.private),
        )

    def score(self, answer: str | None) -> ScoreResult:
        """Score an answer programmatically, with no model in the loop."""
        return self.scorer(answer, self)

    @property
    def chance(self) -> float:
        """Accuracy of guessing uniformly at random."""
        return 1.0 / len(self.answer_space)


def support_total(units: Iterable[InfoUnit], answer_space: Sequence[str]) -> dict[str, float]:
    """Total supporting weight per option over ``units``.

    This is the reference solver: the computation the default scoring rule
    describes. Distractors contribute nothing.
    """
    totals = {option: 0.0 for option in answer_space}
    for unit in units:
        if unit.supports is not None:
            totals[unit.supports] += unit.weight
    return totals


class Environment(ABC):
    """A deterministic generator of distributed-information tasks.

    Subclasses must set :attr:`name` and :attr:`version` and implement
    :meth:`generate`. Everything else has a default.

    :attr:`version` matters more than it looks: a committed run is only
    reproducible while the generator that produced it is unchanged, so an
    environment whose generation changes gets a new version (or a new name)
    rather than an edit. See ``CLAUDE.md`` rule 6.
    """

    #: Short identifier, used on the command line and in run manifests.
    name: str = ""

    #: Generation version. Bump it rather than changing how existing seeds
    #: generate, or committed runs stop reproducing from the code.
    version: str = "1"

    @abstractmethod
    def generate(self, seed: int) -> DistributedTask:
        """Generate one task deterministically from ``seed``.

        The same seed must always give a byte-identical task. The audit relies
        on it, and so does every paired comparison between conditions.
        """
        raise NotImplementedError

    def generate_batch(self, n: int, seed: int = 0) -> list[DistributedTask]:
        """Generate ``n`` tasks from consecutive seeds starting at ``seed``."""
        if n < 0:
            raise ValueError("n must be non-negative")
        return [self.generate(seed + i) for i in range(n)]

    def seed_split(self) -> SeedSplit | None:
        """Declared train / eval (and optionally pilot) seed ranges.

        Returning ``None`` means the environment declares no split, and the
        audit says so: an RL user then has nothing stopping them from training
        on the seeds they later report.
        """
        return None

    def conditions(self, task: DistributedTask) -> Mapping[str, Condition]:
        """The opening prompts each experimental arm sends for ``task``.

        An environment that does not describe its conditions returns ``{}``, and
        the objective and condition-diff checks are reported as ``skipped``
        rather than passed -- they were not run, which is not the same as
        nothing being wrong.
        """
        return {}

    def config_summary(self) -> Mapping[str, Any]:
        """Configuration worth recording on a Validity Card.

        The default reflects a ``config`` attribute when there is one.
        """
        config = getattr(self, "config", None)
        if config is None:
            return {}
        if hasattr(config, "__dataclass_fields__"):
            return {f: getattr(config, f) for f in config.__dataclass_fields__}
        return {}

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name} v{self.version}>"


def binomial_tail_p(k: int, n: int, p: float) -> float:
    """One-sided p-value for ``k`` or more successes in ``n`` trials under ``p``.

    Exact, so it behaves at the extremes where a normal approximation does not
    -- the v0 audit found bootstrap intervals collapsing to zero width on an
    all-one-value sample (``docs/audit.md`` L6). Used by the audit to ask
    whether a shortcut beats chance.
    """
    if n <= 0:
        return 1.0
    k = max(0, min(k, n))
    if k == 0:
        return 1.0
    if not 0.0 < p < 1.0:
        return 1.0 if p >= 1.0 else 0.0
    # Log space throughout: math.comb(20000, 5000) overflows a float, and the
    # battery is run over tens of thousands of tasks when checking a generator.
    log_p = math.log(p)
    log_q = math.log1p(-p)
    total = 0.0
    for i in range(k, n + 1):
        log_term = (
            math.lgamma(n + 1)
            - math.lgamma(i + 1)
            - math.lgamma(n - i + 1)
            + i * log_p
            + (n - i) * log_q
        )
        total += math.exp(log_term)
    return min(1.0, total)
