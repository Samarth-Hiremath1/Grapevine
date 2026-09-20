# Results

Model `gpt-5.6-luna`, procedurally generated hidden-profile tasks, three agents,
four options (chance 25%). Every number below is recomputed from committed runs
by `python -m grapevine.experiments.report_tables`, which writes
`docs/figures/results_tables.json`. Intervals on single conditions are exact
Clopper-Pearson 95% intervals; intervals on differences are paired bootstrap 95%
intervals over the same tasks.

![Accuracy by condition, with and without the task stated](figures/accuracy_by_condition.png)

## What holds

**Splitting the facts across agents who cannot talk is catastrophic, and stating
the task does not help.** Condition B, where three agents each answer from their
own facts and vote, scored 1/200 (0.5%, [0.0%, 2.8%]) with the task unstated and
0/100 (0.0%, [0.0%, 3.6%]) with the question and scoring rule stated. Every agent
sees the shared facts, which put the decoy ahead 5 to 2 in its own view, so every
agent picks the decoy and the vote is unanimous (tie rate 0.0% in both arms).
This is the one result the rest of the work could not move.

**Communication recovers the loss.** With the task unstated, instructed
discussion (C) scored 134/200 (67.0%) and neutral discussion (D) 111/200 (55.5%),
against 1/200 for B. With the task stated, both reached the full-information
condition: C 100/100, D 99/100, and A with a matched prompt 100/100.

## What we got wrong, and how we found it

The first write-up of this experiment reported that the communicating team
surfaced every required fact in 200 of 200 episodes and still finished 18.5
points below the single agent with all the facts. We read that as a failure to
integrate pooled evidence. It was not. It was underspecification.

No prompt in the original four conditions contained the task's question, and
nothing told the models how answers were scored (one point per supporting fact,
most points wins). The generator wrote a question into every task, but the
rollout engine only copied it into the log. This was found by reading the
generator against the prompts after the first write-up, prompted by transcripts
in which agents kept asking for the decision rule. In condition C an agent asked
for criteria, weighting, a ranking or the decision to produce in 174 of 200
episodes (keyword match, see Limitations). One example, `hidden_profile-1006`,
where all six facts supporting the correct candidate were shared:

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

Devon was the decoy. The same task with the question and rule stated:

> **r1 agent0:** I know two relevant facts about Finley: Finley handled the
> largest incident of the last quarter calmly, and led a cross-functional team of
> eight. Please share any additional candidate-strength facts you have [...]
>
> **r3 agent0 (aggregator):** `{"answer":"Finley"}`

We then ran a registered follow-up (the "rule arm") that prepends the question
and the scoring rule to every prompt and changes nothing else. On the same 100
tasks, C went from 68/100 to 100/100, and requests for criteria fell from 174 of
200 episodes to 2 of 100.

**The methodological point is the transferable result:** an evaluation that does
not tell agents what they are being scored on can produce a clean-looking
coordination failure that disappears when the objective is stated. Surfacing
metrics will not catch it, because the facts are being shared; the agents just
do not know what to do with them.

Both errors were found the same way, by an adversarial audit of our own
pipeline. The assumption ledger (`docs/assumptions.md`) was written and committed
*before* any of its checks ran, so the list was not shaped by what turned out to
be convenient to verify; the findings are in `docs/audit.md`.

A second error followed from the first. With the task stated, C (100/100) and D
(99/100) scored above A (96/100), which read as distributed teams beating a
single agent with every fact. An audit of our own pipeline found A's prompt
differed from B-D in presentation as well as information: a flat list with no
shared/private headers, a different system prompt, and a template line reading
"Full team discussion: (you have all information; no discussion needed)". A
registered rerun giving one agent every fact in B-D's layout scored 100/100. The
apparent advantage was the prompt. With the task stated, every communicating
condition matches full information; none beats it.

## Requests for the decision rule collapse when it is given

The clearest direct evidence for the underspecification reading is not an
accuracy number. It is that the agents stop asking what they are supposed to do.

| Condition | Episodes where an agent asked for criteria, weighting, a ranking or the decision to produce |
|---|---|
| C, task not stated | 174 / 200 |
| C, task stated | 2 / 100 |
| D, task not stated | 136 / 200 |
| D, task stated | 1 / 100 |

The agents were not confused about the facts; they shared those. They were
asking for the objective, and once it was supplied the requests stopped and the
answers became correct. This is a keyword match (criteria, weighting, rubric,
ranking, "what decision", "what output") and was not hand-validated, so treat the
counts as approximate and the direction as the result.

## The position effect disappears when the task is stated

With the task unstated, accuracy falls as the correct answer moves later in the
option list. With it stated, the effect is gone.

