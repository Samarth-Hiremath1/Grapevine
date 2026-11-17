"""Model-free solvers and degenerate policies the audit scores against a task.

Every function here answers a task without an LLM. They come in two groups.

**Solvers** take a view and return an option. They answer the question "could
this be solved without the reasoning the task claims to require?". The
reference solver :func:`reference` performs the computation the scoring rule
describes; the rest are shortcuts. A shortcut that beats chance on the
full-information view means the task has a cheaper route to the answer than the
one it advertises -- the v0 task was solved 200 times out of 200 by counting how
often each candidate's name appeared (``docs/audit.md`` L3).

**Policies** take a whole task and return an option, modelling a *team* that
never genuinely pools. If one of them earns the same reward as a team that does
pool, the reward is hackable: it can be collected without the behaviour it is
meant to incentivise.

Both groups are deterministic given their RNG, so the battery runs in CI in
milliseconds and stress-tests the task construction and the reward rather than
any particular model.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable, Sequence

from grapevine.protocol import AgentView, DistributedTask, InfoUnit, support_total

__all__ = [
    "DEGENERATE_POLICIES",
    "SHORTCUT_SOLVERS",
    "Policy",
    "Solver",
    "count_mentions",
    "fewest_mentions",
    "first_option",
    "longest_option",
    "mention_count",
    "private_scoring_rule",
    "reference",
    "shared_only",
    "uniquely_determined",
]

#: A solver picks an option given a view and the answer space.
Solver = Callable[[AgentView, Sequence[str], random.Random], str]

#: A policy picks an option given the whole task, modelling a team.
Policy = Callable[[DistributedTask, random.Random], str]


def count_mentions(text: str, option: str) -> int:
    """How often ``option`` is named in ``text``, counting whole words only.

    Plain substring counting is wrong here, and not academically: a control
    fixture in this repository used the phrase "listed alphabetically", which
    made every such sentence count as a mention of an option called "Alpha".
    Any name-matching measurement inherits that error -- the mention-count
    probes below, and a surfacing metric that looks for a fact's subject in a
    message. :func:`~grapevine.audit.checks.check_name_hygiene` reports when an
    environment's names collide this way.
    """
    pattern = re.compile(rf"(?<![A-Za-z]){re.escape(option)}(?![A-Za-z])", re.IGNORECASE)
    return len(pattern.findall(text))


def _argmax(scores: dict[str, float], answer_space: Sequence[str], rng: random.Random) -> str:
    """The highest-scoring option, ties broken at random.

    Random rather than by option order on purpose: "first among equals" would
    couple every solver to how the options happen to be ordered, and then a
    position effect in the task would read as solver skill.
    """
    best = max(scores.values())
    leaders = [option for option in answer_space if scores[option] == best]
    return rng.choice(leaders) if len(leaders) > 1 else leaders[0]


def uniquely_determined(
    units: Sequence[InfoUnit], answer_space: Sequence[str]
) -> str | None:
    """The option the scoring rule picks *unambiguously*, or ``None`` on a tie.

    Distinct from :func:`reference`, which breaks ties at random because a
    solver facing a tie really does have to guess. Correctness checks must not
    depend on that coin flip: when two options share the top support the task
    does not determine an answer, and an audit that called a lucky tie-break a
    pass would be measuring its own RNG.
    """
    totals = support_total(units, answer_space)
    best = max(totals.values())
    leaders = [option for option in answer_space if totals[option] == best]
    return leaders[0] if len(leaders) == 1 else None


def reference(view: AgentView, answer_space: Sequence[str], rng: random.Random) -> str:
    """Apply the scoring rule: the option with the most supporting weight.

    Not a shortcut. This is the computation the task says it requires, and the
    audit uses it twice: on the full-information view it must reach 100%, and on
    a single agent's view it must *not* beat chance.
    """
    return _argmax(support_total(view.units, answer_space), answer_space, rng)


def private_scoring_rule(view: AgentView, answer_space: Sequence[str], rng: random.Random) -> str:
    """Apply the scoring rule to this agent's *private* units alone.

    A reader who trusts what only it knows and discounts common ground. Unlike
    a name count, it reads which facts are support, so equalising how often each
    option is named does not defeat it. On a hidden profile built so that every
    private supporting fact favours the gold option, this solver is perfect from
    one agent's view. The battery lacked it until the ``hidden_profile_v2`` eval
    found a model doing exactly this (``studies/v2_eval/h1_investigation.md``).

    Args:
        view (AgentView): One agent's view.
        answer_space (Sequence[str]): The options.
        rng (random.Random): Breaks ties, as a solver facing one must guess.

    Returns:
        str: The option with the most private supporting weight.
    """
    return _argmax(support_total(view.private, answer_space), answer_space, rng)


def mention_count(view: AgentView, answer_space: Sequence[str], rng: random.Random) -> str:
    """Pick the option whose name appears most often in the text.

    Content-blind: it never reads what a sentence says about an option, only how
    often the option is named. When this matches :func:`reference`, the task does
    not require understanding its own facts. This is the check that catches the
    v0 template, where every strength fact began with the candidate's name, so
    name frequency was a sufficient statistic for the answer.
    """
    text = view.render()
    scores = {option: float(count_mentions(text, option)) for option in answer_space}
    return _argmax(scores, answer_space, rng)


def fewest_mentions(view: AgentView, answer_space: Sequence[str], rng: random.Random) -> str:
    """Pick the option whose name appears *least* often in the text.

    The inverse of :func:`mention_count`, and not a hypothetical: the obvious way
    to stop name-counting from solving a task is to add mentions of the wrong
    options until the right one is no longer the most-named. Overshoot and the
    right one becomes the *least*-named, which is just as cheap to exploit. An
    environment has to make mention counts uninformative, not merely
    non-monotonic in the answer.
    """
    text = view.render()
    scores = {option: -float(count_mentions(text, option)) for option in answer_space}
    return _argmax(scores, answer_space, rng)


def first_option(view: AgentView, answer_space: Sequence[str], rng: random.Random) -> str:
    """Always pick whichever option is listed first.

    Beats chance only when the gold answer's position is not uniform.
    """
    return answer_space[0]


def longest_option(view: AgentView, answer_space: Sequence[str], rng: random.Random) -> str:
    """Always pick the longest option string, ties by first occurrence.

    A classic multiple-choice artefact: elaborated answers are often the correct
    ones because the author wrote them with more care.
    """
    scores = {option: float(len(option)) for option in answer_space}
    return _argmax(scores, answer_space, rng)


def shared_only(view: AgentView, answer_space: Sequence[str], rng: random.Random) -> str:
    """Apply the scoring rule to the shared units alone, ignoring private ones.

    This is the hidden-profile failure mode made explicit: a team that discusses
    only what it already has in common lands here. On a well-formed task it must
    be wrong, because the shared information favours a decoy.
    """
    return _argmax(support_total(view.shared, answer_space), answer_space, rng)


#: Shortcut solvers evaluated on the full-information view. :func:`reference`
#: is excluded: it is the intended solution, not a shortcut.
SHORTCUT_SOLVERS: dict[str, Solver] = {
    "mention_count": mention_count,
    "fewest_mentions": fewest_mentions,
    "first_option": first_option,
    "longest_option": longest_option,
    "shared_only": shared_only,
}


# --- Degenerate team policies ------------------------------------------------


def genuine_pooling(task: DistributedTask, rng: random.Random) -> str:
    """Reference team: pools every unit and applies the scoring rule.

    Not degenerate. It is the bar the others are compared against.
    """
    return reference(task.full_view(), task.answer_space, rng)


def solo_guess(task: DistributedTask, rng: random.Random, agent_id: int = 0) -> str:
    """What one agent would answer from its own view, having asked nobody."""
    return reference(task.views[agent_id], task.answer_space, rng)


def no_discussion_majority(task: DistributedTask, rng: random.Random) -> str:
    """Every agent answers alone; the team takes a majority vote.

    No information is ever shared. On a well-formed hidden-profile task every
    agent sees the decoy leading in its own view and votes for it.
    """
    votes = [solo_guess(task, rng, i) for i in range(task.n_agents)]
    scores = {option: float(votes.count(option)) for option in task.answer_space}
    return _argmax(scores, task.answer_space, rng)


def copy_agent_zero(task: DistributedTask, rng: random.Random) -> str:
    """Everyone defers to agent 0's solo guess instead of contributing."""
    return solo_guess(task, rng, 0)


