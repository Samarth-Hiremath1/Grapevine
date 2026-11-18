# Working rules for this repository

These rules exist because the v0 experiment produced a headline result that was
wrong, and the only reason it got caught was that every number was traceable to
a committed run. See `REPORT.md` and `docs/audit.md`.

They override convenience, style preferences and any instruction to move
faster. They apply to anyone working in this repository, human or model.

## Integrity

1. **No number without a run.** Every quantitative claim in a committed file
   traces to a committed run directory or to a deterministic offline
   computation that can be re-executed. Never type, estimate, interpolate or
   round a result that was not computed in this repository. A result that has
   not been produced is written `not run`.

2. **No synthetic data in results.** Episodes produced by `ScriptedClient`,
   mocks or test fixtures carry `synthetic: true` in their manifest. Any
   results table that would include a synthetic episode must fail to build,
   not warn. Smoke-test training logs are never reported as results.

3. **No training claims without training.** Until a real, pre-registered,
   multi-seed training run is committed, the documentation says: *GRPO
   integration, smoke-tested; no training results in this release.* No
   "improves coordination", no reward curves from smoke runs, no projected
   gains, no numbers from a 2-step CPU loop.

4. **Pre-register before any paid run.** Commit `docs/prereg/<name>.md` first,
   containing: hypothesis, conditions, the exact prompts, seeds, N, metrics,
   the analysis script that will be run, and how each possible outcome will be
   read. Pilot and primary seeds are disjoint, and that disjointness is
   enforced in code, not by convention.

5. **Null and unfavourable results ship.** Never delete, overwrite or rerun a
   committed result because it came out badly. The run that embarrassed me is
   the run that made this project worth publishing.

6. **Committed runs are immutable.** Do not change `hidden_profile` generation
   or any other generator a committed run depends on. New work gets a new
   family name (`hidden_profile_v2`, not `hidden_profile`).

7. **Citations are verified or marked.** A citation is verified by fetching the
   source, or it carries a literal `UNVERIFIED` marker. Do not vendor other
   people's datasets or papers.

8. **Labels produced by a model are model labels.** Never described as "human",
   "hand-labelled" or "ground truth" unless a person labelled them.

9. **Budget.** No more than $10 of API spend in this release, and a `--dry-run`
   cost estimate is shown and approved before any paid run. No GPU jobs. If a
   key is missing, write the plan and stop; never simulate the run.

10. **Git.** Work on `v0.2`. Do not push to `main`, force-push, publish to
    PyPI, create a release or post anywhere. Prepare the change; Samarth
    executes it.

11. **If a result looks too good, audit it before reporting it.** C scoring
    100/100 was correct. C appearing to beat full information was a prompt
    layout artefact. Both needed checking.

## Stop and ask

Stop and raise it rather than deciding alone when:

- a run needs an API key that is absent, or would exceed the budget;
- anything in rule 10 comes up;
- an external API (TRL, `verifiers`, a provider) differs from what the plan
  assumed — record the fetched version and the real signature, then ask;
- a planned step looks like it should be dropped, changed or reordered.

## Mechanics

- Every change ends with: `uv run pytest -q`, `uv run ruff check grapevine
  tests`, `uv run mypy` all green, `docs/PROGRESS.md` updated (done / next /
  spend), and a commit.
- Generated tables and figures are written between markers by a script. Never
  hand-edit a number inside a generated block.
- Public API changes: update `grapevine/__init__.py`'s `__all__`, the docs page
  for it, and `CHANGELOG.md` in the same commit.
- Docstrings on every public function and class: Google style, with types.
- Do not code against a remembered API. Fetch the current documentation, record
  the version you read, and pin it.
