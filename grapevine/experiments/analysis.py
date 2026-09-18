"""Per-condition metrics and uncertainty for the coordination ablation.

Every metric here is computed from ground-truth environment state (the gold
answer, the engineered decoy option, the known required private facts) or from
mechanical properties of the transcript. No LLM judge is involved anywhere.

Per-condition rates (accuracy, decoy rate) use exact Clopper-Pearson 95%
intervals. The earlier percentile bootstrap collapses to a zero-width interval
when every episode has the same outcome (1/200 gave [0, 1.5%], 100/100 gave
[100%, 100%]; see audit L6). Differences between conditions on the same tasks
still use a paired percentile bootstrap, since a difference of two binary
outcomes is not itself binomial.
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field
from typing import Any

from grapevine.rewards.reward import compute_surfacing
from grapevine.rollout.engine import Episode

#: Number of bootstrap resamples used for confidence intervals.
N_BOOTSTRAP = 10_000


def bootstrap_ci(
    values: list[float], n_resamples: int = N_BOOTSTRAP, seed: int = 0, alpha: float = 0.05
) -> tuple[float, float]:
    """Percentile bootstrap confidence interval for the mean of ``values``.

    Args:
        values: Per-episode observations (e.g. 1.0/0.0 correctness).
        n_resamples: Number of bootstrap resamples.
        seed: Seed for reproducibility -- the same data always yields the same CI.
        alpha: Significance level; 0.05 gives a 95% interval.

    Returns:
        ``(low, high)``. Returns ``(nan, nan)`` for an empty input.
    """
    if not values:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(values)
    means: list[float] = []
    for _ in range(n_resamples):
        total = 0.0
        for _ in range(n):
            total += values[rng.randrange(n)]
        means.append(total / n)
    means.sort()
    lo_idx = int((alpha / 2) * n_resamples)
    hi_idx = min(int((1 - alpha / 2) * n_resamples), n_resamples - 1)
    return (means[lo_idx], means[hi_idx])


def _binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p), summed in log space for stability."""
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 1.0 if k >= n else 0.0
    log_p, log_q = math.log(p), math.log1p(-p)
    total = 0.0
    for i in range(k + 1):
        log_term = (
            math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
            + i * log_p + (n - i) * log_q
        )
        total += math.exp(log_term)
    return min(total, 1.0)


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact Clopper-Pearson interval for ``k`` successes in ``n`` trials.

    Found by bisection on the binomial CDF, so no SciPy dependency. The bounds
    are 0 when ``k == 0`` and 1 when ``k == n``; otherwise the lower bound solves
    ``P(X >= k) = alpha/2`` and the upper bound ``P(X <= k) = alpha/2``.
    """
    if n <= 0:
        return (float("nan"), float("nan"))
    if not 0 <= k <= n:
        raise ValueError(f"k={k} outside [0, n={n}]")

    def solve(f: Any) -> float:
        lo, hi = 0.0, 1.0
        for _ in range(100):
            mid = (lo + hi) / 2
            if f(mid):
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2

    lower = 0.0 if k == 0 else solve(lambda p: 1.0 - _binom_cdf(k - 1, n, p) >= alpha / 2)
    upper = 1.0 if k == n else solve(lambda p: _binom_cdf(k, n, p) <= alpha / 2)
    return (lower, upper)


@dataclass
class ConditionSummary:
    """Aggregate metrics for one experimental condition.

    Attributes:
        condition: Condition label (``full_info`` / ``no_communication`` /
            ``communication``).
        n: Number of episodes.
        accuracy: Fraction whose team answer equals the gold answer.
        accuracy_ci: Clopper-Pearson 95% interval for ``accuracy``.
        decoy_rate: Fraction landing on the engineered decoy -- the option that
            shared information alone favours. The mechanistic metric: failures
            concentrated here indicate reasoning from common ground rather than
            pooled private evidence.
        decoy_rate_ci: Clopper-Pearson 95% interval for ``decoy_rate``.
        other_wrong_rate: Fraction wrong but not on the decoy.
        parse_failures: Episodes where no option could be parsed at all. Reported
            separately so refusals are never silently scored as reasoning errors.
        tie_rate: Fraction of episodes decided by the tie-break (no-communication
            only; ``None`` elsewhere).
        accuracy_ties_incorrect: Accuracy when every tie-broken episode is scored
            incorrect -- a lower bound showing how much the tie-break rule moves
            the headline number (no-communication only).
        surfacing_rate: Mean fraction of required private facts that appeared in
            the discussion. Only meaningful where a channel exists; ``None`` for
            conditions with no communication.
        total_cost_usd: Summed per-episode cost.
    """

    condition: str
    n: int
    accuracy: float
    accuracy_ci: tuple[float, float]
    decoy_rate: float
    decoy_rate_ci: tuple[float, float]
    other_wrong_rate: float
    parse_failures: int
    parse_failure_rate: float
    tie_rate: float | None
    accuracy_ties_incorrect: float | None
    surfacing_rate: float | None
    total_cost_usd: float
    total_prompt_tokens: int
    total_completion_tokens: int
    total_calls: int
    ci_method: str = "clopper-pearson"
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-ready dict."""
        return asdict(self)


