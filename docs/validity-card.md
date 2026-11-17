# The Validity Card

What `grapevine audit` writes, what each part means, and what an audit can and
cannot establish. The card is `validity_card.json` (for machines and for run
manifests, which record its hash) and `validity_card.md` (for people).

## Statuses

| Status | Meaning | Stops a card passing? |
|---|---|---|
| `pass` | The check ran and found nothing. | no |
| `measured` | The check quantified a partial-information advantage -- what one agent, or a team that does not pool, can do -- and confirmed no failure. **The numbers are the result.** | no |
| `warn` | A real limitation that narrows what a result means. | no |
| `inconclusive` | Too little evidence to classify. Never presented as a pass. | no |
| `fail` | A confirmed validity failure. A coordination result from this environment would not mean what it says. | **yes** |
| `skipped` | The check could not run, because the environment does not provide what it needs. Never presented as a pass. | no |

The **verdict** is the worst status present, in the order pass, measured, warn,
inconclusive, fail; `skipped` is listed but does not count. A card **passes**
when no check failed. The RL audit gate refuses a card that does not pass,
unless `--allow-flagged` is given and recorded.

## The two checks that measure

`solo_solvability` asks what one agent can do from its own view;
`reward_hacking` asks what a team that never pools can earn. Each reports one
of three things:

- **`fail` -- a confirmed shortcut.**
  - `solo_solvability`: some probe, on one agent's view, commits to a single
    option on at least 20 tasks and is never wrong when it does. How certain
    that is, and what it does and does not mean, is below under "How sure is a
    reliable shortcut?".
  - `reward_hacking`: a non-pooling team cannot be distinguished from pooling,
    or the reward pays for something other than being right.
  - Deterministic answer leakage -- one unit that settles a task, or a view that
    names only the gold option -- is the separate check `leak`, which fails on
    a single leaking task.
- **`measured` -- an advantage, quantified.** No confirmed failure. The card
  reports the numbers below, and the status does not change with sample size.
- **`inconclusive` -- fewer than 20 tasks.** Too few for the held-out probe and
  the twin test.

These rules are the only thresholds in the classification, and each is a floor
on evidence or a zero tolerance for error, not a tolerance on how large an
advantage may be. The card does not decide whether a measured advantage is
acceptable: that depends on what pooling adds, which it reports alongside.

### How sure is a reliable shortcut?

The rule detects a probe that commits to one option on at least 20 tasks and is
never wrong. Two different questions are worth separating.

**Could an uninformative probe do this by luck?** Only if every assumption here
holds is the answer "almost never":

- the probe's committed choice is independent of which option is gold (the
  null of no information);
- the gold option is uniform over `m` options, so a committed guess is right with
  probability `1/m` -- `balance` tests this, and a skewed answer order breaks it;
- commitments on different tasks are independent -- true here, because each task
  is generated from its own seed, but not for a hand-built task set with
  near-duplicates.

Then 20 right commitments has probability `(1/m)²⁰`, about 9×10⁻¹³ for four
options. `solo_solvability` runs 19 probes, three of which see the same tasks
through different agents; a union bound, which needs no independence between
probes, gives at most 19 × 0.25²⁰ ≈ 1.7×10⁻¹¹ per audit. Repeated audits add
their own terms.

**Does it mean the shortcut is perfect?** No. Environments of the kind in
"Why zero information is a diagnostic" are never uninformative, so the relevant
comparison is a probe with *some* information, not none. Twenty right out of
twenty is consistent with a true accuracy-when-committing as low as 83.2% (the
two-sided 95% Clopper-Pearson bound, `0.025^(1/20)`; at 200 commitments, 98.2%).
The card reports this bound for every such probe as
`accuracy_when_committed_lower95`, and the `fail` summary quotes it. So
"reliable" means *right whenever it commits, on enough tasks that its accuracy
when committing is high with 95% confidence* -- not certainly perfect, and not
necessarily on every task, since a probe may decline to commit.

### What `solo_solvability` reports

| Field | What it is |
|---|---|
| `primary_estimate` | The learned probe, fitted on half the batch and scored on the other half, pooled over agents: accuracy, 95% Wilson interval, advantage over chance, share of the pooling gain, n. The least optimistic estimate here. |
| `probes` | Each of six explicit probes per agent, and the learned probe: accuracy, interval, advantage, share of pooling gain, commitments and how many were right, and its p-value against chance. A k-way tie containing the gold option scores 1/k. |
| `full_information_accuracy` | How often the stated rule reaches the answer with everything pooled. |
| `feature_twin_test` | Per agent: views with a feature twin that has a different answer, views whose feature twins all agree, views with no feature twin (below). Feature-level only. |
| `zero_information_diagnostic` | Whether any probe beats chance at the Bonferroni-corrected alpha. **Diagnostic only.** |
| `minimum_detectable_accuracy` | The lowest true single-view accuracy a per-agent probe that commits to one option detects with 80% power at this n. The diagnostic's power. |
| `rule` | The classification rule above, in words. |

The best explicit probe is the best of nineteen and is biased upwards. Report
`primary_estimate` when quoting one number.

### The feature-level twin test

