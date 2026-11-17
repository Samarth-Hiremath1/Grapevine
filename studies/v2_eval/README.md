# Does the v0 result hold on `hidden_profile_v2`?

The pre-registered eval of v0.2. Pre-registration:
[`docs/prereg/hidden_profile_v2_eval.md`](../../docs/prereg/hidden_profile_v2_eval.md),
committed before any call. Its §11 records every decision and deviation, with
dates, in the order they happened.

**Read this first.** The eval found a flaw in the environment it was run on.
`hidden_profile_v2` passed the audit battery as it stood. The battery then
turned out to lack a probe: an agent that applies the scoring rule to its own
private facts alone gets the answer every time (300/300 agents on these tasks),
and one of the three models partly did that. The probe is now in the battery
and v2 fails it. Written up as A2 in [`docs/audit.md`](../../docs/audit.md); the
investigation is [`h1_investigation.md`](h1_investigation.md). Every number
below was produced on v2 as it is, and is read with that in mind.

## What was run

| | Pilot | Primary |
|---|---|---|
| Run | `runs/20261116T074017Z_pilot/` | `runs/20261116T091238Z_primary/` |
| Seeds | 9000–9019 | 10000–10099 |
| Models | `gpt-5.6-luna`, `gpt-6-luna`, `gpt-4o-mini` | same |
| Calls | 1,320 | 6,600 |
| Episodes | 360/360 | 1,800/1,800 |
| Truncated calls | 1 | 14 |
| Cost | $0.2521 (ceiling $1.34) | $1.2812 (ceiling $6.69) |

Six cells per model: three conditions (`full_info`, `no_communication`,
`communication`) by objective stated or not. The pilot checked the plumbing
only; no threshold was crossed and nothing in the design changed. Its
accuracies were not read and are not results. The analysis was run once on the
primary run.

## Reading, against what was pre-registered

Each model stands alone (§10). Nothing is averaged across models.

**H4 — full information near ceiling with the objective stated (≥ 90%).**
Holds for `gpt-5.6-luna` (98/100) and `gpt-6-luna` (99/100). Fails for
`gpt-4o-mini` (62/100), so by the pre-registered reading every
`gpt-4o-mini` communication result is a capability result, not a coordination
result.

**H3 — the main contrast** (`full_info − communication`, stated; predicted
within ±5 points with the 95% interval including 0).

- `gpt-5.6-luna`: +3.0 points, 95% [−2.0, +8.0]. **The v0 finding replicates**
  on this environment for this model, in the pre-registered sense. Not a
  general property of LLM teams.
- `gpt-6-luna`: +7.0 points, 95% [+2.0, +13.0], Bonferroni [+0.0, +15.0].
  **This falls between the pre-registered readings.** It is not a replication
  (the 95% interval excludes 0, and the mean is outside ±5), not a coordination
  gap (the Bonferroni interval does not exclude 0; its lower bound is exactly
  0), and not "inconclusive" as defined (that reading needs the interval to
  include 0). The pre-registration did not anticipate this case, so no reading
  is claimed.
- `gpt-4o-mini`: +28.0 points, Bonferroni [+11.0, +45.0]. Read through H4 as a
  capability result. The transcript audit the "gap" reading requires before a
  coordination claim has not been done, and no coordination claim is made.

**H2 — stating the objective helps where the information is available**
(`stated − unstated` > 0 in `full_info` and `communication`).

- `gpt-5.6-luna`: supported in both: +11.0 in `full_info`, +34.0 in
  `communication`, both Bonferroni intervals above 0.
- `gpt-6-luna`: +25.0 in `communication`; **+0.0 in `full_info`**, 95%
  [−3.0, +3.0]. By the pre-registered reading, for this model the rule is
  recoverable from the facts without being stated, and the v0
  underspecification explanation does not carry over to `full_info`.
- `gpt-4o-mini`: **the opposite direction** in `full_info` (−24.0, Bonferroni
  [−37.0, −12.0]); −11.0 in `communication`, interval including 0. Stating the
  rule made this model worse with full information. Bounded by H4.

**H1 — no communication at or below chance in both cells.**

- `gpt-5.6-luna` and `gpt-6-luna`: consistent with H1 in all four cells (at
  most 8/100).
- `gpt-4o-mini`, unstated: 45/100, 95% [35.0%, 55.3%], above 25% chance. This
  triggered the pre-registered H1 reading, which is why A2 was found. The cell
  is a measure of what this model chose to do on a task that permits a
  single-agent answer, not of what one agent cannot do.

## What this does not show

- Nothing about coordination in general: one environment, three models, N=100.
- Nothing about `no_communication` as a lower bound for v2: since A2, the task
  allows one agent to answer alone, and these cells only show which models did
  not.
- Nothing from the pilot.

