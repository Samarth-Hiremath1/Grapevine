"""Task families behind a common :class:`~grapevine.envs.base.Env` interface."""

from typing import Any

from grapevine.envs.base import Env, Task
from grapevine.envs.hidden_profile import HiddenProfileConfig, HiddenProfileEnv
from grapevine.envs.split_evidence import SplitEvidenceConfig, SplitEvidenceEnv

#: Registry mapping a family name to its ``(Env, Config)`` classes. Only
#: families that are fit to run appear here; see :data:`UNREGISTERED`.
REGISTRY: dict[str, tuple[type[Env], type[Any]]] = {
    HiddenProfileEnv.family: (HiddenProfileEnv, HiddenProfileConfig),
}

#: Families that exist in the package but are deliberately not runnable, mapped
#: to the reason. The classes stay importable so their tests keep running and so
#: the defect can be fixed, but nothing that resolves a family by name -- the
#: CLI, the experiment runner, the training entry point -- will hand one out.
#:
#: ``split_evidence``'s final reasoning hop reads "From X, the active route
#: continues to Z", where Z is the gold answer, so whichever agent holds that
#: hop holds the answer outright. Over 100 generated tasks the answer appeared
#: in some agent's context in all 100. An environment that leaks its answer to a
#: single agent cannot measure distributed information, which is the whole
#: premise (see ``docs/decisions.md`` and ``docs/methodology.md``).
UNREGISTERED: dict[str, str] = {
    SplitEvidenceEnv.family: (
        "leaks the gold answer into a single agent's view in 100 of 100 generated "
        "tasks, so no condition built on it measures pooling"
    ),
}


def unavailable_reason(family: str) -> str | None:
    """Explain why ``family`` cannot be used, or return ``None`` if it can.

    Args:
        family: A task family name.

    Returns:
        A one-line reason suitable for an error message when the family exists
        but is unregistered, or ``None`` when the family is usable or unknown.
    """
    return UNREGISTERED.get(family)


__all__ = [
    "Env",
    "Task",
    "HiddenProfileEnv",
    "HiddenProfileConfig",
    "SplitEvidenceEnv",
    "SplitEvidenceConfig",
    "REGISTRY",
    "UNREGISTERED",
    "unavailable_reason",
]
