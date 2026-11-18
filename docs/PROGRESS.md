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

---

## Step 5 — RL and post-training infrastructure

*2026-11-15. Branch `v0.2`.*

**GRPO integration, smoke-tested; no training results in this release.**

**Done**

- **`grapevine.rl` behind an `[rl]` extra**, pinned to TRL 1.18 — the version
  whose docs were read in Step 1, replacing a stale `trl>=0.11`. The reward
  contract was then confirmed from the installed 1.18.0 source. A core-only
  install pulls in no torch and `import grapevine.rl` loads nothing heavy; CI
  asserts both.
- **Rewards.** Team outcome from the environment's own scorer by default. An
  optional information-surfacing shaping term, off by default, because it is
  collectable without answering: the audit gained a `recite_without_answering`
  policy, and any positive weight now fails `reward_hacking`.
  `RewardedEnvironment` wraps an environment so the audit scores with the
  training reward itself. Shared, split and surfacing-weighted credit helpers;
  nothing counterfactual.
- **A protocol-native rollout** that runs any `DistributedTask` (the v0 engine
  only runs the legacy `Task`), records every prompt — which the v0 episodes
  never did — states the objective in every turn (asserted per turn), and tags
  turns with role, round, trainable and synthetic.
- **The isolation bug is fixed and proven fixed.** Frozen partners are
  separately loaded models, eval mode, `requires_grad` off. A test takes an
  optimiser step that demonstrably moves the policy and checks the partner's
  weight hash, its greedy output, and that it shares no tensor storage with the
  policy. A negative control rebuilds the v0 bug — a partner wrapping the policy
  object — and requires it to fail the same check. LoRA trains only `lora_`
  parameters and leaves the partner untouched; the policy client is bound to
  `trainer.model`, the PEFT-wrapped one. Endpoint and scripted partners too.
- **Self-play**, recorded as `partners_frozen: false`. Not through
  `rollout_func` as planned; reasoning in `docs/decisions.md`.
- **The audit gate.** `grapevine train` audits the environment with the training
  reward on its training seeds before loading any model, refuses a failing card
  or an environment with no seed split, and records `--allow-flagged` in the
  manifest when it is used.
- **Run manifest** with model, seed, environment version, card hash, reward
  config, partners and whether frozen, provenance at start and end, and
  `reportable` with reasons. Every run in this release is not reportable: none
  has a pre-registration.
- **`grapevine eval --policy`** on held-out seeds only, beside chance, the best
  content-blind shortcut, a common-ground-only team and a no-talk team, with
  Clopper-Pearson intervals. Synthetic reports say so.
- **Configs.** `configs/rl_smoke_cpu.yaml` runs in CI; `configs/rl_single_gpu.yaml`
  opens with `# not run`.
- **Deleted** `grapevine/train/`, its configs and smoke test, and
  `grapevine/diagnostics/` with the `diagnose` subcommand. The NeMo-RL notes
  moved to `docs/notes/nemo_rl.md`, marked archived.
- **CI split in two.** `core` proves the light install; `rl-smoke` runs the smoke
  run, isolation tests, the CLI smoke config and a GPU-config dry run from the
  lock. Linux now locks CPU torch instead of side-stepping the lock with
  `uv pip install`.
- `docs/rl.md`: reward design, partners, gate, manifest, configs, eval, and a
  table of exactly what has and has not been run.

**What the smoke run actually shows.** Two steps complete through TRL with
`loss 0` and `grad_norm 0`: a random model earns the same zero reward on every
completion, so GRPO has no advantage to follow and changes nothing. That is the
honest outcome of a wiring test, and why the isolation test adds a
completion-dependent reward of its own.

**Not done from the brief:** the `verifiers` adapter (skipped by decision in
Step 1), and refreshing a frozen partner from the policy every N steps (frozen
copy and endpoint were implemented instead; the brief asked for one of the
three).

**Checks:** 330 passed, 0 skipped with `[rl]` installed. `ruff` clean, `mypy
--strict` clean over 42 files. Both committed Validity Cards regenerated for the
new audit policy with unchanged verdicts — v1 still fails on the same three
checks, v2 still passes all thirteen.

**Next**

Step 6 — the eval run: write the pre-registration and the analysis script, then
stop for a decision on keys and budget, as agreed in Step 1.

