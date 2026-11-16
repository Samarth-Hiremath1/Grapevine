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

---

## Step 3 — The environment protocol and `grapevine audit`

*2026-11-15. Branch `v0.2`.*

**Done**

- **`grapevine/protocol.py` — the one interface outside users implement.**
  `DistributedTask`, `Environment`, `AgentView`, `InfoUnit`, `Objective`,
  `ScoreResult`, `Condition`, `SeedSplit`. It asks for a little more than "a
  prompt and a gold string", and each part is what makes a check possible:
  information *units* so minimality can remove one and ask whether the answer
  changes; an objective carrying the question *and* the scoring rule; a
  programmatic scorer so correctness never needs a model; optional
  `conditions()` and `seed_split()` hooks. The minimum to implement is
  `generate(seed)`; everything else defaults, and checks that need more report
  `skipped` rather than `pass`.
- **`grapevine audit <env>` with twelve checks**, emitting `validity_card.json`
  and a Markdown card. Offline, no key, under a second on 200 tasks. Exits 2 on
  a failing card so it works as a CI gate; a warning does not fail it. `envs`
  lists what can be audited. `diagnose` is deprecated in favour of the
  `reward_hacking` check and removed in 0.3.0.
- **Calibrated, not asserted.** `tests/fixtures/flawed_envs/` holds ten
  environments, each the clean control with exactly one flag flipped — a test
  asserts exactly one. The control passes all twelve checks; every planted
  defect is caught by the check named for it. Collateral is recorded rather than
  tolerated silently: a leak really does also make a task solo-solvable.
- **Rediscovers the v0 audit by finding number.** L3 (name counting solves
  200/200), I1 (the objective never reached the models), L2 (one support pattern
  across all 200 tasks), L9 (agent 0 holds one more fact), L4 (the baseline arm's
  framing differed) — plus the checks that should still pass: G3, G5, and the
  scorer D1 fixed. `split_evidence` is a real-world positive control: the leak
  check reproduces the hand count of 100 out of 100.
- **The battery found something the hand audit missed.** Every private fact in
  `hidden_profile` supports the correct option and the distractors name nobody,
  so an agent asking only "whose name is in my own notes?" is right in 200 of
  200 tasks with no pooling. G6 tested solo solvability by applying the task's
  own scoring rule to one view, which gives the decoy, so it read 0/200 and was
  filed as clean — right about the rule, wrong about the space of things a model
  might do. Written up as **A1** in `docs/audit.md`, pinned by a test. It changes
  no reported number (condition B scored 0.5%, so the models did not take the
  shortcut) but it changes what B can be read as measuring, and it is a hard
  constraint on `hidden_profile_v2`.
- Two bugs in my own checks, both found by running them: `minimality` and
  `full_solvability` were using an argmax that breaks ties at random, so a lucky
  coin flip counted as a pass — they now require the answer to be *uniquely*
  determined. And `condition_diff` was comparing whole prompts, which always
  differ when arms differ in information; it now compares framing with the
  task's content stripped out, which is what L4 was actually about.
- `hidden_profile`'s Validity Card is committed at
  `studies/underspecification/validity_card.{json,md}`, regenerated by the
  study's reproduce command and diffed in CI. Verdict: fail — 3 fail, 4 warn,
  5 pass.
- `docs/audit-battery.md` documents the twelve checks, the four statuses, how
  the calibration works, and what the battery does *not* do. The README now
  leads with the tool.
- Public API exported from `grapevine/__init__.py` with `__all__` (22 names).
  `Env` and `Task` stay as deprecated aliases for one release.

**Known duplication, deliberate:** `grapevine/diagnostics/hacking.py` still
implements its degenerate policies against the pre-protocol `Env`, alongside the
protocol versions in `grapevine/audit/solvers.py`. The old module is referenced
by the committed study and is removed in Step 5, when `grapevine/train/` goes.

**Checks:** 214 passed, 1 skipped (was 124/1). `ruff check grapevine tests
studies` clean. `mypy --strict`, 38 files, clean. The study's tables, figure and
Validity Card all regenerate byte-identically.

**Next**

Step 4 — `hidden_profile_v2`: facts that do not lead with the candidate's name
and whose mention counts are uninformative by construction, private support
spread across options so A1 cannot recur, a larger frozen content pool across a
few domains, varied support patterns, the objective stated by default, and
train/eval seed splits declared in the environment. Then its committed Validity
Card, and `split_evidence` fixed or deleted.

**Spend:** $1.5322 cumulative. $0.00 this step — the battery makes no API calls.

