# Decision log

Judgment calls made while building the coordination ablation, and why. Newest
last.

## Exclude `split_evidence` from the experiment

*2026-09-08.* The family leaks the gold answer. Its final reasoning hop reads
"From X, the active route continues to Z" where Z is the answer, so whichever
agent holds that hop holds the answer string outright. Over 100 generated tasks
the gold answer appeared in some agent's context in 100 of them.

This breaks the experiment. A no-communication agent could answer correctly with
no pooling at all, so condition B would not measure what it claims to. It also
explains something seen earlier: the offline `answer_only_no_discussion`
diagnostic scored 0.557 on `split_evidence` against roughly chance on
`hidden_profile`.

`hidden_profile` was checked over the same 100 tasks and is clean: no required
private fact in the shared block, the full-information context contains every
required fact, and no single agent's context on its own favours the correct
candidate.

`run.py` rejects any family other than `hidden_profile` at config-load time
rather than leaving it to a reader to notice. Fixing `split_evidence` (by naming
the terminal station only through a property rather than the answer string) is
worth doing, but it is a task-design change and does not belong in the middle of
an experiment.

## Per-episode cost accounting was wrong under concurrency

*2026-09-08.* Usage was computed by reading the client's running totals before
and after an episode and subtracting. Since episodes share one client and every
`await` lets them interleave, each episode absorbed the others' tokens. Measured:
four concurrent episodes reported 13, 14, 15 and 16 calls when each had made 4,
summing to 58 against a true total of 16. Only the client-level total was right.

The published baseline script used exactly this pattern with concurrency 4, so
any cost or token figure it produced would have been wrong. Replaced with an
accumulator that sums the completions an episode actually received. Regression
test added.

## Fail loudly on an unpriced model

*2026-09-08.* `pricing_for()` returned a zero-cost fallback for unknown models,
so running a model absent from the price table would have reported a cost of
$0.0000 that looked like a measurement. Added `require_pricing()`, which raises,
and put it on the runner's startup path.

## Tie-break rule for condition B

*2026-09-08, before the pilot.* With 3 agents and 4 options, three-way vote
splits are possible and the rule used to resolve them could move condition B's
headline accuracy on its own. Fixed in advance: among options tied for the top
vote count, pick uniformly at random from a `random.Random` seeded with the task
id.

Rejected the simpler "first option in the list" because option order is shuffled
per task, so that rule would couple the tie-break to option ordering instead of
being neutral. The seeded rule is reproducible and unbiased with respect to the
correct answer, and a test checks it spreads evenly over 600 tasks.

Condition B reports the tie rate as a first-class number, and reports accuracy
both with the rule applied and with every tie scored incorrect, so a reader can
see how much the rule is doing.

## System prompts differ between conditions B and C

*2026-09-08.* Conditions are otherwise identical in temperature, `max_tokens`,
retry policy and model. The system prompt has to differ: condition C's prompt
tells agents to share facts and ask teammates for what they are missing, which
is incoherent instruction for an agent that has no channel and would waste its
output budget. Recorded here because it is a real difference between arms, not
something to bury.

## Skip the Batch API

*2026-09-08.* Condition C cannot be batched — agent 2's prompt contains agent 1's
message, so the calls are strictly sequential. A and B could be, but at this
scale the saving is well under a dollar and the cost is a second code path plus
up to 24 hours of turnaround. Keeping every condition on one synchronous path
also avoids introducing a difference between arms that has nothing to do with
the hypothesis.

## Do not claim prompt caching

*2026-09-08.* Automatic prompt caching applies at 1024 tokens and up. Measured
prompt sizes here are roughly 93 (system), 310 (agent turn) and 440 tokens
(aggregator with history), so it does not trigger. Noted rather than claimed.

## GPT-5.6 rejects an explicit temperature

*2026-09-09, during the pilot.* Two API incompatibilities surfaced on the first
real call. `gpt-5.6-luna` requires `max_completion_tokens` instead of
`max_tokens`, and it rejects any explicit `temperature` other than the default
of 1. The first is a straight rename. The second changes the design: the
registered 0.7 discussion / 0.0 answer settings cannot be applied.

