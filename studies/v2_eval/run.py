"""Run the pre-registered ``hidden_profile_v2`` eval. Dry run first, always.

    # The estimate, with no key and no network.
    python -m studies.v2_eval.run --phase pilot --models gpt-5.6-luna --dry-run

    # A real run needs an explicit spending ceiling at or above the estimate.
    python -m studies.v2_eval.run --phase pilot --models gpt-5.6-luna --approve-usd 0.50

Spending is guarded three ways (``CLAUDE.md`` rule 9). A run refuses to start
unless ``--approve-usd`` is at least the estimate; refuses if the approval would
take total spend across every committed run past the $10 budget; and stops as
soon as live spend reaches the approved amount. A run that stops early is kept
and reported as incomplete, never deleted or rerun to look better (rule 5).

Every call is logged with its usage, including hidden reasoning tokens, and its
finish reason. A call that hit the output cap is a named failure
(``truncated``), never silently scored as a wrong answer.

``--scripted`` replaces the model with an offline stub, for tests. Its runs are
marked ``synthetic: true``, and the analysis refuses to build a table from them.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from grapevine.rollout.client import (
    Completion,
    LLMClient,
    Message,
    OpenAICompatibleClient,
    ScriptedClient,
    require_pricing,
    supports_temperature,
)
from grapevine.rollout.engine import parse_answer, tally_votes
from grapevine.settings import has_key, load_env
from studies.v2_eval.design import (
    CELLS,
    DESIGN,
    ENVIRONMENT,
    decision_messages,
    discussion_messages,
)

STUDY_DIR = Path(__file__).resolve().parent
REPO_ROOT = STUDY_DIR.parent.parent

#: Output tokens per call in the committed v0 runs: 794,186 completion tokens
#: over 7,260 calls on gpt-5.6-luna with a 400-token cap. Computed from the run
#: manifests, not estimated. Used as the point estimate for every model; the
#: worst case assumes every call hits the cap.
V0_COMPLETION_TOKENS_PER_CALL = 109.4

#: Characters per token for the input estimate. A rough constant for English
#: text with these tokenizers; the estimate is labelled as one.
CHARS_PER_TOKEN = 4.0


class BudgetError(RuntimeError):
    """The run would exceed what was approved or what the budget allows."""


# --- Spend accounting ------------------------------------------------------------


def committed_spend(root: Path = REPO_ROOT) -> float:
    """Total spend recorded by every committed run manifest in the repository."""
    total = 0.0
    for manifest in sorted(root.glob("studies/*/runs/*/manifest.json")):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("synthetic"):
            continue
        total += float(data.get("total_cost_usd", 0.0))
    return total


def estimate(models: Sequence[str], phase: str) -> dict[str, Any]:
    """Calls, tokens and cost for a run, before it happens.

    Input tokens come from the actual prompts of every task in the phase, with
    later-round histories filled by messages of the v0 average length. Output
    tokens are given two ways: at the v0 average, and with every call at the
    output cap. Raises if any model's price is unknown.
    """
    seeds = DESIGN.seeds(phase)
    filler = "x" * int(V0_COMPLETION_TOKENS_PER_CALL * CHARS_PER_TOKEN)
    input_chars = 0
    n_calls = 0
    for seed in seeds:
        task = ENVIRONMENT.generate(seed)
        for condition, objective in CELLS:
            if condition == "full_info":
                prompts = [decision_messages(task, condition, objective)]
            elif condition == "no_communication":
                prompts = [
                    decision_messages(task, condition, objective, agent_id=i)
                    for i in range(task.n_agents)
                ]
            else:
                prompts = []
                history: list[tuple[int, str]] = []
                for round_no in range(1, DESIGN.n_rounds + 1):
                    for agent in range(task.n_agents):
                        prompts.append(
                            discussion_messages(task, agent, history, round_no, objective)
                        )
                        history.append((agent, filler))
                prompts.append(
                    decision_messages(
                        task, condition, objective, agent_id=DESIGN.aggregator, history=history
                    )
                )
            for messages in prompts:
                input_chars += sum(len(m.content) for m in messages)
                n_calls += 1

    input_tokens = input_chars / CHARS_PER_TOKEN
    per_model: dict[str, Any] = {}
    for model in models:
        price = require_pricing(model)  # fails loudly on an unpriced model
        typical_out = n_calls * V0_COMPLETION_TOKENS_PER_CALL
        worst_out = n_calls * DESIGN.max_output_tokens
        per_model[model] = {
            "calls": n_calls,
            "input_tokens_est": round(input_tokens),
            "cost_at_v0_output_length_usd": round(price.cost(int(input_tokens), int(typical_out)), 4),
            "cost_if_every_call_hits_cap_usd": round(price.cost(int(input_tokens), int(worst_out)), 4),
        }
    return {
        "phase": phase,
        "tasks": len(seeds),
        "cells_per_model": len(CELLS),
        "per_model": per_model,
        "total_at_v0_output_length_usd": round(
            sum(m["cost_at_v0_output_length_usd"] for m in per_model.values()), 4
        ),
        "total_if_every_call_hits_cap_usd": round(
            sum(m["cost_if_every_call_hits_cap_usd"] for m in per_model.values()), 4
        ),
        "committed_spend_usd": round(committed_spend(), 4),
        "budget_usd": DESIGN.budget_usd,
    }


# --- Per-call logging ------------------------------------------------------------


@dataclass
class CallLog:
    """Every call a run makes, and the live spend."""

    ceiling_usd: float
    calls: list[dict[str, Any]] = field(default_factory=list)
    spent_usd: float = 0.0

    def record(self, completion: Completion, **where: Any) -> None:
        self.spent_usd += completion.cost_usd
        self.calls.append(
            {
                **where,
                "prompt_tokens": completion.prompt_tokens,
                "completion_tokens": completion.completion_tokens,
                "reasoning_tokens": completion.reasoning_tokens,
                "finish_reason": completion.finish_reason,
                "truncated": completion.truncated,
                "cost_usd": completion.cost_usd,
            }
        )
        if self.spent_usd >= self.ceiling_usd:
            raise BudgetError(
                f"live spend ${self.spent_usd:.4f} reached the approved ${self.ceiling_usd:.4f}"
            )


async def _call(
    client: LLMClient,
    log: CallLog,
    messages: list[Message],
    *,
    temperature: float,
    **where: Any,
) -> Completion:
    completion = await client.complete(
        messages, max_tokens=DESIGN.max_output_tokens, temperature=temperature
    )
    log.record(completion, **where)
    return completion


# --- One episode per cell ----------------------------------------------------------


async def run_episode(
    client: LLMClient, log: CallLog, model: str, seed: int, condition: str, objective: str
) -> dict[str, Any]:
    """Run one task in one cell and return its episode record."""
    task = ENVIRONMENT.generate(seed)
    where = {"model": model, "seed": seed, "condition": condition, "objective": objective}
    options = list(task.answer_space)
    turns: list[dict[str, Any]] = []
    truncated = False

    def note(agent: int, round_no: int, kind: str, messages: list[Message], c: Completion) -> None:
        nonlocal truncated
        truncated = truncated or c.truncated
        turns.append(
            {
                "agent": agent,
                "round": round_no,
                "kind": kind,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "completion": c.text,
                "finish_reason": c.finish_reason,
                "truncated": c.truncated,
            }
        )

    votes: list[str | None] = []
    tie = False
    if condition == "full_info":
        messages = decision_messages(task, condition, objective)
        c = await _call(client, log, messages, temperature=DESIGN.decision_temperature,
                        agent=0, round=1, kind="answer", **where)
        note(0, 1, "answer", messages, c)
        answer = parse_answer(c.text, options)
    elif condition == "no_communication":
        for agent in range(task.n_agents):
            messages = decision_messages(task, condition, objective, agent_id=agent)
            c = await _call(client, log, messages, temperature=DESIGN.decision_temperature,
                            agent=agent, round=1, kind="vote", **where)
            note(agent, 1, "vote", messages, c)
            votes.append(parse_answer(c.text, options))
        # Ties broken uniformly at random, seeded by the task id: the v0 rule,
        # fixed in advance and unbiased with respect to the correct answer.
        answer, tie, _ = tally_votes(votes, options, task.task_id)
    else:
        history: list[tuple[int, str]] = []
        for round_no in range(1, DESIGN.n_rounds + 1):
            for agent in range(task.n_agents):
                messages = discussion_messages(task, agent, history, round_no, objective)
                c = await _call(client, log, messages, temperature=DESIGN.discussion_temperature,
                                agent=agent, round=round_no, kind="discussion", **where)
                note(agent, round_no, "discussion", messages, c)
                history.append((agent, c.text.strip()))
        agg = DESIGN.aggregator
        messages = decision_messages(task, condition, objective, agent_id=agg, history=history)
        c = await _call(client, log, messages, temperature=DESIGN.decision_temperature,
                        agent=agg, round=DESIGN.n_rounds + 1, kind="answer", **where)
        note(agg, DESIGN.n_rounds + 1, "answer", messages, c)
        answer = parse_answer(c.text, options)

    return {
        "task_id": task.task_id,
        "seed": seed,
        "model": model,
        "condition": condition,
        "objective": objective,
        "gold": task.gold_answer,
        "decoy": task.metadata["decoy_option"],
        "options": options,
        "answer": answer,
        "correct": answer == task.gold_answer and not truncated,
        "parse_failure": answer is None,
        "truncated": truncated,
        "votes": votes,
        "tie": tie,
        "turns": turns,
    }


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True, cwd=REPO_ROOT
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _scripted_client() -> ScriptedClient:
    """Offline stub: names the first option every time. For tests only."""

    def responder(messages: list[Message]) -> str:
        user = messages[-1].content
        if "Choose exactly one of these options:" in user:
            first = user.split("Choose exactly one of these options: ", 1)[1].split(",")[0]
            return '{"answer": "' + first.strip().rstrip(".") + '"}'
        return "Here is what I know."

    return ScriptedClient(responder, model="scripted")


async def _run(
    models: Sequence[str], phase: str, log: CallLog, scripted: bool, out: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    episodes: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    stopped: str | None = None
    with (out / "episodes.jsonl").open("w", encoding="utf-8") as fh:
        for model in models:
            client: LLMClient = _scripted_client() if scripted else OpenAICompatibleClient(model)
            for seed in DESIGN.seeds(phase):
                for condition, objective in CELLS:
                    try:
                        episode = await run_episode(client, log, model, seed, condition, objective)
                    except BudgetError as exc:
                        stopped = str(exc)
                        return episodes, failures, stopped
                    except Exception as exc:  # noqa: BLE001 - recorded, never swallowed
                        failures.append(
                            {"model": model, "seed": seed, "condition": condition,
                             "objective": objective, "error": f"{type(exc).__name__}: {exc}"}
                        )
                        continue
                    episodes.append(episode)
                    fh.write(json.dumps(episode, ensure_ascii=False) + "\n")
    return episodes, failures, stopped


def main(argv: list[str] | None = None) -> int:
    """Estimate, or run, one phase of the pre-registered eval."""
    parser = argparse.ArgumentParser(
        prog="python -m studies.v2_eval.run",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--phase", choices=("pilot", "primary"), required=True)
    parser.add_argument("--models", required=True, help="comma-separated model ids")
    parser.add_argument("--dry-run", action="store_true", help="estimate cost; make no calls")
    parser.add_argument("--approve-usd", type=float, default=None,
                        help="spending ceiling; must be at least the estimate")
    parser.add_argument("--scripted", action="store_true",
                        help="offline stub instead of a model; output is synthetic")
    parser.add_argument("--out", default=None, help="run directory (default: runs/<ts>_<phase>)")
    args = parser.parse_args(argv)

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    plan = estimate(models, args.phase)
    print(json.dumps(plan, indent=2))
    if args.dry_run:
        return 0

    needed = plan["total_at_v0_output_length_usd"]
    remaining = DESIGN.budget_usd - plan["committed_spend_usd"]
    if not args.scripted:
        # The key lives in a gitignored .env, as for the v0 runner. Only its
        # presence is ever checked; the value is never printed or logged.
        load_env()
        if not has_key("openai"):
            print("no OPENAI_API_KEY in the environment or .env; refusing to run", file=sys.stderr)
            return 2
        if args.approve_usd is None:
            print("refusing to spend without --approve-usd (run --dry-run first)", file=sys.stderr)
            return 2
        if args.approve_usd < needed:
            print(f"--approve-usd {args.approve_usd} is below the estimate ${needed}", file=sys.stderr)
            return 2
        if args.approve_usd > remaining:
            print(f"--approve-usd {args.approve_usd} would exceed the remaining budget "
                  f"${remaining:.4f} of ${DESIGN.budget_usd}", file=sys.stderr)
            return 2

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.out) if args.out else STUDY_DIR / "runs" / f"{stamp}_{args.phase}"
    out.mkdir(parents=True, exist_ok=False)  # never overwrite a run
    started = datetime.now(UTC).isoformat(timespec="seconds")
    commit_start, dirty_start = _git("rev-parse", "HEAD"), bool(_git("status", "--porcelain"))
    log = CallLog(ceiling_usd=float("inf") if args.scripted else float(args.approve_usd))

    episodes, failures, stopped = asyncio.run(_run(models, args.phase, log, args.scripted, out))

    with (out / "calls.jsonl").open("w", encoding="utf-8") as fh:
        for call in log.calls:
            fh.write(json.dumps(call) + "\n")
    expected = len(models) * len(DESIGN.seeds(args.phase)) * len(CELLS)
    manifest = {
        "kind": "grapevine.v2_eval.run/1",
        "phase": args.phase,
        "models": models,
        "synthetic": bool(args.scripted),
        "design": DESIGN.to_dict(),
        "estimate": plan,
        "approved_usd": args.approve_usd,
        "started_utc": started,
        "finished_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit_start": commit_start,
        "git_dirty_start": dirty_start,
        "git_commit_end": _git("rev-parse", "HEAD"),
        "n_calls": len(log.calls),
        "total_cost_usd": round(log.spent_usd, 6),
        "reasoning_tokens": sum(c["reasoning_tokens"] for c in log.calls),
        "truncated_calls": sum(c["truncated"] for c in log.calls),
        "temperature_honoured": {m: supports_temperature(m) for m in models},
        "episodes_expected": expected,
        "episodes_completed": len(episodes),
        "complete": len(episodes) == expected and not failures and stopped is None,
        "stopped_early": stopped,
        "failures": failures,
        "seed_check": "pilot and primary seeds are disjoint (enforced by Design)",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(episodes)}/{expected} episodes, ${log.spent_usd:.4f}"
          + (f", STOPPED: {stopped}" if stopped else ""))
    return 0 if manifest["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

