"""The pre-registered eval is fixed, audited and guarded before it is run.

Nothing here calls a model. Every check runs offline, on the design, the frozen
prompts, a scripted run, and the guards that stand between a command and a bill.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from grapevine.audit import Status, audit
from studies.v2_eval import analyze, freeze, run
from studies.v2_eval.design import (
    CANDIDATE_MODELS,
    CELLS,
    DESIGN,
    ENVIRONMENT,
    MARKERS,
    Design,
    EvalDesign,
    decision_messages,
    opening_prompts,
)


class TestDesign:
    def test_six_cells(self) -> None:
        assert len(CELLS) == 6
        assert {c for c, _ in CELLS} == {"full_info", "no_communication", "communication"}

    def test_pilot_and_primary_seeds_are_disjoint_and_held_out(self) -> None:
        """Enforced in code, not by convention (CLAUDE.md rule 4)."""
        assert not set(DESIGN.pilot_seeds) & set(DESIGN.primary_seeds)
        split = ENVIRONMENT.seed_split()
        assert set(DESIGN.primary_seeds) <= set(split.eval)
        assert set(DESIGN.pilot_seeds) <= set(split.pilot)
        assert not set(DESIGN.primary_seeds) & set(split.train)

    def test_overlapping_seeds_are_refused(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            Design(pilot_seeds=DESIGN.primary_seeds[:20], n_pilot=20)

    def test_seeds_outside_the_eval_split_are_refused(self) -> None:
        with pytest.raises(ValueError, match="eval split"):
            Design(primary_seeds=tuple(range(100)))

    def test_the_v2_baselines_are_already_audited(self) -> None:
        """The two single-call arms are v2's own audited conditions, word for word."""
        task = ENVIRONMENT.generate(DESIGN.primary_seeds[0])
        v2 = ENVIRONMENT.conditions(task)
        for condition in ("full_info", "no_communication"):
            ours = decision_messages(task, condition, "stated")[-1].content
            assert ours == v2[condition].prompts[0], condition
        assert MARKERS == {k: v for k, v in MARKERS.items()}


class TestTheArmsAreAudited:
    """The pre-registered prompts are checked by the battery, not just written down."""

    @pytest.fixture(scope="class")
    def card(self):  # type: ignore[no-untyped-def]
        return audit(EvalDesign(), n_tasks=100, seed=DESIGN.primary_seeds[0])

    def test_only_the_unstated_arms_fail_the_objective_check(self, card) -> None:  # type: ignore[no-untyped-def]
        """That is the manipulation, so it is the one failure there should be."""
        rows = {r["condition"]: r["states_objective"] for r in card.get("objective").detail["conditions"]}
        assert rows == {
            f"{c}_{o}": o == "stated" for c, o in CELLS
        }

    def test_no_arm_differs_beyond_what_it_declares(self, card) -> None:  # type: ignore[no-untyped-def]
        result = card.get("condition_diff")
        assert result.status is Status.PASS, result.summary
        assert result.detail["verdict_counts"]["differs only by its declared difference"] == 15

    def test_every_prompt_in_a_stated_arm_states_both_halves(self) -> None:
        task = ENVIRONMENT.generate(DESIGN.primary_seeds[3])
        for condition, objective in CELLS:
            for prompt in opening_prompts(task, condition, objective):
                stated = task.objective.question in prompt and task.objective.scoring_rule in prompt
                assert stated == (objective == "stated"), (condition, objective)


class TestFrozenPrompts:
    def test_the_committed_prompts_match_the_design(self) -> None:
        assert freeze.main(["--check"]) == 0

    def test_a_changed_template_is_caught(self, monkeypatch: pytest.MonkeyPatch) -> None:
        before = freeze.digest()
        monkeypatch.setitem(MARKERS, "communication", MARKERS["communication"] + " Please.")
        assert freeze.digest() != before

    def test_the_prereg_quotes_the_fixed_prompt_text_verbatim(self) -> None:
        from studies.v2_eval.design import SYSTEM_PROMPT

        prereg = Path("docs/prereg/hidden_profile_v2_eval.md").read_text(encoding="utf-8")
        assert SYSTEM_PROMPT in prereg
        for marker in MARKERS.values():
            assert marker in prereg

    def test_the_prereg_records_the_committed_digests(self) -> None:
        prereg = Path("docs/prereg/hidden_profile_v2_eval.md").read_text(encoding="utf-8")
        digests = json.loads(freeze.DIGEST_PATH.read_text(encoding="utf-8"))
        assert digests["pilot"]["sha256"] in prereg
        assert digests["primary"]["sha256"] in prereg


