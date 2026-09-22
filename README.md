# Grapevine

**Question:** when the facts needed for a decision are split across LLM agents,
what breaks?

**Finding (one model, one generated task family):** splitting the facts across
three agents who cannot talk dropped accuracy from 85.5% to 0.5%, and it stayed
at 0% even when the task was stated. Letting them talk recovered most of the
loss. The gap that remained, which we first reported as a coordination failure,
was underspecification: no prompt told the models what they were being scored
on. With the task and scoring rule stated, the communicating teams scored
100/100 and 99/100, the same as a single agent given every fact.

**The transferable lesson:** an evaluation that does not tell agents their
objective can produce a coordination failure that looks real — every fact gets
shared, the team still chooses wrong — and vanishes once the objective is
stated.

![Accuracy by condition, with and without the task stated](docs/figures/accuracy_by_condition.png)

## What this is and isn't

This reproduces a known phenomenon, the hidden-profile effect (Stasser & Titus,
1985), which HiddenBench (arXiv:2505.11556) studies in LLM groups: when shared
evidence favours one option and the evidence for the right one is spread across
members, groups choose the wrong one. Grapevine makes no novelty claim for that.

What it adds is a small, fully logged case study of how an evaluation of this
effect can mislead, together with the audit that caught it.

**The underspecification finding is about our own task construction, not a
criticism of HiddenBench: HiddenBench states the objective and the payoff to its
models in the system prompt, and we did not.** Their correctness also rests on
elimination logic, ours on a counting convention we never stated, and their
headline metric is the share of individual agents choosing correctly while ours
is a single group answer. So their 30.1% and 80.7% are not directly comparable to
any number here. `docs/results.md` sets out the comparison in full.

It is one model (`gpt-5.6-luna`), one procedurally generated task template, three
agents, two discussion rounds, four options.

## Results

| Condition | Task not stated | Task and rule stated |
|---|---|---|
| A. one agent, all facts | 171/200 · 85.5% | original prompt 96/100 · 96%<br>matched prompt 100/100 · 100% |
| B. three agents, no talking | 1/200 · 0.5% | 0/100 · 0% |
| C. three agents, told to share | 134/200 · 67.0% | 100/100 · 100% |
| D. three agents, neutral prompt | 111/200 · 55.5% | 99/100 · 99% |

Chance is 25%. The task-not-stated runs used 200 tasks (seeds 1000-1199); the
rule arm used 100 (seeds 1000-1099), and every comparison between the two uses
those 100. Intervals, paired differences and the full account are in
`docs/results.md`.

- **B is the robust result.** With no communication every agent sees the decoy
  ahead in its own facts and votes for it, whether or not the task is stated.
- **The sharing instruction mattered because the task was underspecified.**
  C over D was +11.5 points [+3.0, +20.0] without the task and +1.0 [0.0, +3.0]
  with it.
- **We first read the C-versus-A gap as an integration failure.** Agents shared
  every required fact in 200 of 200 episodes and still trailed A by 18.5 points.
  Transcripts showed agents asking what decision they were supposed to make (174
  of 200 C episodes). Stating the task took C from 68/100 to 100/100 on the same
  tasks, and those requests fell to 2 of 100.
- **A second mistake, also caught:** with the task stated, C and D first appeared
  to beat A (100 and 99 against 96). A's prompt was laid out differently from the
  other conditions. Given the same layout, A scored 100/100.

## How it was checked

The docs that matter most here are the ones about our own errors:

- `docs/assumptions.md` — every assumption the result rests on, written before
  any of them were tested.
- `docs/audit.md` — what each check found, by severity, including the findings
  that made the work look worse.
- `docs/decisions.md` — every judgement call, dated, including conditions
  registered before they were run.

## Limitations

- The task has a trivial shortcut: counting name mentions solves 200 of 200
  full-information contexts.
- All 200 tasks share one support pattern (correct 6, decoy 5, others 1 and 0)
  and the same 12 fact sentences: one puzzle in 200 arrangements, not 200
  problems.
