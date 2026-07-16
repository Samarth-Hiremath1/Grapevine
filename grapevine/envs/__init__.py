"""Task families behind a common :class:`~grapevine.envs.base.Env` interface."""

from grapevine.envs.base import Env, Task
from grapevine.envs.hidden_profile import HiddenProfileConfig, HiddenProfileEnv
from grapevine.envs.split_evidence import SplitEvidenceConfig, SplitEvidenceEnv

#: Registry mapping a family name to its ``(Env, Config)`` classes.
REGISTRY = {
    HiddenProfileEnv.family: (HiddenProfileEnv, HiddenProfileConfig),
    SplitEvidenceEnv.family: (SplitEvidenceEnv, SplitEvidenceConfig),
}

__all__ = [
    "Env",
    "Task",
    "HiddenProfileEnv",
    "HiddenProfileConfig",
    "SplitEvidenceEnv",
    "SplitEvidenceConfig",
    "REGISTRY",
]
