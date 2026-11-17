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

## `experiments/baseline/` removed

*2026-09-22, before merging the audit branch.* Deleted the early two-condition
baseline script and its `results.md`. It was superseded by the four-condition
ablation in `grapevine/experiments/run.py`, was never run against a live API, and
recorded no numbers. A "superseded" header on a file called `results.md` is still
an invitation to mistake it for current results, which is the only reason to
delete rather than keep it.

The last commit containing it is `4cde7e8`; recover it with
`git show 4cde7e8:experiments/baseline/run_baseline.py`. Nothing outside the
directory referenced it, and no reported number came from it. The ruff invocation
in CI and in `README.md` no longer names the now-absent `experiments` path.

## Skip the `verifiers` adapter in v0.2

*2026-11-15, during v0.2 planning.* The plan was to expose `hidden_profile_v2`
through `verifiers` as a taskset plus a multi-agent `Env`, but only if that
turned out to be a small, clean wrapper. It does not.

The v1 API documented at `docs.primeintellect.ai` is a good fit on paper: an
`Env` subclass with `async def run(self, task, agents)`, one `vf.AgentConfig`
per role so each agent can have its own model, and `agents.<role>.trainable =
False` to freeze a helper role. That is close to what Grapevine's conditions
need.

The problem is availability. The latest release of `verifiers` on PyPI is
0.4.1, which is a different library generation from the one the docs describe.
The documented install is `git clone PrimeIntellect-ai/verifiers && uv sync`;
the local commands (`vf-run`, `vf-validate`) run from inside that clone; full
evaluations go through `prime-rl`; and Harbor tasksets require Python 3.12+
while this project supports 3.11+. The minimal taskset package layout is not
specified on the pages that describe building one.

Taking that on means a dependency `uv.lock` cannot pin, a second CLI toolchain
in CI, and a Python floor raised for a feature nobody has asked for yet. It
also cuts against the rule that external APIs are pinned to a version actually
read: a git `main` is not a version.

Decision: no adapter in v0.2. It goes in the README roadmap as "`verifiers` v1
multi-agent adapter (per-role `AgentConfig`, non-trainable helper roles)",
without a date, and is revisited when v1 is released to PyPI. TRL GRPO remains
the only training integration, which is enough for what Step 5 claims.

## PyPI distribution name `grapevine-mas`

*2026-11-15.* The import name `grapevine` is what the code, the docs and the
committed runs already use, and changing it would break every path in the
repository for no gain. But `grapevine` on PyPI is taken by an unrelated
project, so the distribution name has to differ.

`grapevine-mas` (multi-agent systems) was checked against the PyPI JSON API on
2026-11-15: both `grapevine-mas` and `grapevine_mas` return HTTP 404, so the
name is free under PyPI's normalisation. `pip install grapevine-mas` then
`import grapevine` is a common and well-understood split.

Nothing is published in v0.2. The release workflow is prepared and left
untriggered.

## Pre-register the eval run; decide on spending later

*2026-11-15.* The planned eval run wanted three inexpensive current models from
different providers. Only `OPENAI_API_KEY` is set in this environment, so that
design cannot be executed as written.

Rather than quietly narrowing it to one provider now, or dropping it, the
pre-registration and the analysis script are written during Steps 2-5 — both
cost nothing and neither commits to a run. Whether the run happens, on which
models, and under what budget is decided once `hidden_profile_v2` exists and
there is something worth measuring. Until a run is committed, every document
says `not run`.

## Keep `split_evidence` as a negative example rather than fixing or deleting it

*2026-11-15, Step 4.* The plan said to fix the family so it passes its audit or
delete it, whichever was cheaper. Deleting is cheaper — fixing means redesigning
the hop chain so the terminal station is identified by a property rather than
named, which is task-design work the release does not need now that
`hidden_profile_v2` fills the environment slot.

I kept it anyway, and this is the reason. `split_evidence` is the only
environment in this repository that leaked its answer *for real*: it was
registered, nearly used for condition B, and caught by hand before any run
(`docs/decisions.md`, 2026-09-08). The leak check now reproduces that hand count
exactly — the gold answer is readable from a single agent's view in 100 of 100
generated tasks — which is the strongest available evidence that the check works
on something other than a fixture I planted myself. A synthetic flawed
environment can always be accused of being built to be caught.

The risk of keeping it is that someone runs it. That is guarded four ways: it is
in `UNREGISTERED` so nothing resolving a family by name hands one out, the CLI
refuses it with the reason, the experiment runner refuses it at config-load
time, and `grapevine audit split_evidence` reports FAIL with the finding. A test
asserts the leak itself, so re-registering it without a fix fails.

If this looks like dodging the instruction rather than answering it, delete the
module, its adapter entry and its tests; nothing else depends on it.

## Self-play without `rollout_func`

*2026-11-15, Step 5.* The plan said shared-policy self-play would go through
TRL's experimental `rollout_func`, the only hook that puts gradient on every
turn of an episode. I did not do that.

`rollout_func` makes the caller responsible for generation, token ids and
log-probabilities for every turn, which is a second generation path to keep
correct against TRL's own, and it is marked experimental in the version pinned.
For a release whose RL claim is "wired and smoke-tested", that is a lot of
surface for no result.

