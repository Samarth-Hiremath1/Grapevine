"""RL and post-training on distributed-information environments.

**GRPO integration, smoke-tested; no training results in this release.**

Install with the ``[rl]`` extra. Importing this package does not import
``torch``, ``transformers`` or ``trl``; they load only when a model is.

What is here:

* :mod:`grapevine.rl.rewards` -- the team outcome reward from the environment's
  scorer, an optional surfacing shaping term (off by default, and flagged by the
  audit when on), and shared-team credit helpers.
* :mod:`grapevine.rl.rollout` -- a protocol-native episode runner that records
  every prompt, and the :class:`Turn` / :class:`Trajectory` records with role
  and turn tags.
* :mod:`grapevine.rl.partners` -- scripted, frozen, endpoint and self-play
  partners. Frozen means a separately loaded copy, never the trainer's model.
* :mod:`grapevine.rl.gate` -- the audit gate: training refuses a flagged
  environment unless ``--allow-flagged`` is passed and recorded.
* :mod:`grapevine.rl.grpo` -- the TRL ``GRPOTrainer`` wiring.
* :mod:`grapevine.rl.eval` -- evaluation on held-out seeds beside the baselines
  a policy must beat.

Read ``docs/rl.md`` for what has and has not been run.
"""

from __future__ import annotations

from grapevine.rl.config import LoraSettings, RLConfig, load_config, make_environment
from grapevine.rl.gate import AuditGateError, GateResult, audit_gate
from grapevine.rl.partners import PARTNER_KINDS, HFClient, PartnerSpec, scripted_partner
from grapevine.rl.rewards import (
    RewardBreakdown,
    RewardConfig,
    RewardedEnvironment,
    shared_credit,
    split_credit,
    surfaced_fraction,
    surfacing_credit,
)
from grapevine.rl.rollout import RolloutSettings, Trajectory, Turn, run_episode, run_episode_sync

__all__ = [
    "PARTNER_KINDS",
    "AuditGateError",
    "GateResult",
    "HFClient",
    "LoraSettings",
    "PartnerSpec",
    "RLConfig",
    "RewardBreakdown",
    "RewardConfig",
    "RewardedEnvironment",
    "RolloutSettings",
    "Trajectory",
    "Turn",
    "audit_gate",
    "load_config",
    "make_environment",
    "run_episode",
    "run_episode_sync",
    "scripted_partner",
    "shared_credit",
    "split_credit",
    "surfaced_fraction",
    "surfacing_credit",
]