Decision: omit the temperature field entirely and let every call run at the
model default of 1.0. The setting is then identical across all three conditions,
so it does not confound the comparison, but answer turns are no longer
deterministic and within-condition variance is higher than planned. The manifest
records `temperature_requested`, `temperature_honoured: false` and
`effective_temperature: 1.0` so nobody reads the config and assumes 0.0 was used.

The alternative was switching to a model that accepts a temperature. Not worth
it: sampling noise is absorbed by the bootstrap intervals, and changing model
would cost the pilot.

## Condition D registered in advance

*2026-09-09, after the pilot, before the primary run.* The pilot showed
condition C recovering almost the whole gap (80% against a 90% ceiling) with a
100% surfacing rate. C's system prompt tells agents to share facts and ask for
what they are missing, so the obvious objection is that the instruction, not the
discussion, produced the result.

Rather than caveat it, condition D measures it: identical to C in agents,
rounds, aggregator, temperature, token budget and seeds, with only the
share/ask directive removed from the two discussion prompts. Both prompts are
written verbatim into `methodology.md`, and this entry is committed before the
run, so D is a registered condition and not a post-hoc addition.

C is described as *instructed* pooling everywhere it is reported. The C-D
difference is the secondary finding.

## Two generator problems found after the primary run

*2026-09-12.* Both came from reading `hidden_profile.py` against the prompts,
and both were checked against the 200 primary tasks before being written up.

**The question never reaches the models.** The generator writes a question into
every task ("who is the strongest candidate?"), but the engine only copies it
into the logged episode. No prompt in any condition contains it, and no prompt
states the scoring rule (one point per supporting fact, most points wins). The
aggregator in `hidden_profile-6` asking for "weighting criteria" was not being
fussy; it had not been told what to decide. A keyword count finds agents asking
for criteria, a decision rule or a ranking in 174 of 200 condition C episodes.
This confounds the reading that C's residual gap is an integration failure.

**Every task uses the whole strength pool.** `_STRENGTHS` has 12 entries and
this configuration consumes 12 strength facts per task, so all 200 primary tasks
contain the same 12 sentences. They vary in names, assignment and order only.

Both are stated in `results.md` limitations, and the integration-failure
interpretation there has been downgraded to a hypothesis.

**The generator was not changed.** The primary run already used it, so expanding
the pool now would change the content of seeds 1000-1199: the committed run
could no longer be regenerated from the code, and any new arm run on the same
seeds would no longer be paired with it.

Resolved the same day: the pool stays as it is and there is no replication for
now. The template limitation is stated in `results.md`, and the committed run
stays reproducible from the code.

## Rule arm registered in advance

*2026-09-12, before running.* Tests whether the residual A − C gap is
underspecification. A and C are re-run on seeds 1000-1099 (N=100) with the task
question and the scoring rule at the top of every prompt, identical text in both
conditions. The generator is unchanged, so every rule-arm task is the same task
the primary run used on that seed and the comparison is paired. The exact text
and the readings committed to in advance are in `methodology.md`.

N=100 rather than 50 because at a decoy rate around 33% the interval is roughly
±13 points at 50 and ±9 at 100, and the extra cost is under ten cents.

The flag that adds the statement (`show_task`) is off by default, and a test
checks the default prompts are byte-identical to before, so the default command
still reproduces the four-condition run. The rule conditions only run when named
with `--conditions`.

## Presentation-matched condition A, registered in advance

*2026-09-18, before running.* With the task stated, C (100/100) and D (99/100)
scored above A (96/100). The audit (L4) found A differs from B/C/D in
presentation as well as information: a flat fact list with no shared/private
headers, the system prompt "You are an expert decision-maker. Reason carefully,
then answer.", and a user prompt containing "Full team discussion: (you have all
information; no discussion needed)". A 4-point gap is within what that could
produce, so "distributed teams beat full information" is not claimed until the
confound is controlled.