| Condition | Correct at option position 0 / 1 / 2 / 3 |
|---|---|
| A, task not stated | 49/54, 40/46, 48/55, 34/45 (91%, 87%, 87%, 76%) |
| C, task not stated | 44/54, 30/46, 35/55, 25/45 (81%, 65%, 64%, 56%) |
| D, task not stated | 36/54, 26/46, 27/55, 22/45 (67%, 57%, 49%, 49%) |
| C, task stated | 28/28, 24/24, 22/22, 26/26 |
| D, task stated | 28/28, 24/24, 22/22, 25/26 |
| A matched, task stated | 28/28, 24/24, 22/22, 26/26 |

Correct positions are balanced across the 200 tasks (54/46/55/45), so condition
averages are not biased by this; it adds variance, and it is a second symptom of
models falling back on position when they do not know what they are optimising.
It was not formally tested.

## Table

| Condition | Task not stated (seeds 1000-1199) | Task not stated (seeds 1000-1099) | Task and rule stated (seeds 1000-1099) |
|---|---|---|---|
| **A** one agent, all facts | 171/200 · 85.5% [79.8, 90.1] | 83/100 · 83.0% [74.2, 89.8] | original prompt: 96/100 · 96.0% [90.1, 98.9]<br>matched prompt: 100/100 · 100% [96.4, 100] |
| **B** three agents, no talking | 1/200 · 0.5% [0.0, 2.8] | 0/100 · 0.0% [0.0, 3.6] | 0/100 · 0.0% [0.0, 3.6] |
| **C** three agents, told to share | 134/200 · 67.0% [60.0, 73.5] | 68/100 · 68.0% [57.9, 77.0] | 100/100 · 100% [96.4, 100] |
| **D** three agents, neutral prompt | 111/200 · 55.5% [48.3, 62.5] | 53/100 · 53.0% [42.8, 63.1] | 99/100 · 99.0% [94.6, 100] |

C and D discuss for 2 rounds; a designated aggregator then answers. The task-not-
stated runs used 200 tasks and the rule arm 100, so the middle column restricts
the first to the rule arm's tasks for a like-for-like comparison. Where A is
compared with the other conditions in the task-not-stated arm, it is the
original A; no matched-prompt A was run without the rule.

Effect of stating the task, same 100 tasks, paired:

| Condition | Change in accuracy |
|---|---|
| A (original prompt) | +13 pts [+6, +20] |
| A (matched prompt), vs original A without the rule | +17 pts [+10, +25] |
| B | 0 pts (0/100 both) |
| C | +32 pts [+23, +41] |
| D | +46 pts [+36, +56] |

Differences between conditions, paired over the same tasks:

| Comparison | Task not stated (n=200) | Task stated (n=100) |
|---|---|---|
| C − B | +66.5 [+60.0, +73.0] | +100 (100/100 vs 0/100) |
| D − B | +55.0 [+48.0, +62.0] | +99 [+97, +100] |
| C − D | +11.5 [+3.0, +20.0] | +1.0 [0.0, +3.0] |
| A − C | +18.5 [+12.0, +25.5] (original A) | −4.0 [−8.0, −1.0] (original A) |
| A (matched) − C | not run | 0 (100/100 both) |

When a difference is 100/100 against 0/100, or 100/100 against 100/100, the
paired bootstrap interval has zero width and says nothing; the per-condition
exact intervals above are the uncertainty to use.

**The sharing instruction mattered mostly because the task was
underspecified.** Telling agents to share their facts and ask for what they were
missing (C versus D) was worth 11.5 points [+3.0, +20.0] when the task was
unstated and 1.0 point [0.0, +3.0] once it was stated. Surfacing moved the same
way: D surfaced 81.4% of required facts without the rule and 88.0% with it; C was
at 100% in both.

**Every wrong answer was the decoy.** In every condition in the table, no parsed
wrong answer ever landed on an option other than the decoy. The
decoy rate is therefore the complement of accuracy minus parse failures, and is
not reported separately.

## Relation to HiddenBench

**This is a finding about our own task construction, not a criticism of
HiddenBench. HiddenBench states the objective to its models; we did not.**

HiddenBench (Li, Naito and Shirado, arXiv:2505.11556v4, ICML 2026) reports
**30.1%** accuracy for multi-agent LLM groups under distributed information
against **80.7%** for single agents given complete information. Both were checked
against the paper's abstract (PDF SHA-256
`f8aa0dc11b590f398c58b9ab396c05c18f12c8d1fe6a842d6b6c78bb1ebc3842`). The PDF is
not in this repository; its arXiv licence does not permit redistribution.

Three differences mean our numbers cannot be read against theirs:

1. **They tell the models the task; we did not.** Their discussion system prompt
   begins with the task description (Appendix A.4). The published example states
   what must be decided, lists the options, says "There is only one correct
   evacuation location", and gives the payoff for choosing it. Our prompts
   contained no question and no scoring rule. The failure we first reported was
   produced by that omission, which is ours alone.
2. **Correctness is established differently.** HiddenBench tasks are built so
   that the answer follows by elimination: "every other option should clash with
   at least one fact". Ours rest on a counting convention - most supporting facts
   wins - that we never stated to the models and that cannot be derived from the
   facts themselves.
