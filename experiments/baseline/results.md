# Baseline: HiddenBench-style gap on Grapevine tasks

**Status: not yet run in this repository.** No results are recorded here because
no API key was available, and this project does not fabricate numbers.

To populate this file with real results, set an API key and run the experiment:

```bash
export OPENAI_API_KEY=...           # your key
python experiments/baseline/run_baseline.py \
    --provider openai --model gpt-4o-mini \
    --family hidden_profile --k 30 --agents 3 --rounds 2
```

This runs 30 tasks/condition through the single-agent (full context) and
distributed-team conditions and rewrites this file with accuracy, surfacing rate,
gap-closure, and cost.
