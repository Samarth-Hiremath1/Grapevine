# Results

Run `20260910T065248Z_primary`, commit `4311f6f2`, clean working tree.
Model `gpt-5.6-luna`, 200 hidden-profile tasks per condition, seeds 1000-1199,
identical across all four conditions. 3,600 API calls, no failures, no retries
exhausted. Total cost $0.7574, wall-clock 14 minutes 16 seconds.

Two things to read before the numbers. First, **no model in any condition was
shown the task's question or told how answers are scored.** Second, **the 200
tasks are 200 permutations of one 12-sentence template**, not 200 independent
problems. Both are explained under Limitations, and both limit what the results
below can support.

## Headline

Splitting the information across three agents took accuracy from 85.5% to 0.5%.
Letting those agents talk recovered most of it, to 67.0%, and roughly a fifth of
that recovery came from explicitly telling them to share what they hold rather
than from discussion alone.

In the instructed-sharing condition every required private fact was surfaced in
all 200 episodes, and accuracy still sat 18.5 points below the single-agent
ceiling. Why is not settled yet; see "Full surfacing did not close the gap".

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
unsolvable — condition A reaches 85.5% with the same facts. Each B agent sees
the shared facts, which are built to favour one wrong candidate, plus two private
facts for the right one, and picks the candidate its own facts support most.
By construction that is the decoy. B chose it in 199 of 200 episodes.

**Every wrong answer, in every condition, was the decoy.** The
"other wrong option" rate is 0.000 across all four conditions. Not one of the
800 episodes landed on a wrong candidate other than the decoy. Decoy rate is
therefore close to the complement of accuracy here and adds little independent
signal. What it does establish is that failures are systematic: groups do not
guess, they pick the option the most visible evidence supports.

**Communication recovers most of the loss, and the instruction is part of it.**
Discussion alone (D) is worth +52.5 points over silence. Adding the explicit
instruction to share facts and ask for what is missing (C) is worth a further
+14.0 points [+6.0, +22.5] and raises the surfacing rate from 82.7% to 100%.
The interval on that difference excludes zero, so the instruction does
something, but discussion does the larger share. C is described as *instructed*
pooling everywhere in this repository for that reason.

## Full surfacing did not close the gap

In condition C, **all 200 of 200 episodes surfaced 100% of the required private
facts**, and accuracy was 67.0%, 18.5 points below condition A. Of the 66 C
episodes that failed, 47 had full surfacing *and* were solved by condition A on
the same task. Condition D shows the same shape more weakly: its 85 fully
surfaced episodes scored 61.2%, its 115 partially surfaced episodes 47.0%.
Surfacing helps, and it was not enough.

A representative failure, `hidden_profile-1006` from the primary run. Gold
answer Finley (6 supporting facts), decoy Devon (5 shared). All six Finley facts
reached the transcript:

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

The same pattern first showed up in the pilot (`hidden_profile-6`).

There are two readings of this, and the current data cannot tell them apart.

The first is an integration failure: the aggregator has the evidence in front of
it and weighs it badly, favouring the five reasons in its own context over the
six in the transcript.

The second is that the models were never told what they were being graded on.
The agents above are asking for exactly the thing that was withheld — what
decision to produce and what criteria to apply. That was not an unusual
transcript. By a keyword match for requests about criteria, weighting, a
ranking, or the decision to produce, at least one agent asked in 174 of 200
condition C episodes and 133 of 200 condition D episodes. Asking was not a
marker of failure: C scored 69.0% in the 174 episodes where someone asked and
53.8% in the 26 where no one did. The keyword match is rough and will miss some
phrasings.

Condition A saw no question and no rule either and still scored 85.5%, which
argues against underspecification being the whole explanation. But A receives
every fact as a single list, where counting mentions is the obvious move, while
C's aggregator receives the same facts spread across a dialogue plus its own
context. The direct test is to state the goal and the scoring rule and run A and
C again on the same seeds. Until that is done, "integration failure" is a
hypothesis, not a finding.

## What we are not claiming

- **This is not a replication of HiddenBench.** The ~30% versus 81% figures in
  that paper are prior work. Our task generator, model, prompts and scoring are
  different, and our communication conditions land well above 30%. The only
  claim shared with that literature is the qualitative one: distributing
  information hurts.
- **Not a claim that agents fail at integration.** See the section above.
- **Not a claim about multi-agent systems in general.** One model, one task
  template, one team size, one round budget, four options.
- **No statistical test was run.** Where intervals exclude zero we say so; we do
  not use the word "significant".

## Limitations

- **No model saw the question or the scoring rule.** Each generated task carries
  a question ("who is the strongest candidate?"), but no prompt in any of the
  four conditions includes it, and nothing anywhere tells the models that the
  correct answer is the candidate with the most supporting facts. Models saw the
  facts, the list of options, and an instruction to choose the single best one.
  The only task-like cues were the header "Facts known to the whole committee"
  (conditions B, C and D, not A) and distractor sentences that happen to mention
  a hiring committee or the role, present in 188 of 200 primary tasks. Every
  accuracy figure in this document measures agreement with a rule the models had
  to infer.
- **N=200 is 200 permutations of one template.** The strength-fact pool has
  exactly 12 sentences and this configuration uses exactly 12 per task, so all
  200 tasks contain the same 12 strength sentences. Tasks differ in which 4 of
  8 names are the options (66 distinct name sets across the 200), which
  candidate is correct and which is the decoy, which sentences attach to which
  candidate, which 4 of 8 distractors appear, and ordering. The bootstrap
  intervals describe variation over those permutations, not over task content,
  and a model could in principle pick up regularities of the one template.
- **Temperature was not controlled as registered.** `gpt-5.6-luna` rejects an
  explicit temperature, so the pre-registered 0.7 discussion / 0.0 answer
  settings could not be applied. Every call ran at the model default of 1.0.
  This is uniform across all four conditions and so does not confound the
  comparison, but answer turns are not deterministic and within-condition
  variance is higher than planned. The manifest records
  `temperature_honoured: false` and `effective_temperature: 1.0`.
- **The margin is one fact by construction.** The correct candidate wins by
  exactly one supporting fact, which is what makes every private fact necessary.
  It also means the task demands precise counting rather than holistic judgement.
- **Surfacing is a string-match proxy.** It detects verbatim to near-verbatim
  sharing, which the C prompt explicitly asks for. It will miss heavy paraphrase
  and can be fooled by negation. Transcripts were read by hand to confirm the
  100% figure in C is real rather than a matching artefact.
- **Condition B's interval is nearly degenerate**, at 1 correct in 200.
- **C and D necessarily differ in system prompt**, which is the manipulation, but
  it also means they differ in prompt length and wording, not only in the
  presence of an instruction.
- **Single model, single run.** No seed-level replication of the whole
  experiment.

## Next experiment

State the goal and the scoring rule in the prompt and re-run conditions A and C
on the same seeds. If C's decoy rate drops sharply, the A − C gap was mostly
underspecification. If it holds, the aggregator fails to weigh pooled evidence
even when it knows exactly what it is being asked, which is the stronger claim
and the one that would justify a training intervention.

Separately, the strength-fact pool should be enlarged so tasks draw different
content, and the four-condition result replicated on it.
