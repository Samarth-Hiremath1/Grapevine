# Methodology

How the coordination experiment is set up and scored. Parts marked *registered*
were written down and committed before the data they describe was collected.
Later changes are dated in `docs/decisions.md`.

## Task generation

Tasks come from `grapevine/envs/hidden_profile.py`: a hiring decision over 4
candidates, so chance is 25%. A candidate's support is its number of supporting
facts, and the correct candidate has the most once every fact is pooled.

- **Shared facts** go to every agent and give one wrong candidate, the *decoy*, a
  strict lead. None supports the correct candidate.
- **Private facts** are split evenly across agents and all support the correct
  candidate.
- **Filler facts** carry no support, split between the shared block and the
  private contexts.

The decoy receives one fewer supporting fact than the correct candidate's total
private support. Three properties follow: on shared facts alone the decoy leads;
with everything pooled the correct candidate leads by exactly one; removing any
single private fact removes that lead. `tests/test_hidden_profile.py` asserts all
three, and the audit rechecked them on every seed used (0 violations in 200).

The configuration used throughout: 3 agents, 6 shared facts, 2 private facts per
agent, 4 filler facts, 4 options. At that setting every task has the same support
pattern (correct 6, decoy 5, another candidate 1, the last 0) and draws on the
same 12 strength sentences; tasks differ in which names are options, which
sentence attaches to which name, which filler appears, and ordering. Generation
is deterministic in the seed.

### Why `split_evidence` is not used

The second family in `grapevine/envs/` ends its chain with a fact naming the
answer, so one agent holds it verbatim (100 of 100 sampled tasks). An agent in
the no-communication condition could then answer without pooling, so the runner
rejects that family.

## Information assignment

Agent *i* receives the shared block plus its own private facts and nothing else.
`tests/test_no_communication.py` asserts no agent's prompt contains another
agent's private facts; the audit found 0 leaks over 200 seeds x 3 agents. Before
the experiment, over 100 tasks: no required private fact appeared in the shared
block, the full-information context contained every required fact, and no single
agent's own facts favoured the correct candidate.

## Conditions

Conditions within a run share task seeds, so comparisons are paired. Comparisons
across runs pair episodes by task id (`grapevine.experiments.compare`).

**A - `full_info`.** One agent receives every fact and answers directly. This is
a full-information baseline, not an upper bound: with the task stated, the
communicating conditions matched it. A's original prompt differs from B-D in
presentation as well as information; the matched variant below controls for that.

**B - `no_communication`.** Each of the 3 agents answers from its own context.
There is no channel of any kind. The group answer is the majority vote.

**C - `communication` (instructed).** The same 3 agents exchange messages for 2
rounds; agent 0 then answers, seeing its own context and the transcript. The
system prompt tells agents to share their facts and ask for what they lack.

**D - `communication_neutral`.** Identical to C except that the system and turn
prompts do not tell agents to share or ask, on every call including aggregation.
The first D run sent C's instructed system prompt at the aggregation step; it was
rerun after that fix and only the rerun is reported.

B and C differ in whether agents can talk, C and D in whether they are told to
pool, A and C in whether the information is distributed at all.

### Rule arm (registered 2026-09-12; extended to B and D 2026-09-18)

No prompt in A-D contains the task's question or states how answers are scored.
The rule arm prepends the question and the scoring rule (`TASK_STATEMENT`, below)
to every prompt of a condition and changes nothing else. It covers all four
conditions on seeds 1000-1099 (N=100), the first half of the task-not-stated
seeds, as `full_info_rule`, `no_communication_rule`, `communication_rule` and
`communication_neutral_rule`. A and C were registered and run first; B and D were
added after the audit so every condition is measured both ways.

Registered reading: the quantity of interest is the change in the A - C gap,
since A also lacked the rule. If the gap closes and C's decoy rate falls sharply,
the gap was underspecification. If both hold, the aggregator fails to use pooled
evidence even when told the rule.

