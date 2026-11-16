"""Expose the frozen v0 generators through the :mod:`grapevine.protocol` interface.

The ``hidden_profile`` and ``split_evidence`` generators predate the protocol,
and ``hidden_profile`` in particular cannot be changed: committed runs are only
reproducible while the generator that produced them is untouched
(``CLAUDE.md`` rule 6). So instead of rewriting them, this module wraps them.

That makes the v0 environment auditable without editing a byte of it, which is
the point — the whole case for ``grapevine audit`` is that it finds problems in
environments people have already run. ``hidden_profile_v2`` implements
:class:`~grapevine.protocol.Environment` natively and needs no adapter.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from grapevine.envs.base import Task
from grapevine.envs.hidden_profile import HiddenProfileConfig, HiddenProfileEnv
from grapevine.envs.split_evidence import SplitEvidenceConfig, SplitEvidenceEnv
from grapevine.protocol import (
    AgentView,
    Condition,
    DistributedTask,
    Environment,
    InfoUnit,
    Objective,
)
from grapevine.rollout.engine import (
    SCORING_RULE,
    TASK_STATEMENT,
    RolloutConfig,
    aggregator_messages,
    discussion_messages,
    no_communication_messages,
    single_agent_messages,
)

__all__ = ["HiddenProfileV1", "SplitEvidenceV1"]


def _supported_option(text: str, options: tuple[str, ...]) -> str | None:
    """Which option a ``hidden_profile`` fact is evidence for, if any.

    A fact supports an option exactly when it starts with that option's name --
    the same rule the generator's own ``_shared_support`` uses, so the units
    carry the support structure the generator built and not a re-derivation of
    it.
    """
    for option in options:
        if text.startswith(option + " "):
            return option
    return None


def _join(messages: Any) -> str:
    """Render one model call's messages as the single block the model receives."""
    return "\n\n".join(m.content for m in messages)


class HiddenProfileV1(Environment):
    """The v0 ``hidden_profile`` generator, behind the environment protocol.

    Generation is delegated unchanged to :class:`HiddenProfileEnv`, so every
    seed produces the same task the committed runs used. The adapter adds what
    the protocol asks for and the legacy ``Task`` does not express: an explicit
    objective, information units with their support structure, a programmatic
    scorer, and the conditions the study ran.

    This environment is expected to fail its audit. That is not a bug in the
    adapter — the failures are the v0 findings in ``docs/audit.md``, and
    ``tests/test_audit.py`` asserts the battery still finds them.
    """

    name = "hidden_profile"
    version = "1"

    def __init__(self, config: HiddenProfileConfig | None = None) -> None:
        """Wrap a configured v0 generator.

        Args:
            config: Passed straight through to :class:`HiddenProfileEnv`. The
                default matches the committed runs (3 agents, 6 shared facts, 2
                private per agent, 4 distractors, 4 options).
        """
        self._env = HiddenProfileEnv(config)

    @property
    def config(self) -> HiddenProfileConfig:
        """The wrapped generator's configuration."""
        return self._env.config

    def legacy_task(self, seed: int) -> Task:
        """The legacy :class:`Task` for ``seed``, exactly as the runs used it."""
        return self._env.generate(seed)

    def generate(self, seed: int) -> DistributedTask:
        """Generate the task for ``seed`` as a :class:`DistributedTask`."""
        task = self._env.generate(seed)
        options = tuple(task.options)

        shared_texts: list[str] = list(task.metadata["shared_facts"])
        private_texts: list[list[str]] = [list(f) for f in task.metadata["private_facts"]]

        shared = tuple(
            InfoUnit(f"s{i}", text, _supported_option(text, options))
            for i, text in enumerate(shared_texts)
        )
        views = []
        by_text: dict[str, str] = {u.text: u.unit_id for u in shared}
        for agent_id, texts in enumerate(private_texts):
            private = tuple(
                InfoUnit(f"a{agent_id}p{j}", text, _supported_option(text, options))
                for j, text in enumerate(texts)
            )
            for unit in private:
                by_text[unit.text] = unit.unit_id
            views.append(AgentView(agent_id=agent_id, shared=shared, private=private))

        required = tuple(
            by_text[text] for text in task.required_private_facts if text in by_text
        )

        return DistributedTask(
            task_id=task.task_id,
            objective=Objective(question=task.question, scoring_rule=SCORING_RULE),
            answer_space=options,
            gold_answer=task.answer,
            views=tuple(views),
            required_units=required,
            metadata={
                "family": self.name,
                "version": self.version,
                "seed": seed,
                "decoy_option": task.metadata.get("decoy_option"),
                "support": task.metadata.get("support"),
            },
        )

    def conditions(self, task: DistributedTask) -> Mapping[str, Condition]:
        """The nine conditions the v0 study ran, as their opening prompts.

        Rendered from the same builders the rollout engine calls, so these are
        the prompts that were actually sent, not a description of them. Each
        ``_rule`` arm declares that the task statement is its only difference
        from the arm it mirrors, which is the claim the study rests on; the
        condition-diff check verifies it.
        """
        legacy = self._env.generate(int(task.metadata["seed"]))
        statement = TASK_STATEMENT.format(question=legacy.question) + "\n\n"

        base = RolloutConfig()
        neutral = replace(base, prompt_style="neutral")
        specs: list[tuple[str, str, RolloutConfig, str]] = [
            ("full_info", "one agent, every fact, original flat layout", base, "single"),
            (
                "full_info_matched",
                "one agent, every fact, laid out like the team conditions",
                replace(base, full_info_presentation="matched"),
                "single",
            ),
            ("no_communication", "every agent answers alone, majority vote", base, "solo"),
            ("communication", "discussion, agents instructed to share and ask", base, "team"),
            ("communication_neutral", "discussion, no share/ask directive", neutral, "team"),
        ]
        out: dict[str, Condition] = {}
        for cond_name, description, cfg, kind in specs:
            for rule in (False, True):
                full_name = f"{cond_name}_rule" if rule else cond_name
                run_cfg = replace(cfg, show_task=rule)
                prompts: tuple[str, ...]
                if kind == "single":
                    prompts = (_join(single_agent_messages(legacy, run_cfg)),)
                elif kind == "solo":
                    prompts = tuple(
                        _join(no_communication_messages(legacy, i, run_cfg))
                        for i in range(legacy.n_agents)
                    )
                else:
                    prompts = tuple(
                        _join(discussion_messages(legacy, i, [], 1, run_cfg))
                        for i in range(legacy.n_agents)
                    ) + (_join(aggregator_messages(legacy, [], run_cfg)),)
                expected = {cond_name: statement} if rule else {f"{cond_name}_rule": statement}
                out[full_name] = Condition(
                    name=full_name,
                    description=(
                        f"{description}; task and scoring rule stated"
                        if rule
                        else f"{description}; objective never stated"
                    ),
                    prompts=prompts,
                    expected_diff=expected,
                )
        return out

    def config_summary(self) -> Mapping[str, Any]:
        """The wrapped generator's configuration, for the Validity Card."""
        cfg = self._env.config
        return {f: getattr(cfg, f) for f in cfg.__dataclass_fields__ if f != "seed"}


