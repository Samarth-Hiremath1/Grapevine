"""Reproduce the HiddenBench-style gap on Grapevine's generated tasks.

Runs ``K`` tasks through two conditions using an inexpensive API model:

1. **single agent, full context** -- the upper bound (all facts in one context);
2. **distributed team** -- the same tasks with facts split across agents.

Results (accuracy per condition, gap-closure, surfacing rate, cost, seed) are
written to ``experiments/baseline/results.md``. API keys are read from the
environment; if none is set, the script generates the tasks, prints the exact
command to run, and exits 0 without fabricating any numbers.

Usage:
    python experiments/baseline/run_baseline.py --model gpt-4o-mini --k 30

Environment:
    OPENAI_API_KEY   (for --provider openai, the default)
    ANTHROPIC_API_KEY(for --provider anthropic)
    OPENAI_BASE_URL  (optional; for OpenAI-compatible gateways)
"""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

from grapevine.envs import REGISTRY
from grapevine.eval.metrics import EvalMetrics, compute_metrics
from grapevine.rollout.client import AnthropicClient, LLMClient, OpenAICompatibleClient
from grapevine.rollout.engine import (
    Episode,
    RolloutConfig,
    TranscriptWriter,
    run_episode,
    run_single_agent,
)

RESULTS_PATH = Path(__file__).parent / "results.md"
TRANSCRIPT_PATH = Path(__file__).parent / "transcripts.jsonl"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--provider", choices=["openai", "anthropic"], default="openai")
    p.add_argument("--model", default="gpt-4o-mini", help="inexpensive model id")
    p.add_argument("--family", choices=sorted(REGISTRY), default="hidden_profile")
    p.add_argument("--k", type=int, default=30, help="tasks per condition")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--agents", type=int, default=3, help="team size (distributed condition)")
    p.add_argument("--rounds", type=int, default=2, help="discussion rounds")
    p.add_argument("--concurrency", type=int, default=4, help="max concurrent episodes")
    return p.parse_args(argv)


def _has_key(provider: str) -> bool:
    return bool(
        os.environ.get("OPENAI_API_KEY")
        if provider == "openai"
        else os.environ.get("ANTHROPIC_API_KEY")
    )


def _make_client(provider: str, model: str) -> LLMClient:
    if provider == "anthropic":
        return AnthropicClient(model)
    return OpenAICompatibleClient(model)


def _build_env(family: str, n_agents: int):  # type: ignore[no-untyped-def]
    env_cls, config_cls = REGISTRY[family]
    # Give the team enough shared facts to satisfy the decoy-lead constraint.
    if family == "hidden_profile":
        return env_cls(
            config_cls(
                n_agents=n_agents,
                n_shared_facts=max(6, 2 * n_agents),
                n_private_facts_per_agent=2,
                n_distractors=4,
            )
        )
    return env_cls(config_cls(n_agents=n_agents))


async def _run_all(
    args: argparse.Namespace, client: LLMClient
) -> tuple[list[Episode], list[Episode]]:
    """Run both conditions over K tasks and return (team_episodes, single_episodes)."""
    env = _build_env(args.family, args.agents)
    tasks = env.generate_batch(args.k, args.seed)
    rollout_cfg = RolloutConfig(n_rounds=args.rounds, aggregation="aggregator")
    sem = asyncio.Semaphore(args.concurrency)

    async def team(task):  # type: ignore[no-untyped-def]
        async with sem:
            return await run_episode(task, client, rollout_cfg)

    async def single(task):  # type: ignore[no-untyped-def]
        async with sem:
            return await run_single_agent(task, client, rollout_cfg)

    team_eps = await asyncio.gather(*(team(t) for t in tasks))
    single_eps = await asyncio.gather(*(single(t) for t in tasks))
    return list(team_eps), list(single_eps)


