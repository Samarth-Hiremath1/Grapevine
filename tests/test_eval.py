"""Tests for evaluation metrics and the transcript viewer / CLI."""

from __future__ import annotations

from pathlib import Path

from grapevine.cli import main
from grapevine.eval.metrics import compute_metrics
from grapevine.eval.view import view_transcript
from grapevine.rollout.engine import Episode, TranscriptMessage, TranscriptWriter


def _make_episode(correct: bool, surfaced: bool, condition: str | None = None) -> Episode:
    required = ["Avery led a cross-functional team of eight."]
    messages = []
    if surfaced:
        messages.append(TranscriptMessage(1, 0, "discussion", required[0]))
    else:
        messages.append(TranscriptMessage(1, 0, "discussion", "I have nothing useful."))
    return Episode(
        task_id="hidden_profile-0",
        family="hidden_profile",
        question="Who is best? Options: Avery, Blair.",
        options=["Avery", "Blair"],
        gold_answer="Avery",
        team_answer="Avery" if correct else "Blair",
        correct=correct,
        messages=messages,
        required_private_facts=required,
        n_agents=2,
        config={},
        usage={"cost_usd": 0.01},
        metadata={"condition": condition} if condition else {},
    )


def test_compute_metrics_gap_closure() -> None:
    team = [_make_episode(True, True), _make_episode(False, False)]  # 50% team acc
    single = [
        _make_episode(True, True, "single_agent_full_context"),
        _make_episode(True, True, "single_agent_full_context"),
    ]  # 100% on the full-information condition
    metrics = compute_metrics(team, single)
    assert metrics.team_accuracy == 0.5
    assert metrics.single_agent_accuracy == 1.0
    assert metrics.chance_accuracy == 0.5  # two options
    # gap-closure = (0.5 - 0.5) / (1.0 - 0.5) = 0.0
    assert metrics.gap_closure == 0.0
    assert metrics.surfacing_rate == 0.5
    assert metrics.team_cost_usd == 0.02


def test_compute_metrics_without_single() -> None:
    team = [_make_episode(True, True)]
    metrics = compute_metrics(team)
    assert metrics.single_agent_accuracy is None
    assert metrics.gap_closure is None


def test_viewer_runs_on_written_transcript(tmp_path: Path) -> None:
    path = tmp_path / "t.jsonl"
    with TranscriptWriter(path) as writer:
        writer.write(_make_episode(True, True))
        writer.write(_make_episode(False, False))
    # Should not raise while rendering.
    view_transcript(path)


def test_cli_gen_and_audit(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    tasks_path = tmp_path / "tasks.jsonl"
    rc = main(["gen", "hidden_profile", "--n", "3", "--out", str(tasks_path)])
    assert rc == 0
    assert tasks_path.exists()
    assert len(tasks_path.read_text().strip().splitlines()) == 3

    # `grapevine diagnose` was folded into the audit as its reward_hacking check.
    # Under the outcome reward hidden_profile's reward is not hackable, so that
    # check alone passes and the command exits 0.
    rc = main(["audit", "hidden_profile", "--n", "100", "--only", "reward_hacking"])
    assert rc == 0
    assert "`reward_hacking`" in capsys.readouterr().out

    # The full battery fails it, on the findings the study is about: exit 2.
    assert main(["audit", "hidden_profile", "--n", "100"]) == 2


def test_cli_train_dry_run_needs_no_model(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """`grapevine train --dry-run` runs the gate without torch or a download."""
    import yaml

    config = yaml.safe_load(Path("configs/rl_smoke_cpu.yaml").read_text(encoding="utf-8"))
    config["output_dir"] = str(tmp_path / "out")
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    assert main(["train", str(path), "--dry-run"]) == 0
    assert '"dry_run": true' in capsys.readouterr().out
    assert (tmp_path / "out" / "manifest.json").exists()


def test_cli_train_refuses_a_flagged_reward(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    import yaml

    config = yaml.safe_load(Path("configs/rl_smoke_cpu.yaml").read_text(encoding="utf-8"))
    config["output_dir"] = str(tmp_path / "out")
    config["reward"]["surfacing_weight"] = 0.5
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    assert main(["train", str(path), "--dry-run"]) == 2
    assert "refusing to train" in capsys.readouterr().err
    assert main(["train", str(path), "--dry-run", "--allow-flagged"]) == 0


def test_cli_eval_with_a_scripted_policy(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    out = tmp_path / "eval"
    rc = main(["eval", "--policy", "scripted", "--n", "5", "--rounds", "1", "--out", str(out)])
    assert rc == 0
    assert "Synthetic" in capsys.readouterr().out
    import json

    assert json.loads((out / "eval.json").read_text())["synthetic"] is True


def test_cli_metrics(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "t.jsonl"
    with TranscriptWriter(path) as writer:
        writer.write(_make_episode(True, True))
        writer.write(_make_episode(True, True, "single_agent_full_context"))
    rc = main(["metrics", str(path)])
    assert rc == 0
    assert "Distributed-team accuracy" in capsys.readouterr().out
