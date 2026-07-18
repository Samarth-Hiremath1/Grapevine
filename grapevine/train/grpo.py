"""GRPO training loop wiring the multi-agent rollout and verifiable reward.

The policy model generates candidate opening messages for agent 0; TRL's
``GRPOTrainer`` optimises those generations against a reward computed by running
the rest of the multi-agent rollout and applying the exact-match verifiable
reward (see :mod:`grapevine.train.reward`).

Everything is config-driven (YAML in ``configs/``). A tiny smoke configuration
runs two optimisation steps on CPU to prove the loop is wired; a separate GPU
configuration is provided for real training. This module intentionally reports
no accuracy numbers -- running real training is future work.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from grapevine.envs import REGISTRY
from grapevine.envs.base import Task
from grapevine.rollout.client import LLMClient, Message, ScriptedClient
from grapevine.rollout.engine import AGENT_TURN_PROMPT, TEAM_SYSTEM_PROMPT, RolloutConfig
from grapevine.train.reward import team_reward_for_completions


@dataclass
class TrainConfig:
    """Parsed training configuration (mirrors the YAML files in ``configs/``)."""

    model_name: str
    env_family: str
    env_params: dict[str, int]
    n_train_tasks: int
    rollout: RolloutConfig
    aux_backend: str  # "model" | "scripted"
    grpo: dict[str, Any]
    seed: int
    output_dir: str
    raw: dict[str, Any] = field(default_factory=dict)


def load_config(path: str | Path) -> TrainConfig:
    """Load and validate a training YAML config."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    model = data["model"]
    env = data["env"]
    rollout = data.get("rollout", {})
    env_params = {
        k: int(env[k])
        for k in (
            "n_agents",
            "n_shared_facts",
            "n_private_facts_per_agent",
            "n_distractors",
            "n_options",
        )
        if k in env
    }
    aux_backend = str(rollout.get("aux_backend", "model"))
    if aux_backend not in ("model", "scripted"):
        raise ValueError("rollout.aux_backend must be 'model' or 'scripted'")
    return TrainConfig(
        model_name=str(model["name"]),
        env_family=str(env["family"]),
        env_params=env_params,
        n_train_tasks=int(env.get("n_train_tasks", 64)),
        rollout=RolloutConfig(
            n_rounds=int(rollout.get("n_rounds", 2)),
            aggregation=str(rollout.get("aggregation", "aggregator")),
            max_tokens=int(rollout.get("max_tokens", 256)),
        ),
        aux_backend=aux_backend,
        grpo=dict(data.get("grpo", {})),
        seed=int(data.get("seed", 0)),
        output_dir=str(data.get("output_dir", "runs/grapevine")),
        raw=data,
    )


def build_env(cfg: TrainConfig) -> Any:
    """Instantiate the configured environment."""
    if cfg.env_family not in REGISTRY:
        raise ValueError(f"unknown env family '{cfg.env_family}'")
    env_cls, config_cls = REGISTRY[cfg.env_family]
    # Base Env has a no-arg constructor; concrete envs take their config.
    return env_cls(config_cls(**cfg.env_params))  # type: ignore[call-arg]


def build_dataset(cfg: TrainConfig) -> Any:
    """Build a Hugging Face ``Dataset`` of agent-0 opening-turn prompts.

    Each row carries the plain-text prompt the policy generates from, plus a JSON
    serialisation of the full task so the reward function can reconstruct it and
    run the rest of the rollout.
    """
    from datasets import Dataset

    env = build_env(cfg)
    tasks = env.generate_batch(cfg.n_train_tasks, cfg.seed)
    rows = []
    for task in tasks:
        prompt = _agent0_prompt(task, cfg.rollout)
        rows.append({"prompt": prompt, "task_json": task.to_json()})
    return Dataset.from_list(rows)


def _agent0_prompt(task: Task, rollout: RolloutConfig) -> str:
    """The plain-text opening-turn prompt for agent 0 (system + user concatenated)."""
    system = TEAM_SYSTEM_PROMPT.format(agent_id=0, n_agents=task.n_agents)
    user = AGENT_TURN_PROMPT.format(
        context=task.agent_contexts[0],
        history="(no messages yet)",
        round_no=1,
        n_rounds=rollout.n_rounds,
    )
    return f"{system}\n\n{user}"


