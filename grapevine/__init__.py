"""Grapevine: check whether a multi-agent eval or RL environment measures coordination.

A distributed-information task is one where no single agent holds enough to
answer, so the answer only becomes derivable once agents pool what they know.
That premise is what makes a coordination claim mean anything, and it is also
what quietly breaks. ``grapevine audit`` checks for the ways it breaks --
answers leaking into one view, content-blind shortcuts, an objective that never
reaches the models, a scorer that can be farmed -- and emits a Validity Card.

The tool exists because the first result this repository published was wrong.
A coordination failure that survived full information sharing turned out to be
objective underspecification: no prompt told the models what they were being
scored on. See ``studies/underspecification/`` and ``docs/audit.md``.

Quickstart, offline and with no API key::

    grapevine audit hidden_profile

Everything exported here is public API and follows semantic versioning.
Anything not listed in ``__all__`` is internal and may change in any release.

Subpackages:

* :mod:`grapevine.protocol` -- the environment protocol you implement.
* :mod:`grapevine.audit` -- the validity battery and the Validity Card.
* :mod:`grapevine.envs` -- bundled environments and the registry.
* :mod:`grapevine.rollout` -- the async multi-agent engine and provider clients.
* :mod:`grapevine.rewards` -- verifiable reward and transcript signals.
* :mod:`grapevine.eval` -- accuracy metrics and a transcript viewer.
* :mod:`grapevine.experiments` -- experiment runner and statistics.
"""

from grapevine.audit import CheckResult, Status, ValidityCard, audit, check_ids
from grapevine.envs import (
    DEFAULT_ENVIRONMENT,
    get_environment,
    list_environments,
    register_environment,
)
from grapevine.envs.base import Env, Task
from grapevine.envs.hidden_profile_v2 import HiddenProfileV2, HiddenProfileV2Config
from grapevine.envs.venue_choice import VenueChoice
from grapevine.protocol import (
    AgentView,
    Condition,
    DistributedTask,
    Environment,
    InfoUnit,
    Objective,
    Scorer,
    ScoreResult,
    SeedSplit,
    exact_match,
    support_total,
)

__all__ = [
    # The environment protocol: the one interface you implement.
    "AgentView",
    "Condition",
    "DistributedTask",
    "Environment",
    "InfoUnit",
    "Objective",
    "ScoreResult",
    "Scorer",
    "SeedSplit",
    "exact_match",
    "support_total",
    # The audit.
    "CheckResult",
    "Status",
    "ValidityCard",
    "audit",
    "check_ids",
    # The registry and the bundled environment.
    "DEFAULT_ENVIRONMENT",
    "HiddenProfileV2",
    "HiddenProfileV2Config",
    "VenueChoice",
    "get_environment",
    "list_environments",
    "register_environment",
    # Deprecated: the pre-protocol interface. Kept for one release because the
    # committed v0 runs load through it. Use Environment and DistributedTask.
    "Env",
    "Task",
    "__version__",
]

__version__ = "0.2.0"
