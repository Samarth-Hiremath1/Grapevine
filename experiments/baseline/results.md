# Baseline (superseded)

This early two-condition script has been superseded by the four-condition
coordination ablation in `grapevine/experiments/run.py`. It was never run
against a live API, and no results were ever recorded here.

For the experiment that was actually run, and its numbers, see:

- `docs/results.md` — results, transcripts, limitations
- `runs/20260910T065248Z_primary/` — the run itself, with manifest and transcripts

To reproduce that:

```bash
python -m grapevine.experiments.run --config configs/coordination_ablation.yaml
```