*Does the evidence pattern of one view pin down the answer?* Two views are
**feature twins** when they have the same evidence pattern: the same multiset,
over options, of (private support, private mentions, shared support, shared
mentions). A view has a **feature twin with a different answer** when another
option in the same view has gold's profile, or another audited view with the
same pattern has its gold option elsewhere. Otherwise its feature twins all
agree, or it has none in the batch.

**What it does not show.** Feature twins are not indistinguishable
observations. The text an agent actually reads -- wording, the order of units,
their length -- differs between feature twins, and nothing here checks that it
carries no information. So a feature twin with a different answer means the
evidence *pattern* leaves the answer open; it does not prove the full view
does. Conversely, feature twins that all agree are consistent with a view that
determines its answer, not proof of one. The test is reported as evidence
alongside the probes and never decides a status on its own.

## Why zero information is a diagnostic, not a requirement

The strict test -- no single-view solver beats chance -- cannot be met by a large
class of environments, including every one in this repository. The argument,
with its assumptions:

**Assumptions.**

1. *Additive decision.* The gold option is, by construction, the unique argmax
   of a total `T(o) = Σ_k g_k(o)` in which each term `g_k` is a function of
   what a single agent can see. Shared information counts as one term.
2. *Unique winner.* The argmax is unique on every task.
3. *Finite expectations* for every term.
4. *Uniform answer.* The gold option is uniformly distributed over the `m`
   options, so chance accuracy is `1/m`. The generators here shuffle the
   answer order, which gives this; `balance` tests it.

**Claim.** Some single view is not independent of the gold option, and under
assumption 4 the Bayes-optimal guess from that view is right more often than
`1/m`.

**Argument.** If every view were independent of the gold option, then for each
term `E[g_k(gold)] = E[mean_o g_k(o)]`, because averaging over a gold option that
is independent of `g_k` is averaging over options. Summing,
`E[T(gold)] = E[mean_o T(o)]`. But by assumptions 1 and 2, `T(gold) > T(o)` for
every other `o`, so `T(gold) > mean_o T(o)` on every task and, with 3,
`E[T(gold)] > E[mean_o T(o)]`. Contradiction. So some view `V` has a posterior
`P(gold = o | V)` that differs from uniform with positive probability. Where it
differs, its largest entry exceeds `1/m`, so `E[max_o P(gold = o | V)] > 1/m`:
the Bayes-optimal accuracy from `V` beats chance.

**Checked here.** `tests/test_audit.py::TestClassification` verifies the
identity the argument rests on, on 1,000 control tasks: summed over views,
gold's lean equals gold's lead in the pooled total (0.75 facts per task for a
one-fact margin over four options). The control's exact Bayes-optimal
single-view accuracy, 29.8%, is computed in `studies/battery_calibration/bound.py`
and matched by the generator.

**Where it does not apply.**

- Without assumption 4 the claim weakens to "some view carries information";
  an informative view need not raise accuracy above the best prior guess.
- Non-additive rules: "the option with an odd number of supporting facts", or
  any rule whose total is not a sum of per-view terms, can be built so that
  every single view is exactly uninformative.
- It says nothing about *which* view is informative, or how much: possibly one
  agent's view and not the others', and possibly very little.
- It is about the generator's distribution, not about a fixed, hand-picked set
  of tasks.

So for environments that satisfy the assumptions, a zero-information
requirement would fail every one of them once enough tasks were audited, and
pass them before that. That is why it is reported as a diagnostic, with its
power, and the status is decided by whether a shortcut is confirmed.

## What an audit can establish

- That a specific, checked failure is present: a leak, a reliable solo
  shortcut, a content-blind shortcut, a hackable reward, an unstated
  objective, a lenient scorer, and the other checks in `docs/audit-battery.md`.
- How much one agent, or a team that does not pool, can do, with an interval
  and the audit's power to detect more.
- How often the evidence pattern of a view, at the level of four counts per
  option, leaves the answer open (the feature-level twin test). Not that the
  full view does.

## What it cannot establish

- **That an environment measures coordination.** A pass means the checks found
  nothing at this sample size.
- **That no shortcut exists.** The probes and the twin test see support and
  name counts per block; a shortcut through wording, order or length is not
  looked for, and the learned probe only learns over the channels it is given.
- **That a measured advantage is acceptable.** That is a judgement about the
  study, compared with what pooling adds.
- **Anything about model behaviour.** The audit runs no model.
- **That the battery is calibrated against flaws other people would plant.**
  Every fixture was written by the author of the checks.

## Thresholds, all of them

| What | Value | Where |
|---|---|---|
| Significance for "beats chance" | 0.05, Bonferroni-corrected within a check | `family_alpha` |
| Minimum tasks to classify `solo_solvability`, `reward_hacking` | 20 | `MIN_TASKS_TO_CLASSIFY` |
| Reliable solo shortcut | at least 20 commitments, none wrong (accuracy when committing ≥ 83.2% at 95% when exactly 20) | `check_solo_solvability` |
| Leak tolerance | 0 tasks | `check_leak` |
| Power reported | 80% | `minimum_detectable_accuracy` |
| "Indistinguishable from pooling" | 0.05, not corrected | `check_reward_hacking` |

Before this specification, `solo_solvability` and `reward_hacking` failed when
any probe beat chance. No committed run, result or pre-registered number
changes with the reclassification; the committed cards were regenerated.
