# Response to the external review

The review is `docs/review-v0.2.md`, committed verbatim. Each finding was
re-derived independently before anything was changed; the numbers that differ
from the review's are given. Re-derivations that need code are in
`studies/v2_eval/review_followup.py`, whose output (`review_followup.md`) CI
checks. None of it is pre-registered, and no pre-registered number changed.

Status: **fixed**, **documented** (stated in the docs, not fixed), or **open**
(needs a decision by Samarth).

| Finding | Reproduced | Status |
|---|---|---|
| B1 "replicates" not supported | Yes. Agent 0 decides (`design.py`, `aggregator = 0`); private-only rule gives gold for every agent. Surfacing proxy: 16 of 95, not 17 | **fixed** (wording) |
| M1 single-view shortcuts outside the battery | Yes, and wider: "named, not most-named" is 600/600 on the clean control and the example too, not only v2 | **fixed**, with a limit that cannot be fixed (below) |
| M2 partial leak passes | Yes, exactly (23, 43, 69 of 200) | **fixed** |
| M3 minimality count | Yes (capped sample reported as total) | **fixed** |
| M4 `gpt-6-luna` H3 read loosely | Yes (8 v 1 discordant, 4 truncated, McNemar 0.039, seed 1 gives −1.0) | **fixed** (wording) |
| M5 who produced the labels | Settled from the session transcript: a model | **fixed** (relabelled everywhere) |
| m1 "run in CI" | Yes | **fixed** |
| m2 PROGRESS and prereg status | Yes | **fixed** |
| m3 verify-claims narrower than worded | Yes | **fixed** in part |
| m4 frozen digest covers unsent prompts | Not re-checked | **documented** |
| m5 false-fail study not independent | Judgement accepted | **documented**; tie noise **fixed** |
| m6 unregistered numbers that disagree | Yes | **fixed** |
| m7 battery mechanics | Judgement accepted | **documented** |
| m8 `gpt-4o-mini` result not audited | Judgement accepted | **documented** |
| n1 nits | Yes | **fixed**, except PyPI links (open, already recorded) |

## B1. "Replicates the v0 finding"

Accepted. The pre-registered reading the claim rested on says "on an
environment with no known shortcut", and after A2 that premise is false; the
deciding agent has the shortcut. `studies/v2_eval/README.md`, `README.md` and
the launch drafts now say: no gap detected; that a team matches full
information is not established; not a replication. The original sentence is
quoted in the study README so the revision is visible.

The surfacing proxy, re-run with the repository's matcher at its default
threshold, gives 16 of 95 correct `gpt-5.6-luna` communication episodes in which
agents 1 and 2 did not surface every gold fact they held; the review found 17.
The difference is in how turns are joined, and either way the point holds. It is
reported as exploratory, with the matcher's known recall.

## M1. Shortcuts the battery does not probe

Reproduced, and worse than reported. The review gave the "named, not
most-named" probe for v2 only; it is also 600/600 on the clean control and the
example, because in every layout here an agent's private notes name gold and one
other option, and the other is named more. The example environment and the
docs page that presents it now say it is an example of the protocol, not of a
sound design. `docs/audit-battery.md` has a "Known gaps" section, and the
README says what a passing card does and does not mean.

*Update, same day, after Samarth chose to extend the battery.* Fixed, in four
parts:

- `solo_solvability` gained `named_not_most_named_privately`,
  `least_shared_support`, and a learned probe that fits any rule over the
  within-view ranks of private and shared support and name counts on half the
  batch and tests it on the other half.
- Tie-breaks are scored by their expected value, with an exact null, so a
  solver with no information can no longer fail an environment by luck.
- The clean control and the example were rebuilt: every block names every
  option equally often, gold wins by exactly one fact, and each total is split
  over the agents at random. Both old control layouts are kept as negative
  controls (`legacy_pointer_support`, `legacy_gold_only_private_support`) and
  fail on every seed range tested.
