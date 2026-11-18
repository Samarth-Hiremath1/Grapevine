# PR draft: `v0.2` → `main`

Opened on 2026-11-18 with Samarth's approval, after the v0.1.0 PR merged and was
tagged. Merging it needs his separate approval and green GitHub CI on all five
jobs (`launch/release-checklist.md`).

---

<!-- PR body begins here -->

## What this is

v0.2 turns the audit that corrected this repository's first result into a tool,
ships one environment and the GRPO wiring around it, and runs one small
pre-registered eval. Everything is in the record as it came out, including the
parts that went against the plan.

## What ships

- **`grapevine audit`**: thirteen offline checks on a distributed-information
  environment, written as a Validity Card. Exit code 2 when a check fails.
  Calibrated against planted-flaw fixtures and a clean control that must pass
  every check ([`docs/audit-battery.md`](https://github.com/Samarth-Hiremath1/Grapevine/blob/v0.2/docs/audit-battery.md)), and measured
  for false fails over 40 seed ranges
  ([`studies/battery_calibration/`](https://github.com/Samarth-Hiremath1/Grapevine/blob/v0.2/studies/battery_calibration/README.md)).
- **The environment protocol**, and a complete example environment in one file
  that passes on its eval seeds ([`examples/`](https://github.com/Samarth-Hiremath1/Grapevine/blob/v0.2/examples/README.md)).
- **`venue_choice`**, the default and supported environment. It passes its
  audit with a measured single-view advantage, and training and evaluation use
  it without `--allow-flagged`. It is the example environment, promoted
  unchanged.
- **`hidden_profile_v2`**, a documented flawed case study. It passed the battery
  when it was built. The eval below found a shortcut the battery had no probe
  for, and it now fails `solo_solvability`. Its generator is frozen because
  committed runs depend on it, so the failure stays on its card.
- **`grapevine.rl`**: TRL GRPO with an audit gate, frozen partners proven
  unchanged after an optimiser step, and a protocol-native rollout. **GRPO
  integration, smoke-tested; no training results in this release.** The gate
  refuses `hidden_profile_v2` unless `--allow-flagged` is passed, and records it.
- **The v0 case study** under `studies/underspecification/`, reproducible with
  one command, prompts frozen by digest.
- **The pre-registered eval** under `studies/v2_eval/`.
- **`grapevine verify-claims`**: the numbers registered in `docs/claims.yaml`
  are re-derived from committed runs and must appear verbatim in the docs. Its
  first run caught a dollar figure mangled by shell expansion.
- Packaging as `grapevine-mas` 0.2.0, a docs site built with `--strict`,
  community files, CI on Python 3.11–3.13, and a release workflow that is not
  triggered.

## The eval

Pre-registered (`docs/prereg/hidden_profile_v2_eval.md`) and committed before any
call. Three models, 100 held-out tasks, six cells each; read model by model in
[`studies/v2_eval/README.md`](https://github.com/Samarth-Hiremath1/Grapevine/blob/v0.2/studies/v2_eval/README.md), against the readings
registered in advance:

- `gpt-5.6-luna`: no gap detected between a communicating team and one agent
  with every fact. Not a replication: the deciding agent can reach the answer
  from its own private facts, and pooling was not measured.
- `gpt-6-luna` missed the pre-registered prediction, and no pre-registered
  reading applies.
- `gpt-4o-mini` is below the pre-registered capability bar, so its contrasts
  are read as capability results.

A pre-registered tripwire — a single agent beating chance without
communication — fired for `gpt-4o-mini`. Investigating it, as the
pre-registration required, found the battery's gap: applying the scoring rule to
one agent's private facts alone picks the answer for every agent on v2. Written
up as A2 in `docs/audit.md`.

## Things a reviewer should know

- **A passing card means the thirteen checks found nothing at that sample size**,
  never that an environment is sound. The review's names-only shortcut and
  partial-leak findings are now caught, with the old layouts kept as negative
  controls; what the battery still cannot see is under "Known gaps" in
  `docs/audit-battery.md`.
- **Validity Card statuses changed.** `solo_solvability` and `reward_hacking`
  fail only on a confirmed shortcut and otherwise report `measured`: the
  advantage with an interval and the audit's power. Under stated assumptions
  (`docs/validity-card.md`), an environment decided by summed evidence always has
  some single-view advantage, so a zero-information requirement would pass or
  fail the same environment depending on sample size. It is kept as a labelled
  diagnostic.
- **This branch's workflows run on GitHub for the first time here.** All five
  jobs were run locally, step by step from the workflow file, and pass. The
  v0.1.0 PR's older single-job workflow passed on GitHub on `cdf828d` and again
  on the merge commit `681d6dc`.
- **README links are absolute**, pinned to `main`, so they resolve on PyPI once
  this merges; a test checks every one points at a file that exists.
- **`release.yml` publishes to PyPI on a `v*` tag.** It is not triggered by this
  PR, and the existing `v0.1.0` tag points at a commit without it. No PyPI
  trusted publisher is configured yet.
- Total API spend for the whole project: see `docs/PROGRESS.md`; the eval's own
  runs are in their manifests.

## Independent review

An independent pass with no prior context reviewed the branch:
[`docs/review-v0.2.md`](https://github.com/Samarth-Hiremath1/Grapevine/blob/v0.2/docs/review-v0.2.md), committed verbatim. Its verdict:
the bookkeeping holds, the scientific claims were stronger than the evidence.
Every finding was re-derived before anything changed, and
[`docs/review-v0.2-response.md`](https://github.com/Samarth-Hiremath1/Grapevine/blob/v0.2/docs/review-v0.2-response.md) says what was
done about each. In short: the eval's readings were rewritten to drop
"replicates" and to state the failed `gpt-6-luna` prediction plainly; the
minimality count bug is fixed; the battery now catches the names-only shortcut
and partial leaks, scores tie-breaks by expectation, and reports the smallest
advantage each audit could have seen; the clean control and the example were
rebuilt; and the v0 surfacing labels turned out to be model labels, now
described as such everywhere.

## Checks

```bash
uv run pytest -q
uv run ruff check grapevine tests studies examples
uv run mypy
uv run --extra docs mkdocs build --strict
uv run grapevine verify-claims
```
