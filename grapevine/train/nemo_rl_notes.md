# Attempting the Grapevine smoke config on NVIDIA NeMo-RL

**Status: did not reach a training step.** NeMo-RL installed cleanly, but its GRPO path has no
CPU-capable generation backend, so the Grapevine CPU smoke config cannot run on it. Grapevine v0
therefore stays on Hugging Face TRL, which does have an HF-based CPU generation path and lets the
2-step smoke test run in CI.

Everything below is a record of an attempt actually performed — commands, versions, and verbatim
errors. Nothing here is reconstructed from memory or documentation.

## Environment

| Item | Value |
| --- | --- |
| OS | macOS 15.6, `arm64` (Apple silicon), CPU-only — no NVIDIA GPU |
| uv | 0.11.29 (`901092ee1`, 2026-07-15) |
| NeMo-RL | `0.6.0+bbc5808`, commit `bbc58087a4d718250d51a95460f9b0c4cdd004a1` (2026-07-19) |
| Python (NeMo-RL) | 3.13.14 |
| Python (Grapevine) | 3.11.4 |
| torch | 2.11.0 |
| transformers | 5.8.1 |
| ray | 2.56.1 |
| vllm | not installed (no macOS/CPU wheel used) |

## What happened, in order

### 1. `pip install nemo-rl` gives an empty placeholder package

```bash
uv pip install nemo-rl
# + nemo-rl==0.0.0
```

The PyPI distribution is version `0.0.0`. It carries the official project summary
("NeMo RL: A Scalable and Efficient Post-Training Library…") and the Apache-2.0 license, so it is a
genuine NVIDIA placeholder rather than a typosquat — but it ships no functional code:

```python
>>> import nemo_rl; dir(nemo_rl)
['package_info']          # only __init__.py + package_info.py
>>> from nemo_rl.algorithms.grpo import GRPOTrainer
ModuleNotFoundError: No module named 'nemo_rl.algorithms'
```

Also note `Requires-Dist = None` — the placeholder declares no dependencies, so a naive
`pip install nemo-rl` silently produces an unusable environment with no error. Installation must be
done from source.

### 2. Python version constraint conflicts with Grapevine

`pyproject.toml` pins:

```toml
requires-python = ">=3.13.13,<3.14"
```

Grapevine targets Python 3.11, so NeMo-RL cannot share Grapevine's virtualenv. This is a hard
constraint, not a warning — the install aborts on a 3.11 interpreter. For this attempt I provisioned
a separate 3.13.14 environment (`uv python install 3.13`).

Worth flagging: a `>=3.13.13` floor is unusually aggressive (3.13.13 is a recent patch release), and
it forecloses the 3.10–3.12 range most of the surrounding RL ecosystem still targets.

### 3. Cloning without submodules produces a misleading uv error

```bash
git clone --depth 1 https://github.com/NVIDIA-NeMo/RL.git NeMo-RL
cd NeMo-RL && uv pip install -e .
```

```
× Failed to build `nemo-rl @ file:///private/tmp/NeMo-RL`
├─▶ Failed to parse entry: `nemo-gym`
╰─▶ `nemo-gym` references a workspace in `tool.uv.sources` (e.g., `nemo-gym
    = { workspace = true }`), but is not a workspace member
```

The message points at `tool.uv.sources`/workspace configuration, which reads like a packaging bug in
`pyproject.toml`. The actual cause is unrelated: `tool.uv.workspace` declares the member

```toml
members = ["3rdparty/Gym-workspace/Gym", "research/template_project"]
```

and `3rdparty/Gym-workspace/Gym` is a **git submodule** (per `.gitmodules`). A plain `git clone`
leaves that directory empty, so the workspace member does not exist and uv reports a confusing
"not a workspace member" error instead of "submodule not initialized."

**Fix:**

```bash
git submodule update --init --recursive --depth 1
```

This is the single most reportable item here: a first-time contributor following a normal
clone-then-install flow gets an error that misdirects them toward the packaging config. See the
draft issue at the end.

### 4. Source install succeeded on macOS arm64

After initializing submodules, `uv pip install -e .` completed successfully, resolving `torch==2.11.0`,
`transformers==5.8.1`, `ray==2.56.1`, and ~200 further packages. The dependency set is
platform-guarded well: CUDA-only components (`nvidia-cudnn-cu13`, `deep_ep`, `tilelang`,
`nvidia-nvshmem-cu13`, prebuilt `flash-attn` wheels) are correctly gated behind
`sys_platform == 'linux'` markers, so the macOS install did not attempt any CUDA build. Imports work:

```python
>>> import nemo_rl; nemo_rl.__version__
'0.6.0+bbc5808'
>>> from nemo_rl.algorithms import grpo   # OK
```

Credit where due — a large CUDA-centric project installing cleanly on CPU-only macOS is not a given.

### 5. Running GRPO fails: no CPU generation backend

```bash
python examples/run_grpo_sliding_puzzle.py
```

```
File "nemo_rl/algorithms/grpo.py", line 986, in init_vllm
    pg = VllmGeneration(cluster=inference_cluster, config=generation_config)
