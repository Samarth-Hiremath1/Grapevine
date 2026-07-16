"""Split-evidence multi-hop QA generator.

This family builds a multi-hop question whose reasoning chain is *cut apart* and
distributed across agents: hop *i* of the chain -- the fact linking entity
``E_i`` to entity ``E_{i+1}`` -- is held privately by agent *i* and by no one
else. A single agent can therefore never answer alone; the team must relay every
hop's evidence to trace the chain from the starting entity to the final one.

Entities are synthetic station codes (e.g. ``Station K7Q``) so the answer is a
pure function of the distributed evidence rather than of any world knowledge the
model might have memorised, which keeps the reward strictly verifiable.

Distractor hops (decommissioned spurs from off-path stations) and shared filler
never create an alternative path from the start, so the correct terminal station
is always unique.
"""

from __future__ import annotations

import random
import string
from dataclasses import dataclass

from grapevine.envs.base import Env, Task


@dataclass
class SplitEvidenceConfig:
    """Configuration for :class:`SplitEvidenceEnv`.

    Attributes:
        n_agents: Number of reasoning hops; each agent holds exactly one true
            hop of the chain. Must be >= 2.
        n_shared_facts: Number of decision-irrelevant filler statements shown to
            every agent.
        n_private_facts_per_agent: Total private statements per agent. Exactly
            one is the agent's true hop; the remaining ``n - 1`` are distractor
            spurs. Must be >= 1.
        n_distractors: Number of decoy terminal stations mixed into the options
            (options therefore contain the answer plus up to this many decoys,
            trimmed to ``n_options``).
        n_options: Number of answer options presented. Must be >= 2.
        seed: Optional base seed, stored for reference.
    """

    n_agents: int = 3
    n_shared_facts: int = 2
    n_private_facts_per_agent: int = 1
    n_distractors: int = 3
    n_options: int = 4
    seed: int | None = None

    def __post_init__(self) -> None:
        if self.n_agents < 2:
            raise ValueError("n_agents must be >= 2 (need at least two hops)")
        if self.n_private_facts_per_agent < 1:
            raise ValueError("n_private_facts_per_agent must be >= 1")
        if self.n_options < 2:
            raise ValueError("n_options must be >= 2")
        if self.n_distractors < 0:
            raise ValueError("n_distractors must be >= 0")


_SHARED_NOTES = [
    "The regional network operated on standard gauge track.",
    "All stations reported status on the hour.",
    "Route maps were reissued at the start of the season.",
    "The dispatch office kept a duplicate of every timetable.",
    "Signal lamps were replaced on a rolling schedule.",
    "The network's control room ran two shifts a day.",
]


class SplitEvidenceEnv(Env):
    """Procedural generator for split-evidence multi-hop QA tasks."""

    family = "split_evidence"

    def __init__(self, config: SplitEvidenceConfig | None = None) -> None:
        """Create the environment.

        Args:
            config: Task-family configuration. A default
                :class:`SplitEvidenceConfig` is used when omitted.
        """
        self.config = config or SplitEvidenceConfig()

    def generate(self, seed: int) -> Task:
        """Generate a single split-evidence task deterministically from ``seed``.

        The returned :class:`Task` places one true hop in each agent's private
        context; ``required_private_facts`` is exactly the list of those hops, in
        chain order, and ``answer`` is the unique terminal station reachable by
        following them from the start.
        """
        cfg = self.config
        rng = random.Random(seed)

        n_hops = cfg.n_agents
        # Unique station codes: chain stations first, then decoys/off-path.
        n_codes = (n_hops + 1) + cfg.n_distractors + n_hops * cfg.n_private_facts_per_agent
        codes = _unique_codes(rng, n_codes)
        chain = codes[: n_hops + 1]
        pool = codes[n_hops + 1 :]  # off-path stations for decoys and spurs

        start = chain[0]
        answer = chain[-1]

        # --- True hops (one per agent, in chain order) --------------------
        true_hops: list[str] = [
            f"From {chain[i]}, the active route continues to {chain[i + 1]}."
            for i in range(n_hops)
        ]

        # --- Distractor spurs: off-path sources so they never chain from start.
        spur_sources = iter(pool[cfg.n_distractors :])  # reserve first decoys for options

        def spur_fact() -> str:
            src = next(spur_sources)
            dst = rng.choice(chain[1:] + pool)
            return f"From {src}, a decommissioned spur once led to {dst}."

        # --- Assemble per-agent private contexts --------------------------
        private_facts: list[list[str]] = []
        for i in range(n_hops):
            facts = [true_hops[i]]
            for _ in range(cfg.n_private_facts_per_agent - 1):
                facts.append(spur_fact())
            rng.shuffle(facts)
            private_facts.append(facts)

        # --- Shared filler ------------------------------------------------
        shared_notes = rng.sample(_SHARED_NOTES, min(cfg.n_shared_facts, len(_SHARED_NOTES)))
        while len(shared_notes) < cfg.n_shared_facts:
            shared_notes.append(f"Maintenance bulletin #{len(shared_notes) + 1} was filed on time.")
        shared_facts: list[str] = list(shared_notes)

        # --- Options ------------------------------------------------------
        decoy_stations = pool[: cfg.n_distractors]
        option_pool = [answer] + decoy_stations
        # Trim / pad options to exactly n_options, always keeping the answer.
        if len(option_pool) > cfg.n_options:
            others = [o for o in option_pool if o != answer]
            option_pool = [answer] + rng.sample(others, cfg.n_options - 1)
        else:
            extra = iter(_unique_codes(rng, cfg.n_options, exclude=set(codes)))
            while len(option_pool) < cfg.n_options:
                option_pool.append(next(extra))
        options = option_pool[:]
        rng.shuffle(options)

        # --- Agent contexts -----------------------------------------------
        shared_block = (
            "\n".join(f"- {f}" for f in shared_facts) if shared_facts else "- (none)"
        )
        agent_contexts: list[str] = []
        for facts in private_facts:
            private_block = "\n".join(f"- {f}" for f in facts)
            agent_contexts.append(
                "Notes available to everyone:\n"
                f"{shared_block}\n\n"
                "Route records only you hold:\n"
                f"{private_block}"
            )

        question = (
            f"A signal enters the network at {start} and always follows the active route "
            f"from each station to the next. At which station does it finally arrive? "
            f"Options: {', '.join(options)}."
        )

        task = Task(
            task_id=f"{self.family}-{seed}",
            agent_contexts=agent_contexts,
            question=question,
            options=options,
            answer=answer,
            required_private_facts=list(true_hops),
            metadata={
                "family": self.family,
                "seed": seed,
                "shared_facts": shared_facts,
                "private_facts": private_facts,
                "chain": chain,
                "start": start,
            },
        )
        return task


def _unique_codes(rng: random.Random, n: int, exclude: set[str] | None = None) -> list[str]:
    """Return ``n`` unique synthetic station codes like ``Station K7Q``."""
    exclude = exclude or set()
    codes: list[str] = []
    seen: set[str] = set(exclude)
    while len(codes) < n:
        code = "Station " + "".join(
            rng.choice(string.ascii_uppercase) if k % 2 == 0 else rng.choice(string.digits)
            for k in range(3)
        )
        if code not in seen:
            seen.add(code)
            codes.append(code)
    return codes