## Results, as the analysis wrote them

The block below is `runs/20261116T091238Z_primary/results.md`, copied by
`python -m studies.v2_eval.report`. CI checks it matches.

<!-- BEGIN GENERATED: results (python -m studies.v2_eval.report) -->

## hidden_profile_v2 eval: 20261116T091238Z_primary

### gpt-5.6-luna

| Condition | Objective stated | Objective not stated |
|---|---|---|
| full_info | 98/100 · 98.0% [93.0%, 99.8%] | 87/100 · 87.0% [78.8%, 92.9%] |
| no_communication | 0/100 · 0.0% [0.0%, 3.6%] | 5/100 · 5.0% [1.6%, 11.3%] |
| communication | 95/100 · 95.0% [88.7%, 98.4%] | 61/100 · 61.0% [50.7%, 70.6%] |

| Contrast | Mean | 95% | Bonferroni |
|---|---:|---:|---:|
| objective effect, full_info | +11.0 | [+4.0, +18.0] | [+2.0, +21.0] |
| objective effect, no_communication | -5.0 | [-10.0, -1.0] | [-12.0, +0.0] |
| objective effect, communication | +34.0 | [+23.0, +45.0] | [+20.0, +49.0] |
| communication - no_communication, stated | +95.0 | [+90.0, +99.0] | [+88.0, +100.0] |
| full_info - communication, stated | +3.0 | [-2.0, +8.0] | [-4.0, +11.0] |
| communication - no_communication, unstated | +56.0 | [+45.0, +67.0] | [+40.0, +71.0] |
| full_info - communication, unstated | +26.0 | [+16.0, +36.0] | [+13.0, +40.0] |

### gpt-6-luna

| Condition | Objective stated | Objective not stated |
|---|---|---|
| full_info | 99/100 · 99.0% [94.6%, 100.0%] | 99/100 · 99.0% [94.6%, 100.0%] |
| no_communication | 0/100 · 0.0% [0.0%, 3.6%] | 8/100 · 8.0% [3.5%, 15.2%] |
| communication | 92/100 · 92.0% [84.8%, 96.5%] | 67/100 · 67.0% [56.9%, 76.1%] |

| Contrast | Mean | 95% | Bonferroni |
|---|---:|---:|---:|
| objective effect, full_info | +0.0 | [-3.0, +3.0] | [-4.0, +4.0] |
| objective effect, no_communication | -8.0 | [-14.0, -3.0] | [-16.0, -2.0] |
| objective effect, communication | +25.0 | [+14.0, +36.0] | [+10.0, +40.0] |
| communication - no_communication, stated | +92.0 | [+86.0, +97.0] | [+84.0, +98.0] |
| full_info - communication, stated | +7.0 | [+2.0, +13.0] | [+0.0, +15.0] |
| communication - no_communication, unstated | +59.0 | [+48.0, +69.0] | [+44.0, +73.0] |
| full_info - communication, unstated | +32.0 | [+23.0, +41.0] | [+20.0, +45.0] |

### gpt-4o-mini

| Condition | Objective stated | Objective not stated |
|---|---|---|
| full_info | 62/100 · 62.0% [51.7%, 71.5%] | 86/100 · 86.0% [77.6%, 92.1%] |
| no_communication | 8/100 · 8.0% [3.5%, 15.2%] | 45/100 · 45.0% [35.0%, 55.3%] |
| communication | 34/100 · 34.0% [24.8%, 44.2%] | 45/100 · 45.0% [35.0%, 55.3%] |

| Contrast | Mean | 95% | Bonferroni |
|---|---:|---:|---:|
| objective effect, full_info | -24.0 | [-33.0, -15.0] | [-37.0, -12.0] |
| objective effect, no_communication | -37.0 | [-47.0, -27.0] | [-51.0, -23.0] |
| objective effect, communication | -11.0 | [-24.0, +2.0] | [-29.0, +7.0] |
| communication - no_communication, stated | +26.0 | [+16.0, +36.0] | [+13.0, +40.0] |
| full_info - communication, stated | +28.0 | [+16.0, +40.0] | [+11.0, +45.0] |
| communication - no_communication, unstated | +0.0 | [-13.0, +13.0] | [-18.0, +18.0] |
| full_info - communication, unstated | +41.0 | [+31.0, +51.0] | [+26.0, +55.0] |

<!-- END GENERATED: results -->

## Reproduce

```bash
uv run python -m studies.v2_eval.analyze studies/v2_eval/runs/20261116T091238Z_primary
uv run python -m studies.v2_eval.h1_investigation --check
uv run python -m studies.v2_eval.report --check
```

The first command rewrites `results.json` and `results.md` from the committed
episodes; `git diff` should show nothing. Re-running the calls themselves costs
money and needs a key; see the pre-registration §9.