### Presentation-matched A (registered 2026-09-18)

`full_info_matched_rule`: one agent with every fact, as in A, but in B-D's layout
and framing - the same shared/private blocks, a system prompt built like B's, and
B's answer prompt without its "deciding alone" line. Run with the task stated
only, on seeds 1000-1099. It exists because with the task stated C and D first
appeared to beat original A, whose prompt differs in presentation.

### Held constant

Model, output cap (400 tokens), retry policy (5 attempts with exponential backoff
on 429 and 5xx) and option count are identical across conditions. Temperature was
registered as 0.7 for discussion and 0.0 for answers, but `gpt-5.6-luna` rejects
an explicit temperature, so every call ran at the model default of 1.0; manifests
record `temperature_honoured: false`. System prompts necessarily differ between
conditions, since a B agent cannot be told to ask teammates anything. All are
below.

## Tie-breaking in condition B (registered before the pilot)

Among options sharing the top vote count, one is chosen uniformly by a
`random.Random` seeded with the task id: reproducible, and neutral with respect
to the correct answer. "First option in the list" was rejected because option
order is itself shuffled per task. Tie rate is reported; it was 0.0% in every B
run, so the rule never fired.

## Scoring

The reward is exact match of the parsed group answer against the gold option,
from generator ground truth. No LLM judge is used anywhere.

`parse_answer` returns an option only when the response identifies exactly one:
the value of a `{"answer": ...}` JSON field if present (matched exactly after
stripping case and punctuation, or naming exactly one option as a whole word),
otherwise free text naming exactly one option as a whole word. Anything else -
empty, a single letter, several options named - is a parse failure, scored
incorrect and reported separately. An earlier version guessed instead (audit D1);
re-parsing all 2,120 committed answers and votes under the current rule changes
none of them.

## Metrics

**Accuracy**, per condition.

**Decoy rate.** In every condition reported, every parsed wrong answer was the
decoy, so decoy rate is the complement of accuracy minus parse failures. It is in
`results_tables.json` but not discussed separately.

**Parse failures**, per condition.

**Surfacing rate.** Mean fraction of required private facts appearing in the
discussion (C and D only), matched against the known fact strings by normalised
substring, content-token overlap, or difflib ratio at 0.7. Against 40 hand labels
it has precision 1.00 and recall about 0.86: it misses paraphrase and never
credits an unshared fact.

**Asked for criteria.** Episodes where any discussion message matches a keyword
pattern for requests about criteria, weighting, a ranking, or the decision to
produce. A rough, unvalidated proxy.

## Statistics

Single-condition rates use exact Clopper-Pearson 95% intervals. Differences
between conditions use a paired percentile bootstrap (10,000 resamples) over
tasks present in both, aligned by task id; a pair whose task sets differ is not
computed, and the run exits with an error rather than pairing different tasks.
When both sides of a difference are all-correct or all-wrong, the bootstrap
interval has zero width and the per-condition intervals should be used instead.
No multiplicity correction is applied; the task-not-stated comparisons were
checked and all still exclude zero at a Bonferroni-adjusted alpha of 0.05/4.

## Cost controls

The Batch API was not used: C and D are sequential by construction, and batching
A and B would have saved well under a dollar. Prompt caching does not apply,
since OpenAI caches from 1,024 tokens and the largest prompt here is about 440.

## Reproducibility

Each run writes a new timestamped directory under `runs/` and never overwrites.
Its `manifest.json` records the config, seed range, git commit and dirty flag at
the start of the run and again at the end, timings, per-condition metrics, token
and cost totals, and failures. `uv.lock` pins the environment. Reruns regenerate
the same tasks from the same seeds, but not the same answers, because temperature
cannot be set for this model. Pilot seeds (0-19) are disjoint from reported seeds
(1000-1199).

## Prompts, verbatim

Generated from the constants in `grapevine/rollout/engine.py`. Braces are filled
per task and turn: `{context}` is the agent's facts, `{history}` the transcript
so far as `Agent i: message` lines, `{options}` the four candidate names.

