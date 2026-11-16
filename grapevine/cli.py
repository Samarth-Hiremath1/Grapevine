"""Command-line interface for Grapevine.

Subcommands:

* ``grapevine audit <env>`` -- run the validity battery over an environment and
  write its Validity Card. Offline, no API key, no GPU.
* ``grapevine view <transcript.jsonl>`` -- pretty-print a rollout transcript with
  private facts color-coded by whether/when they surfaced.
* ``grapevine gen <family>`` -- generate tasks and print or save them as JSONL.
* ``grapevine diagnose <family>`` -- run the reward-hacking battery and print (or
  save) a Markdown report.
* ``grapevine metrics <transcript.jsonl>`` -- aggregate accuracy/surfacing
  metrics from a transcript.
* ``grapevine envs`` -- list auditable environments.
* ``grapevine diagnose <family>`` -- **deprecated**, superseded by ``audit``'s
  ``reward_hacking`` check. Removed in 0.3.0.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import fields
from pathlib import Path

from grapevine.envs import REGISTRY, unavailable_reason
from grapevine.envs.base import Env


def _build_env(family: str, overrides: dict[str, int]) -> Env:
    """Instantiate an environment for ``family`` with integer config overrides.

    Raises:
        SystemExit: If the family is unknown, or exists but is unregistered
            because of a known defect (the message says which).
    """
    if family not in REGISTRY:
        reason = unavailable_reason(family)
        if reason is not None:
            raise SystemExit(
                f"family '{family}' is not available: it {reason}. "
                f"Choose from: {', '.join(REGISTRY)}"
            )
        raise SystemExit(f"unknown family '{family}'. Choose from: {', '.join(REGISTRY)}")
    env_cls, config_cls = REGISTRY[family]
    valid = {f.name for f in fields(config_cls)}
    kwargs = {k: v for k, v in overrides.items() if k in valid and v is not None}
    # The base Env has a no-arg constructor; concrete envs take their config.
    return env_cls(config_cls(**kwargs))  # type: ignore[call-arg]


def _cmd_audit(args: argparse.Namespace) -> int:
    """Audit an environment and emit its Validity Card."""
    from grapevine.audit import audit, check_ids
    from grapevine.envs import get_environment

    try:
        env = get_environment(args.env)
    except KeyError as exc:
        raise SystemExit(str(exc).strip("\"'")) from exc

    if args.only:
        requested = tuple(c.strip() for c in args.only.split(",") if c.strip())
        unknown = [c for c in requested if c not in check_ids()]
        if unknown:
            raise SystemExit(
                f"unknown check(s): {', '.join(unknown)}. "
                f"Choose from: {', '.join(check_ids())}"
            )
    else:
        requested = None

    card = audit(env, n_tasks=args.n, seed=args.seed, alpha=args.alpha, only=requested)

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "validity_card.json").write_text(card.to_json(), encoding="utf-8")
        (out / "validity_card.md").write_text(card.to_markdown(), encoding="utf-8")
        print(f"wrote {out / 'validity_card.json'} and validity_card.md")
    elif args.format == "json":
        print(card.to_json(), end="")
    else:
        print(card.to_markdown(), end="")

    # Exit 2 on a failing card so this is usable as a CI gate. Warnings do not
    # fail the command: a limitation that is reported and understood is not the
    # same as an environment that does not measure what it claims.
    if not card.passed:
        print(
            f"\naudit FAILED: {', '.join(card.flagged_checks)}",
            file=sys.stderr,
        )
        return 2
    print(f"\naudit passed ({card.verdict.value}) for {env.name} v{env.version}", file=sys.stderr)
    return 0


def _cmd_envs(args: argparse.Namespace) -> int:
    """List the environments that can be audited."""
    from grapevine.envs import ENVIRONMENTS, UNREGISTERED, get_environment

    for name in sorted(ENVIRONMENTS):
        env = get_environment(name)
        note = ""
        reason = UNREGISTERED.get(name)
        if reason is not None:
            note = f"  [not runnable: {reason}]"
        print(f"{name} (v{env.version}){note}")
    return 0


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
    """Deprecated: superseded by the ``reward_hacking`` check in ``audit``."""
    from grapevine.diagnostics.hacking import diagnose, report_markdown

    print(
        "grapevine diagnose is deprecated and will be removed in 0.3.0. It is now "
        "the `reward_hacking` check inside the full battery, which also covers the "
        "leak, shortcut and scorer failures a reward check alone cannot see:\n"
        f"    grapevine audit {args.family} --only reward_hacking\n"
        f"    grapevine audit {args.family}\n",
        file=sys.stderr,
    )

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
    # Deliberately not `choices=`: an unregistered family should get the
    # explanation from _build_env rather than argparse's bare "invalid choice".
    parser.add_argument(
        "family", metavar="family", help=f"task family ({', '.join(sorted(REGISTRY))})"
    )
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

    p_audit = sub.add_parser(
        "audit",
        help="run the validity battery over an environment (offline, no API key)",
    )
    p_audit.add_argument("env", metavar="env", help="environment name; see `grapevine envs`")
    p_audit.add_argument(
        "--n", type=int, default=200, help="tasks to audit (default: 200)"
    )
    p_audit.add_argument("--seed", type=int, default=0, help="base seed (default: 0)")
    p_audit.add_argument(
        "--alpha", type=float, default=0.05, help="significance level (default: 0.05)"
    )
    p_audit.add_argument(
        "--only", default=None, help="comma-separated check ids to run instead of all"
    )
    p_audit.add_argument(
        "--out",
        default=None,
        help="directory to write validity_card.json and validity_card.md into",
    )
    p_audit.add_argument(
        "--format",
        choices=("md", "json"),
        default="md",
        help="output format when not writing to --out (default: md)",
    )
    p_audit.set_defaults(func=_cmd_audit)

    p_envs = sub.add_parser("envs", help="list auditable environments")
    p_envs.set_defaults(func=_cmd_envs)

    p_view = sub.add_parser("view", help="pretty-print a transcript JSONL")
    p_view.add_argument("transcript", help="path to a transcript .jsonl file")
    p_view.add_argument("--threshold", type=float, default=0.7, help="surfacing match threshold")
    p_view.set_defaults(func=_cmd_view)

    p_gen = sub.add_parser("gen", help="generate tasks as JSONL")
    _add_env_args(p_gen)
    p_gen.set_defaults(func=_cmd_gen)

    p_diag = sub.add_parser(
        "diagnose",
        help="(deprecated) reward-hacking diagnostics; use `audit` instead",
    )
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
