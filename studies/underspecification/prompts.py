"""Reconstruct the exact prompts that produced this study's committed episodes.

The committed episodes record every model *response* but not the prompts that
elicited them, so a change to a prompt template would silently break the claim
that these runs reproduce from the code. This module closes that gap: given a
committed episode and the task regenerated from its seed, it rebuilds every
message that was sent, in order.

It does so by calling the same builders the rollout engine itself calls
(:func:`~grapevine.rollout.engine.discussion_messages` and friends), not by
re-deriving the templates. A reconstruction that drifted from the engine would
therefore be a bug in the engine, not in this file.

The role of each recorded message determines which builder produced it, and the
history passed to that builder is exactly the messages recorded before it:

====================================  ====================================
Recorded message                      Builder
====================================  ====================================
``discussion``                        ``discussion_messages``
``answer`` in a 1-agent episode       ``single_agent_messages``
``answer`` otherwise                  ``aggregator_messages``
``vote`` with no discussion recorded   ``no_communication_messages``
``vote`` otherwise                    ``vote_messages``
====================================  ====================================
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from grapevine.envs.base import Task
from grapevine.envs.hidden_profile import HiddenProfileConfig, HiddenProfileEnv
from grapevine.rollout.client import Message
from grapevine.rollout.engine import (
    Episode,
    RolloutConfig,
    aggregator_messages,
    discussion_messages,
    no_communication_messages,
    single_agent_messages,
    vote_messages,
)

#: Config fields the runner reads out of a config's ``env`` block.
_ENV_FIELDS = (
    "n_agents",
    "n_shared_facts",
    "n_private_facts_per_agent",
    "n_distractors",
    "n_options",
)


def env_for_run(run_dir: Path) -> HiddenProfileEnv:
    """Build the environment a committed run used, from that run's manifest.

    The manifest is the only honest source for this: it records the resolved
    environment config as it was at the time of the run, so the environment is
    not reconstructed from today's defaults.

    Args:
        run_dir: A committed run directory containing ``manifest.json``.

    Returns:
        The configured environment.

    Raises:
        ValueError: If the run used a family other than ``hidden_profile``.
    """
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    env_cfg = dict(manifest["config"]["env"])
    family = env_cfg.pop("family", "hidden_profile")
    if family != "hidden_profile":
        raise ValueError(f"{run_dir.name} used family {family!r}, not 'hidden_profile'")
    return HiddenProfileEnv(
        HiddenProfileConfig(**{k: int(v) for k, v in env_cfg.items() if k in _ENV_FIELDS})
    )


def task_for(episode: Episode, env: HiddenProfileEnv) -> Task:
    """Regenerate the task an episode was run on, from its recorded seed.

    Args:
        episode: A committed episode.
        env: An environment configured exactly as the run configured it.

    Returns:
        The regenerated task.

    Raises:
        ValueError: If the episode records no seed, or if the regenerated task
            does not match what the episode recorded. A mismatch means the
            generator has changed and the run no longer reproduces.
    """
    seed = episode.metadata.get("seed")
    if seed is None:
        # The pilot and single-agent runs predate the seed field; recover it
        # from the task id, which has always been f"{family}-{seed}".
        seed = int(episode.task_id.rsplit("-", 1)[1])
    task = env.generate(int(seed))
    if task.task_id != episode.task_id:
        raise ValueError(f"regenerated {task.task_id}, expected {episode.task_id}")
    mismatches = [
        field
        for field, regenerated, recorded in (
            ("question", task.question, episode.question),
            ("options", task.options, episode.options),
            ("answer", task.answer, episode.gold_answer),
            (
                "required_private_facts",
                sorted(task.required_private_facts),
                sorted(episode.required_private_facts),
            ),
        )
        if regenerated != recorded
    ]
    if mismatches:
        raise ValueError(
            f"{episode.task_id} no longer regenerates from its seed: {', '.join(mismatches)} differ"
        )
    return task


def reconstruct(episode: Episode, task: Task) -> list[list[Message]]:
    """Every model call made during ``episode``, as the messages that were sent.

    Args:
        episode: A committed episode.
        task: The task it ran on, from :func:`task_for`.

    Returns:
        One list of messages per model call, in call order. The length matches
        the number of recorded messages, since each recorded message is one
        model response.

    Raises:
        ValueError: If a recorded message has a role the engine cannot produce.
    """
    cfg = RolloutConfig(**episode.config)
    had_discussion = any(m.role == "discussion" for m in episode.messages)
    calls: list[list[Message]] = []
    for i, recorded in enumerate(episode.messages):
        history = episode.messages[:i]
        if recorded.role == "discussion":
            calls.append(discussion_messages(task, recorded.agent_id, history, recorded.round_no, cfg))
        elif recorded.role == "answer":
            if episode.n_agents == 1:
                calls.append(single_agent_messages(task, cfg))
            else:
                calls.append(aggregator_messages(task, history, cfg))
        elif recorded.role == "vote":
            if had_discussion:
                calls.append(vote_messages(task, recorded.agent_id, history, cfg))
            else:
                calls.append(no_communication_messages(task, recorded.agent_id, cfg))
        else:
            raise ValueError(f"unknown message role {recorded.role!r} in {episode.task_id}")
    return calls


def as_plain(calls: list[list[Message]]) -> list[list[dict[str, str]]]:
    """Render reconstructed calls as JSON-ready ``{"role", "content"}`` dicts."""
    return [[{"role": m.role, "content": m.content} for m in call] for call in calls]


def digest(episodes: list[Episode], env: HiddenProfileEnv) -> str:
    """A SHA-256 over every reconstructed prompt byte for ``episodes``.

    One digest covers a whole condition, so byte-identity can be asserted over
    every committed episode without storing every prompt. Episodes are sorted by
    task id first, so the digest does not depend on file order.

    Args:
        episodes: The condition's episodes.
        env: An environment configured as the run configured it.

    Returns:
        The hex digest.
    """
    h = hashlib.sha256()
    for episode in sorted(episodes, key=lambda e: e.task_id):
        task = task_for(episode, env)
        payload: Any = {"task_id": episode.task_id, "calls": as_plain(reconstruct(episode, task))}
        h.update(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return h.hexdigest()