Run 9 (`full_info_matched_rule`, seeds 1000-1099, N=100, rule shown) keeps A's
information identical — one agent, every shared and private fact — and changes
only presentation:

- Context in the same two blocks agents see: "Facts known to the whole
  committee:" (the shared facts, identical to every agent's) and "Facts only you
  know:" (every agent's private facts, in agent order).
- System prompt built like condition B's: "You are Agent 0 of a 1-agent group.
  You hold all of the group's information: every shared fact and every private
  fact. Reason carefully over the information you have and commit to the best
  answer you can."
- User prompt is condition B's with its "You are deciding alone, with no
  discussion." line removed: the context, then "Choose exactly one of these
  options: {options}." and the JSON instruction. No "team discussion" wording.
- The identical task statement and rule used in the rest of the rule arm.

Reading, fixed now: if matched A lands near 96%, the A < C/D gap with the rule
is not a presentation artefact and can be stated carefully. If it rises to
around 100%, the gap was presentation, and the statement becomes "with the task
stated, every communicating condition matches full information". Both A variants
are reported, and the text says which one each comparison uses.

## Phase 2: what the audit changed

*2026-09-18/19.* Fixes made after the audit (`docs/audit.md`), each with a
regression test that fails on the old code:

- **Aggregator ignored `prompt_style`** (L11). The aggregation and vote branches
  always sent the instructed system prompt, so condition D's decision step was
  not neutral. Fixed; D was rerun from scratch and only the rerun is reported
  (106/200 to 111/200, a change of +2.5 points [-5.5, +11.0], so the confound was
  not driving the old number).
- **Parser guessed instead of failing** (D1). Substring matching in both
  directions mapped an empty or one-letter answer to the first option, and free
  text took the last-mentioned option; 7 of 18 adversarial cases returned a wrong
  option. Now an option is returned only when exactly one is identified.
  Re-parsing all 2,120 committed answers and votes changes nothing, so no
  reported number moved.
- **Paired differences could misalign** (D2). Positional zipping after dropping
  failed episodes is replaced by alignment on task id; mismatched task sets are
  refused and the run exits with an error.
- **Provenance was captured at the end of a run** (D3). Now taken before the
  first API call and again at the end, with both in the manifest.
- **Bootstrap intervals collapsed at the extremes** (L6). Per-condition rates now
  use exact Clopper-Pearson intervals; 1/200 reads [0.02%, 2.75%] rather than
  [0, 1.5%]. Differences keep the paired bootstrap.
- **No pinned environment** (R3). Added `uv.lock`.

Two conditions were added so every arm is measured both ways: B and D with the
task stated, and a presentation-matched A (registered separately above).

## Reframing after the rule arm

*2026-09-19.* The headline changed from "full surfacing did not close the gap" to
underspecification. With the task and scoring rule stated, C reached 100/100 and
D 99/100, and requests for the decision rule fell from 174/200 to 2/100 in C. The
"single-agent ceiling" language is removed everywhere: A is a full-information
baseline, not an upper bound, since matched-prompt A and C both reach 100/100 and
a name-counting heuristic solves A's contexts 200/200.

B is the result that survived unchanged (0/100 with and without the rule) and now
leads the write-up.

## HiddenBench figures verified; PDF not committed

*2026-09-19.* The 30.1% and 80.7% figures were checked against arXiv:2505.11556v4
(SHA-256 `f8aa0dc11b590f398c58b9ab396c05c18f12c8d1fe6a842d6b6c78bb1ebc3842`) and
match its abstract. The PDF is **not** added to the repository: its arXiv licence
(nonexclusive-distrib/1.0) does not grant redistribution rights. It is cited by
arXiv version and checksum instead.

Their prompts were checked too (Appendix A.4): HiddenBench states the objective
and payoff to its models, so our underspecification finding is about our setup
and is not evidence about their numbers. Their correctness rests on elimination
logic and their headline metric is per-agent selection rate, so their figures are
not directly comparable to ours. `docs/results.md` says so explicitly.

The Stasser & Titus (1985) citation details remain **UNVERIFIED**: no copy of
that paper was consulted.
