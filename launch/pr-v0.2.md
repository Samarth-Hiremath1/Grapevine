# PR draft: `v0.2` → `main`

Not opened. Open it after the v0.1.0 PR (`pr-v0.1.0.md`) has merged, with the
commands in `release-checklist.md`. I do not push or open PRs (`CLAUDE.md`
rule 10).

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
  Calibrated against planted-flaw fixtures for eleven of the thirteen checks
  and a clean control that must pass all of them
  ([`docs/audit-battery.md`](docs/audit-battery.md)).
- **The environment protocol**, and a complete example environment in one file
  that passes on its eval seeds ([`examples/`](examples/README.md)).
- **`hidden_profile_v2`**, the default environment. It passed the battery when
  it was built. The eval below found a shortcut the battery had no probe for,
  and it now fails `solo_solvability`. Its generator is frozen because committed
  runs depend on it, so the failure stays on its card.
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
[`studies/v2_eval/README.md`](studies/v2_eval/README.md), against the readings
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

- **A passing card means the thirteen checks found nothing**, not that an
  environment is sound. The review found single-view shortcuts the battery has
  no probe for in every environment here, including the example that passes;
  and a decisive leak in one task in five passes. Listed under "Known gaps" in
  `docs/audit-battery.md`; the battery is not changed in this PR.
- **A clean environment fails about one audit in twenty**, on `shortcuts`,
  because equalised name counts leave the content-blind solvers breaking ties at
  random. Measured and documented; the battery is not changed, as that would
  change every committed card.
- **CI has never run on GitHub.** Every job was run locally, and a clean clone of
  the branch passes with no API key, but the workflows run here for the first
  time.
- **README links are relative** and will not resolve on PyPI. To be settled
  before the first upload.
- Total API spend for the whole project: see `docs/PROGRESS.md`; the eval's own
  runs are in their manifests.

## Independent review

An independent pass with no prior context reviewed the branch:
[`docs/review-v0.2.md`](docs/review-v0.2.md), committed verbatim. Its verdict:
the bookkeeping holds, the scientific claims were stronger than the evidence.
Every finding was re-derived before anything changed, and
[`docs/review-v0.2-response.md`](docs/review-v0.2-response.md) says what was
done about each. In short: the eval's readings were rewritten to drop
"replicates" and to state the failed `gpt-6-luna` prediction plainly; the
minimality count bug is fixed; the battery's gaps are documented, not fixed;
and who produced the v0 surfacing labels is still open.

## Checks

```bash
uv run pytest -q
uv run ruff check grapevine tests studies examples
uv run mypy
uv run --extra docs mkdocs build --strict
uv run grapevine verify-claims
```