class SplitEvidenceV1(Environment):
    """The v0 ``split_evidence`` multi-hop generator, behind the protocol.

    Kept auditable rather than registered. Its final reasoning hop names the
    terminal station, which is the answer, so whichever agent holds that hop can
    answer with no pooling at all (``docs/decisions.md``). It is here as a real
    positive control for the leak and solo-solvability checks: a synthetic
    fixture can be made to fail on purpose, but this one failed for real, in a
    family that was registered and nearly used.
    """

    name = "split_evidence"
    version = "1"

    def __init__(self, config: SplitEvidenceConfig | None = None) -> None:
        """Wrap a configured v0 generator."""
        self._env = SplitEvidenceEnv(config)

    @property
    def config(self) -> SplitEvidenceConfig:
        """The wrapped generator's configuration."""
        return self._env.config

    def generate(self, seed: int) -> DistributedTask:
        """Generate the task for ``seed`` as a :class:`DistributedTask`."""
        task = self._env.generate(seed)
        options = tuple(task.options)
        shared_texts = list(task.metadata.get("shared_facts", []))
        private_texts = [list(f) for f in task.metadata.get("private_facts", [])]

        # A hop supports the option it terminates at: that is the inference the
        # chain licenses once the preceding hops are known.
        def supports(text: str) -> str | None:
            named = [o for o in options if o in text]
            return named[-1] if named else None

        shared = tuple(
            InfoUnit(f"s{i}", text, supports(text)) for i, text in enumerate(shared_texts)
        )
        by_text: dict[str, str] = {u.text: u.unit_id for u in shared}
        views = []
        for agent_id, texts in enumerate(private_texts):
            private = tuple(
                InfoUnit(f"a{agent_id}p{j}", text, supports(text))
                for j, text in enumerate(texts)
            )
            for unit in private:
                by_text[unit.text] = unit.unit_id
            views.append(AgentView(agent_id=agent_id, shared=shared, private=private))

        required = tuple(
            by_text[text] for text in task.required_private_facts if text in by_text
        )
        return DistributedTask(
            task_id=task.task_id,
            objective=Objective(
                question=task.question,
                scoring_rule=(
                    "the answer is the station the active route reaches last, following "
                    "each hop in turn from the starting station."
                ),
            ),
            answer_space=options,
            gold_answer=task.answer,
            views=tuple(views),
            required_units=required,
            metadata={"family": self.name, "version": self.version, "seed": seed},
        )

    def config_summary(self) -> Mapping[str, Any]:
        """The wrapped generator's configuration, for the Validity Card."""
        cfg = self._env.config
        return {f: getattr(cfg, f) for f in cfg.__dataclass_fields__ if f != "seed"}
