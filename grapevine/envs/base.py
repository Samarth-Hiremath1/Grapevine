"""Common task representation and environment interface.

Every task family in Grapevine produces the same :class:`Task` structure and
implements the same :class:`Env` protocol, so the rollout engine, reward
functions and training loop are entirely agnostic to which family generated a
task.

The defining property shared by all families is *distributed evidence*: no
single agent context is sufficient to answer the question, and the answer is
only derivable once every fact in ``required_private_facts`` has been shared.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Task:
    """A single distributed-information decision task.

    Attributes:
        task_id: Stable, unique identifier (includes the family and seed).
        agent_contexts: One private context string per agent. The information an
            agent holds at the start of the episode. In the hidden-profile
            family each context contains the common (shared) facts plus that
            agent's private facts; in split-evidence each context holds one
            reasoning hop.
        question: The question posed to the team.
        options: The answer options. The team must select exactly one.
        answer: The correct option. Guaranteed to be an element of ``options``.
        required_private_facts: The minimal set of privately-held fact strings
            that must be surfaced in conversation for the answer to be
            derivable. Used both for the verifiable-reward construction and for
            the surfacing-rate metric.
        metadata: Family-specific extra data (shared facts, per-agent private
            facts, support tallies, seed, ...). Never required for scoring but
            used by the evaluation and diagnostics code to reconstruct the
            full-information context and to verify task well-formedness.
    """

    task_id: str
    agent_contexts: list[str]
    question: str
    options: list[str]
    answer: str
    required_private_facts: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def n_agents(self) -> int:
        """Number of agents this task is distributed across."""
        return len(self.agent_contexts)

    def full_context(self) -> str:
        """Return the single-agent, full-information view of this task.

        This is the union of every fact (shared facts once, plus every agent's
        private facts) rendered as one context block. It is the input used for
        the single-agent upper-bound condition in evaluation.
        """
        shared: list[str] = list(self.metadata.get("shared_facts", []))
        private: list[str] = []
        for facts in self.metadata.get("private_facts", []):
            private.extend(facts)
        lines = shared + private
        if not lines:
            # Fall back to concatenating the raw agent contexts.
            return "\n".join(self.agent_contexts)
        return "\n".join(f"- {line}" for line in lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain ``dict`` (JSON-ready)."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialise to a JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        """Reconstruct a :class:`Task` from :meth:`to_dict` output."""
        return cls(
            task_id=data["task_id"],
            agent_contexts=list(data["agent_contexts"]),
            question=data["question"],
            options=list(data["options"]),
            answer=data["answer"],
            required_private_facts=list(data["required_private_facts"]),
            metadata=dict(data.get("metadata", {})),
        )


class Env(ABC):
    """Abstract base class for a procedurally generated task family.

    A concrete environment is configured once (via its own config dataclass) and
    then generates deterministic :class:`Task` instances as a function of an
    integer seed. Determinism under seed is a hard requirement and is covered by
    the test suite.
    """

    #: Short identifier for the family, e.g. ``"hidden_profile"``.
    family: str

    @abstractmethod
    def generate(self, seed: int) -> Task:
        """Generate a single task deterministically from ``seed``."""
        raise NotImplementedError

    def generate_batch(self, n: int, seed: int) -> list[Task]:
        """Generate ``n`` tasks using seeds ``seed, seed+1, ..., seed+n-1``.

        The default implementation simply calls :meth:`generate` with
        consecutive seeds; subclasses rarely need to override it.
        """
        if n < 0:
            raise ValueError("n must be non-negative")
        return [self.generate(seed + i) for i in range(n)]
