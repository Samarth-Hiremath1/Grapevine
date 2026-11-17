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
grapevine audit hidden_profile_v2            # card to stdout
grapevine audit hidden_profile_v2 --out cards/
```

The exit code is 0 when no check failed and 2 when one did, so an audit can
gate CI. `hidden_profile_v2` currently exits 2: it fails `solo_solvability`
(see [A2](audit.md#a2-a1-was-closed-for-name-counts-only-and-a-model-found-the-rest)).

From Python:

```python
from grapevine import audit, get_environment

env = get_environment("hidden_profile_v2")
card = audit(env, n_tasks=200, seed=env.seed_split().eval.start)
print(card.verdict, card.flagged_checks)
print(card.to_markdown())
```

## Read a card

Each check is `pass`, `warn`, `fail` or `skipped`, with a one-line summary and
the evidence behind it. A card passes when no check failed; warnings do not stop
it. Each check holds its false-alarm rate at 5%. A pass is a bound, not a
guarantee: `solo_solvability` reports the smallest single-view advantage the
audit could have detected, and for a task decided by summed evidence some
advantage always exists; [why](audit-battery.md#why-a-pass-is-a-bound).

## Next

- [Write an environment](writing-an-environment.md) and audit it.
- Run the examples: `python examples/02_write_an_environment.py`.
- [Train with GRPO](rl.md), behind the audit gate.
