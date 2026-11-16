# Pre-registration: does the v0 result survive on an audited environment?

**Status: pre-registered, not run.** Committed 2026-11-15, before any call to a
model for this study. No pilot has been run. Every document reports this result
as `not run` until a primary run is committed under `studies/v2_eval/runs/`.

**Models chosen and pilot approved 2026-11-15** (§11). The primary run needs its
own approval after the pilot.

The design is in `studies/v2_eval/design.py`, the runner in `run.py`, the
analysis in `analyze.py`. This document is written from that code. If the two
ever disagree, the code is what ran, and the disagreement is a deviation to be
recorded in §11.

---

## 1. Question

The v0 study (`studies/underspecification/`) found that, with the task's
question and scoring rule stated, three communicating agents matched a single
agent holding every fact: 100/100 and 99/100 against 100/100. Without them, the
communicating teams trailed by double digits, and the gap had looked like a
coordination failure.

But v0's environment fails its own audit. Counting how often each candidate's
name appears solved 200 of 200 tasks, and each agent's private notes named only
the correct candidate. "The team matched the single agent" may therefore have
meant "both counted names".

`hidden_profile_v2` removes both shortcuts and passes all thirteen checks
(`environments/hidden_profile_v2/validity_card.md`). **Does the v0 result hold
on it?**

## 2. Hypotheses

Stated before any data, with the direction of each.

- **H1 — no communication fails, with or without the objective.** On v2 a single
  agent's view favours the decoy under the scoring rule, and its private notes
  point at a non-gold option by construction. Predicted: accuracy at or below
  25% chance in both `no_communication` cells.
- **H2 — stating the objective helps wherever the information is available.**
  v2 mixes supporting facts with logistics sentences that name candidates but
  count for nobody, and only the stated rule says which is which. Predicted:
  `stated − unstated` > 0 in `full_info` and in `communication`.
- **H3 — with the objective stated, communication matches full information.**
  The v0 finding. Predicted: `full_info − communication`, objective stated,
  within ±5 points with its 95% interval including 0.
- **H4 — full information is near ceiling with the objective stated.** Predicted:
  `full_info`, stated, at or above 90%. Every other number is read against this
  one.

## 3. Environment and tasks

`hidden_profile_v2` v2, default configuration: 3 agents, 4 options, one
gold-supporting fact per agent (two on seeds that draw the larger support
level), margin 1, all three domains (hiring, vendor, site). Frozen sentence pool,
SHA-256 `798d96e46481df23d857f769da6905ffa8eba9e01043dc3cc0595248dc3da4ee`.
Gold answers come from the generator's construction, never from a model.

| Phase | Seeds | Tasks per cell | Source |
|---|---|---|---|
| Pilot | 9000–9019 | 20 | v2's declared `pilot` split |
| Primary | 10000–10099 | 100 | v2's declared `eval` split |

Pilot and primary seeds are disjoint, and that is enforced in code:
`Design.__post_init__` refuses overlap and refuses seeds outside the declared
splits, and `SeedSplit` refuses overlapping splits. No seed in either phase is a
training seed.

## 4. Conditions

Six cells per model. Every task is run in every cell, so all contrasts are
paired by task.

| Condition | Calls per task | What the agent sees |
|---|---:|---|
| `full_info` | 1 | Every fact, laid out exactly as an agent's view is (presentation-matched; v0's L4) |
| `no_communication` | 3 | One agent's view each; majority vote, ties broken uniformly at random seeded by task id |
| `communication` | 7 | One agent's view each; 2 rounds of discussion, agents 0, 1, 2 in order; agent 0 then decides |

Each crossed with **objective `stated`** (the question and scoring rule at the
top of every prompt) and **`unstated`** (omitted; nothing else changes).

Prompts are neutral: no condition tells agents to share facts or to ask for
them. In v0 that instruction mattered only while the task was unstated.

## 5. Exact prompts

System prompt, every call in every cell:

```text
You are taking part in a group decision. Be concise.
```

The one line that says which arm a prompt belongs to:

- `full_info`: `You hold every fact relevant to this decision; there is nobody to consult.`
- `no_communication`: `You hold only part of the evidence and must decide alone: there is no discussion, and you will never see what the others hold.`
- `communication`: `You hold only part of the evidence; your teammates hold the rest, and you can talk to them before deciding.`

Decision call (every cell), with `{discussion}` empty except in `communication`,
where it is `Full team discussion:` followed by the transcript:

```text
{marker}

{objective}{context}

{discussion}Choose exactly one of these options: {options}.
Respond with only a JSON object: {"answer": "<one option exactly as written>"}.
```

Discussion call (`communication` only):

```text
{marker}

{objective}{context}

Conversation so far:
{history}

It is your turn (round {round_no} of 2). Write a short message to your teammates. Do not give a final answer yet.
```

