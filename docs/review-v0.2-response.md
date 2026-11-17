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
| M1 single-view shortcuts outside the battery | Yes, and wider: "named, not most-named" is 600/600 on the clean control and the example too, not only v2 | **documented**; battery change **open** |
| M2 partial leak passes | Yes, exactly (23, 43, 69 of 200) | **documented**; battery change **open** |
| M3 minimality count | Yes (capped sample reported as total) | **fixed** |
| M4 `gpt-6-luna` H3 read loosely | Yes (8 v 1 discordant, 4 truncated, McNemar 0.039, seed 1 gives −1.0) | **fixed** (wording) |
| M5 who produced the labels | Cannot be settled from the repository | **open** |
| m1 "run in CI" | Yes | **fixed** |
| m2 PROGRESS and prereg status | Yes | **fixed** |
| m3 verify-claims narrower than worded | Yes | **fixed** in part |
| m4 frozen digest covers unsent prompts | Not re-checked | **documented** |
| m5 false-fail study not independent | Judgement accepted | **documented** |
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

Not changed: the battery. Adding these probes would fail the clean control and
the example, so it means redesigning both, and it changes every committed card.
That is a decision for Samarth (open).

## M2. Partial leaks

Reproduced exactly. Documented under "Known gaps". Making `leak` fail on any
decisive unit, with dose-response fixtures, is a battery change and is open with
M1.

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

Open. `docs/audit.md` and `docs/assumptions.md` say the 40 labels were made by
hand by one person. Nothing in the repository records who, and if they were made
by a model, `CLAUDE.md` rule 8 requires every one of those documents to say so.
Samarth has been asked. Until it is settled, the label-derived numbers are not
registered in `docs/claims.yaml`.

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
  their 80 audits are about 40 independent ones, and "false alarm" is relative
  to the battery. Not re-run.
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
