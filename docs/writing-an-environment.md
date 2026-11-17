# Writing an environment

An environment implements one interface, `grapevine.Environment`:

| Method | Required | What the audit does with it |
|---|---|---|
| `generate(seed)` | yes | Builds the tasks every check runs on. Must be deterministic. |
| `conditions(task)` | no | Enables `objective` and `condition_diff`: are the arms told what they are deciding, and do they differ only as declared? |
| `seed_split()` | no | Enables `seed_split`, and stops an RL run training on the seeds it reports. |
| `config_summary()` | no | Recorded on the card. |

A task is a `DistributedTask`: an `Objective` (a question and a scoring rule,
both of which must reach the prompts verbatim), an answer space, the gold
answer from the generator's construction, one `AgentView` per agent (shared and
private `InfoUnit`s), the units declared required, and a programmatic scorer.

Each `InfoUnit` says which option it supports, or none. That label is what lets
the audit apply the scoring rule itself, and what lets it tell a solver that
reads the facts from one that only counts names.

## A complete example

`examples/02_write_an_environment.py` is a whole environment in one file. The
comments say which check each design choice is there for. The three that matter
most:

- **Every block names every option equally often.** Each agent's private notes
  name each option exactly six times, as supporting facts plus neutral
  mentions, and the shared notes support each option once. So no name count,
  anywhere, says anything. Padding the shared block to equalise totals, as an
  earlier version did, is itself a leak: the gold option gets the least padding.
- **Nobody's notes are built to point anywhere.** Each option's total is split
  over the agents at random. Giving every agent private support for gold and
  more for one other option, as earlier versions did, is solved from one view by
  "pick the option I hold support for that is not the most-named".
- **Gold wins by exactly one fact.** That makes every gold fact necessary, and
  keeps the single-view lean as small as an additive task allows.

!!! warning "Expect `solo_solvability` and `reward_hacking` to fail sometimes"
    For a task decided by summed evidence, some single view always leans
    towards the answer; here the best possible single-view accuracy is about
    30% against 25% chance. The audit sees a lean that small on some seed ranges
    and not others, and always at large n. When it fires on this design it
    fires only through probes that read the support facts. That is the
    irreducible lean, not a shortcut: see
    [why a pass is a bound](audit-battery.md#why-a-pass-is-a-bound).

```python
--8<-- "examples/02_write_an_environment.py"
```

## Audit it

```bash
python examples/02_write_an_environment.py
```

Or register it and use the CLI:

```python
from grapevine import register_environment
register_environment("venue_choice", VenueChoice)
```
