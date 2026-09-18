# Pre-publication audit

Branch `audit/pre-publication`, 2026-09-18. Assumptions under test are listed in
`docs/assumptions.md`, which was written and committed (`55aac5a`) before any of
these checks ran. Every finding below comes from an executed check. Nothing has
been fixed yet; fixes follow review.

All checks were offline, against committed code and committed run data. **API
spend for this audit: $0.**

Severity: **Invalidating** — a published claim or number is wrong or has
nothing behind it. **Limiting** — the result is narrower than the docs state.
**Latent defect** — a code bug that did not affect any reported number but would
on reuse. **Cosmetic**. **Clean** — checked, holds.

---

## Invalidating

### I1. The "single-agent ceiling" is not a ceiling, and the headline gap it anchors has been explained away by a run already in hand

*Assumptions C5, C6, G10.*

README and `docs/results.md` describe condition A as "the single-agent ceiling"
and report C as "18.5 points below the single-agent ceiling", with the reading
that "getting the facts onto the table did not close the gap." The figure labels
the comparison the same way.

Three executed results contradict that framing:

1. **The rule arm (run `20260913T013826Z_rule_arm`, commit `40dc112`, clean tree,
   0 failures, $0.1845) closes the gap entirely.** On the 100 matched seeds
   1000-1099, stating the task question and scoring rule took C from 68/100 to
   **100/100** (paired difference +32 pts, 95% bootstrap [+23, +41]) and C's
   decoy rate from 32% to **0%**. A rose from 83/100 to 96/100. The A − C gap went
   from +15 to **−4** points (change −19, [−29, −9]). With the task stated, the
   distributed team beats the "ceiling".
2. **The 100/100 is not a leak.** Gold position over those seeds is
   {0: 28, 1: 24, 2: 22, 3: 26} and C + rule's chosen positions are identical,
   i.e. it tracks the answer, not a slot. No question stem names the gold
   candidate. `show_task` is recorded as true on all 200 rule-arm episodes. In the
   transcript for `hidden_profile-1006`, which the primary C run got wrong, the
   agents share the same facts as before and the aggregator answers Finley (gold).
3. **A is beaten by a trivial rule.** Counting how often each candidate's name
   appears in A's exact context picks the correct answer in **200/200** tasks. A
   scored 171/200. A measures how reliably the model applies an unstated counting
   rule, not an upper bound on what the information supports.

This run exists on disk, uncommitted, and is not mentioned in any published
document; README and `results.md` still describe it as "the next experiment".

**What still stands:** every number in the four-condition tables is correctly
computed (see Clean, C3/C4). Distributing the information without communication
(B, 0.5%) is still catastrophic, and discussion still recovers most of it. What
does not stand is the claim that C's residual deficit reflects a failure to use
pooled information: under this task, it is removed by telling the model what it is
being asked.

### I2. The HiddenBench figures in `docs/results.md` are unverified and unmarked

*Assumption C2.*

`docs/results.md` ("What we are not claiming") states "the ~30% versus 81%
figures in that paper". No copy of arXiv:2505.11556 is in the repository and the
number has never been checked against the source in this project. Under the
audit rules it must be marked **UNVERIFIED** or verified; it is currently neither.
The README's HiddenBench sentence is qualitative and does not quote numbers. The
Stasser & Titus (1985) citation details are likewise **UNVERIFIED**.

---

## Limiting

### L1. All four-condition numbers are conditional on a task the models were never given

*Assumption C5 / prior decision log.* Already disclosed as a limitation, but I1
turns it from a caveat into a measured effect: +32 points for C, +13 for A. B and D
were **not** re-run with the rule, so how much of their numbers depends on the
missing task statement is **UNVERIFIED**. B is plausibly unaffected (each agent
still sees the decoy leading 5 to 2 in its own facts), but that has not been
measured.

### L2. The 200 tasks are one puzzle, numerically as well as textually

