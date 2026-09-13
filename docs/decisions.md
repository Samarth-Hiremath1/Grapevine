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
