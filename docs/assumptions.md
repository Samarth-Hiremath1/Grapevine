# Assumption ledger

Everything the coordination ablation's validity rests on. Written **before**
running any of the checks, so the list is not shaped by what turned out to be
convenient to test. Findings live in `docs/audit.md`; this file is the list of
things that could be wrong.

Two problems have already been found this way, both after results were written
up: the strength-fact pool is fully consumed by every task, so 200 "independent"
tasks share one template; and the task question never reaches any model's
prompt. Both were assumptions nobody had written down. The working assumption
here is that more remain.

Each entry: what is assumed, where in the code it lives, and how it could be
checked empirically. "Check" means an executed measurement, not an argument.

Status values used in `docs/audit.md`: **Invalidating** (a reported number is
wrong or unsupported), **Limiting** (the result is narrower than stated),
**Cosmetic**, **Clean**.

---

## G. Generator

**G1. Task content varies across seeds.**
`_STRENGTHS` (12 entries) and `strength_fact()` in `grapevine/envs/hidden_profile.py`.
The experiment config consumes 12 strength facts per task. Already known to be
false in the sense that every task uses the whole pool; the open questions are
how many genuinely distinct surface realisations exist in total, and whether the
docs state the limitation at the right strength.
*Check:* enumerate distinct strength-sentence sets, distinct name sets, distinct
(name, sentence) assignments, and distinct full context strings over the 200
primary seeds; compute the size of the realisation space analytically.

**G2. Distractor content varies.**
`_DISTRACTOR_NOTES` (8 entries), `distractor_fact()`. 4 private distractors per
task plus any shared fill.
*Check:* distinct distractor sets over the primary seeds; whether the pool is
also fully consumed at other configs.

**G3. The correct option's position is uniform over the option list.**
`options = rng.sample(...)` then `correct_idx, decoy_idx = rng.sample(range(n), 2)`.
*Check:* tally gold index and decoy index over several thousand seeds; test
against uniform.

**G4. Model answers are not position-biased, and position does not predict correctness.**
Not a generator property, but it interacts with G3: if models favour, say, the
first listed option and gold is uniform, accuracy is unaffected on average, but a
*non-uniform* gold position would inflate or deflate a condition.
*Check:* from committed episodes, tally the index of each condition's chosen
option; cross-tabulate chosen index against gold index.

**G5. Structural invariants hold for the configuration actually used, not just the default.**
`HiddenProfileConfig.__post_init__` and the three properties in the class
docstring; `tests/test_hidden_profile.py` covers four configs.
*Check:* recompute all three invariants directly on all 200 primary seeds and
100 rule-arm seeds rather than on test configs.

**G6. No degenerate seeds.**
No task should be solvable from a single agent's context alone, and every task
should be solvable when everything is pooled.
*Check:* for each seed used, compute argmax support over each agent's own visible
facts (is correct ever the unique argmax?), and argmax over all facts (is correct
always the unique argmax?).

**G7. No distractor names an option.**
`_DISTRACTOR_NOTES` are meant to be decision-irrelevant. `_shared_support()`
attributes a fact to an option by `fact.startswith(option + " ")`, so a distractor
beginning with a candidate name would silently corrupt the support tally.
*Check:* substring search for all 8 candidate names in every distractor string
and in every generated fact; verify `_shared_support` totals against the
independently tracked `support` dict.

**G8. Fact strings are unique within a task.**
`used_facts` guard in both fact builders. Duplicate facts would double-count in
surfacing.
*Check:* assert uniqueness across shared + all private facts for every seed used.

**G9. Agents are symmetric apart from which private facts they hold.**
Private facts are dealt round-robin (`i % n_agents`), but distractors are dealt
`j % n_agents` with `n_distractors=4` over 3 agents, so agent 0 receives 2
distractors and agents 1 and 2 receive 1 each. Agent 0 is also always the
aggregator (`aggregator_index=0`).
*Check:* measure per-agent context length and distractor count across seeds; from
condition B episodes, compare per-agent vote accuracy by agent index.

**G10. The task cannot be solved by a shallow surface heuristic.**
Each strength fact begins with a candidate's name, so the correct candidate's
name appears exactly `total_private` times and the decoy's `total_private - 1`
times in the pooled text. Counting name mentions is therefore sufficient, without
reading any fact content.
*Check:* implement a name-frequency-only policy over condition A's exact context
and measure its accuracy; compare with A's measured accuracy.

**G11. Option names are not substrings of one another or of other fact text.**
`_CANDIDATES` are first names; `parse_answer` does substring matching.
*Check:* pairwise substring test over all candidate names; search each name as a
substring inside generated facts where it is not the leading token.

---

## P. Prompts and conditions