def summarize_condition(
    condition: str, episodes: list[Episode], bootstrap_seed: int = 0
) -> ConditionSummary:
    """Compute the full metric set for one condition.

    ``decoy_rate`` requires each episode to carry ``metadata["decoy_option"]``
    (the runner attaches it from the task's ground truth). Episodes without it
    contribute 0 to the decoy tally.
    """
    n = len(episodes)
    if n == 0:
        raise ValueError(f"no episodes for condition {condition!r}")

    correct = [1.0 if e.correct else 0.0 for e in episodes]
    decoy_hits = [
        1.0
        if (e.team_answer is not None and e.team_answer == e.metadata.get("decoy_option"))
        else 0.0
        for e in episodes
    ]
    parse_failures = sum(1 for e in episodes if e.team_answer is None)
    other_wrong = sum(
        1
        for e, d in zip(episodes, decoy_hits, strict=True)
        if (not e.correct) and d == 0.0 and e.team_answer is not None
    )

    # Tie statistics: no-communication only.
    tie_flags = [e.metadata.get("was_tie") for e in episodes]
    has_ties = any(f is not None for f in tie_flags)
    tie_rate: float | None = None
    acc_ties_incorrect: float | None = None
    if has_ties:
        ties = [1.0 if f else 0.0 for f in tie_flags]
        tie_rate = sum(ties) / n
        acc_ties_incorrect = (
            sum(
                1.0
                for e, t in zip(episodes, ties, strict=True)
                if e.correct and t == 0.0
            )
            / n
        )

    # Surfacing only means something where agents can actually see each other.
    surfacing: float | None = None
    if any(m.role == "discussion" for e in episodes for m in e.messages):
        rates = [compute_surfacing(e).surfacing_rate for e in episodes]
        surfacing = sum(rates) / len(rates)

    return ConditionSummary(
        condition=condition,
        n=n,
        accuracy=sum(correct) / n,
        accuracy_ci=clopper_pearson(int(sum(correct)), n),
        decoy_rate=sum(decoy_hits) / n,
        decoy_rate_ci=clopper_pearson(int(sum(decoy_hits)), n),
        other_wrong_rate=other_wrong / n,
        parse_failures=parse_failures,
        parse_failure_rate=parse_failures / n,
        tie_rate=tie_rate,
        accuracy_ties_incorrect=acc_ties_incorrect,
        surfacing_rate=surfacing,
        total_cost_usd=sum(float(e.usage.get("cost_usd", 0.0)) for e in episodes),
        total_prompt_tokens=int(sum(float(e.usage.get("prompt_tokens", 0.0)) for e in episodes)),
        total_completion_tokens=int(
            sum(float(e.usage.get("completion_tokens", 0.0)) for e in episodes)
        ),
        total_calls=int(sum(float(e.usage.get("n_calls", 0.0)) for e in episodes)),
    )


def paired_difference_ci(
    a: list[float], b: list[float], n_resamples: int = N_BOOTSTRAP, seed: int = 0
) -> tuple[float, tuple[float, float]]:
    """Bootstrap the mean paired difference ``a - b`` over the same tasks.

    Conditions are run on identical task seeds, so pairing removes
    task-difficulty variance and gives a tighter, more honest interval than
    comparing two independent CIs.

    Returns:
        ``(mean_difference, (low, high))``.
    """
    if len(a) != len(b):
        raise ValueError("paired comparison requires equal-length inputs")
    if not a:
        return (float("nan"), (float("nan"), float("nan")))
    diffs = [x - y for x, y in zip(a, b, strict=True)]
    mean = sum(diffs) / len(diffs)
    return (mean, bootstrap_ci(diffs, n_resamples=n_resamples, seed=seed))