**Spend:** $1.5322 cumulative. $0.00 this step.

---

## Step 6 — Pre-registration (the run follows separately)

*2026-11-15. Branch `v0.2`. Committed before any call to a model.*

**Done**

- `docs/prereg/hidden_profile_v2_eval.md`: question, four hypotheses with
  directions, six cells (three conditions × objective stated or not), N=100 on
  v2's eval seeds 10000–10099, a 20-task pilot on its pilot seeds 9000–9019
  (disjointness enforced in code), the exact prompts pinned by SHA-256, seven
  paired contrasts per model with Bonferroni intervals, and a reading committed
  in advance for every outcome.
- `studies/v2_eval/`: the design, a runner with per-call logging and three
  spending guards, the analysis script the pre-registration names, and the
  prompt freeze. The analysis refuses synthetic, pilot and incomplete runs.
- The six arms are audited: `objective` fails exactly the three unstated arms,
  and all 15 pairs differ in framing only by what each declares.
- The client now records each call's finish reason and hidden reasoning tokens,
  and treats a call that hit the cap as a named failure — the data the v0 audit
  lacked for L10.
- Candidate prices checked against the provider's pricing page; `gpt-6-luna` and
  `gpt-5-nano` added. How `gpt-6-luna` handles `temperature` is unverified and
  says so.
- Samarth chose all three candidate models and approved the pilot with a hard
  ceiling of $1.34. Both are recorded in the pre-registration's §11.

**Checks:** 359 passed. `ruff`, `mypy --strict` clean. Both freeze checks pass.

**Next:** the pilot, then a separate approval before the primary run.

**Spend:** $1.5322 cumulative. $0.00 this step.

---

## Step 6 — Pilot

*2026-11-16. Branch `v0.2`. Run at commit `15a1e5d`, working tree clean.*

**Done**

- Ran the approved pilot: `gpt-5.6-luna`, `gpt-6-luna`, `gpt-4o-mini` on the
  20 pilot tasks (seeds 9000–9019), six cells each. 1,320 calls, 360/360
  episodes, $0.2521 against a $1.34 ceiling. Committed unchanged as
  `studies/v2_eval/runs/20261116T074017Z_pilot/`.
- The three pre-registered pilot checks:
  - rejected parameters: 0 errors; every call finished `stop` or `length`;
  - truncation: 1 call of 1,320 (`gpt-6-luna`), below the 2% threshold, so
    the 1,200-token cap stays;
  - parse failures: 0 of 360 episodes.
- No design change. Pilot accuracies were not read and are not a result
  (the analysis script refuses pilot runs).

**Checks:** see the commit.

**Next:** a separate approval for the primary run (100 tasks, 6,600 calls),
then the analysis, once.

**Spend:** $1.7843 cumulative. $0.2521 this step.

---

## Step 6 — Primary run and the H1 investigation

*2026-11-16. Branch `v0.2`. Run at commit `45e5185`, working tree clean.*

**Done**

- Samarth approved the primary run with a $6.69 ceiling; recorded in the
  pre-registration before any call.
- Ran it: 6,600 calls, 1,800/1,800 episodes, $1.2812, 14 truncated calls.
  Ran the pre-registered analysis once. Both committed unchanged
  (`studies/v2_eval/runs/20261116T091238Z_primary/`).
- The pre-registration's H1 reading was triggered: `gpt-4o-mini`'s
  `no_communication`/unstated cell is above chance. As §10 requires, this was
  investigated before reporting anything else. Finding: the battery has no
  solver that applies the scoring rule to an agent's private facts alone, and
  on v2 that solver picks gold for every agent. Re-executable as
  `python -m studies.v2_eval.h1_investigation`; CI checks it.
- A pre-run budget test counted this eval's own spend twice once the runs
  existed; it now measures from the spend before the eval.

**Checks:** 359 passed. `ruff`, `mypy --strict` clean.

**Next:** Samarth decides how the audit gap is handled before the results are
written up.

**Spend:** $3.0655 cumulative. $1.2812 this step.

---

## Step 6 — Close the audit gap; read the results

*2026-11-16. Branch `v0.2`. No API calls.*

**Done**