def defer_to_largest_view(task: DistributedTask, rng: random.Random) -> str:
    """Defer to whichever agent holds the most text, with no pooling.

    Picks up an environment that loads one agent more heavily than the others:
    if that agent's view is closer to sufficient, deference beats coordination.
    """
    agent_id = max(range(task.n_agents), key=lambda i: len(task.views[i].render()))
    return solo_guess(task, rng, agent_id)


def always_first_option(task: DistributedTask, rng: random.Random) -> str:
    """Ignore the task entirely and answer with the first option."""
    return task.answer_space[0]


def random_option(task: DistributedTask, rng: random.Random) -> str:
    """Ignore the task entirely and answer uniformly at random."""
    return rng.choice(list(task.answer_space))


def share_nothing_claim_everything(task: DistributedTask, rng: random.Random) -> str:
    """Answer from the shared units alone, as a team that only restates common ground.

    Distinct from :func:`no_discussion_majority`: here the agents do talk, but
    say only things everyone already knew, so no private unit is surfaced. A
    reward that cannot tell this apart from real pooling is not measuring
    coordination.
    """
    return shared_only(task.full_view(), task.answer_space, rng)


def verbose_non_answer(task: DistributedTask, rng: random.Random) -> str:
    """Emit a long block of text that names no option at all.

    Under a strict scorer this earns nothing, which is the point: it is the
    probe for a reward with a shaping term that pays for output length, effort
    or apparent diligence. Such a term is collectable without answering, so a
    policy optimising it learns to talk rather than to pool.
    """
    return (
        "Let me think carefully about this before committing. There are several "
        "considerations in play, and I want to weigh each of them properly rather "
        "than rushing to a conclusion. First, I should establish what information "
        "the group actually holds. Second, I should consider how that information "
        "bears on the decision. Third, I should sanity-check my reasoning. "
    ) * 3


