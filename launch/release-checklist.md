# Release checklist: v0.1.0, then v0.2.0 — for Samarth's approval

**The rule for every step below.** No merge, no tag, no GitHub release, no PyPI
upload and no announcement happens unless (a) every GitHub CI job has passed
on the exact commit concerned, and (b) Samarth has approved that specific
step. A red, pending, cancelled or partial run means stop. CI passing elsewhere,
or locally, does not count.

Done so far: the v0.1.0 PR is opened (step 1), with Samarth's approval to
prepare and open it. Nothing has been merged, tagged, published or announced.

## 0. Decisions to approve before anything is pushed

- [ ] The Validity Card reclassification (`docs/validity-card.md`): `fail` only
      on a confirmed shortcut; `measured` for a partial-information advantage;
      `inconclusive` below 20 tasks. Approve, or say what to change.
- [ ] The label correction: the 40 v0 surfacing labels are model labels
      (`docs/audit_surfacing_labels.md`). Approve the wording.
- [ ] `venue_choice` as the default and supported environment, with v0 and
      `hidden_profile_v2` kept as documented flawed case studies.
- [x] README links: now absolute, on `main`; a test requires every one to point
      at a file in the repository. They resolve once `v0.2` is merged.

## 1. v0.1.0: the audited case study

1. ~~Open the PR in `pr-v0.1.0.md`~~ — opened 2026-11-17 as
   https://github.com/Samarth-Hiremath1/Grapevine/pull/1, head `cdf828d`, which
   adds the surfacing-label correction to the 16 reviewed commits.
   **CI status: not run.** Its only job, `lint-and-test` (run 44205827782),
   was not started: GitHub reports "your account is locked due to a billing
   issue". Resolve the billing lock in the account's Billing settings, then
   re-run the job; nothing here can proceed until it is green.
2. **CI gate.** Every check on the PR must pass on its head commit. If any fails,
   stop and fix on `audit/pre-publication`; do not merge red. The branch's
   workflow is the older one (one `lint-and-test` job, unpinned `trl>=0.11`).
3. **With separate approval:** merge, then tag `v0.1.0` on `main` with the
   commands in that file, only once CI on the merge commit on `main` is green.
   No PyPI upload for v0.1.0.

## 2. v0.2: push the branch and open the PR

Depends on 1: `v0.2` is cut from `audit/pre-publication`, so once that is in
`main` the PR shows only the v0.2 work.

```bash
git push -u origin v0.2
gh pr create --base main --head v0.2 \
    --title "v0.2: grapevine audit, hidden_profile_v2, GRPO wiring, and the pre-registered eval" \
    --body-file launch/pr-v0.2.md
```

4. **CI gate.** CI has never run on GitHub. Every job has been run locally and a
   clean clone of the branch passes with no API key, but these five jobs run for
   the first time on the PR, and every one must pass:
   - [ ] `core` — lint, types, every reproducibility check (including the ~3 min
         calibration study), `verify-claims`, the test suite
   - [ ] `tests` on Python 3.11, 3.12 and 3.13
   - [ ] `docs` — `mkdocs build --strict`
   - [ ] `package` — build, `twine check --strict`, examples against the bare wheel
   - [ ] `rl-smoke` — the GRPO smoke and isolation tests with the `[rl]` extra

   Expect to fix something on the first run. Fix on `v0.2`, push, and wait for
   all five again. Do not merge, tag or publish on a red or partial run.
5. Read `docs/review-v0.2.md` and `docs/review-v0.2-response.md` before merging.

## 3. Before the first PyPI upload

Depends on 2 merged with CI green.

6. **README links.** Already absolute (`blob/main/...`, `raw.githubusercontent.com`
   for the figure), and tested to point at real files. After the merge, open
   two or three on GitHub to confirm they resolve.
7. **Trusted publishing.** On PyPI, add a pending trusted publisher for
   `grapevine-mas`: this repository, workflow `release.yml`, environment `pypi`.
   On GitHub, create the environment `pypi` with yourself as a required
   reviewer, so a tag alone cannot publish.
8. **Private vulnerability reporting.** Enable it in the repository's Security
   settings (`SECURITY.md` points to it).
9. **Docs hosting.** Nothing deploys the site. Choose GitHub Pages or Read the
   Docs, and update the `Documentation` URL in `pyproject.toml`.
10. **Changelog date.** Change `CHANGELOG.md`'s "0.2.0 — unreleased" to the
    release date, through a PR with green CI.

## 4. Tag v0.2.0 and publish

Depends on 3, with CI green on the commit to be tagged.

```bash
git checkout main && git pull
git tag -a v0.2.0 -m "v0.2.0"
git push origin v0.2.0
```

11. **CI gate, again.** `release.yml` re-runs the full test suite and the build
    checks on the tag before publishing, and waits for your approval in the
    `pypi` environment. Approve only after its `build` job is green.
12. Create the GitHub release from `CHANGELOG.md`'s 0.2.0 section.

## 5. Announce

13. `announcement.md` is a draft. Nothing is posted until you post it.

## Known limitations shipping with 0.2.0

Stated in the docs; none blocks the release, but each should be known:

- `solo_solvability` and `reward_hacking` report `measured`, not `pass`, for any
  environment whose answer is decided by summed evidence; whether a measured
  advantage is acceptable is the user's judgement.
- Probes and the twin test see support and name counts per block, not wording,
  order or length.
- The condition prompts' layout is not audited; `hidden_profile_v2`'s
  full-information prompt carries a cue.
- Every fixture was written by the author of the checks.
- `hidden_profile_v2` and v0 `hidden_profile` fail their audits and are shipped
  as documented case studies; the GRPO configs use `venue_choice`, which passes.
  There are no training results.