- Samarth chose to close the gap in the battery and not build a v3.
- `solo_solvability` has a fourth probe, `scoring_rule_on_my_private_units`. A
  new planted-flaw fixture, `private_support_all_gold`, is caught by that probe
  and by no other, pinned in `tests/test_audit.py`.
- The clean control had the same layout as v2, so the old control became the
  planted flaw. The control now holds private support for non-gold options and
  passes every check. Its template pool grew so `diversity` still passes.
- `hidden_profile_v2` now fails `solo_solvability`; generator unchanged (rule 6).
  Its card, the v0 study card and the tests are updated. The RL gate refuses v2
  without `--allow-flagged`; the smoke run and CI pass it, and the manifest
  records the override. CI checks the gate refuses the GPU config.
- A2 in `docs/audit.md`; README, `docs/audit-battery.md`, registry comments and
  both RL configs now say v2 is flagged.
- `studies/v2_eval/README.md`: the results read against §10. The tables are
  generated from `results.md` by `python -m studies.v2_eval.report`, which CI
  checks.

**Checks:** see the commit.

**Next:** Step 7 — packaging, docs site, examples, community files, CI matrix.

**Spend:** $3.0655 cumulative. $0.00 this step.

---

## Step 7 — Packaging, docs, examples, community files, CI

*2026-11-16. Branch `v0.2`. No API calls.*

**Done**

- Packaging: distribution `grapevine-mas` 0.2.0 (import `grapevine`), SPDX
  license metadata, classifiers, project URLs, `py.typed`, an sdist limited to
  the package. `uv build` and `twine check --strict` pass; the wheel installs
  alone into a fresh Python 3.13 environment and runs. A test keeps
  `__version__` and `pyproject.toml` in step. The committed cards record the new
  version, regenerated.
- `examples/`: audit two environments; a complete environment in one file that
  passes every check on its eval seeds; scoring and the audit gate. Each runs
  from a temporary directory in the test suite and against the bare wheel in CI.
- Writing the second example surfaced the battery's false-fail rate: 2 audits
  in 40 on clean environments, all `shortcuts`. Measured by
  `studies/battery_calibration/false_fail.py`, documented, CI-checked. The
  battery is not changed (decision recorded for Samarth).
- MkDocs site: home, quickstart, writing an environment (the example included
  verbatim), the battery, RL, API reference from docstrings, the case studies,
  changelog, decisions. `mkdocs build --strict` passes, and was shown to fail on
  a planted broken link and a planted dead anchor.
