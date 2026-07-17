"""Command-line interface for Grapevine.

Subcommands:

* ``grapevine view <transcript.jsonl>`` -- pretty-print a rollout transcript with
  private facts color-coded by whether/when they surfaced.
* ``grapevine gen <family>`` -- generate tasks and print or save them as JSONL.
* ``grapevine diagnose <family>`` -- run the reward-hacking battery and print (or
  save) a Markdown report.
* ``grapevine metrics <transcript.jsonl>`` -- aggregate accuracy/surfacing
  metrics from a transcript.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import fields
from pathlib import Path

from grapevine.envs import REGISTRY
from grapevine.envs.base import Env


def _build_env(family: str, overrides: dict[str, int]) -> Env:
    """Instantiate an environment for ``family`` with integer config overrides."""
    if family not in REGISTRY:
        raise SystemExit(f"unknown family '{family}'. Choose from: {', '.join(REGISTRY)}")
    env_cls, config_cls = REGISTRY[family]
    valid = {f.name for f in fields(config_cls)}
    kwargs = {k: v for k, v in overrides.items() if k in valid and v is not None}
    # The base Env has a no-arg constructor; concrete envs take their config.
    return env_cls(config_cls(**kwargs))  # type: ignore[call-arg]


def _cmd_view(args: argparse.Namespace) -> int:
    from grapevine.eval.view import view_transcript

    path = Path(args.transcript)
    if not path.exists():
        print(f"transcript not found: {path}", file=sys.stderr)
        return 1
    view_transcript(path, threshold=args.threshold)
    return 0


def _cmd_gen(args: argparse.Namespace) -> int:
    env = _build_env(
        args.family,
        {
            "n_agents": args.n_agents,
            "n_shared_facts": args.n_shared_facts,
            "n_private_facts_per_agent": args.n_private,
            "n_distractors": args.n_distractors,
            "n_options": args.n_options,
        },
    )
    tasks = env.generate_batch(args.n, args.seed)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            for task in tasks:
                fh.write(task.to_json() + "\n")
        print(f"wrote {len(tasks)} tasks to {out}")
    else:
        for task in tasks:
            print(task.to_json())
    return 0


def _cmd_diagnose(args: argparse.Namespace) -> int:
    from grapevine.diagnostics.hacking import diagnose, report_markdown

    env = _build_env(
        args.family,
        {
            "n_agents": args.n_agents,
            "n_shared_facts": args.n_shared_facts,
            "n_private_facts_per_agent": args.n_private,
            "n_distractors": args.n_distractors,
            "n_options": args.n_options,
        },
    )
    report = diagnose(env, n_tasks=args.n, seed=args.seed)
    md = report_markdown(report)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"wrote report to {out}")
    else:
        print(md)
    return 0 if not report.any_hackable else 2


def _cmd_metrics(args: argparse.Namespace) -> int:
    from grapevine.eval.metrics import compute_metrics, metrics_markdown
    from grapevine.rollout.engine import Episode, load_transcript

    all_eps = [Episode.from_dict(d) for d in load_transcript(args.transcript)]
    team = [e for e in all_eps if e.metadata.get("condition") != "single_agent_full_context"]
    single = [e for e in all_eps if e.metadata.get("condition") == "single_agent_full_context"]
    if not team:
        print("no team episodes found in transcript", file=sys.stderr)
        return 1
    metrics = compute_metrics(team, single or None)
    print(metrics_markdown(metrics, title=f"Metrics: {Path(args.transcript).name}"))
    return 0


def _add_env_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("family", choices=sorted(REGISTRY), help="task family")
    parser.add_argument("--n", type=int, default=8, help="number of tasks")
    parser.add_argument("--seed", type=int, default=0, help="base seed")
    parser.add_argument("--n-agents", type=int, default=None)
    parser.add_argument("--n-shared-facts", type=int, default=None)
    parser.add_argument("--n-private", type=int, default=None, help="private facts per agent")
    parser.add_argument("--n-distractors", type=int, default=None)
    parser.add_argument("--n-options", type=int, default=None)
    parser.add_argument("--out", type=str, default=None, help="output file (JSONL/MD)")


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser."""
    parser = argparse.ArgumentParser(prog="grapevine", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_view = sub.add_parser("view", help="pretty-print a transcript JSONL")
    p_view.add_argument("transcript", help="path to a transcript .jsonl file")
    p_view.add_argument("--threshold", type=float, default=0.7, help="surfacing match threshold")
    p_view.set_defaults(func=_cmd_view)

    p_gen = sub.add_parser("gen", help="generate tasks as JSONL")
    _add_env_args(p_gen)
    p_gen.set_defaults(func=_cmd_gen)

    p_diag = sub.add_parser("diagnose", help="run reward-hacking diagnostics")
    _add_env_args(p_diag)
    p_diag.set_defaults(func=_cmd_diagnose)

    p_metrics = sub.add_parser("metrics", help="aggregate metrics from a transcript")
    p_metrics.add_argument("transcript", help="path to a transcript .jsonl file")
    p_metrics.set_defaults(func=_cmd_metrics)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``grapevine`` console script."""
    parser = build_parser()
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
