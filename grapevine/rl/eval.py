"""Evaluate a policy on held-out seeds, beside the baselines it has to beat.

``grapevine eval --policy <path>`` exists so that a future training run has a
ready, pre-specified evaluation, rather than one written after seeing what the
policy can do.

Three things are fixed in advance:

* **Held-out seeds only.** The default is the environment's declared ``eval``
  split; ``pilot`` is allowed for a pilot. Training seeds are refused.
* **Baselines on the same tasks.** Chance, the best content-blind shortcut from
  the audit, a team that only discusses common ground, and a team that never
  talks are all scored on exactly the tasks the policy saw. A score means
  something only relative to these; on ``hidden_profile_v2`` every one of them
  is at or below chance by construction, which is the "shortcut-removed probe".
* **Exact intervals.** Clopper-Pearson, as in the case study, because a
  percentile bootstrap collapses at 0% and 100% (``docs/audit.md`` L6).

A policy evaluated with scripted partners, or a scripted policy, produces a
report marked ``synthetic: true``. It is a test of the plumbing, never a result.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from grapevine.audit.solvers import (
    SHORTCUT_SOLVERS,
    no_discussion_majority,
    share_nothing_claim_everything,
)
from grapevine.experiments.analysis import clopper_pearson
from grapevine.protocol import DistributedTask, Environment
from grapevine.rl.partners import HFClient, scripted_partner
from grapevine.rl.rewards import RewardConfig
from grapevine.rl.rollout import RolloutSettings, Trajectory, run_episode
from grapevine.rollout.client import LLMClient

__all__ = ["EvalReport", "evaluate", "load_policy", "baselines"]


@dataclass(frozen=True)
class EvalReport:
    """The result of evaluating one policy.

    Attributes:
        policy: What was evaluated.
        environment: Environment name and version.
        split: Which seed range.
        seeds: First and one-past-last seed.
        n: Tasks evaluated.
        n_correct: Tasks the team answered correctly.
        ci95: Clopper-Pearson 95% interval on accuracy.
        n_parse_failures: Decisions that named no single option.
        mean_reward: Mean training reward under the reward config.
        baselines: Accuracy of each reference strategy on the same tasks.
        synthetic: True when any turn came from a scripted stub.
    """

    policy: str
    environment: str
    split: str
    seeds: tuple[int, int]
    n: int
    n_correct: int
    ci95: tuple[float, float]
    n_parse_failures: int
    mean_reward: float
    baselines: dict[str, dict[str, Any]]
    synthetic: bool

    @property
    def accuracy(self) -> float:
        """Fraction of tasks answered correctly."""
        return self.n_correct / self.n if self.n else 0.0

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready form."""
        return {
            "kind": "grapevine.rl.eval/1",
            "policy": self.policy,
            "environment": self.environment,
            "split": self.split,
            "seeds": list(self.seeds),
            "n": self.n,
            "n_correct": self.n_correct,
            "accuracy": self.accuracy,
            "ci95": list(self.ci95),
            "n_parse_failures": self.n_parse_failures,
            "mean_reward": self.mean_reward,
            "baselines": self.baselines,
            "synthetic": self.synthetic,
            "reportable": not self.synthetic,
        }

    def to_markdown(self) -> str:
        """A short human-readable report."""
        lo, hi = self.ci95
        lines = [
            f"# Evaluation: `{self.policy}` on `{self.environment}`",
            "",
        ]
        if self.synthetic:
            lines += [
                "> **Synthetic.** Scripted turns were involved; this tests the plumbing "
                "and is not a result.",
                "",
            ]
        lines += [
            f"- Split: **{self.split}**, seeds {self.seeds[0]}–{self.seeds[1] - 1} (n={self.n})",
            f"- Accuracy: **{self.n_correct}/{self.n}** · {self.accuracy:.1%} "
            f"[{lo:.1%}, {hi:.1%}] (Clopper-Pearson 95%)",
            f"- Parse failures: {self.n_parse_failures}",
            f"- Mean training reward: {self.mean_reward:.3f}",
            "",
            "## Baselines on the same tasks",
            "",
            "A policy's score means something only relative to these.",
            "",
            "| Strategy | Correct | Accuracy |",
            "|---|---:|---:|",
        ]
        for name, row in self.baselines.items():
            correct = "—" if row["n_correct"] is None else f"{row['n_correct']}/{row['n']}"
            lines.append(f"| {name} | {correct} | {row['accuracy']:.1%} |")
        return "\n".join(lines) + "\n"


