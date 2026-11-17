# PR draft: `audit/pre-publication` → `main`, tag `v0.1.0`

Opened on 2026-11-17 with Samarth's approval to prepare and open it. Merging
it and tagging `v0.1.0` each need his separate approval, and green GitHub CI
on the commit being merged (`CLAUDE.md` rule 10, `launch/release-checklist.md`).

```bash
# Open the PR (review the body first).
gh pr create --base main --head audit/pre-publication \
    --title "Audit the v0 result and correct the headline" \
    --body-file launch/pr-v0.1.0.md

# After it merges, from an up-to-date main:
git tag -a v0.1.0 -m "v0.1.0: the audited case study"
git push origin v0.1.0
```

**Why tag `v0.1.0` and not `v0.2.0`:** this is the case study and the audit that
corrected it, with no library release attached — the package is still
unpublished at `0.0.1`. `v0.1.0` gives the corrected write-up a citable point
before `v0.2` turns the audit into a tool. Semantic versioning on the package
starts at `0.2.0`, when there is a public API to be stable about.

**Scope check:** this PR does not include the `v0.2` branch's work. It is the 17
commits on `audit/pre-publication` as of `cdf828d`: the 16 reviewed earlier, and
one correction made before opening (below). Merge this first; `v0.2` merges
onto the result cleanly (checked with a trial merge).

---

<!-- PR body begins here -->

## What this changes

`main`'s README leads with a coordination failure. That headline is wrong, and
this branch replaces it with what the evidence actually supports.

Three LLM agents hold the facts needed for a hiring decision between them. I
reported that even after they shared every required fact, the team still trailed
a single agent holding everything by 18.5 points, and read that as a failure to
integrate pooled information.

It was not. No prompt in any condition stated the question or the scoring rule.
Transcripts show agents asking what decision they were supposed to be making, in
174 of 200 episodes. Stating the question and the rule took that condition from
68/100 to 100/100 on the same tasks, and those requests fell to 2 of 100.

| Condition | Task not stated | Task and rule stated |
|---|---|---|
| A. one agent, all facts | 171/200 · 85.5% | original prompt 96/100 · 96%<br>matched prompt 100/100 · 100% |
| B. three agents, no talking | 1/200 · 0.5% | 0/100 · 0% |
| C. three agents, told to share | 134/200 · 67.0% | 100/100 · 100% |
| D. three agents, neutral prompt | 111/200 · 55.5% | 99/100 · 99% |

Chance is 25%. Every cell is regenerated from committed episodes by one command;
none is typed in.

**B is the result that survived.** With no communication, every agent sees the
decoy ahead in its own facts and votes for it, with or without the task stated.

**A second mistake, caught the same way.** With the task stated, C and D first
appeared to *beat* the full-information baseline (100 and 99 against 96) — a far
more attention-getting claim. A's prompt was laid out differently from the other
conditions. Given the same layout, A scored 100/100, and the claim evaporated.

## What is in the branch

The audit came first and is committed as it ran:

- `docs/assumptions.md` — every assumption the result rests on, written and
  committed (`55aac5a`) **before** any of them were tested.
- `docs/audit.md` — what each check found, by severity: 2 invalidating, 11
  limiting, 3 latent defects, plus what could not be checked. $0 of API spend;
  every check ran offline against committed code and committed data.
- `docs/decisions.md` — every judgement call, dated, including the conditions
  registered before they were run.
- `REPORT.md` — the narrative account.

Fixes, each with a regression test that fails on the old code:

- The answer parser returned a wrong option instead of failing. Substring
  matching in both directions mapped an empty or one-letter answer to the first
  option; 7 of 18 adversarial cases returned a wrong option. Re-parsing all
  2,120 committed answers and votes moved no reported number.
- Paired differences could misalign after a dropped episode. Now aligned on task
  id, with mismatched task sets refused outright.
- Condition D's aggregator ignored `prompt_style`, so its decision step used the
  instructed prompt. Fixed, and D was rerun from scratch; only the rerun is
  reported (106/200 → 111/200, a change of +2.5 points [−5.5, +11.0], so the
  confound was not driving the old number).
- Run provenance was captured when the manifest was written, not before the
  first call. Now both.
- Bootstrap intervals collapsed at the extremes: 1/200 read [0, 1.5%]. Per-rate
  intervals are now exact Clopper-Pearson, so 1/200 reads [0.02%, 2.75%].
- No pinned environment. `uv.lock` added.

Four new runs so every arm is measured both ways: B and D with the task stated,
and a presentation-matched A, each registered in `docs/decisions.md` before
being run.

## What this does not claim

- One model (`gpt-5.6-luna`), one procedurally generated task template, three
  agents, two rounds, four options.
- The task has a trivial shortcut: counting name mentions solves 200 of 200
  full-information contexts. It measures whether the model counts, and whether
  it knows it should.
- All 200 tasks share one support pattern and the same 12 fact sentences: one
  puzzle in 200 arrangements, not 200 problems.
- Nothing about HiddenBench's results. HiddenBench states the objective and the
  payoff to its models; I did not. Their correctness rests on elimination logic
  and their headline metric is per-agent selection rate, so their figures are
  not comparable to any number here. `docs/results.md` says so explicitly.
- No training results. The GRPO wiring has only ever run a 2-step CPU smoke
  test.

## A correction made before opening

The audit described the 40 labels behind the surfacing metric's precision and
recall as hand labels made by one person. The transcript of the session that
made them shows they were made by the assistant model, with no person labelling
or reviewing them; the metric's verdict was hidden per pair, and messages were
shown truncated to 420 characters. `cdf828d` corrects every description and adds
`docs/audit_surfacing_labels.md`. No number changes: the precision and recall
are now described as agreement with one model's judgement.

## Checks

- 87 passed, 1 skipped. `ruff` clean. `mypy --strict` clean. (Run locally on
  `cdf828d`; GitHub CI runs on this PR.)
- One command rebuilds every table and the figure from the committed runs, with
  no API calls, and CI fails if any generated file changes.
- Task content regenerates byte-for-byte from its seed: 0 of 200 mismatches
  against the committed episodes. Accuracy figures do not regenerate exactly —
  `gpt-5.6-luna` rejects an explicit temperature, so every call ran at 1.0. The
  README says so rather than promising reproduction it cannot deliver.
- Total API spend across every committed run: $1.5322.