**P1. What each condition's model sees is what the methodology says it sees.**
`TEAM_SYSTEM_PROMPT`, `NEUTRAL_SYSTEM_PROMPT`, `SOLO_SYSTEM_PROMPT`,
`AGENT_TURN_PROMPT`, `NEUTRAL_TURN_PROMPT`, `NO_COMM_PROMPT`,
`AGGREGATOR_PROMPT`, `TASK_STATEMENT` in `grapevine/rollout/engine.py`.
*Check:* reconstruct and print a full, byte-exact example prompt for every
condition into the audit report.

**P2. Conditions differ only in the intended manipulation.**
Everything else — token limit, temperature, retry policy, model, number of
options, context ordering — should be identical.
*Check:* tabulate every prompt-affecting parameter per condition from the
committed manifests and from the code; diff the prompt templates.

**P3. Condition A's context is the same information in the same form as B/C/D.**
`Task.full_context()` renders a flat bulleted union with no "Facts known to the
whole committee" / "Facts only you know" headers, and A's system prompt is
"You are an expert decision-maker..." rather than the team prompt. So A differs
from the distributed conditions in *presentation and framing*, not only in
information access. Any A − C gap therefore contains a presentation component.
*Check:* print both and diff; quantify what differs beyond fact access.

**P4. No private information reaches an agent that should not have it.**
Agent *i*'s prompt context should contain only its own private facts. Other
agents' facts may appear only via the shared transcript.
*Check:* for every seed used, reconstruct each agent's turn prompt and assert no
other agent's private fact string appears in the context segment.

**P5. The aggregator's own context does not give it an unintended advantage.**
`AGGREGATOR_PROMPT` includes `task.agent_contexts[agg]` alongside the transcript,
so agent 0's private facts are present twice (own context plus transcript) while
other agents' appear once.
*Check:* confirm from reconstructed prompts; measure whether C's errors favour
options supported by agent 0's own context.

**P6. The rule arm's statement is identical in A and C.**
`TASK_STATEMENT`, `RolloutConfig.show_task`.
*Check:* extract from the rule-arm episodes' recorded config and reconstruct both
prompts; byte-compare the statement block.

**P7. No response was silently truncated.**
`max_tokens=400`. A truncated discussion turn would lower surfacing and could
truncate an aggregator's JSON answer into a parse failure.
*Check:* distribution of `completion_tokens` per call against the cap; count
episodes at or near the limit.

---

## M. Measurement

**M1. `parse_answer` either extracts the intended option or fails loudly.**
`parse_answer` and `_match_option` in `grapevine/rollout/engine.py`.
`_match_option` matches substrings in *both* directions
(`candidate in option or option in candidate`), so short or empty candidate
strings may match an option rather than returning `None`. The free-text fallback
takes the *last-mentioned* option, which can invert an explicit rejection.
*Check:* build an adversarial suite — empty string, single letter, refusal,
multiple options named, option named then rejected, option as substring of
another word, markdown/code-fence variants, wrong-case, trailing punctuation —
and record for each whether it parses correctly, parses *wrongly*, or fails
loudly. Report the fraction that parse wrongly.

**M2. The JSON path, not the fuzzy fallback, produced the reported answers.**
If most answers came through the fallback, M1's risks are load-bearing.
*Check:* re-parse every stored answer/vote message from the committed runs and
classify which branch produced the result.

**M3. The surfacing metric measures what "surfaced" means.**
`fact_surfaced` (substring, content-token overlap ≥ 0.7, difflib ratio ≥ 0.7).
The headline "100% surfacing in 200/200 episodes" rests on it entirely.
*Check:* draw a random sample of at least 30 (fact, message) pairs from committed
transcripts, hand-label each as surfaced or not, and report precision and recall
against the labels, with the specific false positives and false negatives.

**M4. Surfacing is computed over the right messages.**
`_discussion_messages` includes `discussion` and `vote` roles and excludes the
aggregator's `answer`.
*Check:* confirm which roles exist per condition and that no condition's
surfacing figure is computed over a role set the docs do not describe.

**M5. Nothing anywhere depends on an LLM judge.**
*Check:* grep the scoring path for any model call; confirm reward and all metrics
are pure functions of ground truth and transcript text.

**M6. Decoy rate carries information beyond accuracy.**
`other_wrong_rate` was 0.000 in all four conditions, making decoy rate the
complement of accuracy plus parse failures.
*Check:* verify from episodes; state plainly whether it is an independent metric
or a confirmation that failures are systematic.

---

## S. Statistics

**S1. The paired bootstrap is actually paired.**
`paired_difference_ci` zips two lists positionally. In
`grapevine/experiments/run.py` those lists are built from each condition's
episode list, filtered for failures, and only checked for equal length — so a
failure in one condition but not another would misalign tasks silently while
still passing the length check.
*Check:* confirm the primary and rule-arm runs had zero failures (so alignment
holds for reported numbers); demonstrate the misalignment failure mode on
constructed data; verify `compare.py` aligns by task id instead.

**S2. The bootstrap implementation is correct.**
`bootstrap_ci`.
*Check:* hand-compute a percentile bootstrap on a small vector with a fixed seed
and compare; check the percentile index convention at both ends.

