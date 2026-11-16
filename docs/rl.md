# RL and GRPO

> **GRPO integration, smoke-tested; no training results in this release.**
>
> Everything on this page has been run only as a two-step CPU smoke test on a
> tiny *random* model with scripted partners. That proves the loop is wired. It
> does not show that anything learns, and nothing here should be read as if it
> did. `configs/rl_single_gpu.yaml` has never been run.

`grapevine.rl` wires Grapevine environments to TRL's `GRPOTrainer`, with the
audit as a check on the reward before training starts. It is behind an optional
extra so the core install stays light:

```bash
pip install "grapevine-mas[rl]"          # or, in a clone: uv sync --extra rl
grapevine train configs/rl_smoke_cpu.yaml --dry-run   # gate + plan, no model
grapevine train configs/rl_smoke_cpu.yaml             # two steps on CPU
grapevine eval --policy runs/<run>/policy             # held-out seeds
```

Written against **TRL 1.18**, pinned in the extra. The reward-function contract
was confirmed from the installed 1.18.0 source, not from memory: a synchronous
reward function is called on the main thread with `prompts`, `completions`,
`completion_ids`, `trainer_state`, `log_extra`, `log_metric`, and every dataset
column except `prompt` by name. `max_prompt_length` no longer exists in 1.18's
`GRPOConfig`, so it is never passed.

## What has and has not been run

| | Status |
|---|---|
| Two-step CPU smoke run, tiny random model, scripted partners | **run in CI**; `loss 0`, `grad_norm 0` |
| Frozen-partner isolation test, with a negative control | **run in CI** |
| LoRA: only adapter weights train; partner untouched | **run in CI** |
| Self-play: one step, recorded as not frozen | **run in CI** |
| `configs/rl_single_gpu.yaml`, a 0.5B model with LoRA | **not run** |
| Any multi-seed run, any learning curve, any accuracy | **not run** |

Why the smoke run's loss is exactly zero: a random model earns the same reward
(zero) on every completion, so every GRPO group has zero reward variance, every
advantage is zero, and the step changes nothing. TRL logs this as
`frac_reward_zero_std: 1`. That is the honest outcome of a wiring test, and it is
why the isolation test below adds a completion-dependent reward: otherwise "the
partner did not move" would be trivially true of a step that moved nothing.

## How a sample becomes a reward

Each dataset row is one agent's opening turn on one training task. The trainer
generates that turn. The reward function then regenerates the task from its
seed, plays the rest of the episode around the completion, and scores it with
the environment's own scorer. The gradient is on the opening message; the reward
is what the whole team achieved after it.

The trained agent always speaks first in round one. That is what lets its
prompt exist before the episode does: an agent that spoke second would need its
teammates' messages generated before the dataset could be built.

Every prompt in every turn states the task's objective — the question *and* the
scoring rule — and a test asserts it per turn. The v0 result in
`studies/underspecification/` was wrong because no prompt did. The prompts are
otherwise neutral: they do not tell agents to share or to ask, because a
training signal is supposed to teach that, and the study found the instruction
mattered only while the task was underspecified.

## Rewards

**Default: team outcome.** The environment's programmatic scorer applied to the
team's final answer. Verifiable, model-free, and already fuzzed by the audit's
`scorer_fuzz` check.

**Optional: an information-surfacing shaping term, off by default.** It pays a
policy for mentioning the facts the task says must be shared. That sounds like
exactly the behaviour a coordination environment wants, and it is collectable
without coordinating: one agent can recite its notes and never let the team
decide. The audit catches this with its `recite_without_answering` policy, so
**any positive `surfacing_weight` makes the gate refuse to start** unless
`--allow-flagged` is passed, and the manifest records that it was.

That is deliberate rather than a prohibition. Sparse outcome rewards are hard to
learn from and a shaping term may be worth its risk — but a run that optimised a
reward the audit flagged should say so.

**Credit.** `shared_credit` (every agent gets the team reward; the default),
`split_credit` (divided equally) and `surfacing_credit` (in proportion to what
each agent surfaced). None is counterfactual: difference rewards need
counterfactual replay, which is out of scope for this release.

## Partners

The v0 trainer had a real bug here. Its "frozen collaborators" were built from
the very model object the trainer was updating, so every optimiser step changed
them. Nothing was ever trained with it.

