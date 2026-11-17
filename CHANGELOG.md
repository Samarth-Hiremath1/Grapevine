# Changelog

All notable changes to this project. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html) for everything in
`grapevine.__all__`.

## [0.2.0] — unreleased

Prepared on the `v0.2` branch. Not tagged and not published.

### Added

- `grapevine audit`: an offline validity battery of thirteen checks that writes
  a Validity Card, tested against planted-flaw fixtures it must catch and a
  clean control it must pass. Exit code 2 when a
  check fails.
- The environment protocol: `Environment`, `DistributedTask`, `AgentView`,
  `InfoUnit`, `Objective`, `Condition`, `SeedSplit`, `ScoreResult`, `Scorer`,
  `exact_match`, `support_total`.
- `hidden_profile_v2`, the default environment, with a committed Validity Card.
  It fails one check, `solo_solvability`; see "Found by the eval" below.
- `grapevine.rl`: TRL GRPO integration with an audit gate, frozen partners and
  a protocol-native rollout. **Smoke-tested; no training results in this
  release.** `grapevine train`, with `--dry-run` and `--allow-flagged`.
- `grapevine eval` on held-out seeds.
- A pre-registered eval of three models on `hidden_profile_v2`
  (`studies/v2_eval/`), its runs, and its analysis.
- `grapevine verify-claims` and `docs/claims.yaml`: every registered number in
  the documentation is re-derived from a committed run or a deterministic
  computation, and must appear verbatim where it is claimed. A claim can also
  assert values its wording implies but does not print (`expect`).
- Examples under `examples/`, each executed by the test suite.
- A documentation site (MkDocs, built with `--strict`).
- Packaging as `grapevine-mas`, typed (`py.typed`), tested on Python 3.11–3.13.

### Found by the eval

- The battery had no probe that applies the scoring rule to one agent's private
  facts alone. `hidden_profile_v2` passed without it and fails with it. Added
  as a fourth `solo_solvability` probe; recorded as A2 in `docs/audit.md`. The
  RL gate now refuses `hidden_profile_v2` unless `--allow-flagged` is passed.

### Fixed

- `minimality` reported the size of its 10-entry sample as the total count of
  redundant units. Found by the external review (`docs/review-v0.2.md`, M3).

### Found by the review, and fixed

- **Names-only and shared-block shortcuts.** `solo_solvability` gains
  `named_not_most_named_privately`, `least_shared_support` and a cross-validated
  learned probe over within-view feature ranks. The control's two earlier
  layouts are kept as negative controls and fail.
- **Partial answer leaks.** `leak` is zero-tolerance: one leaking task fails.
- **Tie-break noise.** Probes score a k-way tie containing the gold option as
  1/k, with an exact null distribution, instead of drawing one at random.
- **Every card reports `minimum_detectable_accuracy`**, the smallest single-view
  advantage the audit would usually see at its sample size.
- The clean control and the example are rebuilt so that no name count in any
  block is informative and gold wins by exactly one fact.
- `studies/battery_calibration/` now measures missed defects as well as false
  alarms. Response to every finding: `docs/review-v0.2-response.md`.

### Validity Card statuses

- Two new statuses: `measured` (a partial-information advantage quantified, no
  failure confirmed) and `inconclusive` (too little evidence). Neither stops a
  card passing. The verdict order is pass, measured, warn, inconclusive, fail.
- `solo_solvability` fails only on a reliable solo shortcut -- a probe that
  commits on at least 20 tasks and is never wrong -- and otherwise reports the
  single-agent accuracy from a held-out learned probe, chance, advantage, a 95%
  interval, the share of the pooling gain, and the audit's power. `reward_hacking`
  fails only when a non-pooling team matches pooling or the reward pays beyond
  correctness. The strict zero-information test is kept as a labelled diagnostic.
- A twin test reports, per agent, how many views an indistinguishable instance
  with a different answer certifies as not determining the answer.
- Specification: `docs/validity-card.md`, including the assumptions under which
  zero single-view information is impossible.

### Corrected

- The 40 surfacing labels behind the v0 metric's precision and recall are model
  labels, not hand labels; established from the session that made them
  (`docs/audit_surfacing_labels.md`).

### Changed

- The v0 experiment moved to `studies/underspecification/`, behind one
  reproduce command, with its prompts frozen by digest.
- Per-call logging now records the finish reason and hidden reasoning tokens,
  and a truncated call is a named failure.

### Removed

- `grapevine.train` and `grapevine.diagnostics`, replaced by `grapevine.rl` and
  the audit. The `diagnose` command.
- `split_evidence` from the runnable registry: it leaks the answer. Kept as a
  worked negative example.

### Deprecated

- `Env` and `Task`, the pre-protocol interface, kept for one release because the
  committed v0 runs load through it.

## [0.1.0] — unreleased

The audited v0 case study: a coordination failure that turned out to be
objective underspecification. Proposed as a tag on `main`; see
`launch/pr-v0.1.0.md`.