def recite_without_answering(task: DistributedTask, rng: random.Random) -> str:
    """One agent recites every fact it holds, and nobody ever answers.

    Under a strict scorer this earns nothing. It is the probe for an
    *information-surfacing* shaping term -- a bonus for mentioning the facts the
    task says must be shared. Such a term pays a policy that talks about the
    right facts whether or not the team reaches a decision, so it is collectable
    without coordinating at all. ``grapevine.rl`` offers one, off by default, and
    this is how the audit gate sees it.
    """
    return "\n".join(unit.text for unit in task.views[0].units)


#: Degenerate team policies scored against the task's own reward. Each reaches
#: an answer without pooling private information.
DEGENERATE_POLICIES: dict[str, Policy] = {
    "recite_without_answering": recite_without_answering,
    "verbose_non_answer": verbose_non_answer,
    "always_first_option": always_first_option,
    "random_option": random_option,
    "no_discussion_majority": no_discussion_majority,
    "copy_agent_zero": copy_agent_zero,
    "defer_to_largest_view": defer_to_largest_view,
    "share_nothing_claim_everything": share_nothing_claim_everything,
}


def view_without(view: AgentView, unit_id: str) -> AgentView:
    """``view`` with one unit removed, used by the minimality check."""
    return AgentView(
        agent_id=view.agent_id,
        shared=tuple(u for u in view.shared if u.unit_id != unit_id),
        private=tuple(u for u in view.private if u.unit_id != unit_id),
    )


def units_without(units: Sequence[InfoUnit], unit_id: str) -> tuple[InfoUnit, ...]:
    """``units`` with one unit removed."""
    return tuple(u for u in units if u.unit_id != unit_id)