*Assumption G1.* Beyond the known single strength-sentence set: every one of the
200 primary tasks has the identical support profile **(6, 5, 1, 0)** — correct 6,
decoy 5, one other option 1, one option 0. Tasks differ only in names (66 of 70
possible name sets; 54 of 56 correct/decoy pairs), which sentence attaches to
which name, 4-of-8 distractor choice (66 distinct sets), and order. All 200 full
contexts are distinct strings. The bootstrap intervals measure variation over
these permutations only.

### L3. The task is solvable by name counting

*Assumption G10.* See I1.3. Because every strength fact begins with the
candidate's name, frequency of the name is a sufficient statistic. The experiment
therefore measures whether the model counts, and (per I1) whether it knows it
should. It does not measure reasoning over fact content.

### L4. Condition A differs from B/C/D in presentation, not only information

*Assumption P3.* Reconstructed prompts (Appendix): A gets a flat bulleted list
with no "Facts known to the whole committee" / "Facts only you know" headers, a
different system prompt ("You are an expert decision-maker..."), and the
aggregator template with the literal line "Full team discussion: (you have all
information; no discussion needed)". Any A − C difference mixes information access
with framing.

### L5. The surfacing metric misses about 1 in 7 genuine surfacings, and the C−D surfacing gap is partly an artefact

*Assumption M3.* 40 (fact, message) pairs drawn with a fixed seed from holder
messages in C and D, stratified 20 metric-positive / 20 metric-negative, labelled
by hand with the metric's verdict hidden (labels in
`docs/audit_surfacing_labels.json`):

| | Human: surfaced | Human: not |
|---|---:|---:|
| Metric: surfaced | 20 | 0 |
| Metric: not | 8 | 12 |

**Precision 1.00 (20/20; exact 95% lower bound ≈ 0.83). Recall ≈ 0.86** after
weighting the strata by pool size (3,430 metric-positive, 1,370 metric-negative
holder messages); 8 of the 20 metric-negatives were real surfacings. Every miss
is a paraphrase: "reliable test-suite rewrite", "33% cost reduction", "recovery of
a six-month delay", "designed the current on-call rotation".

Consequences: C's 100% cannot be an overcount. D's 82.7% is an undercount. C's
prompt says "State concrete facts verbatim"; D's does not, and the metric rewards
verbatim wording, so part of the reported 100% vs 82.7% gap is the instruction
interacting with the matcher. D's 85/115 full/partial split (61.2% vs 47.0%
accuracy) is contaminated by the same misclassification. Single labeller, n=40.

### L6. Intervals at the extremes are too narrow

*Assumption S4.* The percentile bootstrap cannot represent uncertainty in a
sample that is all one value.

| Cell | Reported (bootstrap) | Exact Clopper-Pearson |
|---|---|---|
| B accuracy, 1/200 | [0.0%, 1.5%] | [0.02%, 2.75%] |
| C + rule accuracy, 100/100 (unpublished) | [100%, 100%] | [96.4%, 100%] |
| A + rule accuracy, 96/100 (unpublished) | [92%, 99%] | [90.1%, 98.9%] |

### L7. "Reproducing the reported result" reproduces the procedure, not the numbers

*Assumptions R2, R3.* Task content regenerates byte-for-byte by seed (0/200
mismatches against committed episodes). Accuracy figures cannot be reproduced
exactly because every call ran at temperature 1.0, which the model does not allow
to be changed. The README section title promises more than that. No lockfile
exists and the manifests record only the Python version (3.11.4), not package
versions; a clean clone today resolved httpx 0.28.1, numpy 2.4.6, matplotlib
3.11.2, python-dotenv 1.2.3, pyyaml 6.0.3.

### L8. Accuracy depends on where the correct answer sits in the option list

