"""The audit gate: no training on an environment the battery has flagged.

Before a single gradient step, the training entry point audits the configured
environment *with the reward the run will actually optimise* -- shaping terms
included, via :class:`~grapevine.rl.rewards.RewardedEnvironment` -- and refuses
to start if any check fails.

It is overridable, because a researcher may have a reason: studying how a
policy exploits a known shortcut is a legitimate experiment. But the override
is never silent. ``--allow-flagged`` is written into the run manifest alongside
the card's hash and the list of checks that failed, so a result trained on a
flagged environment always says so.

The audit runs on the environment's *training* seeds. Auditing the eval seeds
would certify tasks the run never sees.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from grapevine.audit import Status, ValidityCard, audit
from grapevine.protocol import Environment
from grapevine.rl.rewards import RewardConfig, RewardedEnvironment

__all__ = ["AuditGateError", "GateResult", "audit_gate"]


class AuditGateError(RuntimeError):
    """Raised when training is refused because the card is flagged."""

    def __init__(self, card: ValidityCard) -> None:
        self.card = card
        failed = card.by_status(Status.FAIL)
        lines = [
            f"refusing to train on {card.environment} v{card.version}: the audit flagged "
            f"{', '.join(card.flagged_checks)}.",
            "",
        ]
        for result in failed:
            lines.append(f"  - {result.check_id}: {result.summary}")
        lines += [
            "",
            "A policy trained here would be rewarded for whatever the flagged checks "
            "describe, not for coordinating. Fix the environment or the reward, or pass "
            "--allow-flagged to train anyway; that choice is recorded in the run "
            "manifest along with this card's hash.",
        ]
        super().__init__("\n".join(lines))


@dataclass(frozen=True)
class GateResult:
    """What the gate decided, for the run manifest.

    Attributes:
        card: The Validity Card the decision was made on.
        allowed_flagged: True when the card failed and training went ahead
            because ``--allow-flagged`` was passed.
    """

    card: ValidityCard
    allowed_flagged: bool

    @property
    def passed(self) -> bool:
        """True when no check failed."""
        return self.card.passed

    def to_dict(self) -> dict[str, Any]:
        """The manifest entry."""
        return {
            "card_hash": self.card.content_hash(),
            "verdict": str(self.card.verdict),
            "passed": self.card.passed,
            "flagged_checks": list(self.card.flagged_checks),
            "allowed_flagged": self.allowed_flagged,
            "n_tasks": self.card.n_tasks,
            "seed": self.card.seed,
        }


def audit_gate(
    env: Environment,
    reward: RewardConfig,
    *,
    n_tasks: int = 200,
    seed: int | None = None,
    allow_flagged: bool = False,
) -> GateResult:
    """Audit ``env`` under ``reward`` and refuse a flagged card.

    Args:
        env: The environment the run will train on.
        reward: The reward the run will optimise.
        n_tasks: Tasks to audit.
        seed: First seed to audit. Defaults to the start of the environment's
            declared training range.
        allow_flagged: Proceed even when a check fails. Recorded.

    Returns:
        A :class:`GateResult` for the manifest.

    Raises:
        AuditGateError: If a check failed and ``allow_flagged`` is false.
        ValueError: If the environment declares no train/eval split. Training
            without one leaves nothing to stop a run from training on the tasks
            it reports.
    """
    split = env.seed_split()
    if split is None:
        raise ValueError(
            f"{env.name} declares no train/eval seed split, so nothing stops a run from "
            "training on the tasks it will later report. Implement "
            "Environment.seed_split() before training on it."
        )
    start = split.train.start if seed is None else seed
    card = audit(RewardedEnvironment(env, reward), n_tasks=n_tasks, seed=start)
    if not card.passed and not allow_flagged:
        raise AuditGateError(card)
    return GateResult(card=card, allowed_flagged=not card.passed and allow_flagged)