`{objective}` is the task's `Objective.statement()` followed by a blank line, or
empty. `{context}` is the agent's view: "Facts known to everyone:" then "Facts
only you know:". For `full_info` it is every fact in the same two blocks.

**The full text of every opening prompt is frozen by hash**, before any run:

| Phase | Opening prompts | SHA-256 |
|---|---:|---|
| Pilot | 320 | `7a97e5dee30b0144a2c74be9a96520bacc1f572c909160130b34910a918bb4e5` |
| Primary | 1600 | `1fde107ce6d62d149bd8621345ac516ec18c75df4aa88a09338da334644d60b5` |

`studies/v2_eval/prompts_sample.md` holds the complete text for task
`hidden_profile_v2-10000` in all six cells. `python -m studies.v2_eval.freeze
--check` re-derives both and runs in CI. Later discussion turns embed what the
model said and cannot be frozen in advance; their filled-in text is logged per
call.

**The prompts are audited, not just written down.** `EvalDesign` exposes the six
arms to the battery. The `objective` check fails exactly the three `unstated`
arms — that is the manipulation — and `condition_diff` finds that all 15 pairs
of arms differ in framing only by what each declares: its marker line, the
communication arm's discussion scaffolding, and the objective statement.
`tests/test_v2_eval.py` asserts both.

## 6. Settings

- Output cap: **1,200 tokens per call**, reasoning tokens included. v0 used 400
  and lost four answers to what was probably truncation (`docs/audit.md` L10).
- Temperature: 0.7 for discussion, 0.0 for decisions, **where the model accepts
  one**. GPT-5- and GPT-6-family models are sent no temperature and run at their
  default of 1.0; this is recorded per model in the manifest
  (`temperature_honoured`). For `gpt-6-luna` this treatment is **unverified**:
  its model page lists reasoning-token support but does not say how it handles
  `temperature` or `max_tokens`. If the first pilot call rejects a parameter, the
  fix is recorded in §11 before the primary run.
- Reasoning effort: the provider default. Not set.

## 7. Metrics and analysis

The analysis script is `studies/v2_eval/analyze.py`, committed with this
document. It is run once, on the primary run, and its output is the result.

**Per cell:** accuracy with an exact Clopper-Pearson 95% interval; parse
failures; truncated episodes; decoy choices; ties (no communication).

**Scoring of failures.** An episode is correct only if its parsed answer is the
gold option **and no call in it was truncated**. A truncated or unparsable
episode counts as incorrect and is counted separately, so a reader can see how
much of a cell's error is failure to answer rather than a wrong answer.

**Seven contrasts per model**, paired by task id, each as a mean difference in
correctness with a paired-bootstrap 95% interval (10,000 resamples, seed
20261115) and a Bonferroni-adjusted interval for the family of seven:

1. objective effect in `full_info` (`stated − unstated`)
2. objective effect in `no_communication`
3. objective effect in `communication`
4. `communication − no_communication`, stated
5. `full_info − communication`, stated — **the H3 contrast**
6. `communication − no_communication`, unstated
7. `full_info − communication`, unstated

Models are analysed and reported separately. Nothing is pooled across models.
The script refuses to build a table from a synthetic run, from a pilot, or from
an incomplete run unless told to, in which case the output says so first.

## 8. Budget and approval

Estimates from `python -m studies.v2_eval.run --dry-run`, with input tokens from
the actual prompts and output at either v0's measured 109.4 tokens per call
(794,186 completion tokens over 7,260 calls on `gpt-5.6-luna`, from the committed
manifests) or with every call at the 1,200-token cap:

| Model | Price in / out per 1M | Pilot (440 calls) | Primary (2,200 calls) | Primary, every call at cap |
|---|---|---:|---:|---:|
| `gpt-5.6-luna` | $0.20 / $1.20 | $0.1115 | $0.5591 | $3.4383 |
| `gpt-6-luna` | $0.10 / $0.50 | $0.0509 | $0.2555 | $1.4552 |
| `gpt-4o-mini` | $0.15 / $0.60 | $0.0692 | $0.3472 | $1.7867 |
| **All three** | | **$0.2316** | **$1.1618** | **$6.6802** |

Prices from developers.openai.com/api/docs/pricing, checked 2026-11-15.
Committed spend before this study: $1.5322 of the release's $10. Pilot plus
primary on all three models, every call at the cap, would bring the total to
$9.55.

A live run refuses to start without `--approve-usd`, refuses an approval below
the estimate or past the remaining budget, and stops when live spend reaches the
approval. A run that stops early is kept and reported as incomplete.

**Only one provider is available.** The brief asked for up to three inexpensive
current models from different providers; only an OpenAI key exists. All three
candidates are OpenAI models of different families (`gpt-5.6`, `gpt-6`, `gpt-4o`),
which is variety of a kind but is not cross-provider. No claim of generality
across providers will be made.

## 9. Procedure