**S3. Reported comparisons account for how many were run.**
Four paired comparisons plus per-condition intervals are reported with no
multiplicity adjustment.
*Check:* count the comparisons reported in the docs; state whether any conclusion
depends on one marginal interval.

**S4. No interval is computed from a degenerate sample.**
Condition B is 1/200; the uncommitted rule arm has a 100/100 cell. A percentile
bootstrap on an all-identical sample returns a zero-width interval, which is not
a meaningful confidence statement.
*Check:* list every reported interval whose underlying sample is 0/n, n/n, or
within one of either, and say what the bootstrap does there.

**S5. Bootstrap seeds do not create spurious agreement between metrics.**
Accuracy uses seed 0, decoy rate seed 1, paired differences seed 0.
*Check:* confirm resampling is independent where it needs to be.

---

## R. Reproducibility

**R1. The documented install and test commands work from a clean clone.**
`README.md` quick start.
*Check:* clone into a fresh directory, create a fresh environment, run the
documented commands verbatim, record exact failures.

**R2. The documented reproduction command regenerates the reported numbers.**
`README.md` "Reproducing the reported result".
Temperature could not be set and every call ran at the model default of 1.0, so
exact reproduction of the accuracy figures is not possible even in principle.
*Check:* verify that task *content* regenerates identically by seed (free,
offline); state explicitly what does and does not reproduce, and whether the
README currently over-promises.

**R3. The environment is pinned well enough to reproduce.**
`pyproject.toml` uses lower bounds; there is no `uv.lock` in the repository.
*Check:* confirm absence of a lockfile; record the versions actually used for the
committed runs, and whether they are recorded anywhere in the manifests.

**R4. CI is green on what is being published.**
`.github/workflows/ci.yml`.
*Check:* run lint, types and tests locally on the audit branch; check the last CI
conclusion for the published commit.

**R5. The figure regenerates from committed data.**
`grapevine/experiments/figure.py`, `runs/20260910T065248Z_primary/`.
*Check:* regenerate into a scratch directory from the committed run and compare
the source table against the committed `figure_data.csv`.

**R6. Everything the docs reference exists in the repository.**
README references run directories, a figure path, config names, test counts.
*Check:* resolve every path and number mentioned in README and `docs/results.md`.

**R7. No secrets in the repository or its history.**
*Check:* confirm `.env` was never added (done: it was not); scan full history for
key-shaped strings; confirm `.gitignore` covers `.env` and that `.env.example`
contains only placeholders.

---

## C. Claims

**C1. Every factual claim in `README.md` and `docs/results.md` traces to an artifact.**
*Check:* build a claim-by-claim table mapping each to a file, table, manifest
field or log line; flag every claim with nothing behind it.

**C2. Numbers attributed to prior work are accurate.**
README and `docs/results.md` cite HiddenBench (arXiv:2505.11556) for roughly 30%
versus 81%. No PDF of that paper is present in the repository and it has not been
fetched.
*Check:* look for a local source; if absent, mark **UNVERIFIED** in the docs
rather than leaving the figure bare. The same applies to the Stasser & Titus
(1985) citation details.

**C3. Run-level numbers in the docs match the manifests.**
"3,600 API calls", "$0.7574", "14 minutes 16 seconds", "no failures", "82 tests",
"commit 4311f6f2, clean working tree".
*Check:* compare each against `manifest.json` and a test run.

**C4. Derived statistics quoted in prose match recomputation.**
"every wrong answer in all 800 episodes was the decoy"; "47 of the 66 C failures
had full surfacing and were solved by A"; "174 of 200 asked for criteria";
"188 of 200 tasks mention a hiring committee or the role"; "66 distinct name
sets"; condition D's 85/115 surfacing split at 61.2% and 47.0%.
*Check:* recompute each from committed episodes.

**C5. The docs describe the current state of the work.**
`runs/20260913T013826Z_rule_arm/` exists on disk, uncommitted, containing the
experiment that README and `docs/results.md` both describe as the *next*
experiment. The published docs would therefore describe an open question that has
already been measured.
*Check:* confirm the run's contents and provenance; determine whether its result
changes any published claim.

**C6. The rule arm's own result is trustworthy.**
It reports a 100/100 cell, which is the kind of number that is usually an
artifact.
*Check:* leakage analysis — does the statement text or option ordering give the
answer away; is gold position uniform in those 100 seeds; does the condition's
answer distribution track gold or track position; read transcripts by hand.

---

## Known gaps in this ledger

Things that cannot be settled by checking this repository:

- Whether `gpt-5.6-luna` behaves consistently over time. All runs are from a
  three-day window; no re-run was done to measure between-run drift.
- Whether results hold for any other model, team size, round budget, or option
  count. Only one setting of each was ever run.
- Whether the hand labels used for the surfacing metric's precision and recall
  are themselves correct, since one person produced them.
