"""Hidden-profile group-decision task generator.

The *hidden profile* paradigm (Stasser & Titus, 1985) constructs a group
decision in which the information available to the group as a whole points to
one option, but the information *shared* by every member before discussion
points to a different, inferior option. Groups reliably fail these tasks because
members discuss what they already have in common instead of pooling the unique
information each holds privately.

This generator builds an integer-scored instance of that structure so the
"correct answer" is fully verifiable:

* Each option accumulates ``+1`` of support per supporting fact.
* **Shared facts** (known to every agent) give the *decoy* option a strict lead
  over the correct option -- so any agent reasoning from shared information alone
  will prefer the decoy.
* **Private facts** are distributed one cluster per agent and *all* support the
  correct option. They are calibrated so that the correct option overtakes the
  decoy only when every private fact has been surfaced; dropping any single
  required private fact makes the decoy tie or win again.

That last property makes ``required_private_facts`` genuinely minimal, which is
what the surfacing-rate metric and the verifiable reward rely on.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from grapevine.envs.base import Env, Task

# Readable, deterministic content pools. Indexed by the seeded RNG so instances
# are reproducible and fact strings are unique within a task.
_CANDIDATES = [
    "Avery",
    "Blair",
    "Cameron",
    "Devon",
    "Emerson",
    "Finley",
    "Harper",
    "Jordan",
]

_STRENGTHS = [
    "shipped a production ML system end to end",
    "led a cross-functional team of eight",
    "has deep experience with distributed systems",
    "mentored three junior engineers to promotion",
    "cut infrastructure costs by a third at their last role",
    "published peer-reviewed work in the domain",
    "rewrote a flaky test suite to full reliability",
    "designed the on-call rotation the team still uses",
    "owns an open-source library with real adoption",
    "turned around a project that was six months behind",
    "consistently writes clear design documents",
    "handled the largest incident of the last quarter calmly",
]

_DISTRACTOR_NOTES = [
    "The interview panel met in the third-floor conference room.",
    "Scheduling for the debrief ran fifteen minutes late.",
    "The role has been open since the start of the quarter.",
    "Two panelists joined the loop over video call.",
    "The candidate packets were printed double-sided.",
    "Lunch for the panel was ordered from the usual place.",
    "The hiring committee meets on alternating Thursdays.",
    "A calendar conflict pushed one interview to the afternoon.",
]


@dataclass
class HiddenProfileConfig:
    """Configuration for :class:`HiddenProfileEnv`.

    Attributes:
        n_agents: Number of agents (committee members) the task is split across.
        n_shared_facts: Number of facts known to every agent before discussion.
            Must be at least ``n_agents * n_private_facts_per_agent - 1`` so the
            decoy can be given a strict pre-discussion lead over the correct
            option (raised as a :class:`ValueError` otherwise).
        n_private_facts_per_agent: Number of correct-supporting facts held
            privately by each agent.
        n_distractors: Number of decision-irrelevant filler facts, split between
            the shared pool and the agents' private contexts.
        n_options: Number of answer options (candidates). Defaults to 4.
        seed: Optional base seed stored for reference (``generate`` takes the
            operative seed as an argument).
    """

    n_agents: int = 3
    n_shared_facts: int = 6
    n_private_facts_per_agent: int = 2
    n_distractors: int = 4
    n_options: int = 4
    seed: int | None = None

    def __post_init__(self) -> None:
        if self.n_agents < 2:
            raise ValueError("n_agents must be >= 2 for a group-decision task")
        if self.n_private_facts_per_agent < 1:
            raise ValueError("n_private_facts_per_agent must be >= 1")
        if self.n_options < 2:
            raise ValueError("n_options must be >= 2")
        if self.n_options > len(_CANDIDATES):
            raise ValueError(f"n_options must be <= {len(_CANDIDATES)}")
        total_private = self.n_agents * self.n_private_facts_per_agent
        if self.n_shared_facts < total_private - 1:
            raise ValueError(
                "n_shared_facts must be >= n_agents * n_private_facts_per_agent - 1 "
                f"(got n_shared_facts={self.n_shared_facts}, "
                f"needed >= {total_private - 1}) so the decoy can hold a strict "
                "pre-discussion lead."
            )
        if self.n_distractors < 0:
            raise ValueError("n_distractors must be >= 0")


class HiddenProfileEnv(Env):
    """Procedural generator for hidden-profile group-decision tasks."""

    family = "hidden_profile"

    def __init__(self, config: HiddenProfileConfig | None = None) -> None:
        """Create the environment.

        Args:
            config: Task-family configuration. A default
                :class:`HiddenProfileConfig` is used when omitted.
        """
        self.config = config or HiddenProfileConfig()

    def generate(self, seed: int) -> Task:
        """Generate a single hidden-profile task deterministically from ``seed``.

        The returned :class:`Task` satisfies, and stores enough metadata to
        verify, the three defining properties:

        1. Among shared facts alone, the decoy option strictly leads.
        2. With all facts pooled, the correct option strictly leads.
        3. Every fact in ``required_private_facts`` is necessary for (2).
        """
        cfg = self.config
        rng = random.Random(seed)

        options = rng.sample(_CANDIDATES, cfg.n_options)
        correct_idx, decoy_idx = rng.sample(range(cfg.n_options), 2)
        correct = options[correct_idx]
        decoy = options[decoy_idx]

        total_private = cfg.n_agents * cfg.n_private_facts_per_agent
        # Shared support for the decoy: exactly one less than the total private
        # support that will accrue to the correct option. This gives the decoy a
        # strict pre-discussion lead while ensuring every private fact is needed.
        decoy_shared = total_private - 1

        strengths = rng.sample(_STRENGTHS, len(_STRENGTHS))
        used_facts: set[str] = set()
        counter = {"s": 0, "d": 0}

        def strength_fact(name: str) -> str:
            """Return a unique, readable strength statement supporting ``name``."""
            base = strengths[counter["s"] % len(strengths)]
            round_no = counter["s"] // len(strengths)
            counter["s"] += 1
            fact = f"{name} {base}."
            if round_no > 0:
                fact = f"{name} {base} (also noted in review pass {round_no + 1})."
            while fact in used_facts:  # defensive; keeps every fact string unique
                counter["s"] += 1
                fact = f"{name} {base} (review note {counter['s']})."
            used_facts.add(fact)
            return fact

        # --- Shared facts -------------------------------------------------
        shared_facts: list[str] = [strength_fact(decoy) for _ in range(decoy_shared)]
        support: dict[str, int] = {opt: 0 for opt in options}
        support[decoy] += decoy_shared

        # Remaining shared slots go to other wrong options, each kept strictly
        # below the decoy so the decoy remains the unique shared-information
        # leader. The correct option receives no shared support.
        other_wrong = [o for i, o in enumerate(options) if i not in (correct_idx, decoy_idx)]
        remaining_shared = cfg.n_shared_facts - decoy_shared
        w = 0
        while remaining_shared > 0 and other_wrong:
            target = other_wrong[w % len(other_wrong)]
            if support[target] + 1 <= decoy_shared - 1:
                shared_facts.append(strength_fact(target))
                support[target] += 1
                remaining_shared -= 1
            w += 1
            if w > len(other_wrong) * (decoy_shared + 1):
                break  # capacity exhausted; fall through to distractor fill
        # Any shared slots we could not assign as (bounded) option support become
        # decision-irrelevant shared distractors.
        distractor_pool = rng.sample(_DISTRACTOR_NOTES, len(_DISTRACTOR_NOTES))

        def distractor_fact() -> str:
            """Return a unique, decision-irrelevant filler statement."""
            base = distractor_pool[counter["d"] % len(distractor_pool)]
            round_no = counter["d"] // len(distractor_pool)
            counter["d"] += 1
            fact = base if round_no == 0 else f"{base} (item {round_no + 1})"
            while fact in used_facts:
                counter["d"] += 1
                fact = f"{base} (item {counter['d']})"
            used_facts.add(fact)
            return fact

        while remaining_shared > 0:
            shared_facts.append(distractor_fact())
            remaining_shared -= 1

        rng.shuffle(shared_facts)

        # --- Private facts (all support the correct option) ---------------
        private_correct: list[str] = [strength_fact(correct) for _ in range(total_private)]
        support[correct] += total_private
        rng.shuffle(private_correct)

        # Distribute the correct-supporting private facts evenly across agents.
        private_facts: list[list[str]] = [[] for _ in range(cfg.n_agents)]
        for i, fact in enumerate(private_correct):
            private_facts[i % cfg.n_agents].append(fact)

        # Sprinkle private distractors as noise across agents.
        for j in range(cfg.n_distractors):
            private_facts[j % cfg.n_agents].append(distractor_fact())

        for facts in private_facts:
            rng.shuffle(facts)

        # --- Assemble agent contexts --------------------------------------
        shared_block = "\n".join(f"- {f}" for f in shared_facts)
        agent_contexts: list[str] = []
        for facts in private_facts:
            private_block = "\n".join(f"- {f}" for f in facts)
            agent_contexts.append(
                "Facts known to the whole committee:\n"
                f"{shared_block}\n\n"
                "Facts only you know:\n"
                f"{private_block}"
            )

        question = (
            "The hiring committee must recommend exactly one candidate for the role. "
            f"Based on all available information, who is the strongest candidate? "
            f"Options: {', '.join(options)}."
        )

        task = Task(
            task_id=f"{self.family}-{seed}",
            agent_contexts=agent_contexts,
            question=question,
            options=options,
            answer=correct,
            required_private_facts=list(private_correct),
            metadata={
                "family": self.family,
                "seed": seed,
                "shared_facts": shared_facts,
                "private_facts": private_facts,
                "correct_option": correct,
                "decoy_option": decoy,
                "support": support,
                "shared_support": _shared_support(shared_facts, options),
            },
        )
        return task


def _shared_support(shared_facts: list[str], options: list[str]) -> dict[str, int]:
    """Count how many shared facts name (support) each option.

    A shared fact supports an option iff the fact string starts with that
    option's name. Used to verify the pre-discussion decoy lead.
    """
    tally = {opt: 0 for opt in options}
    for fact in shared_facts:
        for opt in options:
            if fact.startswith(opt + " "):
                tally[opt] += 1
                break
    return tally
