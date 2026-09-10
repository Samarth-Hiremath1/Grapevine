# Results

Run `20260910T065248Z_primary`, commit `4311f6f2`, clean working tree.
Model `gpt-5.6-luna`, 200 hidden-profile tasks per condition, seeds 1000-1199,
identical across all four conditions. 3,600 API calls, no failures, no retries
exhausted. Total cost $0.7574, wall-clock 14 minutes 16 seconds.

## Headline

Splitting the information across three agents took accuracy from 85.5% to 0.5%.
Letting those agents talk recovered most of it, to 67.0%, and roughly a fifth of
that recovery came from explicitly telling them to share what they hold rather
than from discussion alone.

The part worth dwelling on is what the recovery does *not* fix. In the
instructed-sharing condition every required private fact was surfaced in all 200
episodes, and accuracy still sat 18.5 points below the single-agent ceiling.

## Table

| Condition | N | Accuracy | 95% CI | Decoy rate | Surfacing | Parse fails |
|---|---:|---:|---|---:|---:|---:|
| A. Full information (1 agent) | 200 | 85.5% | [80.5, 90.0] | 14.5% | n/a | 0 |
| B. Distributed, no communication | 200 | 0.5% | [0.0, 1.5] | 99.5% | n/a | 0 |
| C. Distributed, instructed sharing, 2 rounds | 200 | 67.0% | [60.5, 73.5] | 33.0% | 100.0% | 0 |
| D. Distributed, neutral prompt, 2 rounds | 200 | 53.0% | [46.0, 60.0] | 46.0% | 82.7% | 2 |

Chance is 25% (four options). Intervals are percentile bootstrap over episodes,
10,000 resamples. Conditions C and D are identical apart from the discussion
prompt; both use two rounds and the same aggregator.

Paired differences on the same task seeds:

| Comparison | Difference | 95% CI |
|---|---:|---|
| C − B (communication vs none) | +66.5 pts | [+60.0, +73.0] |
| D − B (neutral discussion vs none) | +52.5 pts | [+45.5, +59.5] |
| C − D (effect of the sharing instruction) | +14.0 pts | [+6.0, +22.5] |
| A − C (remaining gap to the ceiling) | +18.5 pts | [+12.0, +25.5] |

Condition B tie rate was **0.0%**: all three agents voted identically in all 200
episodes, so the pre-registered tie-break never fired. Accuracy with ties scored
incorrect is 0.5%, unchanged.

## Findings

**Distributing the information is close to fatal on its own.** Condition B
scored 0.5%, far below the 25% chance line. That is not because the task is
unsolvable — condition A solves it 85.5% of the time with the same facts. It is
because the shared facts every agent sees are constructed to favour one wrong
candidate, and agents reasoning from what they can see walk straight into it.
B picked exactly that candidate in 199 of 200 episodes.

**Every wrong answer, in every condition, was the decoy.** The
"other wrong option" rate is 0.000 across all four conditions. Not one episode
in 800 chose a wrong candidate that was not the engineered decoy. Because of
this, decoy rate here is essentially the complement of accuracy and adds no
independent signal; what it establishes is that failures are systematic rather
than noisy. Groups do not get confused and guess. They confidently pick the
option that common ground supports.

**Communication recovers most of the loss, and the instruction is part of it.**
Discussion alone (D) is worth +52.5 points over silence. Adding the explicit
instruction to share facts and ask for what is missing (C) is worth a further
+14.0 points [+6.0, +22.5], and raises the surfacing rate from 82.7% to 100%.
The interval on that difference excludes zero, so the instruction does something,
but discussion is doing the larger share of the work. This is why C is described
as *instructed* pooling everywhere in this repository: the headline recovery
number is not a property of multi-agent discussion in the abstract.

## Surfacing is not the bottleneck

This is the result that most changed how we read the rest.

In condition C, **all 200 of 200 episodes surfaced 100% of the required private
facts**. Elicitation, the failure the toolkit was originally built around, did
not occur at all. Accuracy was still 67.0%, which is 18.5 points below the
single-agent ceiling of 85.5%. Of the 66 C episodes that failed, 47 had full
surfacing *and* were solved correctly by condition A on the same task.

