"""Grapevine: a research toolkit for the Hidden Profile failure in multi-agent LLM teams.

The package is organised into independent subpackages:

* :mod:`grapevine.envs` -- procedurally generated tasks behind a common ``Env`` interface.
* :mod:`grapevine.rollout` -- the async multi-agent conversation engine and provider client.
* :mod:`grapevine.rewards` -- verifiable reward plus auxiliary transcript signals.
* :mod:`grapevine.eval` -- accuracy / gap-closure metrics and a transcript viewer.
* :mod:`grapevine.diagnostics` -- reward-hacking checks against degenerate policies.
* :mod:`grapevine.train` -- GRPO wiring (Hugging Face TRL) driven by the rollout engine.
"""

from grapevine.envs.base import Env, Task

__all__ = ["Env", "Task"]
__version__ = "0.0.1"
