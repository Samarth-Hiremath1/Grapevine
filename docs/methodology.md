# Methodology

This describes how the coordination ablation is set up and scored. Everything
here was fixed before any data was collected.

## Task generation

Tasks come from `grapevine/envs/hidden_profile.py`. Each instance is a group
decision over `n_options` candidates (4 by default, so chance is 25%). Support
for a candidate is counted in whole facts: one supporting fact is worth one
point, and the best candidate is the one with the most supporting facts once
every fact is on the table.

The split between shared and private information is what makes the task a hidden
profile:

- **Shared facts** are given to every agent. They are assigned so that one wrong
  candidate, the *decoy*, has a strict lead. No shared fact supports the correct
  candidate.
- **Private facts** are split evenly across agents, and all of them support the
  correct candidate.
- **Distractors** are decision-irrelevant filler, split between the shared pool
  and the private contexts.

The decoy is given exactly one fewer supporting fact than the total private
support the correct candidate will receive. Three properties follow, and
`tests/test_hidden_profile.py` asserts all three for every configuration used:

1. On shared information alone, the decoy strictly leads.
2. With every fact pooled, the correct candidate strictly leads.
3. The correct candidate's final margin is exactly one, so dropping any single
   private fact removes its lead. Every required private fact is load-bearing.

Tasks are deterministic in their seed. `generate_batch(n, seed)` uses seeds
`seed .. seed+n-1`.

### Why `split_evidence` is not used

The repository contains a second task family, `split_evidence`, which is
excluded from this experiment. Its reasoning chain ends with a hop of the form
"From X, the active route continues to Z", where Z is the gold answer, so one
agent holds the answer string verbatim. A check over 100 generated tasks found
the gold answer present in some agent's context in 100 of them. An agent in the
no-communication condition could therefore answer correctly without any pooling,
which breaks the comparison the experiment is built on. `run.py` rejects the
family at config-load time. See `docs/decisions.md`.

## Information assignment

Agent *i* receives the shared block plus its own private facts, and nothing
else. `tests/test_no_communication.py::test_agents_are_isolated_no_shared_state`
asserts that no agent's prompt contains another agent's private facts, and that
no discussion history reaches the no-communication condition.

Two integrity checks were run over 100 tasks before the experiment:

- No required private fact appears in the shared block (0/100).
- The full-information context contains every required private fact (100/100).
- No single agent's context, on its own, favours the correct candidate (0/100).

## Conditions

All three conditions run over the same task seeds, so comparisons are paired.