Instead, self-play uses the same plain reward function as the frozen-partner
mode. Every agent's opening turn is a dataset row; the trainer generates it with
gradient, and the rest of the episode — every other agent and every later turn
— is generated by the *current* policy without gradient. One model plays every
agent, every role is trained, and the manifest records `partners_frozen:
false`. What is lost is gradient on turns after the opening; `docs/rl.md` says
so and lists `rollout_func` under what is deliberately not here.

## Linux CI uses CPU torch from the lock

*2026-11-15, Step 5.* PyPI's Linux torch wheel is the CUDA build, several
gigabytes. The old CI side-stepped the lock with `uv pip install torch
--index-url .../cpu`, so the tested environment was not the locked one. Now
`pyproject.toml` routes torch to PyTorch's CPU index on Linux only, via
`[tool.uv.sources]`, and a lock-time constraint keeps torch on 2.14 everywhere.
The CPU index carries 2.14.1 rather than 2.14.0, so Linux CI runs 2.14.1+cpu
where macOS runs 2.14.0 — a patch-level difference, noted rather than chased.
None of this touches the published package's dependencies.

## Docs on MkDocs and Material, pinned, despite Material's end of life

*2026-11-16, Step 7.* The plan named MkDocs with `--strict`. Material for
MkDocs' PyPI page, read on 2026-11-16, says it reaches end of life on
2027-05-05, with critical fixes until then, and names Zensical as its
maintained successor. The site uses MkDocs 1.6.1, Material 9.8.1,
mkdocstrings 1.0.8 and mkdocstrings-python 2.0.11, pinned exactly in the `docs`
extra. A migration is a roadmap item, not v0.2 work: the site is a plain
configuration with no custom theme code, so it should move with little effort.

`docs/results.md` is excluded from the site, because its figure lives in
`studies/` outside `docs/` and a strict build refuses the link. It is read on
GitHub, where the relative path resolves (it had been broken since Step 2 moved
the figure; fixed now). Anchor validation is raised from `info` to `warn`, so a
dead in-page link also fails the build.

## Actions pinned by commit SHA

*2026-11-16, Step 7.* Every action in `.github/workflows/` is pinned to the
commit its release tag pointed to when resolved through the GitHub API on
2026-11-16, with the tag in a comment: `actions/checkout` v7.0.1,
`astral-sh/setup-uv` v10.3.3 (the SHA matches its README),
`actions/upload-artifact` v7.0.2, `actions/download-artifact` v8.0.2,
`pypa/gh-action-pypi-publish` v1.14.3. A tag can be moved; a SHA cannot.

## The release workflow publishes nothing until Samarth sets it up

*2026-11-16, Step 7.* `release.yml` runs only on a `v*` tag. It checks the tag
against the package version, runs the tests, builds, runs `twine check
--strict`, and hands the files to a separate publish job that has
`id-token: write` and nothing else. Publishing uses PyPI trusted publishing, so
no token exists to leak. It needs two things that cannot be done from the
repository and are left to Samarth: a GitHub environment `pypi`, and a trusted
publisher on PyPI for `grapevine-mas`. Without them the publish job fails before
uploading anything.

Not handled: the README is the PyPI long description, and its relative links
(`docs/...`, `studies/...`) will not resolve on PyPI. Rewriting them to absolute
URLs needs a target branch that has the files, which `main` does not yet.
Recorded here so it is decided before the first upload rather than discovered
after it.

## A clean environment fails about one audit in twenty

*2026-11-16, Step 7.* Writing `examples/02_write_an_environment.py` surfaced
that it passed on its eval seeds and failed `shortcuts` on seeds 9000–9199.
Measured on it and on the test control over 40 disjoint seed ranges each: 2
failing audits in 40 for both, all on `shortcuts`
(`studies/battery_calibration/README.md`). That is the 5% per-check false-alarm
rate the Bonferroni correction allows, reached in one check because equalised
name counts leave the content-blind solvers breaking exact ties at random.

Documented in `docs/audit-battery.md` and in the example. Not changed in the
battery: scoring a tie by its expected value rather than a random draw would
remove most of this noise, but it changes what every committed card says, and
that is a decision for Samarth rather than a side effect of packaging.

## Extend the battery; do not add a tolerance to `solo_solvability`

*2026-11-16, after the external review.* Samarth chose to extend the battery
for the review's M1 (names-only shortcut) and M2 (partial leaks) rather than
only document them, and to rebuild the clean control and the example so they
pass "without weakening thresholds to force a pass".

Building the rebuilt control surfaced an architectural limit: when the answer is
the argmax of summed evidence, some single view always carries information about
it, so no design can make every single-view solver sit at chance
(`docs/audit-battery.md`, "Why a pass is a bound"). The tightest construction
leaves an exact Bayes-optimal single-view accuracy of 29.8% against 25%, and the
strengthened battery sees that on 17 of 40 seed ranges.

Decision: keep `solo_solvability`'s threshold as it was -- any probe
significantly above chance fails -- and say what that means, rather than add a
tolerance that would make the control pass. A tolerance is the principled fix
(compare the single-view advantage with what pooling adds), but its size is a
judgement about what counts as "distributed enough", and adopting one changes
what a pass means for every environment. Left open for Samarth.

Scoring tie-breaks by expectation is not a threshold change: it leaves the null
rate at its nominal level, gives an uninformative solver exactly chance with no
variance, and loses no power on a real signal. It removed most of the old
one-in-twenty false alarms on `shortcuts`.

The control's mentions per option per agent (6) was chosen for prompt size
before the strengthened audit was run on it, and is not tuned to its verdict.