3. **The metric is different.** HiddenBench's default accuracy is the proportion
   of individual agents choosing the correct option after discussion. Every
   number here is a single group answer, from a designated aggregator (C, D) or a
   majority vote (B). The 30.1% and 80.7% figures are therefore not directly
   comparable to any number in this document.

Two further differences worth knowing: HiddenBench agents "are not informed
whether their information differs from that of others", whereas ours are told
"Each teammate holds different private information, and no one can answer alone";
and HiddenBench spans 65 tasks and 15 models against our one template and one
model.

What the two share is the qualitative observation that splitting information
across agents hurts, and that failures concentrate on the option the shared
evidence favours.

### The lesson we take from this

An evaluation can withhold its objective without its authors noticing, and the
resulting gap can look exactly like a coordination failure: the agents share
every fact, the team still answers wrong, and a surfacing metric shows 100%. Ours
did. The check that catches it is cheap - state the objective and rerun - and it
is worth doing before attributing a gap to coordination. That is a warning about
building evaluations, this one very much included.

## Limitations

- **The task has a trivial shortcut.** Every strength fact begins with the
  candidate's name, so counting name mentions identifies the correct answer in
  200 of 200 condition-A contexts. The experiment measures whether the model
  counts, and whether it knows it should; it does not test reasoning over fact
  content.
- **The 200 tasks are one puzzle.** All 200 share the support pattern (6, 5, 1,
  0): correct option 6 facts, decoy 5, one other option 1, one 0. All use the
  same 12 strength sentences. They differ in names (66 of 70 possible name sets),
  which sentence goes with which name, which 4 of 8 filler sentences appear, and
  order. Intervals describe variation over those permutations only.
- **The rule arm is N=100 against N=200** for the task-not-stated runs. Every
  rule-arm comparison uses the matched 100 tasks (seeds 1000-1099).
- **Accuracy depends on where the correct answer sits in the option list**, when
  the task is unstated. By option position 0/1/2/3: A 49/54, 40/46, 48/55,
  34/45 (91%, 87%, 87%, 76%); C 44/54, 30/46, 35/55, 25/45 (81%, 65%, 64%, 56%);
  D 36/54, 26/46, 27/55, 22/45 (67%, 57%, 49%, 49%). Correct positions are
  balanced across the 200 tasks (54/46/55/45), so condition averages are not
  biased by it. With the task stated the effect disappears: C, D and matched A
  are 100% in every position except one D error at position 3.
- **The surfacing metric misses about one genuine surfacing in seven.** Against
  40 hand-labelled (fact, message) pairs from the task-not-stated C and D
  transcripts, it has precision 1.00 (20/20) and recall about 0.86 (weighted by
  how often the metric fires; 8 of 20 pairs it scored as not surfaced were
  surfaced in paraphrase). It never credits a fact that was not shared, so C's
  100% is not an overcount; D's figures are undercounts. Only C's prompt asks
  agents to state facts verbatim, and the metric rewards verbatim wording, so part
  of the C-versus-D surfacing gap is the metric. One labeller. Labels:
  `docs/audit_surfacing_labels.json`.
- **"Asked for criteria" is a keyword match** on words such as criteria,
  weighting, ranking and "what decision". It was not validated by hand.
- **Condition A's original prompt differs from B-D in presentation.** This is
  why the matched-prompt A exists; it was run only with the task stated. The
  task-not-stated comparisons with A use the original prompt.
- **The aggregator is not a typical agent.** Four filler sentences are dealt
  round-robin to three agents, so agent 0 always holds 2 and the others 1 (mean
  context 622 against 565 characters). Agent 0 is always the aggregator, and its
  own private facts appear in its final prompt twice (its context and the
  transcript). Not measured for effect.
- **Temperature was stuck at 1.0.** `gpt-5.6-luna` rejects an explicit
  temperature, so the registered 0.7/0.0 settings were never applied. The setting
  is uniform across conditions, but runs are not bit-reproducible: rerunning the
  documented command regenerates the same tasks (0 of 200 differ), not the same
  answers.
- **Condition D had 4 parse failures (2 before the aggregator fix), all empty
  responses.** They came from episodes using roughly 1,100-1,300 completion
  tokens. The likely cause is hidden reasoning tokens exhausting the 400-token
  output cap, which for this model family includes reasoning. That is probable,
  not confirmed: usage is logged per episode, not per call.
- **Condition D was rerun.** The original D run sent the instructed system
  prompt at the aggregation step. It was rerun with the neutral prompt
  throughout: 106/200 → 111/200, a change of +2.5 points [−5.5, +11.0]. Only the
  rerun is reported; the original is kept in `runs/20260910T065248Z_primary/`.
- **One model, one task family, one team size, one round budget, four options.**

## Cost

All committed runs, including pilots: $1.5322. The audit reruns (fixed D, B and
D with the rule, matched A) cost $0.5144 of that.
