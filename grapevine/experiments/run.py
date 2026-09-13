"""Entry point for the coordination ablation.

Runs the same procedurally generated hidden-profile tasks through four
conditions and writes everything needed to reproduce the numbers:

* ``full_info`` (A) -- one agent sees every fact. The accuracy ceiling.
* ``no_communication`` (B) -- N agents each see only their own private context
  and answer independently; the group answer is a majority vote.
* ``communication`` (C) -- the same N agents, but they discuss for ``n_rounds``
  before a designated aggregator answers. The prompt instructs fact-sharing.
* ``communication_neutral`` (D) -- identical to C except the discussion prompt
  does not instruct sharing or asking.

Conditions run on identical task seeds so comparisons are paired.

Usage:
    python -m grapevine.experiments.run --config configs/coordination_ablation.yaml

Every run writes to a fresh timestamped directory under ``output_dir``; nothing
is ever overwritten.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from grapevine.envs import REGISTRY
from grapevine.envs.base import Task
from grapevine.experiments.analysis import (
    ConditionSummary,
    paired_difference_ci,
    summarize_condition,
)
from grapevine.rollout.client import (
    AnthropicClient,
    LLMClient,
    OpenAICompatibleClient,
    RetryConfig,
    require_pricing,
)
from grapevine.rollout.engine import (
    TASK_STATEMENT,
    Episode,
    RolloutConfig,
    run_episode,
    run_no_communication,
    run_single_agent,
)
from grapevine.settings import has_key, key_var_for, load_env

CONDITIONS = (
    "full_info",
    "no_communication",
    "communication",
    "communication_neutral",
)

#: A and C with the task question and scoring rule shown. Opt-in via --conditions,
#: so the default command still reproduces the four-condition run.
RULE_CONDITIONS = ("full_info_rule", "communication_rule")
ALL_CONDITIONS = CONDITIONS + RULE_CONDITIONS


def _git_commit() -> str:
    """Return the current git commit hash, or 'unknown' outside a repo."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent.parent.parent,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _git_dirty() -> bool:
    """Return whether the working tree has uncommitted changes."""
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent.parent.parent,
        )
        return bool(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def load_config(path: str | Path) -> dict[str, Any]:
    """Load and lightly validate the experiment YAML."""
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for key in ("model", "env", "rollout", "run"):
        if key not in data:
            raise ValueError(f"config missing required section {key!r}")
    fam = data["env"].get("family", "hidden_profile")
    if fam != "hidden_profile":
        raise ValueError(
            f"family {fam!r} is not supported for this experiment. Only "
            "'hidden_profile' is used: split_evidence leaks the gold answer "
            "verbatim into one agent's context (see docs/decisions.md)."
        )
    return data


def build_env(cfg: dict[str, Any]) -> Any:
    """Instantiate the environment described by the config's ``env`` section."""
    env_cfg = dict(cfg["env"])
    family = env_cfg.pop("family", "hidden_profile")
    env_cls, config_cls = REGISTRY[family]
    # Base Env has a no-arg constructor; concrete envs take their config.
    return env_cls(config_cls(**env_cfg))  # type: ignore[call-arg]


def make_client(cfg: dict[str, Any]) -> LLMClient:
    """Build the LLM client, failing loudly if the model has no pricing entry."""
    model_cfg = cfg["model"]
    provider = model_cfg.get("provider", "openai")
    name = model_cfg["name"]
    # Raises if unpriced, so a run can never report a silent $0.00.
    require_pricing(name)
    retry = RetryConfig(
        max_retries=int(model_cfg.get("max_retries", 5)),
        base_delay=float(model_cfg.get("retry_base_delay", 0.5)),
    )
    if provider == "anthropic":
        return AnthropicClient(name, retry=retry)
    return OpenAICompatibleClient(name, retry=retry)


async def _run_condition(
    condition: str,
    tasks: list[Task],
    client: LLMClient,
    rollout_cfg: RolloutConfig,
    neutral_cfg: RolloutConfig,
    rule_cfg: RolloutConfig,
    concurrency: int,
) -> tuple[list[Episode], list[dict[str, Any]]]:
    """Run one condition over ``tasks``. Returns (episodes, failures).

    A task that raises is recorded in ``failures`` rather than silently dropped,
    so a partially failed run is visible in the output instead of quietly
    shrinking N.
    """
    sem = asyncio.Semaphore(concurrency)
    failures: list[dict[str, Any]] = []

    async def one(task: Task) -> Episode | None:
        async with sem:
            try:
                if condition == "full_info":
                    ep = await run_single_agent(task, client, rollout_cfg)
                elif condition == "full_info_rule":
                    ep = await run_single_agent(task, client, rule_cfg)
                elif condition == "communication_rule":
                    ep = await run_episode(task, client, rule_cfg)
                elif condition == "no_communication":
                    ep = await run_no_communication(task, client, rollout_cfg)
                elif condition == "communication_neutral":
                    ep = await run_episode(task, client, neutral_cfg)
                else:
                    ep = await run_episode(task, client, rollout_cfg)
            except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                failures.append(
                    {"task_id": task.task_id, "error": f"{type(exc).__name__}: {exc}"}
                )
                return None
        # Attach ground truth needed by the decoy metric and the condition label.
        ep.metadata["condition"] = condition
        ep.metadata["decoy_option"] = task.metadata.get("decoy_option")
        ep.metadata["seed"] = task.metadata.get("seed")
        ep.metadata["task_statement_shown"] = condition in RULE_CONDITIONS
        ep.metadata["prompt_style"] = (
            neutral_cfg.prompt_style
            if condition == "communication_neutral"
            else rollout_cfg.prompt_style
        )
        return ep

    results = await asyncio.gather(*(one(t) for t in tasks))
    return [e for e in results if e is not None], failures


def _fmt_pct(x: float | None) -> str:
    return "  n/a " if x is None else f"{x * 100:5.1f}%"


def _print_summary(summaries: dict[str, ConditionSummary], chance: float) -> None:
    """Print a compact human-readable results table to stdout."""
    print()
    print(f"{'condition':<18} {'N':>4} {'acc':>7} {'95% CI':>16} {'decoy':>7} {'parsefail':>10}")
    print("-" * 68)
    for cond in ALL_CONDITIONS:
        s = summaries.get(cond)
        if s is None:
            continue
        ci = f"[{s.accuracy_ci[0]*100:4.1f},{s.accuracy_ci[1]*100:5.1f}]"
        print(
            f"{s.condition:<18} {s.n:>4} {_fmt_pct(s.accuracy)} {ci:>16} "
            f"{_fmt_pct(s.decoy_rate)} {s.parse_failures:>10}"
        )
    print("-" * 68)
    print(f"chance = {chance*100:.1f}%")
    b = summaries.get("no_communication")
    if b is not None and b.tie_rate is not None:
        floor = b.accuracy_ties_incorrect
        floor_str = "n/a" if floor is None else f"{floor * 100:.1f}%"
        print(
            f"condition B tie rate = {b.tie_rate*100:.1f}%  |  "
            f"accuracy with ties scored incorrect = {floor_str}"
        )
    for key, name in (
        ("communication", "C instructed"),
        ("communication_neutral", "D neutral"),
        ("communication_rule", "C + rule"),
    ):
        s2 = summaries.get(key)
        if s2 is not None and s2.surfacing_rate is not None:
            print(f"{name} surfacing rate = {s2.surfacing_rate*100:.1f}%")


def main(argv: list[str] | None = None) -> int:
    """Run the ablation described by a YAML config."""
    parser = argparse.ArgumentParser(
        prog="python -m grapevine.experiments.run",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", required=True, help="path to the experiment YAML")
    parser.add_argument(
        "--label", default=None, help="override the run label used in the output dir name"
    )
    parser.add_argument(
        "--n-episodes", type=int, default=None, help="override run.n_episodes from the config"
    )
    parser.add_argument(
        "--seed-start", type=int, default=None, help="override run.seed_start from the config"
    )
    parser.add_argument(
        "--conditions",
        default=None,
        help=(
            "comma-separated subset of conditions to run "
            f"(default: {','.join(CONDITIONS)}; opt-in: {','.join(RULE_CONDITIONS)})"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="generate tasks and print the plan without making any API calls",
    )
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    run_cfg = dict(cfg["run"])
    if args.n_episodes is not None:
        run_cfg["n_episodes"] = args.n_episodes
    if args.seed_start is not None:
        run_cfg["seed_start"] = args.seed_start
    label = args.label or run_cfg.get("label", "run")

    n_episodes = int(run_cfg["n_episodes"])
    seed_start = int(run_cfg["seed_start"])
    concurrency = int(run_cfg.get("concurrency", 4))

    if args.conditions:
        selected = tuple(c.strip() for c in args.conditions.split(",") if c.strip())
        unknown = [c for c in selected if c not in ALL_CONDITIONS]
        if unknown:
            raise SystemExit(f"unknown condition(s): {unknown}. Choose from {ALL_CONDITIONS}")
    else:
        selected = CONDITIONS

    env = build_env(cfg)
    tasks = env.generate_batch(n_episodes, seed_start)
    chance = 1.0 / len(tasks[0].options)

    rc = dict(cfg["rollout"])
    rollout_cfg = RolloutConfig(
        n_rounds=int(rc.get("n_rounds", 2)),
        aggregation=str(rc.get("aggregation", "aggregator")),
        max_tokens=int(rc.get("max_tokens", 400)),
        temperature=float(rc.get("temperature", 0.7)),
        final_temperature=float(rc.get("final_temperature", 0.0)),
    )

    # Condition D: identical to C except the discussion prompt style.
    neutral_cfg = replace(rollout_cfg, prompt_style="neutral")
    # Rule arm: identical to the base config, plus the question and scoring rule.
    rule_cfg = replace(rollout_cfg, show_task=True)

    print(f"experiment : {label}")
    print(f"model      : {cfg['model']['name']} ({cfg['model'].get('provider','openai')})")
    print(f"env        : {cfg['env']} ")
    print(f"episodes   : {n_episodes} per condition, seeds {seed_start}..{seed_start+n_episodes-1}")
    print(f"rollout    : {rollout_cfg.n_rounds} rounds, temp {rollout_cfg.temperature} "
          f"(discussion) / {rollout_cfg.final_temperature} (answer), "
          f"max_tokens {rollout_cfg.max_tokens}")
    print(f"chance     : {chance*100:.1f}%")

    if args.dry_run:
        print("\n--dry-run: no API calls made.")
        print(f"first task id: {tasks[0].task_id}, options: {tasks[0].options}")
        return 0

    load_env()
    provider = cfg["model"].get("provider", "openai")
    if not has_key(provider):
        var = key_var_for(provider)
        print(
            f"\nERROR: {var} is not set, so no experiment can run.\n"
            f"Create a .env file (cp .env.example .env) and put your key in it, "
            f"or export {var} in this shell.\n"
            "Refusing to fabricate results.",
            file=sys.stderr,
        )
        return 2

    client = make_client(cfg)
    temp_honoured = bool(getattr(client, "supports_temperature", True))
    if not temp_honoured:
        print(
            f"\nNOTE: {cfg['model']['name']} rejects an explicit temperature, so the "
            f"configured {rollout_cfg.temperature}/{rollout_cfg.final_temperature} are NOT "
            "applied. Every call runs at the model default of 1.0, identically across all "
            "conditions."
        )
    started = datetime.now(UTC)
    out_root = Path(run_cfg.get("output_dir", "runs"))
    out_dir = out_root / f"{started.strftime('%Y%m%dT%H%M%SZ')}_{label}"
    out_dir.mkdir(parents=True, exist_ok=False)  # never overwrite a prior run

    all_failures: dict[str, list[dict[str, Any]]] = {}
    summaries: dict[str, ConditionSummary] = {}
    per_condition_correct: dict[str, list[float]] = {}

    for condition in selected:
        print(f"\nrunning condition: {condition} ...", flush=True)
        episodes, failures = asyncio.run(
            _run_condition(
                condition, tasks, client, rollout_cfg, neutral_cfg, rule_cfg, concurrency
            )
        )
        all_failures[condition] = failures
        if failures:
            print(f"  {len(failures)} episode(s) FAILED and were recorded, not dropped")
        if not episodes:
            (out_dir / "failures.json").write_text(
                json.dumps(all_failures, indent=2), encoding="utf-8"
            )
            print(
                f"  no episodes completed for {condition}; aborting. "
                f"failures written to {out_dir / 'failures.json'}",
                file=sys.stderr,
            )
            if failures:
                print(f"  first error: {failures[0]['error'][:300]}", file=sys.stderr)
            return 3
        with (out_dir / f"episodes_{condition}.jsonl").open("w", encoding="utf-8") as fh:
            for ep in episodes:
                fh.write(ep.to_jsonl() + "\n")
        summaries[condition] = summarize_condition(condition, episodes)
        # Keyed by task_id so the paired comparison aligns even if a task failed.
        per_condition_correct[condition] = [1.0 if e.correct else 0.0 for e in episodes]
        print(
            f"  done: acc={summaries[condition].accuracy*100:.1f}%  "
            f"cost=${summaries[condition].total_cost_usd:.4f}"
        )

    finished = datetime.now(UTC)
    total_cost = sum(s.total_cost_usd for s in summaries.values())

    # Paired comparisons on identical task seeds (only where N matches).
    paired: dict[str, Any] = {}
    for lhs, rhs in (
        ("communication", "no_communication"),
        ("communication_neutral", "no_communication"),
        ("communication", "communication_neutral"),
        ("full_info", "communication"),
        ("full_info_rule", "communication_rule"),
    ):
        a, b = per_condition_correct.get(lhs, []), per_condition_correct.get(rhs, [])
        if a and b and len(a) == len(b):
            mean, ci = paired_difference_ci(a, b)
            paired[f"{lhs}_minus_{rhs}"] = {"mean": mean, "ci95": list(ci)}

    manifest = {
        "label": label,
        "started_utc": started.isoformat(),
        "finished_utc": finished.isoformat(),
        "duration_seconds": (finished - started).total_seconds(),
        "git_commit": _git_commit(),
        "git_dirty": _git_dirty(),
        "python": sys.version.split()[0],
        "config_path": str(args.config),
        "config": cfg,
        "resolved": {
            "conditions_run": list(selected),
            "n_episodes": n_episodes,
            "seed_start": seed_start,
            "seeds": [seed_start, seed_start + n_episodes - 1],
            "concurrency": concurrency,
            "rollout": {
                "n_rounds": rollout_cfg.n_rounds,
                "aggregation": rollout_cfg.aggregation,
                "max_tokens": rollout_cfg.max_tokens,
                "temperature_requested": rollout_cfg.temperature,
                "final_temperature_requested": rollout_cfg.final_temperature,
                # gpt-5* and o-series reject an explicit temperature, so the
                # requested values above are not sent and 1.0 applies instead.
                "temperature_honoured": temp_honoured,
                "effective_temperature": (
                    None if temp_honoured else 1.0
                ),
                "token_param": getattr(client, "token_param", "max_tokens"),
                "task_statement_template": TASK_STATEMENT,
                "task_statement_shown_in": [c for c in selected if c in RULE_CONDITIONS],
            },
            "chance_accuracy": chance,
        },
        "client_totals": client.usage(),
        "total_cost_usd": total_cost,
        "failures": all_failures,
        "paired_differences": paired,
        "summaries": {k: v.to_dict() for k, v in summaries.items()},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    _print_summary(summaries, chance)
    print(f"\ntotal cost: ${total_cost:.4f}  (client-reported: ${client.total_cost_usd:.4f})")
    print(f"wrote: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
