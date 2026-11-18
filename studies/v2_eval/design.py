"""The pre-registered design for the ``hidden_profile_v2`` eval run.

Everything a run does is fixed here, before any call is made, and
``docs/prereg/hidden_profile_v2_eval.md`` is written from it. Nothing in this
file may change after the primary run starts. If something must change between
the pilot and the primary run, the change is committed to the pre-registration
first, with its reason, and the pilot is not re-run to make it look better
(``CLAUDE.md`` rules 4 and 5).

The question is the one the v0 study left open. There, with the objective
stated, communicating teams matched a single agent holding every fact (100/100
and 99/100 against 100/100). But that environment was solvable by counting
names, so "matched" might have meant "both counted". ``hidden_profile_v2``
removes that shortcut and the others the battery knows, so this asks whether
the result survives on an environment that passes its own audit.

The prompts are owned by this file, not imported from the library. The v0 lesson
was that a study's prompts must be frozen against the code drifting; a study
that borrowed its templates from a package module would change whenever the
module did. ``prompts_sample.md`` freezes their exact text.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from grapevine.envs.hidden_profile_v2 import HiddenProfileV2
from grapevine.protocol import AgentView, Condition, DistributedTask, Environment, SeedSplit
from grapevine.rollout.client import Message

__all__ = [
    "CANDIDATE_MODELS",
    "CELLS",
    "CONDITIONS",
    "DESIGN",
    "EvalDesign",
    "OBJECTIVE_STATES",
    "decision_messages",
    "discussion_messages",
]

#: The environment, at its default configuration: 3 agents, 4 options, one
#: gold-supporting fact per agent, margin 1, all three domains.
ENVIRONMENT = HiddenProfileV2()

CONDITIONS = ("full_info", "no_communication", "communication")
OBJECTIVE_STATES = ("stated", "unstated")

#: Six cells per model: every condition with and without the objective stated.
CELLS: tuple[tuple[str, str], ...] = tuple(
    (condition, objective) for condition in CONDITIONS for objective in OBJECTIVE_STATES
)

#: Inexpensive current models from the only provider with a key available here.
#: The brief asked for up to three providers; one is available, and the
#: pre-registration says so. Which of these run is decided before the pilot.
CANDIDATE_MODELS = ("gpt-5.6-luna", "gpt-6-luna", "gpt-4o-mini")


@dataclass(frozen=True)
class Design:
    """The fixed parameters of the run.

    Attributes:
        n_primary: Tasks per cell in the primary run.
        n_pilot: Tasks per cell in the pilot.
        primary_seeds: First ``n_primary`` seeds of the environment's eval split.
        pilot_seeds: First ``n_pilot`` seeds of its pilot split. Disjoint from
            the primary seeds, enforced by :class:`~grapevine.protocol.SeedSplit`
            and checked again at run time.
        n_rounds: Discussion rounds in the communication condition.
        aggregator: The agent who decides after discussion.
        max_output_tokens: Per-call output cap. Hidden reasoning tokens count
            against it; v0 used 400 and lost four answers to what was probably
            truncation (``docs/audit.md`` L10). A truncated call is a named
            failure, logged per call.
        discussion_temperature: Where the model accepts a temperature.
        decision_temperature: Likewise, for every answer-producing call.
        bootstrap_resamples: For paired differences.
        bootstrap_seed: Fixed, so the analysis is deterministic.
        budget_usd: The release's total API budget (``CLAUDE.md`` rule 9).
    """

    n_primary: int = 100
    n_pilot: int = 20
    primary_seeds: tuple[int, ...] = tuple(ENVIRONMENT.config.eval_seeds[:100])
    pilot_seeds: tuple[int, ...] = tuple(ENVIRONMENT.config.pilot_seeds[:20])
    n_rounds: int = 2
    aggregator: int = 0
    max_output_tokens: int = 1200
    discussion_temperature: float = 0.7
    decision_temperature: float = 0.0
    bootstrap_resamples: int = 10_000
    bootstrap_seed: int = 20261115
    budget_usd: float = 10.0

    def __post_init__(self) -> None:
        overlap = set(self.primary_seeds) & set(self.pilot_seeds)
        if overlap:
            raise ValueError(f"pilot and primary seeds overlap: {sorted(overlap)[:5]}")
        split: SeedSplit = ENVIRONMENT.seed_split()
        if not set(self.primary_seeds) <= set(split.eval):
            raise ValueError("primary seeds must come from the environment's eval split")
        if not set(self.pilot_seeds) <= set(split.pilot):
            raise ValueError("pilot seeds must come from the environment's pilot split")
        if len(self.primary_seeds) != self.n_primary or len(self.pilot_seeds) != self.n_pilot:
            raise ValueError("seed lists do not match n_primary / n_pilot")

    def seeds(self, phase: str) -> tuple[int, ...]:
        """The seeds for ``phase``: ``"pilot"`` or ``"primary"``."""
        if phase == "pilot":
            return self.pilot_seeds
        if phase == "primary":
            return self.primary_seeds
        raise ValueError(f"phase must be 'pilot' or 'primary', got {phase!r}")

    def calls_per_task(self) -> dict[str, int]:
        """Model calls one task costs in each condition."""
        n_agents = ENVIRONMENT.config.n_agents
        return {
            "full_info": 1,
            "no_communication": n_agents,
            "communication": self.n_rounds * n_agents + 1,
        }

    def to_dict(self) -> dict[str, Any]:
        """For the run manifest."""
        return {
            "n_primary": self.n_primary,
            "n_pilot": self.n_pilot,
            "primary_seeds": [self.primary_seeds[0], self.primary_seeds[-1] + 1],
            "pilot_seeds": [self.pilot_seeds[0], self.pilot_seeds[-1] + 1],
            "n_rounds": self.n_rounds,
            "aggregator": self.aggregator,
            "max_output_tokens": self.max_output_tokens,
            "discussion_temperature": self.discussion_temperature,
            "decision_temperature": self.decision_temperature,
            "bootstrap_resamples": self.bootstrap_resamples,
            "bootstrap_seed": self.bootstrap_seed,
            "budget_usd": self.budget_usd,
            "environment": f"{ENVIRONMENT.name} v{ENVIRONMENT.version}",
            "cells": [list(c) for c in CELLS],
        }


DESIGN = Design()

# --- Prompts --------------------------------------------------------------------

SYSTEM_PROMPT = "You are taking part in a group decision. Be concise."

#: The one line that says which arm a prompt belongs to. The same three lines
#: ``hidden_profile_v2`` uses for its own audited conditions.
MARKERS: dict[str, str] = {
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

DISCUSSION_PROMPT = (
    "{marker}\n\n"
    "{objective}"
    "{context}\n\n"
    "Conversation so far:\n{history}\n\n"
    "It is your turn (round {round_no} of {n_rounds}). Write a short message to your "
    "teammates. Do not give a final answer yet."
)

DECISION_PROMPT = (
    "{marker}\n\n"
    "{objective}"
    "{context}\n\n"
    "{discussion}"
    "Choose exactly one of these options: {options}.\n"
    'Respond with only a JSON object: {{"answer": "<one option exactly as written>"}}.'
)

#: Scaffolding only the communication arm has. Declared as its expected
#: difference from the other arms, so the audit's condition-diff check verifies
#: that this -- the channel -- is the only framing it adds.
COMMUNICATION_SCAFFOLDING = (
    "Conversation so far:\n"
    "(no messages yet)\n"
    "It is your turn (round 1 of {n_rounds}). Write a short message to your teammates. "
    "Do not give a final answer yet.\n"
    "Full team discussion:"
)


def _objective_block(task: DistributedTask, objective: str) -> str:
    if objective == "stated":
        return task.objective.statement() + "\n\n"
    if objective == "unstated":
        return ""
    raise ValueError(f"objective must be 'stated' or 'unstated', got {objective!r}")


def _render_history(history: list[tuple[int, str]]) -> str:
    if not history:
        return "(no messages yet)"
    return "\n".join(f"Agent {agent}: {text}" for agent, text in history)


def _matched_full_view(task: DistributedTask) -> AgentView:
    """Every unit, in the same two blocks and labels an agent sees (L4)."""
    full = task.full_view()
    return AgentView(agent_id=0, shared=full.shared, private=full.private)


def discussion_messages(
    task: DistributedTask,
    agent_id: int,
    history: list[tuple[int, str]],
    round_no: int,
    objective: str,
) -> list[Message]:
    """One discussion turn in the communication condition."""
    return [
        Message("system", SYSTEM_PROMPT),
        Message(
            "user",
            DISCUSSION_PROMPT.format(
                marker=MARKERS["communication"],
                objective=_objective_block(task, objective),
                context=task.views[agent_id].render(),
                history=_render_history(history),
                round_no=round_no,
                n_rounds=DESIGN.n_rounds,
            ),
        ),
    ]


def decision_messages(
    task: DistributedTask,
    condition: str,
    objective: str,
    *,
    agent_id: int = 0,
    history: list[tuple[int, str]] | None = None,
) -> list[Message]:
    """An answer-producing call in any condition.

    ``full_info`` sees every unit; ``no_communication`` sees one agent's view;
    ``communication`` sees the aggregator's view and the whole discussion.
    """
    if condition == "full_info":
        context = _matched_full_view(task).render()
        discussion = ""
    elif condition == "no_communication":
        context = task.views[agent_id].render()
        discussion = ""
    elif condition == "communication":
        context = task.views[agent_id].render()
        discussion = f"Full team discussion:\n{_render_history(history or [])}\n\n"
    else:
        raise ValueError(f"unknown condition {condition!r}")
    return [
        Message("system", SYSTEM_PROMPT),
        Message(
            "user",
            DECISION_PROMPT.format(
                marker=MARKERS[condition],
                objective=_objective_block(task, objective),
                context=context,
                discussion=discussion,
                options=", ".join(task.answer_space),
            ),
        ),
    ]


def opening_prompts(task: DistributedTask, condition: str, objective: str) -> tuple[str, ...]:
    """Every call a cell makes before any model has spoken, as single strings.

    For the communication arm that is each agent's round-one turn plus the
    aggregator's decision prompt with an empty discussion. Used by the audit and
    by ``prompts_sample.md``.
    """

    def joined(messages: list[Message]) -> str:
        return "\n\n".join(m.content for m in messages)

    n_agents = task.n_agents
    if condition == "full_info":
        return (joined(decision_messages(task, condition, objective)),)
    if condition == "no_communication":
        return tuple(
            joined(decision_messages(task, condition, objective, agent_id=i))
            for i in range(n_agents)
        )
    return tuple(
        joined(discussion_messages(task, i, [], 1, objective)) for i in range(n_agents)
    ) + (joined(decision_messages(task, condition, objective, agent_id=DESIGN.aggregator)),)


class EvalDesign(Environment):
    """``hidden_profile_v2`` with the six eval arms as its conditions.

    So the pre-registered prompts are audited, not just written down: the
    battery's ``objective`` check must fail exactly the three ``unstated`` arms
    -- that is the manipulation -- and ``condition_diff`` must find no framing
    difference between any two arms beyond the ones declared here.
    """

    name = "hidden_profile_v2_eval_design"
    version = "1"

    def generate(self, seed: int) -> DistributedTask:
        """Delegated unchanged to ``hidden_profile_v2``."""
        return ENVIRONMENT.generate(seed)

    def seed_split(self) -> SeedSplit:
        """The environment's own split."""
        return ENVIRONMENT.seed_split()

    def conditions(self, task: DistributedTask) -> Mapping[str, Condition]:
        """The six arms, with every intended difference declared."""
        statement = task.objective.statement()
        scaffolding = COMMUNICATION_SCAFFOLDING.format(n_rounds=DESIGN.n_rounds)

        def declares(a: tuple[str, str], b: tuple[str, str]) -> str:
            """The lines arm ``a`` carries that arm ``b`` lacks, by design."""
            parts: list[str] = []
            if a[0] != b[0]:
                parts.append(MARKERS[a[0]])
                if a[0] == "communication":
                    parts.append(scaffolding)
            if a[1] == "stated" and b[1] == "unstated":
                parts.append(statement)
            return "\n".join(parts)

        arms: dict[str, Condition] = {}
        for cell in CELLS:
            name = f"{cell[0]}_{cell[1]}"
            arms[name] = Condition(
                name=name,
                description=f"{cell[0]}, objective {cell[1]}",
                prompts=opening_prompts(task, *cell),
                expected_diff={
                    f"{other[0]}_{other[1]}": declares(cell, other)
                    for other in CELLS
                    if other != cell and declares(cell, other)
                },
            )
        return arms
