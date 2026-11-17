# Release checklist: v0.1.0, then v0.2.0

Everything here is for Samarth to run. Nothing in it has been done
(`CLAUDE.md` rule 10). Each step says what it depends on.

## 1. v0.1.0: the audited case study

1. Review and open the PR in `pr-v0.1.0.md` (`audit/pre-publication` → `main`).
2. After it merges, tag `v0.1.0` on `main` with the commands in that file.

## 2. v0.2: push the branch and open the PR

Depends on 1: `v0.2` is cut from `audit/pre-publication`, so once that is in
`main` the v0.2 PR shows only the v0.2 work, with no rebase.

```bash
git push -u origin v0.2
gh pr create --base main --head v0.2 \
    --title "v0.2: grapevine audit, hidden_profile_v2, GRPO wiring, and the pre-registered eval" \
    --body-file launch/pr-v0.2.md
```

3. Let CI run. It has never run on GitHub: every job was exercised locally, and
   a clean clone of the branch passes, but the matrix, the docs job and the
   package job are first run here. Expect to fix something.
4. Read `docs/review-v0.2.md` before merging; the PR body says what was done
   about each finding.

## 3. Before the first PyPI upload

5. **README links.** The README is the PyPI long description, and its relative
   links (`docs/...`, `studies/...`, the figure) do not resolve on PyPI. Once
   `main` has the files, either rewrite them to absolute
   `https://github.com/Samarth-Hiremath1/Grapevine/blob/v0.2.0/...` URLs, or
   point `readme` at a short PyPI-specific file. Decide before uploading
   (`docs/decisions.md`, "The release workflow publishes nothing until…").
6. **Trusted publishing.** On PyPI, add a pending trusted publisher for project
   `grapevine-mas`: this repository, workflow `release.yml`, environment `pypi`.
   On GitHub, create the environment `pypi`, ideally with yourself as a required
   reviewer, so a tag alone cannot publish.
7. **Private vulnerability reporting.** `SECURITY.md` points to it; enable it in
   the repository's Security settings.
8. **Docs hosting.** The site builds in CI but nothing deploys it. Choose GitHub
   Pages (add a deploy job) or Read the Docs, and update the `Documentation`
   URL in `pyproject.toml`, which currently points at `docs/` on GitHub.

## 4. Tag v0.2.0

Depends on 2 merged and 3 done.

```bash
git checkout main && git pull
git tag -a v0.2.0 -m "v0.2.0"
git push origin v0.2.0
```

The release workflow checks that the tag matches `pyproject.toml`'s version,
runs the tests, builds, checks the metadata, and waits for the `pypi`
environment's approval before publishing.

9. Create the GitHub release from `CHANGELOG.md`'s 0.2.0 section, and change its
   heading from "unreleased" to the date, in a commit before tagging.

## 5. Announce

10. `announcement.md` is a draft. Nothing is posted until you post it.