| `partners.kind` | Who plays the other agents | Frozen? |
|---|---|---|
| `frozen` | A **separately loaded** copy of a checkpoint (the policy's starting point by default), eval mode, `requires_grad` off | yes |
| `endpoint` | An OpenAI-compatible server (vLLM, Ollama, a hosted API) | yes |
| `scripted` | A deterministic stub, for CI. Turns tagged `synthetic` | yes |
| `self` | The policy itself — self-play | **no, by definition** |

`tests/test_rl_training.py` takes an optimiser step that demonstrably changes
the policy and checks that a frozen partner's weights hash identically, its
greedy output is byte-identical, and it shares no tensor storage with the
policy. It then rebuilds the v0 bug — a partner wrapping the policy object — and
requires that version to *fail* the same check, so the test is known to be able
to catch what it exists for.

Under LoRA the partner is the starting checkpoint, loaded separately, and the
policy client is bound to `trainer.model` — the PEFT-wrapped model, the only one
carrying the adapter. A test asserts that only `lora_` parameters train.

**Self-play** (`partners: {kind: self}`): one policy plays every agent, and every
agent's opening turn is a training sample. Turns other than the sampled one are
generated by the current policy without gradient. The manifest records
`partners_frozen: false`.

**Not implemented:** refreshing a frozen partner from the policy every N steps.

## The audit gate

Before any model is loaded, `grapevine train` audits the configured environment
**with the reward the run will optimise** — the scorer wrapped so the shaping
term is included — on the environment's **training** seeds, and refuses to
start if any check fails. It also refuses an environment that declares no
train/eval seed split, since nothing would then stop a run training on the
tasks it reports; v0 `hidden_profile` declares none.

`--allow-flagged` overrides it. The override, the card's hash, its verdict and
the list of failed checks all go into the manifest, and the run is marked not
reportable.

## The run manifest

`runs/<run>/manifest.json` records the model, seed, environment name, version
and config, the Validity Card hash and verdict, the reward config, the partners
and whether they were frozen, the mode and trained roles, provenance at start
and end (commit, dirty tree, library versions), and the global step.

It also records **`reportable`**, with reasons. A run is not reportable when its
partners were scripted, when it names no pre-registration under `docs/prereg/`,
when it was a dry run, or when it trained on a flagged environment. In this
release every run is non-reportable, because none has a pre-registration.

## Configs

- `configs/rl_smoke_cpu.yaml` — tiny random model, scripted partners, two steps.
  Runs in CI. Every trajectory is synthetic.
- `configs/rl_single_gpu.yaml` — `Qwen/Qwen2.5-0.5B-Instruct`, frozen partners,
  LoRA r=16, eight generations per prompt. First line: `# not run`. Reasonable
  defaults, not tuned values.

Every key is validated, and an unknown key is an error: a typo in a reward weight
would otherwise change what a run trains on without changing what its config
appears to say.

## Evaluating a policy

`grapevine eval --policy <path>` plays every agent with the policy on the
environment's held-out **eval** seeds (or `--split pilot`), and refuses the
training split. It reports accuracy with an exact Clopper-Pearson interval,
parse failures and mean reward — and, on exactly the same tasks, the baselines a
policy has to beat: chance, the best content-blind shortcut the audit knows, a
team that discusses only common ground, and a team that never talks.

On `hidden_profile_v2` every baseline sits at or below chance by construction,
which makes its eval split the shortcut-removed probe: a policy cannot score
there by counting names or trusting the majority. On v0 `hidden_profile` the same
report would have shown a content-blind shortcut at 100%, which is the number
any trained policy would have had to beat for its score to mean anything.

A report involving any scripted turn is marked `synthetic: true` and
`reportable: false`.

## What is deliberately not here

- **TRL's experimental `rollout_func`.** It would put gradient on every turn of
  an episode rather than only the opening, at the cost of handling generation
  and log-probabilities ourselves. Self-play here trains every role's opening
  turn instead.
- **A `verifiers` adapter.** The v1 multi-agent API that fits Grapevine is not
  released on PyPI; see `docs/decisions.md`.
- **vLLM generation, multi-GPU, NeMo-RL.** `docs/notes/nemo_rl.md` is an archived
  analysis of a NeMo-RL backend, not something built.
- **Counterfactual credit assignment.**
- **Any training result.**
