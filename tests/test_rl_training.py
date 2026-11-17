"""GRPO with a real model: the smoke run, and proof that frozen partners stay frozen.

Skipped unless the ``[rl]`` extra is installed. Downloads a tiny random model
(``hf-internal-testing/tiny-random-LlamaForCausalLM``) on first run.

The isolation tests are the point of this file. The v0 trainer built its
"frozen" collaborators from the very model object it was updating, so they moved
with every step. These tests take an optimiser step and check, three ways, that
a frozen partner did not:

1. its weights hash identically before and after;
2. its greedy output on a fixed prompt is byte-identical;
3. it shares no tensor storage with the policy at all.

A test that only ever passes proves nothing, so it also reproduces the v0 bug
-- a partner wrapping the policy object -- and requires that version to fail
the same check. And it requires the *policy* to have changed, or "the partner
did not move" would be trivially true of a step that moved nothing.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("torch")
pytest.importorskip("transformers")
pytest.importorskip("trl")
pytest.importorskip("peft")

from grapevine.rl import HFClient, load_config  # noqa: E402
from grapevine.rl.grpo import build_trainer, prepare, train  # noqa: E402
from grapevine.rollout.client import Message  # noqa: E402

os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")

SMOKE = "configs/rl_smoke_cpu.yaml"
TINY = "hf-internal-testing/tiny-random-LlamaForCausalLM"
PROBE = [Message("system", "You are a teammate."), Message("user", "Which supplier?")]


def _greedy(client: HFClient) -> str:
    return asyncio.run(client.complete(PROBE, max_tokens=12, temperature=0.0)).text


def _varied_reward(completions: list[Any], **_: Any) -> list[float]:
    """A reward that differs between completions, so GRPO's advantages are
    non-zero and an optimiser step actually changes the policy.

    The team reward alone is zero for every completion of a random model, which
    gives zero advantage, zero gradient and a step that moves nothing -- and then
    "the partner did not move" would prove nothing.
    """
    texts = [c if isinstance(c, str) else str(c) for c in completions]
    return [float(len(set(t))) / 10.0 for t in texts]


def _config(tmp_path: Path, **partners: Any) -> Any:
    """The smoke config, pointed at a temporary directory, with a real step size."""
    import yaml

    data = yaml.safe_load(Path(SMOKE).read_text(encoding="utf-8"))
    data["output_dir"] = str(tmp_path / "run")
    data["grpo"]["max_steps"] = 1
    data["grpo"]["learning_rate"] = 1.0e-2
    if partners:
        data["partners"] = partners
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return load_config(path)


def test_smoke_config_runs_two_steps_and_writes_a_manifest(tmp_path: Path) -> None:
    """The CI smoke run: the loop is wired. It is not training, and says so."""
    import yaml

    data = yaml.safe_load(Path(SMOKE).read_text(encoding="utf-8"))
    data["output_dir"] = str(tmp_path / "smoke")
    path = tmp_path / "smoke.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    manifest = train(path, allow_flagged=True)

    assert manifest["global_step"] == 2
    assert manifest["n_episodes_played"] > 0
    assert manifest["synthetic"] is True
    assert manifest["reportable"] is False
    assert manifest["partners_frozen"] is True
    # v2 fails solo_solvability (docs/audit.md, A2). The smoke run is plumbing,
    # never a result, and the override is recorded rather than silent.
    assert manifest["audit_gate"]["passed"] is False
    assert manifest["audit_gate"]["allowed_flagged"] is True
    assert manifest["audit_gate"]["flagged_checks"] == ["solo_solvability"]
    for key in ("model", "seed", "environment", "reward", "partners"):
        assert key in manifest, key
    assert manifest["environment"]["version"] == "2"
    assert len(manifest["audit_gate"]["card_hash"]) == 64
    assert manifest["provenance_start"]["libraries"]["trl"].startswith("1.18")

    lines = (tmp_path / "smoke" / "trajectories.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines and all(json.loads(line)["synthetic"] is True for line in lines)


def test_frozen_partners_are_unchanged_after_an_optimizer_step(tmp_path: Path) -> None:
    config = _config(tmp_path, kind="frozen")
    ctx = prepare(config, allow_flagged=True)
    trainer = build_trainer(ctx, extra_reward_funcs=[_varied_reward])
    partner = ctx.partner
    assert isinstance(partner, HFClient)
    policy = trainer.model

    # The partner is a separate load: not one tensor is shared with the policy.
    partner_storage = {p.data_ptr() for p in partner.lm.parameters()}
    policy_storage = {p.data_ptr() for p in policy.parameters()}
    assert partner is not ctx.policy
    assert partner.lm is not policy
    assert not partner_storage & policy_storage
    assert all(not p.requires_grad for p in partner.lm.parameters())
    assert not partner.lm.training

    partner_before = partner.fingerprint()
    partner_output_before = _greedy(partner)
    policy_before = HFClient(policy, trainer.processing_class).fingerprint()

    trainer.train()
    assert trainer.state.global_step == 1

    policy_after = HFClient(policy, trainer.processing_class).fingerprint()
    assert policy_after != policy_before, (
        "the policy did not change, so this step proves nothing about the partner"
    )
    assert partner.fingerprint() == partner_before, "a frozen partner's weights moved"
    assert _greedy(partner) == partner_output_before, "a frozen partner's output changed"


def test_the_v0_bug_would_be_caught(tmp_path: Path) -> None:
    """Negative control: a partner wrapping the policy object, as v0 built it.

    The same check that the real frozen partner passes must fail here. If it did
    not, the test above would be unable to detect the bug it exists for.
    """
    config = _config(tmp_path, kind="scripted")
    ctx = prepare(config, allow_flagged=True)
    trainer = build_trainer(ctx, extra_reward_funcs=[_varied_reward])
    shared = HFClient(trainer.model, trainer.processing_class, frozen=False)

    before = shared.fingerprint()
    trainer.train()
    assert shared.fingerprint() != before, (
        "a partner sharing the policy's weights did not change, so the isolation "
        "check could not tell a frozen partner from the v0 bug"
    )


def test_lora_trains_only_the_adapter_and_leaves_the_partner_alone(tmp_path: Path) -> None:
    """With LoRA the partner is the starting checkpoint, loaded separately.

    The trainer wraps the policy in a PEFT model, so the policy client must be
    bound to ``trainer.model`` -- the wrapped one -- and not the model passed in.
    """
    config = _config(tmp_path, kind="frozen")
    import dataclasses

    from grapevine.rl.config import LoraSettings

    config = dataclasses.replace(
        config, lora=LoraSettings(r=4, alpha=8, dropout=0.0, target_modules=("q_proj", "v_proj"))
    )
    ctx = prepare(config, allow_flagged=True)
    trainer = build_trainer(ctx, extra_reward_funcs=[_varied_reward])
    assert ctx.policy is not None and ctx.policy.lm is trainer.model  # type: ignore[attr-defined]
    trainable = [n for n, p in trainer.model.named_parameters() if p.requires_grad]
    assert trainable and all("lora_" in n for n in trainable)

    partner = ctx.partner
    assert isinstance(partner, HFClient)
    before = partner.fingerprint()
    trainer.train()
    assert partner.fingerprint() == before


def test_self_play_is_recorded_as_not_frozen(tmp_path: Path) -> None:
    """One policy plays every agent; the manifest must not call that frozen."""
    import yaml

    data = yaml.safe_load(Path(SMOKE).read_text(encoding="utf-8"))
    data["output_dir"] = str(tmp_path / "self")
    data["partners"] = {"kind": "self"}
    data.pop("trainable_agents")
    data["grpo"]["max_steps"] = 1
    path = tmp_path / "self.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    manifest = train(path, allow_flagged=True)
    assert manifest["mode"] == "self_play"
    assert manifest["partners_frozen"] is False
    assert manifest["trainable_agents"] == [0, 1, 2]
    assert manifest["global_step"] == 1


def test_the_tiny_model_is_what_ci_uses() -> None:
    assert load_config(SMOKE).model == TINY