Condition D shows the same thing more weakly. Its episodes split into 85 with
full surfacing, which scored 61.2%, and 115 with partial surfacing, which scored
47.0%. Surfacing helps, and it is not sufficient.

Here is a representative failure, `hidden_profile-1006` from the primary run.
Gold answer Finley (6 supporting facts), decoy Devon (5 shared). All six Finley
facts reached the transcript:

> **r1 agent0:** I know these additional facts: the hiring committee meets on
> alternating Thursdays; Finley handled the largest incident of the last quarter
> calmly; the interview panel met in the third-floor conference room; and Finley
> led a cross-functional team of eight. Please share any other candidate-specific
> facts you have and the exact decision or ranking we need to produce.
>
> **r1 agent1:** I know these additional facts: Finley has deep
> distributed-systems experience, owns an open-source library with real adoption
> [...] What exact decision or ranking must we produce, and what evaluation
> criteria or constraints should we apply?
>
> **r1 agent2:** Finley designed the on-call rotation the team still uses,
> rewrote a flaky test suite to full reliability [...] What final output do we
> need — selection, ranking, or hiring recommendation — and what criteria or
> weighting should we apply?
>
> **r3 agent0 (aggregator):** `{"answer":"Devon"}`

Every fact needed to answer was on the table. What the agents kept asking for
was not information but a decision rule — "what criteria or weighting should we
apply". Given a transcript containing six reasons to prefer Finley and their own
context containing five reasons to prefer Devon, the aggregator chose Devon.

The same pattern appeared in the pilot (`hidden_profile-6`, seeds 0-19) and is
what prompted us to measure surfacing conditionally rather than only in
aggregate.

So the distributed penalty here decomposes into two parts. Getting the facts
into the conversation is one problem, and instructed discussion largely solves
it. Weighting the pooled evidence once it is there is a second problem, and
discussion does not solve it at all.

## What we are not claiming

- **This is not a replication of HiddenBench.** The ~30% versus 81% figures in
  that paper are prior work. Our task generator, model, prompts and scoring are
  different, and our communication conditions land well above 30%. The only
  claim shared with that literature is the qualitative one: distributing
  information hurts.
- **Not a claim about multi-agent systems in general.** One model, one task
  family, one team size, one round budget, four options.
- **No statistical test was run.** Where intervals exclude zero we say so; we do
  not use the word "significant".

## Limitations

- **Temperature was not controlled as registered.** `gpt-5.6-luna` rejects an
  explicit temperature, so the pre-registered 0.7 discussion / 0.0 answer
  settings could not be applied. Every call ran at the model default of 1.0.
  This is uniform across all four conditions and so does not confound the
  comparison, but answer turns are not deterministic and within-condition
  variance is higher than planned. The manifest records
  `temperature_honoured: false` and `effective_temperature: 1.0`.
- **The decision rule is implicit.** Nothing in the task states that the best
  candidate is the one with the most supporting facts. Condition A may benefit
  from seeing the facts as one tidy list, which makes counting salient in a way
  a transcript does not. Part of the A − C gap could be presentation rather than
  coordination.
- **The margin is one fact by construction.** The correct candidate wins by
  exactly one supporting fact, which is what makes every private fact necessary.
  It also means the task demands precise counting rather than holistic judgement.
- **Surfacing is a string-match proxy.** It detects verbatim to near-verbatim
  sharing, which the C prompt explicitly asks for. It will miss heavy paraphrase
  and can be fooled by negation. We read transcripts by hand to confirm the 100%
  figure in C is real rather than a matching artefact.
- **Condition B's interval is nearly degenerate**, at 1 correct in 200.
- **C and D necessarily differ in system prompt**, which is the manipulation, but
  it also means they differ in prompt length and wording, not only in the
  presence of an instruction.
- **Single model, single run.** No seed-level replication of the whole
  experiment.

## Next experiment

Make the decision rule explicit and re-run C. If the aggregator is told that the
candidate with the most supporting facts should win, and the A − C gap closes,
then the residual penalty is about applying a weighting rule to a transcript. If
the gap persists, the problem is integrating evidence that arrives as dialogue
rather than as a list, which is the more interesting result and points at what
post-training would need to fix.

This is a cheap experiment: one extra condition, roughly $0.35 at this scale.
