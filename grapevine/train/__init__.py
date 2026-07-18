"""GRPO training pipeline (Hugging Face TRL) driven by the multi-agent rollout.

Heavy dependencies (``torch``/``transformers``/``trl``) are imported lazily inside
the functions that need them, so importing this package is cheap and does not
require the ``train`` extra to be installed.
"""

from grapevine.train.grpo import (
    TrainConfig,
    build_dataset,
    build_env,
    load_config,
    make_aux_client,
    make_reward_func,
    train,
)
from grapevine.train.reward import team_reward_for_completions

__all__ = [
    "TrainConfig",
    "load_config",
    "build_env",
    "build_dataset",
    "make_aux_client",
    "make_reward_func",
    "train",
    "team_reward_for_completions",
]