**A — `full_info`.** One agent receives the union of every fact (shared once,
plus every agent's private facts) and answers directly. This is the accuracy
ceiling: the same information, undistributed.

**B — `no_communication`.** Each of the N agents sees only its own context and
answers independently. There is no shared history and no channel of any kind.
The group answer is the majority vote.

**C — `communication` (instructed sharing).** The same N agents, same contexts,
but they exchange messages for `n_rounds` rounds (2 in this experiment) before a
designated aggregator produces the answer. Each agent sees the full shared
transcript plus its own private context. The system prompt explicitly tells
agents to share their facts and ask for what they are missing.

**D — `communication_neutral`.** Identical to C in every respect (same 3 agents,
same 2 rounds, same aggregator, same temperature, same `max_tokens`, same seeds)
except that the discussion prompts do not instruct fact-sharing or asking.

B and C differ only in whether agents can talk. C and D differ only in whether
the prompt tells them to pool. A and C differ in whether the information is
distributed at all.

### Why D exists

C's prompt instructs sharing, so a reader is entitled to ask whether the
instruction rather than the discussion does the work. D answers that inside the
same experiment instead of leaving it as a caveat. Wherever C is reported it is
described as *instructed* pooling. The C−D gap is the secondary finding.

### The two discussion prompts, verbatim

Condition C system prompt (`TEAM_SYSTEM_PROMPT`):

> You are Agent {agent_id} of a {n_agents}-agent team solving a problem together.
> Each teammate holds different private information, and no one can answer alone.
> Your job is to actively SHARE the specific facts you hold and ASK teammates for
> information you are missing, then reason over everything the team has surfaced.
> State concrete facts verbatim rather than vague summaries. Be concise.

Condition D system prompt (`NEUTRAL_SYSTEM_PROMPT`):

> You are Agent {agent_id} of a {n_agents}-agent team solving a problem together.
> Each teammate holds different private information, and no one can answer alone.
> Discuss the decision with your teammates. Be concise.

Condition C turn prompt (`AGENT_TURN_PROMPT`):

> {context}
>
> Conversation so far:
> {history}
>
> It is your turn (round {round_no} of {n_rounds}). Write a short message to your
> teammates: share the specific facts you hold that are relevant, and ask for any
> information you still need. Do not state a final answer yet.

Condition D turn prompt (`NEUTRAL_TURN_PROMPT`):

> {context}
>
> Conversation so far:
> {history}
>
> It is your turn (round {round_no} of {n_rounds}). Write a short message to your
> teammates. Do not state a final answer yet.

The first two sentences of the system prompt are identical, so both conditions
know the task is distributed and that no one can answer alone. Only the
directive to share and ask is removed. The aggregator prompt is byte-identical
between C and D.

### Rule arm: question and scoring rule shown

*Registered 2026-09-12, before running.* No prompt in conditions A-D contains the
task's question or the rule used for grading, so the models had to infer what
"the single best answer" meant. The rule arm measures how much that matters.

It re-runs A and C with one change. Every prompt in the condition starts with
this block, identical in both, with the task's own question substituted
(`TASK_STATEMENT` in `grapevine/rollout/engine.py`):

> Task: {question}
> Decision rule: the strongest candidate is the one with the most supporting
> facts. Each fact describing a candidate's strengths counts as one supporting
> fact for that candidate.

Everything else is unchanged: model, agents, rounds, aggregator, token budget
and generator. The arm runs on seeds 1000-1099 (N=100), the first half of the
primary run's seeds, so each episode is compared with the primary episode on the
identical task. The conditions are `full_info_rule` and `communication_rule`.
Because they are a separate run, comparisons against the primary run use
`grapevine.experiments.compare`, which matches episodes by task id.

How the result will be read, fixed in advance:

- The quantity of interest is the change in the A − C accuracy gap, not C's
  accuracy alone. A also lacked the rule, so if showing it lifts A and C by the
  same amount, underspecification does not explain the gap.
- If the gap closes and C's decoy rate falls sharply, the residual gap in the
  main result was mostly underspecification.
- If the gap and C's decoy rate hold, the aggregator fails to use pooled
  evidence even when it has been told the rule.
- Anything in between is reported as such, with its interval.

### Parameters held constant

Temperature, retry policy, `max_tokens`, and model are identical across
conditions. Discussion turns use temperature 0.7; every answer-producing turn in
every condition uses temperature 0.0. `max_tokens` is 400 everywhere. Retries
are 5 attempts with exponential backoff on 429 and 5xx responses.

The system prompts differ between B and C, which the conditions require: telling
a B agent to "ask teammates for information you are missing" would instruct it
to do something impossible and waste its output budget. The prompts are kept as
parallel as possible otherwise, and all of them live in
`grapevine/rollout/engine.py` (`TEAM_SYSTEM_PROMPT`, `SOLO_SYSTEM_PROMPT`,
`AGENT_TURN_PROMPT`, `NO_COMM_PROMPT`, `AGGREGATOR_PROMPT`).

## Tie-breaking in condition B

With 3 agents and 4 options, votes can split three ways. The rule was fixed
before the pilot:

> Among the options sharing the top vote count, one is chosen uniformly at
> random by a `random.Random` instance seeded with the task id.

This is deterministic (the same task always resolves the same way, so runs
reproduce) and unbiased with respect to the correct answer. The obvious
alternative, "take the first option in the list", was rejected because option
order is itself shuffled per task, which would entangle the tie-break with
option ordering rather than removing it.
`tests/test_no_communication.py` asserts determinism and checks that the rule
spreads roughly evenly across leaders over 600 tasks.

Because a tie-break rule can move a headline number, condition B reports:

- the **tie rate**, as a first-class metric, and
- accuracy **both** with the tie-break applied and with every tie-broken episode
  scored incorrect, which is a lower bound.

Votes that cannot be parsed count toward no option and are reported separately.

## Reward and scoring

The reward is exact match against the gold answer: 1.0 if the parsed team answer
equals the gold option, 0.0 otherwise. It is computed from environment ground
truth. No LLM judge is used anywhere in this experiment.

Answers are parsed by `parse_answer`, which tries a `{"answer": ...}` JSON object
first and falls back to an option name appearing in the text (preferring the
last mention). If nothing parses, the episode is scored incorrect *and* counted
as a parse failure, so refusals are visible rather than blending into the
reasoning-error count.

## Metrics

All metrics come from ground truth or from mechanical properties of the
transcript.

**Accuracy.** Fraction of episodes whose answer matches gold.

**Decoy rate.** Fraction landing on the decoy, the candidate that shared
information alone favours. This is the mechanistic measurement. Accuracy alone
cannot distinguish "the group was confused" from "the group reasoned from common
ground"; failures concentrated on the decoy point at the second, because the
decoy is exactly what an agent reasoning from shared facts should pick.

**Parse-failure rate.** Episodes with no parseable answer, per condition.

**Tie rate** and **accuracy with ties scored incorrect.** Condition B only.

**Surfacing rate.** Mean fraction of required private facts that appear in the
discussion, matched against the known fact strings by normalised substring, then
content-token overlap, then a difflib ratio, at a 0.7 threshold
(`grapevine/rewards/reward.py`). This is a proxy: it detects verbatim to
near-verbatim sharing, which the agent prompt explicitly asks for, and it will
miss heavy paraphrase and can be fooled by negation. It is reported only for
condition C. For B it is `None` rather than 0.0, since B has no channel and a
zero there would read as a finding rather than a definition.

**Uncertainty.** Percentile bootstrap 95% intervals over episodes, 10,000
resamples, seeded. Bootstrap rather than a normal approximation because
proportions near 0 or 1 would otherwise produce intervals outside [0, 1].
Condition differences use a paired bootstrap over the shared task seeds, which
removes task-difficulty variance.

## Cost controls

**Batch API: not used.** Condition C is inherently sequential — agent 2's prompt
contains agent 1's message — so its calls cannot be submitted as an offline
batch. Conditions A and B could be batched, but at the measured scale of this
experiment the saving is a fraction of a dollar against a split code path and up
to 24 hours of turnaround. Running everything through the same synchronous path
also keeps the conditions identical in every respect except the one under test.

**Prompt caching: not used, and not claimed.** OpenAI applies automatic prompt
caching only to prompts of at least 1024 tokens. The largest prompt in this
experiment is roughly 440 tokens, so the discount does not apply.

## Reproducibility

Every run writes a fresh timestamped directory under `runs/`. Nothing is
overwritten. Each directory contains the per-condition episode JSONL and a
`manifest.json` recording the full config, resolved parameters, seed range, git
commit and whether the tree was dirty, start and end timestamps, per-condition
metrics, client token totals, cost, and any episodes that failed.

Pilot and primary runs use disjoint seed ranges (0-19 and 1000-1199), so no
episode used to validate the design appears in the reported results.