*Assumption G4.* Accuracy by gold position (0,1,2,3): A 0.91/0.87/0.87/0.76;
C 0.81/0.65/0.64/0.56; D 0.65/0.41/0.58/0.44. Gold position is balanced in the
primary seeds (54/46/55/45) and uniform over 5,000 seeds (χ²=1.31), so condition
means are not biased by it, but it is a real behavioural effect adding variance,
and any subset analysis could pick it up. Not formally tested.

### L9. The aggregator is not a typical agent

*Assumptions G9, P5.* Distractors are dealt round-robin, so with 4 distractors
over 3 agents agent 0 always holds 2 and the others 1 (mean context 622 vs 565
characters). Agent 0 is always the aggregator, and its own private facts appear
in its prompt twice (own context plus transcript). Not measured for effect.

### L10. Condition D's two "parse failures" are empty responses

*Assumption P7.* Both (`hidden_profile-1013`, `-1194`) are empty strings in
episodes that used ~1,200 completion tokens. For GPT-5-family models the
`max_completion_tokens=400` cap includes hidden reasoning tokens, so the likely
cause is truncation, not refusal. Cannot be confirmed: usage is logged per
episode, not per call. Docs call them parse failures without saying this.

### L11. Condition D's aggregator uses the instructed system prompt

*Assumptions P1, P2.* Found while generating the appendix. In `run_episode`, the
aggregation branch always sends `TEAM_SYSTEM_PROMPT` ("Your job is to actively
SHARE the specific facts you hold and ASK teammates... then reason over
everything the team has surfaced"), regardless of `prompt_style`. So D's
discussion turns are neutral but its final decision is made under the instructed
prompt. The registered design described D as identical to C "except the system
prompt does NOT instruct fact-sharing or asking"; `methodology.md` only claims the
aggregator *user* prompt is identical. The C − D difference (+14.0 pts) therefore
measures the instruction's effect on discussion, not on the decision step. Whether
the neutral prompt at aggregation would move D is **UNVERIFIED**. See the D
aggregator entry in the appendix.

---

## Latent defects (no reported number affected; must fix before reuse)

These matter because the harness is about to be pointed at HiddenBench and
PAC-BENCH, where answer formats and failure rates will differ.

### D1. `parse_answer` returns a wrong option instead of failing

*Assumption M1.* Adversarial suite of 18 outputs: 11 correct, **7 parsed to a
wrong option**, 0 failed loudly when they should not have. `_match_option`
matches substrings in both directions, so `{"answer": ""}`, `"A"`, `"e"` and `"y"`
all resolve to the first option ("Avery") — a silent bias toward option 0.
`{"answer": "I pick Blair over Avery"}` returns Avery. The free-text fallback
takes the last-mentioned option, so "Blair is best; Avery was close" returns
Avery and "It is between Avery and Blair" returns Blair.

Why no reported number is affected (*M2*): every one of the 1,538 committed answer
and vote messages across all five runs was resolved through the exact-JSON branch.
The only non-parses are D's two empty strings, which correctly returned None.

### D2. Positional pairing in `run.py` misaligns after a failure

*Assumption S1.* `run.py` builds per-condition correctness lists after dropping
failed episodes and zips them positionally, checking only equal length. Constructed
case: one condition loses task 3 and gains task 10 — lengths match, 3 of 10 pairs
align, and the paired difference reads 0.1 where the true value is 0.0. The primary
and rule-arm runs had zero failures and identical task order across conditions, so
their paired numbers are correct (recomputed exactly, see C3/C4). `compare.py`
already aligns by task id.

### D3. Run provenance is captured at the end of the run, not the start

`_git_commit()` and `_git_dirty()` are called when the manifest is written. Editing
or committing during a run would record the wrong commit. Not triggered by any
committed run.

---

## Cosmetic

- README says "82 tests". A clean clone with the documented `.[dev]` install runs
  **80 passed, 1 skipped** (the training-smoke module skips without the `train`
  extra; with it there are 83).
- The figure and tables label A as "Full information / ceiling" (see I1).
- `docs/experiment.md` still describes three registered hypotheses' framing around
  a ceiling.

---

## Clean

| Check | Result |
|---|---|
| G3 answer position uniform | gold χ²=1.31, decoy χ²=0.92 over 5,000 seeds (critical 7.81) |
| G5 invariants on the seeds used | 0 violations over all 200 primary seeds |
| G6 degenerate seeds | 0/200 solvable by one agent alone; 0/200 unsolvable when pooled |
| G7 distractors naming an option | none; `_shared_support` matches tracked support on 200/200 |
| G8 duplicate facts | 0 |
| G11 names as substrings of names | none |
| P4 private information leakage | 0 leaks into any other agent's context over 200 seeds × 3 agents |
| P6 rule statement identical in A and C | byte-identical; recorded on all 200 rule-arm episodes |
| M2 parse branch | 1,538/1,538 answers via exact JSON match |
| M5 LLM judge | none anywhere in scoring |
| M6 decoy rate | 386 of 386 parsed wrong answers were the decoy; decoy rate is the complement of accuracy and adds no independent signal (already stated in docs) |
| S1 pairing in reported runs | 0 failures, identical task order, all four paired intervals recompute exactly |
| S2 bootstrap implementation | matches hand computation exactly |
| S3 multiplicity | all four paired comparisons still exclude 0 at Bonferroni α=0.05/4; tightest, C − D, is [+3.5, +25.0] |
| C3 run-level numbers | 3,600 calls, $0.7574, 14m16s, commit 4311f6f2, clean, 0 failures — all match |
| C4 derived numbers in prose | 386/386 decoy; 47 of 66; 200/200 full surfacing in C; D 85→61.2% / 115→47.0%; 174/200 asked; 188/200 cue; 66 name sets — all reproduce |
| R1 clean clone | install, ruff, mypy, pytest, `uv run grapevine gen` all succeed |
| R2 task determinism | 0/200 mismatches vs committed episodes |
| R4 CI | last run on `main` (40dc112) succeeded |
| R5 figure | regenerates from committed data; numeric columns identical |
| R6 referenced paths | all tracked |
| R7 secrets | `.env` never committed; no key-shaped strings in history |

---

## Could not check

- **HiddenBench and Stasser & Titus figures and citation details.** No source in
  the repository; not fetched, per the audit rules. UNVERIFIED.
- **Per-call truncation** (L10). Usage is aggregated per episode.
- **B and D with the task stated** (L1). Would need new runs.
- **Between-run drift** of `gpt-5.6-luna`. All runs fall in a three-day window.
- **Surfacing label reliability.** One labeller; no second annotator.

---

## Appendix: byte-exact prompts, `hidden_profile-1006`

Reconstructed from the templates in `grapevine/rollout/engine.py` and the task
regenerated from its seed. The C and D aggregator prompts use the actual
transcript from the committed primary run.

### A full_info

System:

```text
You are an expert decision-maker. Reason carefully, then answer.
```

User:

```text
All available information:
- Devon shipped a production ML system end to end.
- Devon published peer-reviewed work in the domain.
- Devon cut infrastructure costs by a third at their last role.
- Devon mentored three junior engineers to promotion.
- Avery consistently writes clear design documents.
- Devon turned around a project that was six months behind.
- The hiring committee meets on alternating Thursdays.
- Finley handled the largest incident of the last quarter calmly.
- The interview panel met in the third-floor conference room.
- Finley led a cross-functional team of eight.
- Finley has deep experience with distributed systems.
- Finley owns an open-source library with real adoption.
- The role has been open since the start of the quarter.
- Finley designed the on-call rotation the team still uses.
- Finley rewrote a flaky test suite to full reliability.
- A calendar conflict pushed one interview to the afternoon.

Full team discussion:
(you have all information; no discussion needed)

Based on everything the team surfaced, decide the single best answer. Choose exactly one of these options: Finley, Avery, Blair, Devon.
Respond with only a JSON object: {"answer": "<one option exactly as written>"}.
```

### B no_communication (agent 0)

System:

```text
You are Agent 0 of a 3-agent group. Each member holds different private information. You must decide ALONE: there is no discussion, you cannot ask anyone anything, and you will never see what the others hold. Reason carefully over the information you have and commit to the best answer you can.
```

User:

```text
Facts known to the whole committee:
- Devon shipped a production ML system end to end.
- Devon published peer-reviewed work in the domain.
- Devon cut infrastructure costs by a third at their last role.
- Devon mentored three junior engineers to promotion.
- Avery consistently writes clear design documents.
- Devon turned around a project that was six months behind.

Facts only you know:
- The hiring committee meets on alternating Thursdays.
- Finley handled the largest incident of the last quarter calmly.
- The interview panel met in the third-floor conference room.
- Finley led a cross-functional team of eight.

You are deciding alone, with no discussion.
Choose exactly one of these options: Finley, Avery, Blair, Devon.
Respond with only a JSON object: {"answer": "<one option exactly as written>"}.
```

### C communication, agent 0, round 1

System:

```text
You are Agent 0 of a 3-agent team solving a problem together. Each teammate holds different private information, and no one can answer alone. Your job is to actively SHARE the specific facts you hold and ASK teammates for information you are missing, then reason over everything the team has surfaced. State concrete facts verbatim rather than vague summaries. Be concise.
```

User:

```text
Facts known to the whole committee:
- Devon shipped a production ML system end to end.
- Devon published peer-reviewed work in the domain.
- Devon cut infrastructure costs by a third at their last role.
- Devon mentored three junior engineers to promotion.
- Avery consistently writes clear design documents.
- Devon turned around a project that was six months behind.

Facts only you know:
- The hiring committee meets on alternating Thursdays.
- Finley handled the largest incident of the last quarter calmly.
- The interview panel met in the third-floor conference room.
- Finley led a cross-functional team of eight.

Conversation so far:
(no messages yet)

It is your turn (round 1 of 2). Write a short message to your teammates: share the specific facts you hold that are relevant, and ask for any information you still need. Do not state a final answer yet.
```

### C aggregator (agent 0), actual transcript

System:

```text
You are Agent 0 of a 3-agent team solving a problem together. Each teammate holds different private information, and no one can answer alone. Your job is to actively SHARE the specific facts you hold and ASK teammates for information you are missing, then reason over everything the team has surfaced. State concrete facts verbatim rather than vague summaries. Be concise.
```

User:

```text
Facts known to the whole committee:
- Devon shipped a production ML system end to end.
- Devon published peer-reviewed work in the domain.
- Devon cut infrastructure costs by a third at their last role.
- Devon mentored three junior engineers to promotion.
- Avery consistently writes clear design documents.
- Devon turned around a project that was six months behind.

Facts only you know:
- The hiring committee meets on alternating Thursdays.
- Finley handled the largest incident of the last quarter calmly.
- The interview panel met in the third-floor conference room.
- Finley led a cross-functional team of eight.

Full team discussion:
Agent 0: I know these additional facts: the hiring committee meets on alternating Thursdays; Finley handled the largest incident of the last quarter calmly; the interview panel met in the third-floor conference room; and Finley led a cross-functional team of eight. Please share any other candidate-specific facts you have and the exact decision or ranking we need to produce.
Agent 1: I know these additional facts: Finley has deep distributed-systems experience, owns an open-source library with real adoption, and the role has been open since the start of the quarter. What exact decision or ranking must we produce, and what evaluation criteria or constraints should we apply?
Agent 2: I know these additional facts: Finley designed the on-call rotation the team still uses, rewrote a flaky test suite to full reliability, and a calendar conflict pushed one interview to the afternoon. What final output do we need—selection, ranking, or hiring recommendation—and what criteria or weighting should we apply?
Agent 0: I hold these additional facts: the hiring committee meets on alternating Thursdays; Finley handled the largest incident last quarter calmly; the interview panel met in the third-floor conference room; and Finley led a cross-functional team of eight. We still need the required output (selection, ranking, or recommendation) and the evaluation criteria or weighting.
Agent 1: Relevant facts I hold: Finley has deep distributed-systems experience, owns an open-source library with real adoption, and the role has been open since the start of the quarter. We still need the required output—selection, ranking, or hiring recommendation—and the evaluation criteria or weighting.
Agent 2: I hold these candidate-relevant facts: Finley designed the team’s still-used on-call rotation and rewrote a flaky test suite to full reliability. A calendar conflict moved one interview to the afternoon, but that is scheduling context rather than candidate evidence. We still need the required output—selection, ranking, or recommendation—and the evaluation criteria/weighting.

Based on everything the team surfaced, decide the single best answer. Choose exactly one of these options: Finley, Avery, Blair, Devon.
Respond with only a JSON object: {"answer": "<one option exactly as written>"}.
```

### D communication_neutral, agent 0, round 1

System:

```text
You are Agent 0 of a 3-agent team solving a problem together. Each teammate holds different private information, and no one can answer alone. Discuss the decision with your teammates. Be concise.
```

User:

```text
Facts known to the whole committee:
- Devon shipped a production ML system end to end.
- Devon published peer-reviewed work in the domain.
- Devon cut infrastructure costs by a third at their last role.
- Devon mentored three junior engineers to promotion.
- Avery consistently writes clear design documents.
- Devon turned around a project that was six months behind.

Facts only you know:
- The hiring committee meets on alternating Thursdays.
- Finley handled the largest incident of the last quarter calmly.
- The interview panel met in the third-floor conference room.
- Finley led a cross-functional team of eight.

Conversation so far:
(no messages yet)

It is your turn (round 1 of 2). Write a short message to your teammates. Do not state a final answer yet.
```

### D aggregator (agent 0), actual transcript — note: system prompt is TEAM_SYSTEM_PROMPT, not the neutral one

System:

```text
You are Agent 0 of a 3-agent team solving a problem together. Each teammate holds different private information, and no one can answer alone. Your job is to actively SHARE the specific facts you hold and ASK teammates for information you are missing, then reason over everything the team has surfaced. State concrete facts verbatim rather than vague summaries. Be concise.
```

User:

```text
Facts known to the whole committee:
- Devon shipped a production ML system end to end.
- Devon published peer-reviewed work in the domain.
- Devon cut infrastructure costs by a third at their last role.
- Devon mentored three junior engineers to promotion.
- Avery consistently writes clear design documents.
- Devon turned around a project that was six months behind.

Facts only you know:
- The hiring committee meets on alternating Thursdays.
- Finley handled the largest incident of the last quarter calmly.
- The interview panel met in the third-floor conference room.
- Finley led a cross-functional team of eight.

Full team discussion:
Agent 0: I know the committee meets on alternating Thursdays; Finley handled the largest incident last quarter calmly; the panel met in the third-floor conference room; and Finley led a cross-functional team of eight. What private facts do you have, and what decision are we being asked to make?
Agent 1: My private facts: Finley has deep distributed-systems experience and owns a widely adopted open-source library. The role has been open since the start of the quarter. I infer we’re deciding which candidate to hire, but I don’t yet know the exact selection criteria or options.
Agent 2: My private facts: Finley designed the team’s current on-call rotation and rewrote a flaky test suite to full reliability. A calendar conflict moved one interview to the afternoon. Combined with your facts, Finley appears strong operationally and technically; we still need the exact decision criteria and candidate options.
Agent 0: We appear to be comparing Devon, Avery, and Finley for the open role. Devon has exceptional delivery, research, cost, and mentoring evidence; Finley has strong operational, distributed-systems, open-source, and leadership experience; Avery’s main evidence is clear design writing. What are the stated role priorities or selection criteria we should apply before deciding?
Agent 1: No explicit priorities have surfaced. I suggest evaluating all three against end-to-end execution, technical depth, operational reliability, leadership/mentoring, and communication. On current evidence, Devon is strongest on delivery and organizational impact, while Finley is strongest on distributed systems and operations; Avery’s evidence mainly supports communication. We should confirm whether the role emphasizes execution, systems expertise, or design communication before selecting.
Agent 2: No explicit priorities have emerged, so we should avoid selecting yet. The evidence favors Devon for broad execution, impact, and mentoring; Finley for systems depth and operational reliability; Avery primarily for communication. The afternoon interview appears logistical, not evaluative. We should confirm the role’s weighting—especially execution versus distributed systems/operations versus design communication—before deciding.

Based on everything the team surfaced, decide the single best answer. Choose exactly one of these options: Finley, Avery, Blair, Devon.
Respond with only a JSON object: {"answer": "<one option exactly as written>"}.
```

### A + rule

System:

```text
You are an expert decision-maker. Reason carefully, then answer.
```

User:

```text
Task: The hiring committee must recommend exactly one candidate for the role. Based on all available information, who is the strongest candidate? Options: Finley, Avery, Blair, Devon.
Decision rule: the strongest candidate is the one with the most supporting facts. Each fact describing a candidate's strengths counts as one supporting fact for that candidate.

All available information:
- Devon shipped a production ML system end to end.
- Devon published peer-reviewed work in the domain.
- Devon cut infrastructure costs by a third at their last role.
- Devon mentored three junior engineers to promotion.
- Avery consistently writes clear design documents.
- Devon turned around a project that was six months behind.
- The hiring committee meets on alternating Thursdays.
- Finley handled the largest incident of the last quarter calmly.
- The interview panel met in the third-floor conference room.
- Finley led a cross-functional team of eight.
- Finley has deep experience with distributed systems.
- Finley owns an open-source library with real adoption.
- The role has been open since the start of the quarter.
- Finley designed the on-call rotation the team still uses.
- Finley rewrote a flaky test suite to full reliability.
- A calendar conflict pushed one interview to the afternoon.

Full team discussion:
(you have all information; no discussion needed)

Based on everything the team surfaced, decide the single best answer. Choose exactly one of these options: Finley, Avery, Blair, Devon.
Respond with only a JSON object: {"answer": "<one option exactly as written>"}.
```

### C + rule, agent 0, round 1

System:

```text
You are Agent 0 of a 3-agent team solving a problem together. Each teammate holds different private information, and no one can answer alone. Your job is to actively SHARE the specific facts you hold and ASK teammates for information you are missing, then reason over everything the team has surfaced. State concrete facts verbatim rather than vague summaries. Be concise.
```

User:

```text
Task: The hiring committee must recommend exactly one candidate for the role. Based on all available information, who is the strongest candidate? Options: Finley, Avery, Blair, Devon.
Decision rule: the strongest candidate is the one with the most supporting facts. Each fact describing a candidate's strengths counts as one supporting fact for that candidate.

Facts known to the whole committee:
- Devon shipped a production ML system end to end.
- Devon published peer-reviewed work in the domain.
- Devon cut infrastructure costs by a third at their last role.
- Devon mentored three junior engineers to promotion.
- Avery consistently writes clear design documents.
- Devon turned around a project that was six months behind.

Facts only you know:
- The hiring committee meets on alternating Thursdays.
- Finley handled the largest incident of the last quarter calmly.
- The interview panel met in the third-floor conference room.
- Finley led a cross-functional team of eight.

Conversation so far:
(no messages yet)

It is your turn (round 1 of 2). Write a short message to your teammates: share the specific facts you hold that are relevant, and ask for any information you still need. Do not state a final answer yet.
```
