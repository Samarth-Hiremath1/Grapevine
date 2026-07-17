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
    ]  # 100% ceiling
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


def test_cli_gen_and_diagnose(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    tasks_path = tmp_path / "tasks.jsonl"
    rc = main(["gen", "hidden_profile", "--n", "3", "--out", str(tasks_path)])
    assert rc == 0
    assert tasks_path.exists()
    assert len(tasks_path.read_text().strip().splitlines()) == 3

    rc = main(["diagnose", "hidden_profile", "--n", "100"])
    assert rc == 0  # not hackable -> exit 0
    out = capsys.readouterr().out
    assert "Reward-hacking diagnostics" in out


def test_cli_metrics(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "t.jsonl"
    with TranscriptWriter(path) as writer:
        writer.write(_make_episode(True, True))
        writer.write(_make_episode(True, True, "single_agent_full_context"))
    rc = main(["metrics", str(path)])
    assert rc == 0
    assert "Distributed-team accuracy" in capsys.readouterr().out