1. Samarth chooses the models and approves the pilot estimate (§11).
2. **Pilot**, seeds 9000–9019, every chosen model, every cell. The pilot is
   checked for exactly three things: every call parses as a request (no
   rejected parameter), the truncation rate, and the parse-failure rate. Its
   accuracies are not looked at for any decision.
3. **The pilot may change only:** the output cap, raised if more than 2% of
   pilot calls were truncated; and a request parameter a model rejected. Any
   change is committed to §11 before step 4. Nothing else changes, and the pilot
   is not re-run to get a better pilot.
4. Samarth approves the primary estimate.
5. **Primary**, seeds 10000–10099, once.
6. `python -m studies.v2_eval.analyze <run>`, once. The output is committed as is.

## 10. How each outcome will be read

Decided now, so the reading cannot be fitted to the result.

**H3, the main contrast** (`full_info − communication`, stated):

- **Interval includes 0 and the mean is within ±5 points.** The v0 finding
  replicates on an environment with no known shortcut: once agents are told what
  they are deciding, a communicating team does as well as one agent holding
  everything. Reported as a replication on one environment and the chosen
  models, not as a general property of LLM teams.
- **`full_info` higher, Bonferroni interval excluding 0.** A coordination gap that
  is not explained by an unstated objective, on an environment that passes its
  audit — the first such evidence in this repository. Before it is reported,
  transcripts are audited for truncation, parse failures, an aggregator that
  ignored facts that were surfaced, and logistics sentences treated as support,
  and that audit is published with the number (rule 11).
- **`communication` higher, Bonferroni interval excluding 0.** Treated as
  suspicious, because a team cannot hold more information than the single
  agent who holds all of it. Checked for truncation or parse failures
  concentrated in `full_info`, and for a framing difference the audit missed;
  reported only with that check.
- **Interval includes 0 but is wider than ±10 points.** Inconclusive at this N.
  Reported as inconclusive, not as a replication.

**H1** (`no_communication`): if either cell's Clopper-Pearson lower bound is above
25%, a single agent can do better than chance alone on v2, which the audit says
it cannot. That would be a gap in the battery, investigated and reported as a
finding about the audit before anything else is reported.

**H2** (objective effects): a positive effect in `full_info` and `communication`
reproduces v0. A null effect in `full_info` would mean the rule is recoverable
from the facts without being stated, and the v0 underspecification explanation
would not carry over to this environment.

**H4**: if `full_info`, stated, is below 90%, the task is harder for the model
than v0's was, and every communication result is read as bounded by what one
agent can do with everything — a capability result, not a coordination result.

**Across models:** each model's result stands alone. If they disagree, that is
reported as disagreement, not averaged away.

**Whatever comes out is the result.** It ships whether it supports, contradicts
or fails to resolve any hypothesis (rule 5).

## 11. Decisions and deviations

Recorded here, dated, before the step they affect.

| Date | Decision or deviation | Reason |
|---|---|---|
| 2026-11-15 | Pre-registration committed; no run made | Agreed at the end of Step 1: pre-register first, decide on spending afterwards |
| 2026-11-15 | Models: **`gpt-5.6-luna`, `gpt-6-luna`, `gpt-4o-mini`** | Samarth's choice, on the §8 estimates |
| 2026-11-15 | Pilot approved with a hard ceiling of **$1.34** (`--approve-usd 1.34`) | Samarth's approval; estimate $0.2316 at v0 output length, $1.3353 if every call hits the cap |
| 2026-11-15 | Runner now loads the key from `.env`, and refuses to run without one | A fix found before any call, not a design change: the runner had never loaded `.env`, so it could not have reached the API |
| 2026-11-16 | Pilot run `20261116T074017Z_pilot` committed unchanged: 1,320 calls, 360/360 episodes, $0.2521 | Run as approved. The three pilot checks: no rejected parameters (0 errors; every call returned `stop` or `length`); 1 truncated call of 1,320, below the 2% threshold; 0 parse failures. Pilot accuracies were not read |
| 2026-11-16 | **No change** to the design: output cap stays at 1,200 tokens, prompts and models unchanged | None of the three checks crossed its threshold, so §9 allows no change |
| 2026-11-16 | Primary run approved with a hard ceiling of **$6.69** (`--approve-usd 6.69`) | Samarth's approval; estimate $1.1618 at v0 output length, $6.6802 if every call hits the cap; $1.7843 already committed |
| 2026-11-16 | Primary run `20261116T091238Z_primary` committed unchanged with the analysis output, run once: 6,600 calls, 1,800/1,800 episodes, $1.2812, 14 truncated calls | Run as approved |
| 2026-11-16 | **H1 reading triggered** for `gpt-4o-mini` (`no_communication`/unstated, lower bound 35.0%). Investigated first, as §10 requires: `studies/v2_eval/h1_investigation.md`. No other result reported yet | Applying the scoring rule to an agent's private facts alone picks gold for 300/300 agents; the battery has no such solver |