- The surfacing metric has precision 1.00 and recall about 0.86 against 40 hand
  labels; it undercounts paraphrased sharing.
- Temperature is stuck at 1.0 for this model, so reruns regenerate the same tasks
  but not the same answers.
- The rule arm is N=100 against N=200.
- With the task unstated, accuracy falls as the correct answer moves later in the
  option list (C: 81% at the first position, 56% at the last).
- Condition D's 4 parse failures are empty responses, probably from hidden
  reasoning tokens exhausting the output cap; not confirmed.

The full list, each with its numbers, is in `docs/results.md`.

## Reproduce

Requires Python 3.11 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Samarth-Hiremath1/Grapevine.git
cd Grapevine
uv sync --locked --extra dev
cp .env.example .env        # put an OpenAI key in .env; it is gitignored
```

Rebuild every table and the figure from the committed runs (no API calls):

```bash
uv run python -m grapevine.experiments.report_tables
```

Rerun the experiments. Runs write to a new timestamped directory under `runs/`
and never overwrite. Costs are what the committed runs cost.

```bash
# Task not stated: A, B, C, D, seeds 1000-1199 (~$0.76)
uv run python -m grapevine.experiments.run --config configs/coordination_ablation.yaml

# Task and rule stated, seeds 1000-1099 (~$0.38 in total)
uv run python -m grapevine.experiments.run --config configs/coordination_ablation.yaml \
    --n-episodes 100 --label rule_arm \
    --conditions full_info_rule,full_info_matched_rule,no_communication_rule,communication_rule,communication_neutral_rule
```

Reruns regenerate identical tasks; answers vary because temperature cannot be
set for this model. Each run directory holds `manifest.json` (config, seeds, git
commit at start and end, metrics, token and cost totals, failures) and one
`episodes_<condition>.jsonl` per condition with full transcripts. To compare a
new run with the committed ones:

```bash
uv run python -m grapevine.experiments.compare \
    --base runs/20260910T065248Z_primary --base-cond communication \
    --other runs/<new-run> --other-cond communication_rule
```

Read a transcript, with each required fact marked by whether and when it was
shared:

```bash
uv run grapevine view runs/20260913T013826Z_rule_arm/episodes_communication_rule.jsonl
```

## Tests

```bash
uv run pytest -q
uv run ruff check grapevine tests
uv run mypy
```

CI runs all three on every push, plus a two-step CPU smoke test of the GRPO
training loop.

## Repository layout

```
grapevine/envs/         task families behind a common Env interface
grapevine/rollout/      async multi-agent engine and provider client
grapevine/rewards/      exact-match reward, fact-surfacing metric
grapevine/experiments/  runner, analysis, cross-run comparison, tables, figure
grapevine/eval/         transcript viewer
grapevine/diagnostics/  degenerate-policy checks against the reward
grapevine/train/        TRL GRPO wiring (smoke-tested only; never trained)
configs/                experiment and training configs
docs/                   results, methodology, assumptions, audit, decisions
runs/                   committed experiment runs, one directory per run
```

Task families plug in through `grapevine/envs/`. `hidden_profile` is the one used
here. `split_evidence` exists but is excluded from experiments because it leaks
the answer to one agent (`docs/decisions.md`). The harness is being extended to
run existing benchmarks as further families; nothing in the results above
depends on that.

## Citation

- Li, Y., Naito, A., & Shirado, H. Systematic Failures in Collective Reasoning
  under Distributed Information in Multi-Agent LLMs. ICML 2026 (PMLR 306).
  arXiv:2505.11556v4. The 30.1% and 80.7% figures quoted in `docs/results.md`
  were checked against its abstract.
- Stasser, G., & Titus, W. (1985). Pooling of unshared information in group
  decision making. *Journal of Personality and Social Psychology*, 48(6),
  1467-1478. **UNVERIFIED**: these citation details have not been checked against
  the source.

## License

MIT, see [LICENSE](LICENSE).
