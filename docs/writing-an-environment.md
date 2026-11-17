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

`examples/02_write_an_environment.py` is a whole environment in one file that
passes every check on its eval seeds. The comments say which check each design
choice is there for. The two that matter most:

- **Private notes must not point at the answer.** Each agent holds support for
  the gold option *and* more support for one other option. A hidden profile
  where every private supporting fact favours gold can be solved by one agent
  reading only its own notes; `hidden_profile_v2` is built that way, and fails.
- **Counting names must say nothing.** Pad with neutral mentions until every
  option is named equally often.

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
