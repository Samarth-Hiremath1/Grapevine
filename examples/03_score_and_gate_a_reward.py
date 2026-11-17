"""Score answers, build a training reward, and let the audit gate judge it.

    python examples/03_score_and_gate_a_reward.py

Offline, no model and no torch: the audit gate is part of ``grapevine.rl`` but
does not need the ``[rl]`` extra to run. It shows what one agent sees, how an
answer is scored, and why the gate refuses to train on ``hidden_profile_v2`` as
it stands, and refuses a reward that can be collected without answering.
"""

from __future__ import annotations

from grapevine import get_environment
from grapevine.rl import AuditGateError, RewardConfig, audit_gate


def main() -> None:
    """Walk one task from view to score to the audit gate."""
    env = get_environment("hidden_profile_v2")
    split = env.seed_split()
    assert split is not None, "v2 declares its train/eval split"
    task = env.generate(split.eval.start)

    print(f"task {task.task_id}: {len(task.views)} agents, options {', '.join(task.answer_space)}")
    print("\nWhat agent 0 sees:\n")
    print(task.views[0].render())

    # The scorer is programmatic and strict: an exact option, nothing else.
    for answer in (task.gold_answer, task.metadata["decoy_option"], f"probably {task.gold_answer}"):
        result = task.score(answer)
        print(f"score({answer!r}) -> correct={result.correct}, reward={result.reward}")

    # The gate audits the environment with the reward the run would optimise.
    for reward in (RewardConfig(), RewardConfig(surfacing_weight=0.3)):
        try:
            audit_gate(env, reward, n_tasks=50)
            print(f"\n{reward.to_dict()}: the gate would allow training")
        except AuditGateError as refused:
            print(f"\n{reward.to_dict()}: refused, flagged {', '.join(refused.card.flagged_checks)}")


if __name__ == "__main__":
    main()