def baselines(tasks: Sequence[DistributedTask], *, seed: int = 0) -> dict[str, dict[str, Any]]:
    """Reference strategies scored on ``tasks``.

    Includes chance, the best content-blind shortcut the audit knows, a team
    that discusses only common ground, and a team that never talks.
    """
    rng = random.Random(seed)
    n = len(tasks)

    def row(correct: int) -> dict[str, Any]:
        return {"n_correct": correct, "n": n, "accuracy": correct / n if n else 0.0}

    shortcut_scores = {
        name: sum(solver(t.full_view(), t.answer_space, rng) == t.gold_answer for t in tasks)
        for name, solver in SHORTCUT_SOLVERS.items()
    }
    best_name = max(shortcut_scores, key=lambda k: shortcut_scores[k])
    chance = sum(t.chance for t in tasks) / n if n else 0.0
    return {
        "chance": {"n_correct": None, "n": n, "accuracy": chance},
        f"best content-blind shortcut ({best_name})": row(shortcut_scores[best_name]),
        "discuss only common ground": row(
            sum(share_nothing_claim_everything(t, rng) == t.gold_answer for t in tasks)
        ),
        "no communication, majority vote": row(
            sum(no_discussion_majority(t, rng) == t.gold_answer for t in tasks)
        ),
    }


def load_policy(spec: str) -> LLMClient:
    """Resolve ``--policy``.

    ``scripted`` gives the CI stub. Anything else is a Hub id or a local path,
    including a PEFT adapter directory, loaded frozen.
    """
    if spec == "scripted":
        return scripted_partner()
    return HFClient.load(spec, frozen=True)


async def _evaluate_async(
    env: Environment,
    policy: LLMClient,
    seeds: Sequence[int],
    settings: RolloutSettings,
    reward: RewardConfig,
) -> list[Trajectory]:
    trajectories: list[Trajectory] = []
    for seed in seeds:
        task = env.generate(seed)
        clients = dict.fromkeys(range(task.n_agents), policy)
        trajectories.append(
            await run_episode(
                task,
                clients,
                settings=settings,
                reward=reward,
                environment=env.name,
                environment_version=env.version,
                seed=seed,
            )
        )
    return trajectories


def evaluate(
    env: Environment,
    policy: LLMClient,
    *,
    policy_name: str,
    split: str = "eval",
    n: int = 200,
    settings: RolloutSettings | None = None,
    reward: RewardConfig | None = None,
) -> tuple[EvalReport, list[Trajectory]]:
    """Evaluate ``policy`` playing every agent on held-out seeds.

    Raises:
        ValueError: If the environment declares no split, the split is
            ``train``, or the split has fewer than ``n`` seeds.
    """
    declared = env.seed_split()
    if declared is None:
        raise ValueError(f"{env.name} declares no seed split, so there are no held-out seeds")
    if split not in ("eval", "pilot"):
        raise ValueError(
            f"refusing to evaluate on the {split!r} split: evaluation uses held-out seeds "
            "(eval, or pilot for a pilot), never the seeds a policy may have trained on"
        )
    seeds_range = declared.eval if split == "eval" else declared.pilot
    if n > len(seeds_range):
        raise ValueError(f"the {split} split has {len(seeds_range)} seeds, fewer than n={n}")
    seeds = list(seeds_range[:n])
    settings = settings or RolloutSettings()
    reward = reward or RewardConfig()

    trajectories = asyncio.run(_evaluate_async(env, policy, seeds, settings, reward))
    tasks = [env.generate(s) for s in seeds]
    n_correct = sum(t.reward.correct for t in trajectories)
    report = EvalReport(
        policy=policy_name,
        environment=f"{env.name} v{env.version}",
        split=split,
        seeds=(seeds[0], seeds[-1] + 1),
        n=len(seeds),
        n_correct=n_correct,
        ci95=clopper_pearson(n_correct, len(seeds)),
        n_parse_failures=sum(t.team_answer is None for t in trajectories),
        mean_reward=sum(t.reward.total for t in trajectories) / len(trajectories),
        baselines=baselines(tasks),
        synthetic=any(t.synthetic for t in trajectories),
    )
    return report, trajectories


def write_report(report: EvalReport, trajectories: Sequence[Trajectory], out: Path) -> None:
    """Write ``eval.json``, ``eval.md`` and ``trajectories.jsonl`` to ``out``."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "eval.json").write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    (out / "eval.md").write_text(report.to_markdown(), encoding="utf-8")
    with (out / "trajectories.jsonl").open("w", encoding="utf-8") as fh:
        for trajectory in trajectories:
            fh.write(json.dumps(trajectory.to_dict(), ensure_ascii=False) + "\n")
