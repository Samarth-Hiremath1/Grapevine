"""CPU smoke test for the GRPO loop.

This proves the training loop is wired end to end: a real ``GRPOTrainer`` runs
two optimisation steps on a tiny model, generating agent-0 messages and scoring
them with the multi-agent-rollout verifiable reward. It asserts only that the
loop executed and the reward function was exercised -- it makes no claim about
accuracy or learning (that requires the GPU config and real training).

Skipped automatically when the optional ``train`` extra (torch/transformers/trl)
is not installed. Downloads a very small test model on first run.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("torch")
pytest.importorskip("transformers")
pytest.importorskip("trl")

from grapevine.train.grpo import (  # noqa: E402
    build_dataset,
    load_config,
    make_aux_client,
    make_reward_func,
    train,
)

CONFIG = "configs/smoke_cpu.yaml"


def test_config_and_dataset_build() -> None:
    cfg = load_config(CONFIG)
    assert cfg.aux_backend == "scripted"
    assert cfg.rollout.n_rounds == 1
    dataset = build_dataset(cfg)
    assert len(dataset) == cfg.n_train_tasks
    assert "prompt" in dataset.column_names
    assert "task_json" in dataset.column_names


def test_reward_func_runs_offline() -> None:
    cfg = load_config(CONFIG)
    dataset = build_dataset(cfg)
    aux = make_aux_client(cfg)  # scripted backend needs no model
    reward = make_reward_func(cfg, aux)
    task_json = list(dataset["task_json"])[:2]
    completions = ["I think the answer is clear.", "Sharing my facts now."]
    rewards = reward(completions=completions, task_json=task_json)
    assert len(rewards) == 2
    assert all(r in (0.0, 1.0) for r in rewards)


@pytest.mark.slow
def test_grpo_smoke_two_steps() -> None:
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")
    trainer = train(CONFIG)
    # The loop actually stepped twice.
    assert trainer.state.global_step == 2
    # The verifiable reward function was logged at least once.
    reward_logged = any(
        any(k.startswith("rewards/") or k == "reward" for k in entry)
        for entry in trainer.state.log_history
    )
    assert reward_logged
