# Quickstart

## Install

The package is prepared for PyPI as `grapevine-mas`; the import name is
`grapevine`. It is **not published yet**. Until it is, install from a clone:

```bash
git clone https://github.com/Samarth-Hiremath1/Grapevine.git
cd Grapevine
uv sync --extra dev          # or: pip install -e ".[dev]"
```

Python 3.11, 3.12 and 3.13 are tested. The `rl` extra adds TRL, PEFT and torch,
and is only needed for `grapevine train`.

## Audit an environment

```bash
grapevine envs                               # what is bundled
grapevine audit venue_choice                 # the supported environment, card to stdout
grapevine audit venue_choice --out cards/
grapevine audit hidden_profile_v2            # a documented flawed case study
```

The exit code is 0 when no check failed and 2 when one did, so an audit can
gate CI. `venue_choice` exits 0 with a measured single-view advantage;
`hidden_profile_v2` exits 2, a reliable solo shortcut
(see [A2](audit.md#a2-a1-was-closed-for-name-counts-only-and-a-model-found-the-rest)).

From Python:

```python
from grapevine import audit, get_environment

env = get_environment("venue_choice")
card = audit(env, n_tasks=200, seed=env.seed_split().eval.start)
print(card.verdict, card.flagged_checks)
print(card.to_markdown())
```

## Read a card

Each check is `pass`, `warn`, `fail` or `skipped`, with a one-line summary and
the evidence behind it. A card passes when no check failed; warnings do not stop
it, and neither do `measured` (an advantage quantified, no failure confirmed) or
`inconclusive` (too little evidence). A pass is never a guarantee against
shortcuts; [the Validity Card](validity-card.md) says exactly what one can and
cannot establish.

## Next

- [Write an environment](writing-an-environment.md) and audit it.
- Run the examples: `python examples/02_write_an_environment.py`.
- [Train with GRPO](rl.md), behind the audit gate.
