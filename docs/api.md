# API reference

Everything in `grapevine.__all__` is public and follows semantic versioning.
Anything else may change in any release.

## Package

::: grapevine
    options:
      show_submodules: false
      members: false

## The environment protocol

::: grapevine.protocol

## The audit

::: grapevine.audit

## Environments

::: grapevine.envs

::: grapevine.envs.venue_choice

::: grapevine.envs.hidden_profile_v2

## Claims

`grapevine verify-claims` re-derives every number registered in
`docs/claims.yaml` and requires it to appear verbatim in its document.

::: grapevine.claims

## RL

Needs the `rl` extra for training; the gate and rewards import without it.

::: grapevine.rl