def _scripted_aux_responder(messages: list[Message]) -> str:
    """Deterministic auxiliary agent used by the smoke test (no second model).

    On a discussion turn it emits a short acknowledgement; on the aggregation
    turn it selects the option mentioned most often in the discussion so far --
    which includes the policy's generated message -- so the reward genuinely
    depends on the model's output while remaining fast and offline.
    """
    user = messages[-1].content
    if "JSON object" not in user:
        return "Noted; sharing what I can and asking for anything missing."
    options = _parse_options(user)
    if not options:
        return '{"answer": ""}'
    # Count mentions in the discussion portion (strip the trailing options list).
    body = user.split("Choose exactly one of these options:")[0].lower()
    counts = {opt: body.count(opt.lower()) for opt in options}
    best = max(counts.values())
    choice = next(opt for opt in options if counts[opt] == best)
    return json.dumps({"answer": choice})


def _parse_options(prompt: str) -> list[str]:
    marker = "Choose exactly one of these options:"
    if marker not in prompt:
        return []
    tail = prompt.split(marker, 1)[1]
    tail = tail.split(".")[0]
    return [o.strip() for o in tail.split(",") if o.strip()]


def make_aux_client(cfg: TrainConfig, model: Any = None, tokenizer: Any = None) -> LLMClient:
    """Construct the auxiliary client that plays non-trained agents."""
    if cfg.aux_backend == "scripted":
        return ScriptedClient(_scripted_aux_responder, model="scripted-aux")
    from grapevine.train.hf_client import LocalHFClient

    if model is not None and tokenizer is not None:
        return LocalHFClient(model, tokenizer, model_name=cfg.model_name)
    return LocalHFClient.from_pretrained(cfg.model_name)


def make_reward_func(cfg: TrainConfig, aux_client: LLMClient) -> Any:
    """Return a TRL-compatible reward function closing over the rollout config."""

    def team_reward(
        completions: list[Any] | None = None,
        task_json: list[str] | None = None,
        **kwargs: Any,
    ) -> list[float]:
        assert completions is not None and task_json is not None
        comps = [_completion_text(c) for c in completions]
        tasks = [Task.from_dict(json.loads(tj)) for tj in task_json]
        return team_reward_for_completions(tasks, comps, aux_client, cfg.rollout)

    team_reward.__name__ = "team_verifiable_reward"
    return team_reward


def _completion_text(completion: Any) -> str:
    """Normalise a TRL completion (plain string or chat message list) to text."""
    if isinstance(completion, str):
        return completion
    if isinstance(completion, list) and completion:
        last = completion[-1]
        if isinstance(last, dict):
            return str(last.get("content", ""))
    return str(completion)


def train(config_path: str | Path) -> Any:
    """Run GRPO training from a YAML config. Returns the trained ``GRPOTrainer``.

    Loads the model, builds the dataset and reward function, and runs
    ``GRPOTrainer.train()``. No metrics are fabricated: the caller inspects the
    trainer/logs for real outcomes.
    """
    import torch  # noqa: F401
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import GRPOConfig, GRPOTrainer

    cfg = load_config(config_path)

    tokenizer = AutoTokenizer.from_pretrained(cfg.model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(cfg.model_name)

    dataset = build_dataset(cfg)
    aux_client = make_aux_client(cfg, model=model, tokenizer=tokenizer)
    reward_func = make_reward_func(cfg, aux_client)

    grpo_args = GRPOConfig(
        output_dir=cfg.output_dir,
        seed=cfg.seed,
        report_to=[],
        save_strategy="no",
        use_vllm=False,
        **cfg.grpo,
    )
    trainer = GRPOTrainer(
        model=model,
        reward_funcs=reward_func,
        args=grpo_args,
        train_dataset=dataset,
        processing_class=tokenizer,
    )
    trainer.train()
    return trainer


def main(argv: list[str] | None = None) -> int:
    """CLI entry: ``python -m grapevine.train.grpo <config.yaml>``."""
    import argparse

    parser = argparse.ArgumentParser(description="Grapevine GRPO training")
    parser.add_argument("config", help="path to a YAML training config")
    args = parser.parse_args(argv)
    train(args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