- Every card reports `minimum_detectable_accuracy`: at 200 tasks, a per-agent
  probe usually misses a true single-view accuracy below 37.2%.

The limit that cannot be designed away: for a task decided by summed evidence,
with the answer uniformly distributed, some single view always carries
information about it (`docs/validity-card.md`, with the assumptions). The rebuilt
control's exact best single-view accuracy is 29.8% against 25% chance.

*Second update, same day.* Rather than add a tolerance, `solo_solvability` and
`reward_hacking` now separate a confirmed shortcut (`fail`: a probe that
commits on at least 20 tasks and is never wrong) from a measured advantage
(`measured`, with an interval, the share of the pooling gain and the audit's
power) and from too little evidence (`inconclusive`). The strict
zero-information test is kept as a labelled diagnostic. A twin test checks, at
the level of the evidence structure, whether views determine the answer. Over 40
seed ranges the control is `measured` on all 40, though the diagnostic rejects
on 17.

## M2. Partial leaks

Reproduced exactly. *Update:* fixed. `leak` now fails on a single leaking task
instead of testing the share of leaking tasks against chance accuracy. Planted
leaks in 5%, 10% and 20% of tasks fail on every seed range tested
(`studies/battery_calibration/README.md`), and a test plants one in a single
task.

## M3. Minimality count

Fixed. The count and the 10-entry sample are now separate, and
`tests/test_audit.py::TestMinimalityCounts` recomputes the count directly and
checks it is not capped. The committed cards changed only in the renamed field
(`tasks_affected`), since neither environment has redundant units.

## M4. `gpt-6-luna`

Accepted. The study README now says the H3 prediction was not met and no
pre-registered reading applies, gives the truncation split, and drops "exactly
0", noting that the bound moves to −1.0 with another bootstrap seed. The McNemar
test is in `review_followup.md` as exploratory; it was not the registered test.

## M5. The surfacing labels

Resolved, 2026-11-16, from the local session transcript in which the labels were
made rather than from anyone's memory: **they are model labels.** The assistant
model in that session drew the sample, labelled the 40 pairs itself, and scored
"my labels" against the metric; no person labelled or reviewed them. The
metric's verdict was hidden per pair, but messages were shown truncated to 420
characters. Every document that called them hand or human labels is corrected,
with the original wording quoted; the JSON is unchanged, and its `human` field is
recorded as a misnomer in `docs/audit_surfacing_labels.md`. The precision and
recall derived from them are agreement with one model's judgement.

## Minor findings and nits

- **m1**: `docs/rl.md` now says "run locally, 2026-11-16; configured for CI,
  not yet run there".
- **m2**: `docs/PROGRESS.md` has a Step 8 entry; the pre-registration's status
  line reads "run", with the original quoted.
- **m3**: claims can now carry `expect`, used for "one support pattern"; "at
  most 8/100" is checked across all four cells; a missing claims file gives a
  plain message instead of a traceback. Short-substring templates remain; they
  catch a changed number but not a changed sentence around it.
- **m4**: documented here, not fixed. CI should check that every prompt that
  actually opened an episode matches the frozen design; the review checked all
  3,600 by hand and found them identical.
- **m5**: accepted: the two clean environments make the same random calls, so
  their audits are correlated, and they are now reported separately, not
  pooled. The tie-break noise behind most of the old false alarms is gone; the
  calibration study now also measures missed defects.
- **m6**: the battery doc now says one clean environment in five, matching the
  simulation; the docstring separates the 23% upper bound for independent probes
  from the simulated rate; the unsupported sentence about tests recording
  collateral is gone.
- **m7**, **m8**: listed under "Known gaps" and in the study README respectively.
- **n1**: the docstring example now shows the real flagged checks; the flag is
  described as a boolean; the README runs examples with `uv run`, and states
  Python 3.11 or later; the deprecated class fixtures are module fixtures.
  `docs/index.md` links to `blob/main`, which resolves once `v0.2` is merged; and
  the PyPI links remain open (`docs/decisions.md`).
