"""Task families behind a common :class:`~grapevine.envs.base.Env` interface."""

from collections.abc import Callable
from typing import Any

from grapevine.envs.adapters import HiddenProfileV1, SplitEvidenceV1
from grapevine.envs.base import Env, Task
from grapevine.envs.hidden_profile import HiddenProfileConfig, HiddenProfileEnv
from grapevine.envs.split_evidence import SplitEvidenceConfig, SplitEvidenceEnv
from grapevine.protocol import Environment

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


#: Environments behind the :mod:`grapevine.protocol` interface, by name. This is
#: the registry ``grapevine audit`` and the RL entry points resolve against.
#: Unlike :data:`REGISTRY`, it includes environments that fail their audit: the
#: audit's job is to say so, not to hide them. What :data:`UNREGISTERED` governs
#: is whether an environment may be *run* to produce results.
ENVIRONMENTS: dict[str, Callable[[], Environment]] = {
    "hidden_profile": HiddenProfileV1,
    "split_evidence": SplitEvidenceV1,
}


def get_environment(name: str) -> Environment:
    """Instantiate a registered environment by name.

    Args:
        name: An environment name, as listed by :func:`list_environments`.

    Returns:
        A fresh instance with its default configuration.

    Raises:
        KeyError: If no environment has that name.
    """
    if name not in ENVIRONMENTS:
        raise KeyError(
            f"unknown environment {name!r}. Available: {', '.join(sorted(ENVIRONMENTS))}"
        )
    return ENVIRONMENTS[name]()


def list_environments() -> tuple[str, ...]:
    """Every registered environment name, sorted."""
    return tuple(sorted(ENVIRONMENTS))


def register_environment(name: str, factory: Callable[[], Environment]) -> None:
    """Register an environment so the CLI and configs can name it.

    Args:
        name: The name to register under.
        factory: A zero-argument callable returning a configured environment.

    Raises:
        ValueError: If the name is already taken. Re-registering silently would
            let one environment's Validity Card be presented for another's
            tasks.
    """
    if name in ENVIRONMENTS:
        raise ValueError(f"environment {name!r} is already registered")
    ENVIRONMENTS[name] = factory


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
    "ENVIRONMENTS",
    "Env",
    "Environment",
    "HiddenProfileV1",
    "SplitEvidenceV1",
    "Task",
    "get_environment",
    "list_environments",
    "register_environment",
    "HiddenProfileEnv",
    "HiddenProfileConfig",
    "SplitEvidenceEnv",
    "SplitEvidenceConfig",
    "REGISTRY",
    "UNREGISTERED",
    "unavailable_reason",
]
