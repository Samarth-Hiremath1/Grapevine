# Progress

Running log for the v0.2 release. One entry per step, newest last. Each entry
records what was finished, what is next, and API spend.

Spend is cumulative across every committed run in the repository and is read
from the run manifests by `python -m grapevine.experiments.report_tables`.

---

## Step 1 — Orient

*2026-11-15. Branch `v0.2`, cut from `audit/pre-publication` (`7fdc544`).*

**Done**

- Read `REPORT.md`, `docs/audit.md`, `docs/assumptions.md`, `docs/decisions.md`
  and the `grapevine/` package.
- Re-verified the starting state: `pytest -q` → 87 passed, 1 skipped; `ruff
  check grapevine tests` → clean; `mypy` (strict, 27 files) → clean; `python -m
  grapevine.experiments.report_tables` rebuilds every table and the figure and
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
