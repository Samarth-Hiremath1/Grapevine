"""``grapevine audit``: does this environment measure coordination, or something else?

An audit runs a battery of model-free checks over a batch of generated tasks and
emits a :class:`~grapevine.audit.card.ValidityCard`. It needs no API key, no
network and no GPU, and it runs in under a second on a few hundred tasks.

Example:
    >>> from grapevine.audit import audit
    >>> from grapevine.envs import get_environment
    >>> card = audit(get_environment("hidden_profile"), n_tasks=50)
    >>> card.verdict
    <Status.FAIL: 'fail'>
    >>> card.flagged_checks
    ('solo_solvability', 'shortcuts', 'objective')

The battery is calibrated, not merely asserted: ``tests/fixtures/flawed_envs/``
holds environments with exactly one planted defect each plus a clean control,
and CI requires every planted flaw to be flagged and the control to pass. It is
also required to rediscover the findings of this repository's own v0 audit
(``docs/audit.md``), by finding number.

That shows it catches the flaws its author thought to plant. It does not show
there are no others: see "Known gaps" in ``docs/audit-battery.md``.
"""

from __future__ import annotations

from grapevine.audit.card import CheckResult, Status, ValidityCard
from grapevine.audit.checks import CHECKS, CheckContext, run_checks
from grapevine.protocol import Environment

__all__ = [
    "CHECKS",
    "CHECK_IDS",
    "CheckContext",
    "CheckResult",
    "Status",
    "ValidityCard",
    "audit",
    "check_ids",
    "run_checks",
]


#: Check ids in card order. Each check function is named ``check_<id>``, and a
#: test asserts the result it returns carries the matching ``check_id``, so this
#: cannot drift from the registry.
CHECK_IDS: tuple[str, ...] = tuple(fn.__name__.removeprefix("check_") for fn in CHECKS)


def check_ids() -> tuple[str, ...]:
    """The ids of every registered check, in card order.

    Useful for ``--only`` on the command line, and for reading which checks the
    training entry point's audit gate refused on.
    """
    return CHECK_IDS


def audit(
    env: Environment,
    *,
    n_tasks: int = 200,
    seed: int = 0,
    alpha: float = 0.05,
    only: tuple[str, ...] | None = None,
) -> ValidityCard:
    """Audit an environment and return its Validity Card.

    Args:
        env: The environment to audit. Only :meth:`Environment.generate` is
            required; checks that need more report ``skipped``.
        n_tasks: How many tasks to generate. The default of 200 matches the v0
            study's N and gives the binomial tests enough power to separate a
            shortcut from chance.
        seed: Base seed. Consecutive seeds are used.
        alpha: Significance level for the "beats chance" and "indistinguishable
            from pooling" tests.
        only: Restrict to these check ids. The card then records that the others
            did not run.

    Returns:
        A :class:`~grapevine.audit.card.ValidityCard`.

    Raises:
        ValueError: If ``n_tasks`` is not positive.
    """
    if n_tasks < 1:
        raise ValueError("n_tasks must be at least 1")

    from grapevine import __version__

    tasks = tuple(env.generate_batch(n_tasks, seed))
    ctx = CheckContext(env=env, tasks=tasks, seed=seed, alpha=alpha, rng_seed=seed)
    results = run_checks(ctx, only=only)
    return ValidityCard(
        environment=env.name,
        version=env.version,
        config=dict(env.config_summary()),
        n_tasks=n_tasks,
        seed=seed,
        results=tuple(results),
        grapevine_version=__version__,
    )