File "nemo_rl/models/generation/vllm/vllm_generation.py", line 184, in __init__
    cluster._init_placement_groups(...)
File "nemo_rl/distributed/virtual_cluster.py", line 813, in _init_placement_groups
    raise ResourceInsufficientError(
nemo_rl.distributed.virtual_cluster.ResourceInsufficientError: Maximum number of retries reached (6).
Cluster resources may be insufficient or cluster itself is highly unstable.
```

GRPO builds a Ray virtual cluster and requests a placement group for a vLLM generation worker. With
no GPU, the placement group is never satisfiable; Ray retries six times and gives up.

This is not a tuning problem — it is structural. `nemo_rl/models/generation/` contains exactly three
backends:

```
nemo_rl/models/generation/{megatron,sglang,vllm}
```

and `nemo_rl/algorithms/grpo.py` dispatches on `backend in {"megatron", "vllm", "sglang"}`. All three
are GPU-only inference stacks. **There is no Hugging Face / CPU generation backend**, so there is no
configuration that runs a NeMo-RL GRPO step on a CPU-only machine.

A secondary friction point: the failure surfaces as a generic Ray `ResourceInsufficientError` after
~6 retries rather than an upfront "no GPUs detected; backend `vllm` requires CUDA" precondition
check. The retry loop also makes the failure slow.

## Conclusion for Grapevine

| | TRL | NeMo-RL |
| --- | --- | --- |
| Python | 3.9+ (works with Grapevine's 3.11) | 3.13.13+ only |
| CPU generation | yes (HF `generate`) | no |
| CI smoke test possible | yes | no |
| Multi-GPU / large-scale training | limited | strong (Ray + vLLM/Megatron) |

Grapevine v0 keeps **TRL**, because the ability to run a real 2-step GRPO smoke test on CPU in CI is
a core requirement of the project — it is what proves the loop is wired without access to a GPU.

NeMo-RL remains attractive for the *full* training runs on the roadmap: it is built for exactly the
multi-GPU scale-out Grapevine will need later, and its `EnvironmentInterface`

```python
class EnvironmentInterface(abc.ABC, Generic[MetadataT]):
    def step(self, message_log_batch, metadata) -> EnvironmentReturn: ...
    def global_post_process_and_metrics(self, batch) -> tuple[BatchedDataDict, dict]: ...
```

is a clean fit for Grapevine's multi-agent rollout: `step` receives OpenAI-style message logs and
returns per-episode rewards, which maps directly onto our transcript + verifiable-reward model. A
future `grapevine/train/nemo_backend.py` would implement this interface and reuse
`grapevine.rewards` unchanged.

**Retry conditions:** revisit when a GPU host is available, or if NeMo-RL adds a CPU/HF generation
backend for smoke testing.

## Draft upstream issue

> **Title:** Confusing `nemo-gym ... is not a workspace member` error when cloning without submodules
>
> **Environment:** NeMo-RL `bbc58087a4d718250d51a95460f9b0c4cdd004a1`, uv 0.11.29, Python 3.13.14,
> macOS 15.6 arm64.
>
> **Repro:**
> ```bash
> git clone --depth 1 https://github.com/NVIDIA-NeMo/RL.git && cd RL
> uv pip install -e .
> ```
>
> **Actual:**
> ```
> × Failed to build `nemo-rl @ file:///.../RL`
> ├─▶ Failed to parse entry: `nemo-gym`
> ╰─▶ `nemo-gym` references a workspace in `tool.uv.sources`, but is not a workspace member
> ```
>
> **Cause:** `tool.uv.workspace.members` includes `3rdparty/Gym-workspace/Gym`, which is a git
> submodule. Without `--recurse-submodules` the directory is empty, so uv cannot resolve the
> workspace member — but the error blames `tool.uv.sources`, sending you to inspect `pyproject.toml`
> rather than to run `git submodule update --init`.
>
> **Suggested fixes:** (a) state `git clone --recurse-submodules` in the README install steps; and/or
> (b) add a preflight check that emits "submodule `3rdparty/Gym-workspace/Gym` is not initialized —
> run `git submodule update --init --recursive`" when a declared workspace member directory is empty.
>
> **Secondary (separate issue):** GRPO on a machine with no GPU fails after ~6 Ray placement-group
> retries with a generic `ResourceInsufficientError`. An upfront check ("backend `vllm` requires
> CUDA; no GPUs detected") would fail faster and much more legibly.