**Agent context (B, C, D)**, built by the generator:

> Facts known to the whole committee:
> - <each shared fact>
>
> Facts only you know:
> - <each of this agent's private facts>

### A, original prompt (task-not-stated runs, and `full_info_rule`)

System:

> You are an expert decision-maker. Reason carefully, then answer.

User (`AGGREGATOR_PROMPT`, with context a flat bulleted list of every fact under
"All available information:" and `{history}` fixed to "(you have all
information; no discussion needed)"):

> {context}
>
> Full team discussion:
> {history}
>
> Based on everything the team surfaced, decide the single best answer. Choose exactly one of these options: {options}.
> Respond with only a JSON object: {"answer": "<one option exactly as written>"}.

### A, presentation-matched prompt (`full_info_matched_rule`)

System (`FULL_INFO_MATCHED_SYSTEM_PROMPT`):

> You are Agent 0 of a 1-agent group. You hold all of the group's information: every shared fact and every private fact. Reason carefully over the information you have and commit to the best answer you can.

User (`FULL_INFO_MATCHED_PROMPT`; context uses the same two blocks as B-D, with
every agent's private facts under "Facts only you know:"):

> {context}
>
> Choose exactly one of these options: {options}.
> Respond with only a JSON object: {"answer": "<one option exactly as written>"}.

### B, no communication

System (`SOLO_SYSTEM_PROMPT`):

> You are Agent {agent_id} of a {n_agents}-agent group. Each member holds different private information. You must decide ALONE: there is no discussion, you cannot ask anyone anything, and you will never see what the others hold. Reason carefully over the information you have and commit to the best answer you can.

User (`NO_COMM_PROMPT`):

> {context}
>
> You are deciding alone, with no discussion.
> Choose exactly one of these options: {options}.
> Respond with only a JSON object: {"answer": "<one option exactly as written>"}.

### C, instructed sharing

System, on every call including aggregation (`TEAM_SYSTEM_PROMPT`):

> You are Agent {agent_id} of a {n_agents}-agent team solving a problem together. Each teammate holds different private information, and no one can answer alone. Your job is to actively SHARE the specific facts you hold and ASK teammates for information you are missing, then reason over everything the team has surfaced. State concrete facts verbatim rather than vague summaries. Be concise.

Discussion turn (`AGENT_TURN_PROMPT`):

> {context}
>
> Conversation so far:
> {history}
>
> It is your turn (round {round_no} of {n_rounds}). Write a short message to your teammates: share the specific facts you hold that are relevant, and ask for any information you still need. Do not state a final answer yet.

### D, neutral

System, on every call including aggregation (`NEUTRAL_SYSTEM_PROMPT`):

> You are Agent {agent_id} of a {n_agents}-agent team solving a problem together. Each teammate holds different private information, and no one can answer alone. Discuss the decision with your teammates. Be concise.

Discussion turn (`NEUTRAL_TURN_PROMPT`):

> {context}
>
> Conversation so far:
> {history}
>
> It is your turn (round {round_no} of {n_rounds}). Write a short message to your teammates. Do not state a final answer yet.

### C and D aggregation (`AGGREGATOR_PROMPT`)

Agent 0 answers after the last round, seeing its own context and the transcript:

> {context}
>
> Full team discussion:
> {history}
>
> Based on everything the team surfaced, decide the single best answer. Choose exactly one of these options: {options}.
> Respond with only a JSON object: {"answer": "<one option exactly as written>"}.

### Task statement (rule arm only, prepended to every prompt of the condition)

`TASK_STATEMENT`, with the task's own question substituted:

> Task: {question}
> Decision rule: the strongest candidate is the one with the most supporting facts. Each fact describing a candidate's strengths counts as one supporting fact for that candidate.

The question reads, for example: "The hiring committee must recommend exactly one
candidate for the role. Based on all available information, who is the strongest
candidate? Options: Finley, Avery, Blair, Devon."
