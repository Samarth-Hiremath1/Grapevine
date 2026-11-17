"""``grapevine.rl`` without a model: rewards, rollout, gate, config, eval.

Everything here runs on scripted clients and needs neither ``torch`` nor
``trl``. The tests that load a model -- the GRPO smoke run and the isolation
test -- are in ``test_rl_training.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from grapevine.audit import Status, audit
from grapevine.envs import get_environment
from grapevine.envs.hidden_profile_v2 import HiddenProfileV2
from grapevine.rl import (
    AuditGateError,
    PartnerSpec,
    RewardConfig,
    RewardedEnvironment,
    RolloutSettings,
    audit_gate,
    load_config,
    run_episode_sync,
    scripted_partner,
    shared_credit,
    split_credit,
    surfaced_fraction,
    surfacing_credit,
)
from grapevine.rl.eval import baselines, evaluate
from grapevine.rl.rollout import opening_messages, speaking_order
from grapevine.rollout.client import Message, ScriptedClient

ENV = HiddenProfileV2()


def _echo_facts(agent_view_text: str) -> ScriptedClient:
    """A scripted agent that repeats its private facts, then answers correctly."""

    def responder(messages: list[Message]) -> str:
        user = messages[-1].content
        if "Choose exactly one" in user:
            return '{"answer": "' + agent_view_text + '"}'
        private = user.split("Facts only you know:", 1)[-1].split("Conversation so far:")[0]
        return private.strip()

    return ScriptedClient(responder, model="echo")


class TestRewardConfig:
    def test_shaping_is_off_by_default(self) -> None:
        assert RewardConfig().surfacing_weight == 0.0
        assert not RewardConfig().shaped

    def test_rejects_negative_or_all_zero_weights(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            RewardConfig(outcome_weight=-1.0)
        with pytest.raises(ValueError, match="at least one"):
            RewardConfig(outcome_weight=0.0, surfacing_weight=0.0)

    def test_rejects_unknown_keys(self) -> None:
        """A typo in a reward weight must not silently change what is optimised."""
        with pytest.raises(ValueError, match="unknown reward keys"):
            RewardConfig.from_mapping({"surfacing_wieght": 0.5})


class TestShapingIsCaughtByTheAudit:
    """The reason the surfacing term is off by default, made executable."""

    def test_the_outcome_reward_passes_the_audit(self) -> None:
        card = audit(RewardedEnvironment(ENV, RewardConfig()), n_tasks=100, seed=0)
        assert card.get("reward_hacking").status is Status.PASS

    def test_any_surfacing_weight_is_flagged(self) -> None:
        """One agent reciting its notes, with nobody answering, earns a surfacing
        bonus. The reward then pays for something other than being right."""
        shaped = RewardConfig(outcome_weight=1.0, surfacing_weight=0.1)
        card = audit(RewardedEnvironment(ENV, shaped), n_tasks=100, seed=0)
        result = card.get("reward_hacking")
        assert result.status is Status.FAIL
        rows = {r["name"]: r for r in result.detail["policies"]}
        assert rows["recite_without_answering"]["pays_beyond_correctness"]
        assert rows["recite_without_answering"]["accuracy"] == 0.0

    def test_the_wrapper_keeps_the_environment_identity(self) -> None:
        wrapped = RewardedEnvironment(ENV, RewardConfig())
        assert (wrapped.name, wrapped.version) == (ENV.name, ENV.version)
        assert wrapped.seed_split() == ENV.seed_split()
        assert "training_reward" in wrapped.config_summary()

    def test_the_scorer_is_unchanged_without_shaping(self) -> None:
        task = ENV.generate(0)
        wrapped = RewardedEnvironment(ENV, RewardConfig()).generate(0)
        assert wrapped.score(task.gold_answer).reward == 1.0
        assert wrapped.score("nonsense").reward == 0.0


class TestCredit:
    def test_shared_and_split(self) -> None:
        assert shared_credit(1.0, 3) == (1.0, 1.0, 1.0)
        assert split_credit(1.0, 4) == (0.25, 0.25, 0.25, 0.25)

    def test_surfacing_credit_follows_what_each_agent_shared(self) -> None:
        task = ENV.generate(0)
        own = [u for u in task.views[1].private if u.unit_id in task.required_units]
        credit = surfacing_credit(1.0, task, {0: ["nothing"], 1: [own[0].text], 2: ["nothing"]})
        assert credit[1] == pytest.approx(1.0)
        assert credit[0] == credit[2] == 0.0

    def test_surfacing_credit_falls_back_to_equal_when_nobody_shared(self) -> None:
        task = ENV.generate(0)
        assert surfacing_credit(0.9, task, {}) == split_credit(0.9, task.n_agents)

    def test_surfaced_fraction_counts_only_the_agents_own_units(self) -> None:
        task = ENV.generate(0)
        theirs = [u.text for u in task.views[2].private if u.unit_id in task.required_units]
        assert surfaced_fraction(task, theirs, agent_id=1) == 0.0
        assert surfaced_fraction(task, theirs, agent_id=2) == 1.0


class TestRollout:
    def test_every_prompt_states_the_objective(self) -> None:
        """The v0 result was wrong because no prompt did. Asserted per turn."""
        task = ENV.generate(3)
        partner = scripted_partner()
        trajectory = run_episode_sync(task, dict.fromkeys(range(task.n_agents), partner))
        statement = task.objective.statement()
        assert trajectory.turns
        for turn in trajectory.turns:
            user = dict(turn.messages)["user"]
            assert task.objective.question in user, turn
            assert task.objective.scoring_rule in user, turn
            assert statement in user

    def test_records_every_prompt_and_tags_turns(self) -> None:
        task = ENV.generate(0)
        settings = RolloutSettings(n_rounds=2)
        trajectory = run_episode_sync(
            task,
            dict.fromkeys(range(task.n_agents), scripted_partner()),
            settings=settings,
            trainable_agents=[1],
            first_speaker=1,
        )
        assert len(trajectory.turns) == task.n_agents * 2 + 1
        assert all(t.messages for t in trajectory.turns)
        assert trajectory.turns[0].agent_id == 1, "the trained agent opens"
        assert trajectory.turns[-1].kind == "answer"
        assert {t.agent_id for t in trajectory.trainable_turns()} == {1}
        assert trajectory.metadata["speaking_order"] == [1, 2, 0]

    def test_scripted_turns_are_marked_synthetic(self) -> None:
        """A trajectory containing a scripted turn is never a result (rule 2)."""
        task = ENV.generate(0)
        trajectory = run_episode_sync(task, dict.fromkeys(range(task.n_agents), scripted_partner()))
        assert trajectory.synthetic
        assert json.loads(json.dumps(trajectory.to_dict()))["synthetic"] is True

    def test_a_fixed_opening_is_used_verbatim_and_not_synthetic(self) -> None:
        task = ENV.generate(0)
        trajectory = run_episode_sync(
            task,
            dict.fromkeys(range(task.n_agents), scripted_partner()),
            first_speaker=2,
            fixed_openings={2: "  my opening  "},
        )
        first = trajectory.turns[0]
        assert (first.agent_id, first.completion, first.synthetic) == (2, "my opening", False)

    def test_the_opening_prompt_is_the_first_turn_prompt(self) -> None:
        """What the GRPO dataset trains on must be what the episode actually sends."""
        task = ENV.generate(4)
        settings = RolloutSettings(n_rounds=1)
        trajectory = run_episode_sync(
            task,
            dict.fromkeys(range(task.n_agents), scripted_partner()),
            settings=settings,
            first_speaker=2,
        )
        expected = tuple((m.role, m.content) for m in opening_messages(task, 2, settings))
        assert trajectory.turns[0].messages == expected

    def test_a_correct_team_is_rewarded(self) -> None:
        task = ENV.generate(0)
        trajectory = run_episode_sync(
            task, dict.fromkeys(range(task.n_agents), _echo_facts(task.gold_answer))
        )
        assert trajectory.team_answer == task.gold_answer
        assert trajectory.reward.correct
        assert trajectory.reward.total == 1.0
        assert trajectory.credit == (1.0,) * task.n_agents

    def test_missing_clients_are_refused(self) -> None:
        task = ENV.generate(0)
        with pytest.raises(ValueError, match="no client"):
            run_episode_sync(task, {0: scripted_partner()})

    def test_speaking_order_rotates(self) -> None:
        assert speaking_order(3, 0) == (0, 1, 2)
        assert speaking_order(3, 2) == (2, 0, 1)
        with pytest.raises(ValueError):
            speaking_order(3, 3)


class TestGate:
    def test_passes_a_clean_environment_and_records_the_card(self) -> None:
        from fixtures.flawed_envs import CLEAN_CONTROL

        result = audit_gate(CLEAN_CONTROL, RewardConfig(), n_tasks=50)
        assert result.passed and not result.allowed_flagged
        entry = result.to_dict()
        assert len(entry["card_hash"]) == 64
        assert entry["seed"] == CLEAN_CONTROL.seed_split().train.start

    def test_refuses_hidden_profile_v2_as_it_stands(self) -> None:
        """v2 fails solo_solvability (docs/audit.md, A2), so the gate refuses it."""
        with pytest.raises(AuditGateError, match="solo_solvability"):
            audit_gate(ENV, RewardConfig(), n_tasks=50)

    def test_refuses_a_shaped_reward_by_default(self) -> None:
        with pytest.raises(AuditGateError, match="reward_hacking"):
            audit_gate(ENV, RewardConfig(surfacing_weight=0.2), n_tasks=50)

    def test_allow_flagged_proceeds_and_says_so(self) -> None:
        result = audit_gate(
            ENV, RewardConfig(surfacing_weight=0.2), n_tasks=50, allow_flagged=True
        )
        assert not result.passed
        assert result.allowed_flagged
        assert "reward_hacking" in result.to_dict()["flagged_checks"]

    def test_refuses_an_environment_with_no_seed_split(self) -> None:
        """v0 hidden_profile declares none, so a run could train on its eval tasks."""
        with pytest.raises(ValueError, match="no train/eval seed split"):
            audit_gate(get_environment("hidden_profile"), RewardConfig(), n_tasks=20)


class TestConfig:
    def test_both_shipped_configs_load(self) -> None:
        smoke = load_config("configs/rl_smoke_cpu.yaml")
        assert smoke.partners.kind == "scripted"
        assert smoke.reward.surfacing_weight == 0.0
        gpu = load_config("configs/rl_single_gpu.yaml")
        assert gpu.partners.frozen and gpu.lora is not None

    def test_the_gpu_config_says_it_has_not_been_run(self) -> None:
        first = Path("configs/rl_single_gpu.yaml").read_text(encoding="utf-8").splitlines()[0]
        assert first.strip() == "# not run"

    def _write(self, tmp_path: Path, text: str) -> Path:
        path = tmp_path / "c.yaml"
        path.write_text(text, encoding="utf-8")
        return path

    BASE = (
        "model: {name: x}\n"
        "environment: {name: hidden_profile_v2, n_train_tasks: 2}\n"
        "grpo: {max_steps: 1}\n"
    )

    def test_rejects_unknown_top_level_keys(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="unknown top-level"):
            load_config(self._write(tmp_path, self.BASE + "rewrad: {}\n"))

    def test_rejects_output_dir_under_grpo(self, tmp_path: Path) -> None:
        text = self.BASE.replace("grpo: {max_steps: 1}", "grpo: {max_steps: 1, output_dir: x}")
        with pytest.raises(ValueError, match="top level"):
            load_config(self._write(tmp_path, text))

    def test_self_play_trains_every_role(self, tmp_path: Path) -> None:
        config = load_config(self._write(tmp_path, self.BASE + "partners: {kind: self}\n"))
        assert config.self_play
        assert config.trainable_agents == (0, 1, 2)
        assert not config.partners.frozen

    def test_self_play_refuses_a_partial_role_list(self, tmp_path: Path) -> None:
        text = self.BASE + "partners: {kind: self}\ntrainable_agents: [0]\n"
        with pytest.raises(ValueError, match="every agent"):
            load_config(self._write(tmp_path, text))

    def test_rejects_an_out_of_range_role(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="not agents"):
            load_config(self._write(tmp_path, self.BASE + "trainable_agents: [7]\n"))

    def test_an_endpoint_needs_a_url(self) -> None:
        with pytest.raises(ValueError, match="base_url"):
            PartnerSpec(kind="endpoint", model="m")

    def test_environment_overrides_reach_the_environment(self, tmp_path: Path) -> None:
        text = self.BASE.replace(
            "n_train_tasks: 2}", "n_train_tasks: 2, config: {n_agents: 4}}"
        )
        config = load_config(self._write(tmp_path, text))
        assert config.environment_config == {"n_agents": 4}

    def test_dry_run_refuses_a_shaped_reward(self, tmp_path: Path) -> None:
        from grapevine.rl.grpo import train

        text = self.BASE + "reward: {surfacing_weight: 0.3}\naudit: {n_tasks: 30}\n"
        text += f"output_dir: {tmp_path / 'out'}\n"
        with pytest.raises(AuditGateError):
            train(self._write(tmp_path, text), dry_run=True)

    def test_dry_run_with_allow_flagged_records_it(self, tmp_path: Path) -> None:
        from grapevine.rl.grpo import train

        text = self.BASE + "reward: {surfacing_weight: 0.3}\naudit: {n_tasks: 30}\n"
        text += f"output_dir: {tmp_path / 'out'}\n"
        manifest = train(self._write(tmp_path, text), dry_run=True, allow_flagged=True)
        assert manifest["audit_gate"]["allowed_flagged"] is True
        assert manifest["reportable"] is False
        assert any("allow-flagged" in r for r in manifest["not_reportable_because"])
        on_disk = json.loads((tmp_path / "out" / "manifest.json").read_text())
        assert "reward_hacking" in on_disk["audit_gate"]["flagged_checks"]


class TestEval:
    def test_refuses_the_training_split(self) -> None:
        with pytest.raises(ValueError, match="held-out"):
            evaluate(ENV, scripted_partner(), policy_name="scripted", split="train", n=5)

    def test_refuses_an_environment_with_no_split(self) -> None:
        with pytest.raises(ValueError, match="no seed split"):
            evaluate(
                get_environment("hidden_profile"), scripted_partner(),
                policy_name="scripted", n=5,
            )

    def test_a_scripted_policy_report_is_synthetic_and_not_reportable(self) -> None:
        report, trajectories = evaluate(
            ENV, scripted_partner(), policy_name="scripted", n=10,
            settings=RolloutSettings(n_rounds=1),
        )
        assert report.synthetic
        assert report.to_dict()["reportable"] is False
        assert "Synthetic" in report.to_markdown()
        assert report.seeds == (10000, 10010), "evaluates on the declared eval seeds"
        assert len(trajectories) == 10

    def test_baselines_are_at_or_below_chance_on_v2(self) -> None:
        """The shortcut-removed probe: on v2's eval split no cheap strategy wins."""
        tasks = [ENV.generate(s) for s in range(10000, 10200)]
        rows = baselines(tasks)
        chance = rows["chance"]["accuracy"]
        for name, row in rows.items():
            if name != "chance":
                assert row["accuracy"] <= chance + 0.06, (name, row)

    def test_baselines_expose_v1s_shortcut(self) -> None:
        """And on v0 they would have shown a policy what it had to beat: 100%."""
        v1 = get_environment("hidden_profile")
        rows = baselines([v1.generate(s) for s in range(1000, 1100)])
        shortcut = next(v for k, v in rows.items() if k.startswith("best content-blind"))
        assert shortcut["accuracy"] == 1.0