class TestSpendingGuards:
    """No command reaches a provider without an explicit, sufficient approval."""

    def test_the_estimate_refuses_an_unpriced_model(self) -> None:
        with pytest.raises(KeyError):
            run.estimate(["gpt-9-imaginary"], "pilot")

    def test_the_estimate_covers_every_call(self) -> None:
        plan = run.estimate(["gpt-5.6-luna"], "primary")
        calls_per_task = sum(DESIGN.calls_per_task()[c] for c, _ in CELLS)
        assert plan["per_model"]["gpt-5.6-luna"]["calls"] == calls_per_task * DESIGN.n_primary

    def test_the_whole_design_fits_the_budget_even_in_the_worst_case(self) -> None:
        pilot = run.estimate(list(CANDIDATE_MODELS), "pilot")
        primary = run.estimate(list(CANDIDATE_MODELS), "primary")
        worst = pilot["total_if_every_call_hits_cap_usd"] + primary["total_if_every_call_hits_cap_usd"]
        assert pilot["committed_spend_usd"] + worst < DESIGN.budget_usd

    def test_a_live_run_needs_an_approval(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert run.main(["--phase", "pilot", "--models", "gpt-5.6-luna"]) == 2
        assert "--approve-usd" in capsys.readouterr().err

    def test_an_approval_below_the_estimate_is_refused(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert run.main(["--phase", "pilot", "--models", "gpt-5.6-luna", "--approve-usd", "0.001"]) == 2
        assert "below the estimate" in capsys.readouterr().err

    def test_an_approval_past_the_budget_is_refused(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert run.main(["--phase", "pilot", "--models", "gpt-5.6-luna", "--approve-usd", "50"]) == 2
        assert "remaining budget" in capsys.readouterr().err

    def test_live_spend_stops_at_the_ceiling(self) -> None:
        from grapevine.rollout.client import Completion

        log = run.CallLog(ceiling_usd=0.01)
        log.record(Completion("a", 1, 1, 0.006))
        with pytest.raises(run.BudgetError):
            log.record(Completion("b", 1, 1, 0.006))


class TestScriptedRunAndAnalysis:
    @pytest.fixture(scope="class")
    def run_dir(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        out = tmp_path_factory.mktemp("v2eval") / "run"
        assert run.main(["--phase", "pilot", "--models", "gpt-5.6-luna", "--scripted",
                         "--out", str(out)]) == 0
        return out

    def test_the_manifest_is_complete_and_synthetic(self, run_dir: Path) -> None:
        manifest = json.loads((run_dir / "manifest.json").read_text())
        assert manifest["synthetic"] is True
        assert manifest["complete"] is True
        assert manifest["episodes_completed"] == DESIGN.n_pilot * len(CELLS)

    def test_every_call_is_logged_with_its_finish_reason(self, run_dir: Path) -> None:
        calls = [json.loads(line) for line in (run_dir / "calls.jsonl").read_text().splitlines()]
        assert calls
        for call in calls:
            for key in ("finish_reason", "reasoning_tokens", "truncated", "cost_usd"):
                assert key in call

    def test_episodes_record_every_prompt(self, run_dir: Path) -> None:
        episodes = [json.loads(line) for line in (run_dir / "episodes.jsonl").read_text().splitlines()]
        assert all(turn["messages"] for e in episodes for turn in e["turns"])

    def test_the_analysis_refuses_synthetic_data(self, run_dir: Path) -> None:
        """Rule 2: a results table containing a synthetic episode must fail to build."""
        with pytest.raises(analyze.SyntheticDataError):
            analyze.analyze(run_dir)

    def test_the_analysis_refuses_a_pilot(self, run_dir: Path, tmp_path: Path) -> None:
        manifest = json.loads((run_dir / "manifest.json").read_text())
        manifest["synthetic"] = False
        fake = tmp_path / "pilot"
        fake.mkdir()
        (fake / "manifest.json").write_text(json.dumps(manifest))
        with pytest.raises(ValueError, match="pilot"):
            analyze.analyze(fake)

    def test_the_analysis_refuses_an_incomplete_run(self, tmp_path: Path) -> None:
        (tmp_path / "manifest.json").write_text(json.dumps(
            {"synthetic": False, "phase": "primary", "complete": False,
             "episodes_completed": 3, "episodes_expected": 10, "stopped_early": "budget"}
        ))
        with pytest.raises(ValueError, match="incomplete"):
            analyze.analyze(tmp_path)


class TestAnalysisMaths:
    def test_cell_summary(self) -> None:
        rows = [
            {"correct": True, "parse_failure": False, "truncated": False, "answer": "A", "decoy": "B"},
            {"correct": False, "parse_failure": False, "truncated": False, "answer": "B", "decoy": "B"},
            {"correct": False, "parse_failure": True, "truncated": True, "answer": None, "decoy": "B"},
        ]
        s = analyze.cell_summary(rows)
        assert (s["n"], s["correct"], s["chose_decoy"], s["parse_failures"], s["truncated"]) == (3, 1, 1, 1, 1)
        assert 0.0 < s["ci95"][0] < 1 / 3 < s["ci95"][1] < 1.0

    def test_paired_contrast_aligns_by_task_id(self) -> None:
        a = {"t1": {"correct": True}, "t2": {"correct": True}}
        b = {"t2": {"correct": False}, "t1": {"correct": True}}
        c = analyze.paired_contrast(a, b, n_contrasts=7)
        assert c["n_paired"] == 2 and c["mean_difference"] == pytest.approx(0.5)

    def test_paired_contrast_refuses_mismatched_tasks(self) -> None:
        """Positional pairing after a dropped episode misaligned v0 (D2)."""
        with pytest.raises(ValueError, match="different tasks"):
            analyze.paired_contrast({"t1": {"correct": True}}, {"t2": {"correct": True}}, n_contrasts=7)

    def test_seven_contrasts_are_preregistered(self) -> None:
        assert len(analyze.CONTRASTS) == 7
