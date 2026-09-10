# Coordination ablation

## Question

When the information needed for a decision is split across agents, how much of
the loss comes from distributing it, and how much does letting the agents talk
recover?

## Hypothesis

Registered before the pilot:

1. Accuracy is highest in `full_info` and lower in both distributed conditions.
2. Failures in the distributed conditions concentrate on the decoy rather than
   spreading across the wrong options, because the shared facts every agent sees
   point at the decoy.
3. Communication recovers some accuracy relative to no communication, but not
   all of the gap to `full_info`.
4. Condition D (registered before running) recovers less than C, showing how
   much of C's recovery comes from the instruction to share rather than from
   discussion itself.

Any of these can come out false. A flat result between B and C, or a
communication condition that does worse than no communication, is a real finding
and is reported as such.

## Conditions

| Condition | Agents | Sees | Answer produced by | Calls/task |
|---|---|---|---|---|
| A `full_info` | 1 | every fact | that agent | 1 |
| B `no_communication` | 3 | own context only | majority vote of independent answers | 3 |
| C `communication` | 3 | own context + full transcript | designated aggregator after 2 rounds | 7 |
| D `communication_neutral` | 3 | own context + full transcript | designated aggregator after 2 rounds | 7 |

C's prompt instructs fact-sharing; D's does not. Both prompts are in
`methodology.md` verbatim. All four run on identical task seeds, so comparisons
are paired.

**Conditions C and D use 2 discussion rounds.** This is stated wherever the
result is reported, since round count is a free parameter that plausibly
matters.

## Parameters

- Model: `gpt-5.6-luna` (OpenAI), $0.20 / $1.20 per MTok as of 2026-09-08
- Task family: `hidden_profile`, 4 options, chance 25%
- 3 agents, 6 shared facts, 2 private facts per agent, 4 distractors
- Temperature requested 0.7 for discussion turns and 0.0 for answer turns, but
  **not applied**: gpt-5.6-luna rejects an explicit temperature, so every call
  ran at the model default of 1.0, uniformly across all four conditions. The
  manifest records this as `temperature_honoured: false`. See the limitations in
  `results.md`.
- `max_tokens` 400, 5 retries with exponential backoff
- Pilot: 20 episodes per condition, seeds 0-19
- Primary: 200 episodes per condition, seeds 1000-1199

Seed ranges are disjoint on purpose. Pilot episodes are used only to validate
the design and never appear in reported results.

## Commands

Set up credentials once:

```bash
cp .env.example .env      # then put your key in .env; it is gitignored
```

Check the plan without spending anything:

```bash
python -m grapevine.experiments.run --config configs/coordination_ablation.yaml --dry-run
```

Pilot:

```bash
python -m grapevine.experiments.run --config configs/coordination_ablation_pilot.yaml
```

A single condition only (used for the condition D pilot):

```bash
python -m grapevine.experiments.run \
    --config configs/coordination_ablation_pilot.yaml \
    --conditions communication_neutral --label pilot_D
```

Primary:

```bash
python -m grapevine.experiments.run --config configs/coordination_ablation.yaml
```

## Output layout

Each run creates `runs/<UTC timestamp>_<label>/` and never overwrites an earlier
one:

```
runs/20260910T065248Z_primary/
  manifest.json                    config, seeds, git commit, timings, metrics, cost
  episodes_full_info.jsonl         one episode per line, full transcript
  episodes_no_communication.jsonl
  episodes_communication.jsonl
  episodes_communication_neutral.jsonl
  accuracy_by_condition.png / .svg
  figure_data.csv
```

`manifest.json` holds everything needed to reproduce a number: the resolved
config, the seed range, the git commit and whether the tree was dirty, per
condition metrics with bootstrap intervals, client token totals, cost, and any
episodes that failed.

Inspect transcripts with the viewer, which colours each required private fact by
whether and when it surfaced:

```bash
grapevine view runs/<dir>/episodes_communication.jsonl
```

## Figure

The main figure is produced from a run directory:

```bash
python -m grapevine.experiments.figure --run runs/<dir>
```

It writes `accuracy_by_condition.png`, `.svg`, and the source table as
`figure_data.csv` inside the run directory, so the plot and its data stay
together.