def _render_results(args: argparse.Namespace, metrics: EvalMetrics) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    def pct(x: float | None) -> str:
        return "n/a" if x is None else f"{x * 100:.1f}%"

    return f"""# Baseline: HiddenBench-style gap on Grapevine tasks

_Generated {now} by `experiments/baseline/run_baseline.py`._

**Setup**: family=`{args.family}`, model=`{args.model}` (provider `{args.provider}`),
K={args.k} tasks/condition, team size={args.agents}, discussion rounds={args.rounds},
seed={args.seed}.

| Condition | Accuracy | Surfacing rate | Cost (USD) |
| --- | ---: | ---: | ---: |
| Single agent (full context) — upper bound | {pct(metrics.single_agent_accuracy)} | n/a | ${metrics.single_cost_usd:.4f} |
| Distributed team ({args.agents} agents, {args.rounds} rounds) | {pct(metrics.team_accuracy)} | {pct(metrics.surfacing_rate)} | ${metrics.team_cost_usd:.4f} |

- **Chance accuracy**: {pct(metrics.chance_accuracy)}
- **Gap-closure** (distributed vs. single-agent ceiling, chance-relative): {pct(metrics.gap_closure)}
- **Total cost**: ${metrics.team_cost_usd + metrics.single_cost_usd:.4f}

The distributed team is expected to trail the single-agent upper bound: the
private-fact surfacing rate above shows how much of the required information the
team actually pooled. Transcripts for inspection: `transcripts.jsonl`
(`grapevine view experiments/baseline/transcripts.jsonl`).
"""


def _render_not_run(args: argparse.Namespace) -> str:
    key_var = "OPENAI_API_KEY" if args.provider == "openai" else "ANTHROPIC_API_KEY"
    return f"""# Baseline: HiddenBench-style gap on Grapevine tasks

**Status: not yet run in this repository.** No results are recorded here because
no API key was available, and this project does not fabricate numbers.

To populate this file with real results, set an API key and run the experiment:

```bash
export {key_var}=...           # your key
python experiments/baseline/run_baseline.py \\
    --provider {args.provider} --model {args.model} \\
    --family {args.family} --k {args.k} --agents {args.agents} --rounds {args.rounds}
```

This runs {args.k} tasks/condition through the single-agent (full context) and
distributed-team conditions and rewrites this file with accuracy, surfacing rate,
gap-closure, and cost.
"""


def main(argv: list[str] | None = None) -> int:
    """Entry point: run the baseline, or emit the run command if no key is set."""
    args = parse_args(argv)

    if not _has_key(args.provider):
        env = _build_env(args.family, args.agents)
        tasks = env.generate_batch(args.k, args.seed)
        key_var = "OPENAI_API_KEY" if args.provider == "openai" else "ANTHROPIC_API_KEY"
        print(f"No {key_var} set — not calling any API and not fabricating results.")
        print(f"Generated {len(tasks)} '{args.family}' tasks (seed {args.seed}).")
        print("To run the baseline for real:")
        print(f"  export {key_var}=...")
        print(
            f"  python experiments/baseline/run_baseline.py --provider {args.provider} "
            f"--model {args.model} --family {args.family} --k {args.k} "
            f"--agents {args.agents} --rounds {args.rounds}"
        )
        RESULTS_PATH.write_text(_render_not_run(args), encoding="utf-8")
        print(f"Wrote placeholder status to {RESULTS_PATH}.")
        return 0

    client = _make_client(args.provider, args.model)
    team_eps, single_eps = asyncio.run(_run_all(args, client))

    with TranscriptWriter(TRANSCRIPT_PATH) as writer:
        for ep in team_eps:
            writer.write(ep)
        for ep in single_eps:
            writer.write(ep)

    metrics = compute_metrics(team_eps, single_eps)
    RESULTS_PATH.write_text(_render_results(args, metrics), encoding="utf-8")
    print(f"Wrote results to {RESULTS_PATH} (total cost ${client.total_cost_usd:.4f}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
