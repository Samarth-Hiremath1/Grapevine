"""Training configuration, loaded from YAML and validated before anything heavy runs.

Every key is checked. An unknown key is an error rather than something silently
ignored, because a typo in a reward weight or a partner setting changes what a
run trains on without changing what its config file appears to say.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from grapevine.envs import ENVIRONMENTS
from grapevine.protocol import Environment
from grapevine.rl.partners import PartnerSpec
from grapevine.rl.rewards import RewardConfig
from grapevine.rl.rollout import RolloutSettings

__all__ = ["LoraSettings", "RLConfig", "load_config", "make_environment"]

_TOP_LEVEL = {
    "model",
    "environment",
    "trainable_agents",
    "partners",
    "reward",
    "rollout",
    "lora",
    "grpo",
    "audit",
    "seed",
    "output_dir",
    "save_policy",
    "preregistration",
}


@dataclass(frozen=True)
class LoraSettings:
    """LoRA adapter settings, passed to ``peft.LoraConfig``."""

    r: int = 16
    alpha: int = 32
    dropout: float = 0.05
    target_modules: tuple[str, ...] = ("q_proj", "k_proj", "v_proj", "o_proj")

    def to_peft(self) -> Any:
        """The ``peft.LoraConfig`` for this setting."""
        from peft import LoraConfig

        return LoraConfig(
            r=self.r,
            lora_alpha=self.alpha,
            lora_dropout=self.dropout,
            target_modules=list(self.target_modules),
            task_type="CAUSAL_LM",
        )


@dataclass(frozen=True)
class RLConfig:
    """A parsed training configuration.

    Attributes:
        model: The policy's starting checkpoint, Hub id or local path.
        environment: Registered environment name.
        environment_config: Overrides for the environment's config dataclass.
        n_train_tasks: Tasks drawn from the environment's training seeds.
        trainable_agents: Roles the policy plays and is trained on. In self-play
            every role is trainable.
        partners: Who plays the other roles.
        reward: The reward the run optimises.
        rollout: Rounds and sampling for the episodes around each completion.
        lora: LoRA settings, or ``None`` for full-parameter training.
        grpo: Passed to ``trl.GRPOConfig`` as keyword arguments.
        audit_n_tasks: Tasks the audit gate checks before training.
        seed: Run seed.
        output_dir: Where the manifest, logs and any saved policy go.
        save_policy: Save the trained policy at the end, for ``grapevine eval``.
        preregistration: Path to the pre-registration this run executes, or
            ``None``. A run without one is never reportable (``CLAUDE.md``
            rule 4).
    """

    model: str
    environment: str
    environment_config: Mapping[str, Any]
    n_train_tasks: int
    trainable_agents: tuple[int, ...]
    partners: PartnerSpec
    reward: RewardConfig
    rollout: RolloutSettings
    lora: LoraSettings | None
    grpo: Mapping[str, Any]
    audit_n_tasks: int = 200
    seed: int = 0
    output_dir: str = "runs/rl"
    save_policy: bool = False
    preregistration: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @property
    def self_play(self) -> bool:
        """True when one policy plays every agent."""
        return self.partners.kind == "self"

    def summary(self) -> dict[str, Any]:
        """The configuration as recorded in the run manifest."""
        return {
            "model": self.model,
            "environment": self.environment,
            "environment_config": dict(self.environment_config),
            "n_train_tasks": self.n_train_tasks,
            "mode": "self_play" if self.self_play else "frozen_partners",
            "trainable_agents": list(self.trainable_agents),
            "partners": self.partners.to_dict(),
            "reward": self.reward.to_dict(),
            "rollout": {
                "n_rounds": self.rollout.n_rounds,
                "aggregator": self.rollout.aggregator,
                "max_tokens": self.rollout.max_tokens,
                "temperature": self.rollout.temperature,
                "answer_temperature": self.rollout.answer_temperature,
            },
            "lora": None if self.lora is None else {
                "r": self.lora.r,
                "alpha": self.lora.alpha,
                "dropout": self.lora.dropout,
                "target_modules": list(self.lora.target_modules),
            },
            "grpo": dict(self.grpo),
            "audit_n_tasks": self.audit_n_tasks,
            "seed": self.seed,
            "output_dir": self.output_dir,
            "save_policy": self.save_policy,
            "preregistration": self.preregistration,
        }


def make_environment(name: str, overrides: Mapping[str, Any] | None = None) -> Environment:
    """Instantiate a registered environment, applying config overrides.

    Raises:
        KeyError: If the environment is not registered.
        ValueError: If overrides are given for an environment that takes none,
            or name a field its config does not have.
    """
    if name not in ENVIRONMENTS:
        raise KeyError(f"unknown environment {name!r}; available: {sorted(ENVIRONMENTS)}")
    overrides = dict(overrides or {})
    if not overrides:
        return ENVIRONMENTS[name]()
    if name != "hidden_profile_v2":
        raise ValueError(f"environment {name!r} does not take config overrides")
    from grapevine.envs.hidden_profile_v2 import HiddenProfileV2, HiddenProfileV2Config

    fields = set(HiddenProfileV2Config.__dataclass_fields__)
    unknown = sorted(set(overrides) - fields)
    if unknown:
        raise ValueError(f"unknown hidden_profile_v2 config keys {unknown}")
    for key in ("train_seeds", "eval_seeds", "pilot_seeds"):
        if key in overrides:
            start, stop = overrides[key]
            overrides[key] = range(int(start), int(stop))
    if "domains" in overrides:
        overrides["domains"] = tuple(overrides["domains"])
    return HiddenProfileV2(HiddenProfileV2Config(**overrides))


def load_config(path: str | Path) -> RLConfig:
    """Load and validate a training config.

    Raises:
        ValueError: On any unknown key, missing section or inconsistent setting.
    """
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    unknown = sorted(set(data) - _TOP_LEVEL)
    if unknown:
        raise ValueError(f"unknown top-level config keys {unknown}")
    for required in ("model", "environment", "grpo"):
        if required not in data:
            raise ValueError(f"config is missing the {required!r} section")

    model = data["model"]
    model_name = str(model["name"] if isinstance(model, Mapping) else model)

    env_block = dict(data["environment"])
    env_unknown = sorted(set(env_block) - {"name", "config", "n_train_tasks"})
    if env_unknown:
        raise ValueError(f"unknown environment keys {env_unknown}")
    env = make_environment(str(env_block["name"]), env_block.get("config"))

    partners = PartnerSpec.from_mapping(data.get("partners"))
    probe = env.generate(0)
    if "trainable_agents" in data:
        trainable = tuple(int(a) for a in data["trainable_agents"])
    else:
        trainable = tuple(range(probe.n_agents)) if partners.kind == "self" else (0,)
    if not trainable:
        raise ValueError("trainable_agents must name at least one agent")
    bad = [a for a in trainable if not 0 <= a < probe.n_agents]
    if bad:
        raise ValueError(f"trainable_agents {bad} are not agents of a {probe.n_agents}-agent task")
    if partners.kind == "self" and set(trainable) != set(range(probe.n_agents)):
        raise ValueError(
            "in self-play one policy plays every agent, so trainable_agents must be "
            "all of them (or omitted)"
        )

    rollout_block = dict(data.get("rollout") or {})
    rollout_unknown = sorted(
        set(rollout_block) - {"n_rounds", "aggregator", "max_tokens", "temperature", "answer_temperature"}
    )
    if rollout_unknown:
        raise ValueError(f"unknown rollout keys {rollout_unknown}")
    rollout = RolloutSettings(**rollout_block)

    lora_block = data.get("lora")
    lora = None
    if lora_block:
        lora_unknown = sorted(set(lora_block) - {"r", "alpha", "dropout", "target_modules"})
        if lora_unknown:
            raise ValueError(f"unknown lora keys {lora_unknown}")
        lora = LoraSettings(
            r=int(lora_block.get("r", 16)),
            alpha=int(lora_block.get("alpha", 32)),
            dropout=float(lora_block.get("dropout", 0.05)),
            target_modules=tuple(
                lora_block.get("target_modules", LoraSettings().target_modules)
            ),
        )

    grpo = dict(data["grpo"])
    for forbidden in ("output_dir", "seed"):
        if forbidden in grpo:
            raise ValueError(
                f"set {forbidden} at the top level, not under grpo, so the manifest and "
                "the trainer cannot disagree"
            )

    audit_block = dict(data.get("audit") or {})
    if set(audit_block) - {"n_tasks"}:
        raise ValueError(f"unknown audit keys {sorted(set(audit_block) - {'n_tasks'})}")

    return RLConfig(
        model=model_name,
        environment=str(env_block["name"]),
        environment_config=dict(env_block.get("config") or {}),
        n_train_tasks=int(env_block.get("n_train_tasks", 64)),
        trainable_agents=trainable,
        partners=partners,
        reward=RewardConfig.from_mapping(data.get("reward")),
        rollout=rollout,
        lora=lora,
        grpo=grpo,
        audit_n_tasks=int(audit_block.get("n_tasks", 200)),
        seed=int(data.get("seed", 0)),
        output_dir=str(data.get("output_dir", "runs/rl")),
        save_policy=bool(data.get("save_policy", False)),
        preregistration=data.get("preregistration"),
        raw=data,
    )