---

## Step 4 — `hidden_profile_v2`: one environment that passes

*2026-11-15. Branch `v0.2`.*

**Done**

- **`hidden_profile_v2` passes all thirteen checks.** Committed card at
  `environments/hidden_profile_v2/validity_card.md`, regenerated by the public
  CLI in CI and diffed. It passes on the train, pilot and held-out eval seed
  ranges and at n=1000, not just on the card's seeds. Each design choice is
  traced in the module docstring to the finding it answers: mention counts
  equalised across options (L3), private blocks that point away from the answer
  (A1), three domains with varying support patterns (L2), the objective stated
  by default (I1), symmetric agents (L9), a presentation-matched baseline and
  one declared line of difference per arm (L4), and a declared train/eval/pilot
  seed split.
- **The generator checks its own invariants and raises.** Nine properties
  verified on every `generate` call, so a bad configuration fails loudly instead
  of producing tasks that look fine and measure nothing. Config validation runs
  at construction and says what to change — including the content budget, so an
  over-ambitious setting fails up front rather than on whichever seed first runs
  the sentence pool dry.
- **The pool is frozen and hashed.** `grapevine/envs/_pool_v2.py` holds three
  domains × 16 supporting and 20 mention sentences. Its provenance is stated
  plainly: drafted by a language model, then read, edited and frozen by hand. It
  carries content only — which option a fact supports is the generator's
  construction, never a model's label. `POOL_SHA256` is asserted by a test, and
  the environment refuses to start if the pool has moved.
- **Two bugs the work surfaced, both in my own code:**
  - A new `fewest_mentions` shortcut solver, added because the obvious way to
    defeat name counting is to pad mentions until gold is no longer the
    most-named — overshoot and it becomes the *least*-named, which is just as
    cheap. It immediately failed the clean control at 44%, so the control was
    rebuilt to equalise counts rather than merely invert them.
  - A **multiple-comparisons defect in the battery itself.** Five shortcut
    probes at an uncorrected α=0.05 fail roughly one clean environment in four.
    v2 was failed on `first_option` at 31.5% (p=0.023) which, measured over
    20,000 seeds, is a genuine fluctuation: gold position is uniform (χ²=2.08).
    The "beats chance" families are now Bonferroni-corrected within each check,
    with the threshold recorded on the card; the "indistinguishable from
    pooling" test is deliberately left uncorrected, because there a smaller α
    would make a degenerate policy *more* likely to be called a match for real
    pooling. A test demonstrates the uncorrected error rate by simulation rather
    than asserting it from theory, and another confirms the correction cannot
    mask v0's 200/200 shortcut.
- **A thirteenth check, `name_hygiene`.** An option name that is a substring of
  another, or that hides inside an ordinary word, makes every name-matching
  measurement partly a count of word fragments — mention counts and the study's
  surfacing metric alike. Found when the control's phrase "listed
  alphabetically" counted as a mention of an option called "Alpha". Mention
  counting now matches whole words. Provenance: G11 and L5.
- `binomial_tail_p` overflowed above ~n=2000 (`math.comb` exceeding a float);
  it now computes in log space.
- Calibration re-verified after all of the above: all eleven planted-flaw
  fixtures still caught, control still clean, `hidden_profile` v1 and
  `split_evidence` still fail.

**Deviation from the plan, flagged.** Step 4 said to fix `split_evidence` so it
passes or delete it, whichever is cheaper. I have done neither: it stays,
unregistered and unrunnable, as the battery's real-world positive control. The
reasoning is in `docs/decisions.md` — deleting is cheaper than fixing, but it
would cost the only example in the repository of an environment that leaked its
answer *for real*, before any of this existed, and the leak check reproducing
the hand count of 100 out of 100 is the strongest evidence the battery works. It
cannot be reached by name, the CLI and runner refuse it with the reason, and
`grapevine audit split_evidence` reports FAIL loudly. **Say the word and I will
delete it.**

**Checks:** 288 passed, 1 skipped (was 214/1). `ruff` clean over `grapevine`,
`tests`, `studies`. `mypy --strict`, 40 files, clean. The study's tables, figure
and card and v2's card all regenerate byte-identically.

**Next**

Step 5 — `grapevine.rl` behind an optional `[rl]` extra: rewards from the
environment's scorer, rollout-to-trajectory conversion, TRL GRPO retargeted to
the version recorded in Step 1, provably frozen partners, the audit gate, LoRA,
and `grapevine eval`. Honestly labelled: no training results.

**Spend:** $1.5322 cumulative. $0.00 this step.