- `CHANGELOG.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (adopts Contributor
  Covenant 2.1 by reference), `SECURITY.md`, `CITATION.cff` (validated against
  schema 1.2.0), issue and pull-request templates.
- CI: actions pinned by SHA; a test matrix on Python 3.11, 3.12 and 3.13; a docs
  job; a package job. `release.yml` for tags only, using trusted publishing;
  not triggered. `actionlint` reports no errors (shellcheck not installed).
  The matrix was run locally on 3.12 and 3.13: 363 passed, 1 skipped (the
  `[rl]` tests) on each.
- README: install, examples, the v0.2 eval in brief, the A2 finding, the roadmap,
  updated test and layout sections.

**Checks:** see the commit.

**Not done:** nothing has run on GitHub, because nothing is pushed. README links
are relative and will not resolve on PyPI (recorded in `docs/decisions.md`).

**Next:** Step 8 — `docs/claims.yaml` and `grapevine verify-claims`, a
clean-clone check, a fresh skeptical review, verified related work, `launch/`
drafts.

**Spend:** $3.0655 cumulative. $0.00 this step.

---

## Step 8 — Claims, clean clone, review, related work, launch drafts

*2026-11-16. Branch `v0.2`. No API calls.*

**Done**

- `grapevine verify-claims` and `docs/claims.yaml`: registered numbers are
  re-derived from committed runs or deterministic functions and must appear
  verbatim in their documents; sources inside synthetic runs are refused. Its
  first run caught `docs/index.md` saying ".28" for "$1.28" (shell expansion).
  CI runs it.
- Related work fetched and recorded (`docs/related-work.md`). HiddenBench's
  prompt and payoff claims re-checked against the same PDF as in September
  (matching SHA-256); its arXiv HTML truncates the templates and cannot confirm
  them. Stasser & Titus remains UNVERIFIED.
- Clean-clone check: a fresh clone, no `.env`, locked install. Everything
  regenerated byte-identically, but three spending-guard tests passed only
  where a local key existed. Fixed; the clone then passed in full, including
  the `[rl]` tests and the CLI smoke run.
- An independent review with no prior context: `docs/review-v0.2.md`, verbatim.
  Every finding was re-derived (`studies/v2_eval/review_followup.py`, CI-checked)
  and answered in `docs/review-v0.2-response.md`. Changed in response: the eval
  readings no longer say "replicates", state that `gpt-6-luna` missed its
  prediction, and name an untested layout cue; the minimality count bug is fixed;
  the battery's gaps are documented under "Known gaps"; several provenance and
  wording errors are corrected.
- `launch/`: the v0.2 PR body, a release checklist, an announcement draft. Not
  opened, not posted.

**Checks:** see the commit.

**Open, for Samarth:** settled in the next entry, except the labels and the
release checklist.

---

## Step 8, continued — Extend the battery for M1 and M2

*2026-11-16. Branch `v0.2`. No API calls, no GPU.*

**Done**

- Samarth chose to extend the battery rather than document the gaps.
- `leak` is zero-tolerance. `solo_solvability` gains a names-only probe, a
  shared-support probe and a cross-validated learned probe over within-view
  ranks, and reports the minimum detectable accuracy on every card. Probes
  score tie-breaks by expected value with an exact null.
- Regression tests: the names-only layout and a 43-of-200 leak fail, on four
  disjoint seed ranges, and only the new probes catch the names-only layout.
  Dose-response leaks at 5%, 10%, 20%, and a single leaking task, all fail.
- The clean control and the example are rebuilt (flat names in every block,
  gold by exactly one fact, random splits). The control's two earlier layouts are
  kept as negative controls, as are two new adversarial fixtures.
- Found while doing it, and written up rather than worked around: for a task
  decided by summed evidence, some single view always carries information, so
  no environment can pass `solo_solvability` reliably. The rebuilt control's
  exact single-view bound is computed and tested; the battery sees it on some
  seed ranges and always at n = 2,000. The threshold was not changed.
- `studies/battery_calibration/` measures false positives and missed defects:
  no negative control missed on any of 10 seed ranges; clean environments fail
  outside the two power-limited checks once in 40.
- Validity Cards regenerated. No committed run, result table or pre-registered
  number changed. 90 claims verify.

**Open, for Samarth:** settled in the next entry, except the release checklist.

---

## Step 8, final — Classify instead of threshold; label provenance

*2026-11-16. Branch `v0.2`. No API calls, no GPU, no new environments.*

**Done**

- Two new statuses, `measured` and `inconclusive`. `solo_solvability` fails only
  on a reliable solo shortcut (a probe that commits on at least 20 tasks and is
  never wrong), and otherwise reports single-agent accuracy from a held-out
  learned probe, chance, advantage, a 95% interval, the share of the pooling
  gain and the audit's power. `reward_hacking` fails only on a non-pooling team
  that matches pooling or a reward that pays beyond correctness. The strict
  zero-information test is a labelled diagnostic.
- A twin test: per agent, how many views an indistinguishable instance with a
  different answer certifies as not determining it.
- Recalibrated: every fixture reports its declared status; the graded leak
  `gold_share_bias` is declared `measured`. Over 40 seed ranges the clean
  control and example report `measured` on both measuring checks every time,
  though the diagnostic rejects on 17; the overall verdict is `measured` on 38,
  with one `shortcuts` failure and one `balance` warning, both type I errors.
- `docs/validity-card.md` specifies the card, every threshold, and the
  impossibility argument with its assumptions; the argument was corrected to
  require a uniformly distributed answer, and its identity is tested.
- The 40 v0 surfacing labels are model labels, established from the session
  transcript that made them. Every description is corrected.
- No committed run, result table or pre-registered number changed. 90 claims
  verify.

**Classifications (n = 200):** v0 `hidden_profile` fail; `hidden_profile_v2`
fail (reliable solo shortcut); clean control and example measured.

**Open, for Samarth:** `launch/release-checklist.md`, starting with its section 0.
GitHub CI has not run.

**Spend:** $3.0655 cumulative. $0.00 this step.

---

## Release corrections before the v0.1.0 PR

*2026-11-17. Branches `v0.2` and `audit/pre-publication`. No API calls.*

**Done**

- The twin test is now the *feature-level* twin test: matching evidence
  patterns is not shown to make full observations indistinguishable, and the
  card, the spec and the docs say so. Field names changed accordingly. (The
  previous entry's "certifies" overstated it.)
- The reliable-shortcut rule's statistics are stated with their assumptions: the
  0.25²⁰ figure holds only for an uninformative probe with a uniform answer and
  independent tasks; a union bound over 19 probes gives about 1.7×10⁻¹¹ per
  audit; against a partly informative probe, 20 of 20 bounds the accuracy when
  committing only to at least 83.2% (95%), which the card now reports.
- `venue_choice`, the example's environment promoted unchanged, is the default
  and supported environment. It passes its audit on four disjoint seed ranges,
  its card is committed and regenerated in CI, and training, the dry run and
  evaluation use it without `--allow-flagged`; `hidden_profile_v2` is still
  refused. v0 and v2 stay as documented flawed case studies.
- README links are absolute, and a test requires each to name a real file.
- The release checklist's rule: no merge, tag, release, upload or announcement
  without green GitHub CI on that exact commit and Samarth's approval of that
  step.
- `audit/pre-publication` gained `cdf828d`, the same surfacing-label
  correction as `v0.2`, before the v0.1.0 PR was opened, so the v0.1.0 tag would
  not carry "hand labels". A trial merge of it into `v0.2` is clean.

**Spend:** $3.0655 cumulative. $0.00 this step.

**v0.1.0 PR.** Opened with Samarth's approval:
https://github.com/Samarth-Hiremath1/Grapevine/pull/1 (head `cdf828d` → `main`).
GitHub CI did not run: the `lint-and-test` job was not started because the
account is locked for a billing issue. Not merged, not tagged.

**v0.1.0 CI.** After the lock was lifted, attempt 4 of the same run passed on
`cdf828d` (2026-11-18): lint, types, byte-identical table regeneration, the
training-extra install and the tests all green.

- Done: the PR's CI gate is met on its head commit.
- Next: Samarth's separate approval to merge PR #1; then green CI on the merge
  commit on `main`; then, with separate approval, the `v0.1.0` tag. `v0.2` is
  still local.

**Spend:** $3.0655 cumulative. $0.00 this step.

**v0.1.0 merged.** With Samarth's approval, PR #1 was merged into `main` as
merge commit `681d6dc` (a merge commit, not a squash, so the commit hashes the
docs cite stay on `main`). CI on `681d6dc` passed every step. `v0.2` merges onto
the new `main` without conflicts (checked with `git merge-tree`).

- Done: v0.1.0 is on `main` with green CI.
- Next: with separate approval, tag `v0.1.0` on `681d6dc`; then, with approval,
  push `v0.2` and open its PR.

**Spend:** $3.0655 cumulative. $0.00 this step.

**v0.1.0 tagged.** With Samarth's approval, annotated tag `v0.1.0` on `681d6dc`,
pushed. Checked first that no workflow on `main` runs on tags (`release.yml`
exists only on `v0.2`); after the push, no run started and there is no GitHub
release. Nothing is on PyPI.

- Done: v0.1.0 is tagged on `main`.
- Next: with approval, push `v0.2` and open its PR; all five CI jobs must pass
  on GitHub.

**Spend:** $3.0655 cumulative. $0.00 this step.

**v0.2 PR.** With Samarth's approval, `v0.2` was pushed and opened as
https://github.com/Samarth-Hiremath1/Grapevine/pull/2. Before opening, the PR
description was brought up to date (`843c04c`): it no longer says README links
are relative, drops a count of calibrated checks that could not be traced, and
makes every link absolute. The first GitHub run of this branch's workflows (run
44267547203, on `843c04c`) passed all five jobs: `core`, `tests` on 3.11, 3.12
and 3.13, `docs`, `package` and `rl-smoke`.

- Done: PR #2 open with green CI on its head commit.
- Next: Samarth reads the review and the response, then decides on merging
  (separate approval, green CI on the head commit). Publishing to PyPI needs
  the trusted publisher, the `pypi` environment and its own approval.

**Spend:** $3.0655 cumulative. $0.00 this step.
