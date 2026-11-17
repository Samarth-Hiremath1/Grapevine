# Changelog

All notable changes to this project. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html) for everything in
`grapevine.__all__`.

## [0.2.0] — unreleased

Prepared on the `v0.2` branch. Not tagged and not published.

### Added

- `grapevine audit`: an offline validity battery of thirteen checks that writes
  a Validity Card, calibrated against planted-flaw fixtures. Exit code 2 when a
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
- Examples under `examples/`, each executed by the test suite.
- A documentation site (MkDocs, built with `--strict`).
- Packaging as `grapevine-mas`, typed (`py.typed`), tested on Python 3.11–3.13.

### Found by the eval

- The battery had no probe that applies the scoring rule to one agent's private
  facts alone. `hidden_profile_v2` passed without it and fails with it. Added
  as a fourth `solo_solvability` probe; recorded as A2 in `docs/audit.md`. The
  RL gate now refuses `hidden_profile_v2` unless `--allow-flagged` is passed.

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
