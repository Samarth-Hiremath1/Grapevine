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
    option on at least 20 tasks and is never wrong when it does. Twenty right
    commitments by luck has probability 0.25²⁰, about 10⁻¹².
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

### What `solo_solvability` reports

| Field | What it is |
|---|---|
| `primary_estimate` | The learned probe, fitted on half the batch and scored on the other half, pooled over agents: accuracy, 95% Wilson interval, advantage over chance, share of the pooling gain, n. The least optimistic estimate here. |
| `probes` | Each of six explicit probes per agent, and the learned probe: accuracy, interval, advantage, share of pooling gain, commitments and how many were right, and its p-value against chance. A k-way tie containing the gold option scores 1/k. |
| `full_information_accuracy` | How often the stated rule reaches the answer with everything pooled. |
| `twin_test` | Per agent: views certified not to determine the answer, views with consistent twins, views with no twin (below). |
| `zero_information_diagnostic` | Whether any probe beats chance at the Bonferroni-corrected alpha. **Diagnostic only.** |
| `minimum_detectable_accuracy` | The lowest true single-view accuracy a per-agent probe that commits to one option detects with 80% power at this n. The diagnostic's power. |
| `rule` | The classification rule above, in words. |

The best explicit probe is the best of nineteen and is biased upwards. Report
`primary_estimate` when quoting one number.

### The twin test

*Does a single view uniquely determine the answer?* Two views count as
indistinguishable when they have the same evidence structure: the same
multiset, over options, of (private support, private mentions, shared support,
shared mentions). A view is **certified not to determine** the answer when an
indistinguishable instance has a different gold option: another option in the
same view has gold's profile, so swapping their names leaves the view
unchanged but moves the answer; or another audited view with the same structure
has its gold elsewhere. Otherwise the view is unresolved, either because it does
determine the answer or because no twin was sampled; the card says which of the
two the audited views could tell apart.

Its assumptions, stated rather than hidden: option names are exchangeable in the
generator, and wording, unit order and text length carry no information. A
shortcut through wording is invisible to this test, and to the learned probe.

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
- That most views do not determine the answer, when the twin test certifies
  them, at the level of the evidence structure.

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
| Reliable solo shortcut | at least 20 commitments, none wrong | `check_solo_solvability` |
| Leak tolerance | 0 tasks | `check_leak` |
| Power reported | 80% | `minimum_detectable_accuracy` |
| "Indistinguishable from pooling" | 0.05, not corrected | `check_reward_hacking` |

Before this specification, `solo_solvability` and `reward_hacking` failed when
any probe beat chance. No committed run, result or pre-registered number
changes with the reclassification; the committed cards were regenerated.
