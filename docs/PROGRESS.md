# Progress

Running log for the v0.2 release. One entry per step, newest last. Each entry
records what was finished, what is next, and API spend.

Spend is cumulative across every committed run in the repository and is read
from the run manifests by `python -m studies.underspecification.reproduce`.

---

## Step 1 — Orient

*2026-11-15. Branch `v0.2`, cut from `audit/pre-publication` (`7fdc544`).*

**Done**

- Read `REPORT.md`, `docs/audit.md`, `docs/assumptions.md`, `docs/decisions.md`
  and the `grapevine/` package.
- Re-verified the starting state: `pytest -q` → 87 passed, 1 skipped; `ruff
  check grapevine tests` → clean; `mypy` (strict, 27 files) → clean; `python -m
  grapevine.experiments.report_tables` (renamed in Step 2) rebuilds every table and the figure and
  leaves the working tree byte-identical.
- Fetched current external APIs and recorded the versions actually read in
  `docs/v0.2-plan.md`: TRL (PyPI 1.18.0, docs read at v1.18.0; lock pins
  1.13.0; `pyproject.toml` still declares `trl>=0.11`), `peft` (0.21.3), and
  `verifiers` (PyPI 0.4.1, while the documented v1 API is a git-clone-only
  library generation).
- Checked provider keys without printing them: only `OPENAI_API_KEY` is set.
- Wrote `CLAUDE.md` (the integrity rules) and `docs/v0.2-plan.md` (scope, the
  fetched APIs, the public API draft, order of work, blockers).

**Next**

Step 2 — make the audited case study the public face: prepare the
`audit/pre-publication` → `main` PR and propose tag `v0.1.0`, move the v0
experiment under `studies/underspecification/` behind one reproduce command
with a test pinning its prompts byte-identical to the committed runs, and
unregister `split_evidence`.

**Blocked on a decision** (detail in `docs/v0.2-plan.md`): the PyPI
distribution name; whether to skip the `verifiers` adapter (recommended, with
reasons); and what to do about Step 6 now that only one provider key exists.

**Spend:** $1.5322 cumulative. $0.00 this step — every check was offline.

---

## Step 2 — Make the audited case study the public face

*2026-11-15. Branch `v0.2`.*

**Done**

- **The v0 experiment is now a study, not part of the library.**
  `studies/underspecification/` holds its configs, its seven committed runs, the
  code that recomputes its numbers, its generated figure, and its own README.
  `studies/` is deliberately not installed with the package: it is the evidence
  for what the library claims, not part of its API. `grapevine/` keeps only the
  reusable harness — the runner, the statistics, cross-run comparison, figures.
- **One command reproduces it**, offline and with no key:
  `python -m studies.underspecification.reproduce`. It rebuilds every table and
  the figure from the committed episodes and leaves the tree byte-identical;
  `--rerun` prints the paid commands that produced each run, with the cost each
  one actually incurred, reconstructed from that run's own manifest rather than
  from memory.
- **The study's prompts are frozen, and the test is real.** The committed
  episodes record responses but not prompts, so a template edit could have
  broken reproduction unnoticed — and since the finding *is* about a prompt,
  that gap mattered. To avoid a reconstruction that merely re-derives the
  templates and checks itself, the prompt construction was extracted out of
  `run_episode` / `run_no_communication` / `run_single_agent` into five public
  builders in `grapevine/rollout/engine.py`, which both the engine and the
  reconstruction now call.
  - The refactor was proven to change no prompt byte by rebuilding every prompt
    with the pre-refactor engine loaded from git and comparing: **1,580 episodes,
    7,260 model calls, 0 differences.**
  - `prompts_golden.json` holds one SHA-256 per committed `(run, condition)`
    pair over every reconstructed prompt byte — 14 digests, full coverage, 2.7 kB.
    `prompts_sample.md` holds the complete prompt text for one task in every
    condition, generated rather than hand-written.
  - `tests/test_study_prompts.py` re-derives both, asserts every task regenerates
    from its seed, and includes a negative control that edits a template to prove
    the check can fail. It also asserts the study's central claim directly: strip
    the task statement from the rule arm's prompts and they are byte-identical to
    the primary run's, across all 100 paired tasks.
- **`split_evidence` is unregistered.** It leaks the gold answer into one agent's
  view in 100 of 100 generated tasks, so nothing that resolves a family by name
  can hand one out. The class stays importable so its tests keep running and
  Step 4 can fix or delete it; the CLI and the experiment runner now refuse it
  with the reason rather than a bare error. A test asserts the leak itself, so
  re-registering it without fixing it fails.
- **The `v0.1.0` PR is drafted** at `launch/pr-v0.1.0.md`: the body, the `gh`
  commands, and the case for `v0.1.0` rather than `v0.2.0`. Not opened, not
  tagged — Samarth executes.
- CI gained a step that checks the frozen prompts, and lint now covers
  `studies/`; `mypy --strict` covers it too.

**Checks:** 124 passed, 1 skipped (was 87/1). `ruff check grapevine tests
studies` clean. `mypy --strict`, 32 files, clean.
`python -m studies.underspecification.reproduce` leaves the tree unchanged.

**Next**

Step 3 — the core: a small `DistributedTask` / `Environment` protocol, then
`grapevine audit` with its battery of checks, calibrated against
`tests/fixtures/flawed_envs/` (one planted defect each, plus a clean control)
and required to rediscover every relevant finding in `docs/audit.md`.

**Spend:** $1.5322 cumulative. $0.00 this step — every check was offline.
