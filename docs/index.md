# Grapevine

Grapevine checks whether a multi-agent LLM eval or RL environment measures
coordination, before you trust a result from it.

A distributed-information task is one where no single agent holds enough to
answer, so the answer only becomes derivable once agents pool what they know.
That premise is what makes a coordination claim mean anything, and it is also
what quietly breaks. `grapevine audit` checks for the ways it breaks and writes
a Validity Card: thirteen checks, offline, no API key, about a second on 200
tasks.

```bash
grapevine audit hidden_profile_v2
```

## Why it exists

This repository's first result was wrong. A coordination failure that survived
full information sharing turned out to be objective underspecification: no
prompt told the models what they were scored on. With the question and the
scoring rule stated, the communicating teams matched a single agent given every
fact. The audit that found it is [the v0 case study](audit.md).

The battery was then built from that audit, and it found something the hand
audit had missed. Its first pre-registered eval then found something the
battery had missed: [A2](audit.md#a2-a1-was-closed-for-name-counts-only-and-a-model-found-the-rest).
Both are in the record, with the numbers that went with them.

## What is in this release

| | Status |
|---|---|
| `grapevine audit` and the Validity Card | Calibrated against planted flaws; [how](audit-battery.md) |
| `hidden_profile_v2` | Bundled; fails one check, `solo_solvability`, found by its own eval |
| `grapevine.rl` (TRL GRPO) | **GRPO integration, smoke-tested; no training results in this release.** |
| The v0 case study | Audited and reproducible from committed runs |
| A pre-registered eval on `hidden_profile_v2` | Run once, $1.28; [read against its pre-registration](https://github.com/Samarth-Hiremath1/Grapevine/blob/main/studies/v2_eval/README.md) |

Results from the v0 study are on GitHub:
[`docs/results.md`](https://github.com/Samarth-Hiremath1/Grapevine/blob/main/docs/results.md).
