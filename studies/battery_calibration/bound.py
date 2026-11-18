"""The exact single-view bound for the clean control's layout.

The control (``tests/fixtures/flawed_envs``) and the example in
``examples/02_write_an_environment.py`` fix the totals at ``t + 1`` for gold and
``t`` for every other option, with ``t`` uniform over ``K..2K``, and split each
total over three agents uniformly among the splits with every share in
``0..K``, independently per option. One agent's view of the support is its
vector of shares. This computes, exactly, the accuracy of the Bayes-optimal
guess from that view: the most any single-view solver can reach.
"""

from __future__ import annotations

from itertools import product


def exact_single_view_bayes(k: int, ts: list[int]) -> float:
    """Exact Bayes-optimal accuracy from one view.

    Args:
        k (int): Mentions per option per agent; each share is in ``0..k``.
        ts (list[int]): The values ``t`` is drawn from, uniformly.

    Returns:
        float: The Bayes-optimal single-view accuracy.
    """

    def ways(total: int, parts: int) -> int:
        return sum(1 for c in product(range(k + 1), repeat=parts) if sum(c) == total)

    like: dict[tuple[int, int], float] = {}
    for tau in set(ts) | {t + 1 for t in ts}:
        whole = ways(tau, 3)
        for x in range(k + 1):
            like[(x, tau)] = ways(tau - x, 2) / whole
    accuracy = 0.0
    for view in product(range(k + 1), repeat=4):
        best = 0.0
        for gold in range(4):
            joint = 0.0
            for t in ts:
                q = 1.0
                for j in range(4):
                    q *= like[(view[j], t + (j == gold))]
                joint += q
            best = max(best, joint / (4 * len(ts)))
        accuracy += best
    return accuracy


def control_bound() -> dict[str, float]:
    """The bound for the control's and the example's parameters (K = 6).

    Returns:
        dict[str, float]: ``bayes`` and ``chance``.
    """
    k = 6
    return {"bayes": exact_single_view_bayes(k, list(range(k, 2 * k + 1))), "chance": 0.25}
