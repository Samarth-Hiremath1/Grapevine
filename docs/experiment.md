# Experiment

What was run, with what parameters, and how to run it again. Design details are
in `docs/methodology.md`; results in `docs/results.md`.

## Question

When the facts needed for a decision are split across agents, how much accuracy
is lost, how much does communication recover, and how much of the remainder is
the evaluation's own fault?

## Hypotheses

Registered before the first run (the first three) and before the rule arm (the
fourth):

1. Accuracy is highest with full information and lower in both distributed
   conditions.
2. Failures concentrate on the decoy rather than spreading over the wrong
   options, because the shared facts point there.
3. Communication recovers some accuracy over no communication.
4. Stating the task question and the scoring rule closes part of the remaining
   gap; the quantity of interest is the change in the A − C gap, since A lacked
   the rule too.

All four came out true. (1) needs qualifying: with the task stated the
communicating conditions match full information rather than trailing it.

## Conditions

| Condition | Agents | Sees | Answer from | Calls/task |
|---|---|---|---|---|
| A `full_info` | 1 | every fact | that agent | 1 |
| B `no_communication` | 3 | own context only | majority vote | 3 |
| C `communication` | 3 | own context + transcript | aggregator after 2 rounds | 7 |
| D `communication_neutral` | 3 | own context + transcript | aggregator after 2 rounds | 7 |

C's prompts tell agents to share facts and ask for what they lack; D's do not,
on every call including aggregation. Each condition also has a rule-arm variant
(`*_rule`) that prepends the task question and scoring rule to every prompt, plus
`full_info_matched_rule`, which gives one agent every fact in B-D's layout.
Prompts are verbatim in `docs/methodology.md`.

## Parameters

- Model `gpt-5.6-luna` (OpenAI), $0.20/$1.20 per MTok as of 2026-09-08
- `hidden_profile`, 4 options (chance 25%), 3 agents, 6 shared facts, 2 private
  facts per agent, 4 filler facts
- 2 discussion rounds; output cap 400 tokens; 5 retries with exponential backoff
- Temperature requested 0.7 discussion / 0.0 answer, **not applied**:
  `gpt-5.6-luna` rejects an explicit temperature, so everything ran at the model
  default of 1.0 (`temperature_honoured: false` in every manifest)
- Task not stated: 200 tasks, seeds 1000-1199. Rule arm: 100 tasks, seeds
  1000-1099. Pilots used seeds 0-19 and appear in no reported number.

## Runs

| Run directory | Conditions | N | Cost |
|---|---|---|---|
| `20260909T064607Z_pilot` | A, B, C (pilot) | 20 | $0.0444 |
| `20260910T064954Z_pilot_D` | D (pilot) | 20 | $0.0315 |
| `20260910T065248Z_primary` | A, B, C, D | 200 | $0.7574 |
| `20260913T013826Z_rule_arm` | A, C + rule | 100 | $0.1845 |
| `20260918T222732Z_D_fixed` | D, aggregator fixed | 200 | $0.3172 |
| `20260918T222744Z_rule_arm_BD` | B, D + rule | 100 | $0.1818 |
| `20260919T011615Z_A_matched_rule` | A matched + rule | 100 | $0.0154 |

Total $1.5322. The reported D is `D_fixed`; the D inside `primary` is superseded
(`docs/decisions.md`). Every run directory is committed.

## Commands

```bash
uv sync --locked --extra dev
cp .env.example .env        # OPENAI_API_KEY; gitignored

# plan only, no API calls
uv run python -m grapevine.experiments.run \
    --config configs/coordination_ablation.yaml --dry-run

# task not stated, A-D, seeds 1000-1199
uv run python -m grapevine.experiments.run --config configs/coordination_ablation.yaml

# task and rule stated, seeds 1000-1099
uv run python -m grapevine.experiments.run --config configs/coordination_ablation.yaml \
    --n-episodes 100 --label rule_arm \
    --conditions full_info_rule,full_info_matched_rule,no_communication_rule,communication_rule,communication_neutral_rule

# rebuild every table and the figure from committed runs (no API calls)
uv run python -m grapevine.experiments.report_tables
```

Useful flags: `--conditions` (subset; rule conditions are opt-in), `--n-episodes`,
`--seed-start`, `--label`, `--dry-run`. Config fields worth knowing:
`run.concurrency`, `env.n_agents`, `rollout.n_rounds`, `model.name`. A model with
no entry in `DEFAULT_PRICING` raises rather than reporting $0.00.

## Output layout

```
runs/<UTC timestamp>_<label>/
  manifest.json                 config, seeds, git commit and dirty flag at start
                                and end, timings, metrics, token and cost totals,
                                failures, paired differences
  episodes_<condition>.jsonl    one episode per line, full transcript
```

`docs/figures/` holds the figure, its CSV, and `results_tables.json` with every
number in `docs/results.md`.

## Reproducing the numbers

`report_tables` regenerates all tables and the figure from the committed runs
with no API calls. Rerunning the experiments regenerates identical tasks (0 of
200 differ from the committed episodes) but not identical answers, since
temperature cannot be set for this model. To compare a fresh run with a committed
one, paired by task id:

```bash
uv run python -m grapevine.experiments.compare \
    --base runs/20260910T065248Z_primary --base-cond communication \
    --other runs/<new-run> --other-cond communication
```
