"""verify-claims catches a stale, mistyped or synthetic number, and passes the real docs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from grapevine.claims import ClaimsError, verify_claims
from grapevine.cli import main


def _repo(tmp_path: Path, doc: str, claims: list[dict[str, object]], data: object) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text(doc, encoding="utf-8")
    (tmp_path / "data.json").write_text(json.dumps(data), encoding="utf-8")
    path = tmp_path / "docs" / "claims.yaml"
    path.write_text(yaml.safe_dump({"claims": claims}), encoding="utf-8")
    return path


def _claim(template: str, path: object = None, **extra: object) -> dict[str, object]:
    source: dict[str, object] = {"json": "data.json"}
    if path is not None:
        source["path"] = path
    return {"id": "c", "file": "README.md", "template": template, "source": source, **extra}


DATA = {"cell": {"correct": 98, "n": 100, "accuracy": 0.98}, "diff": {"mean": 0.03, "lo": -0.02}}


def test_a_true_claim_passes(tmp_path: Path) -> None:
    path = _repo(tmp_path, "It scored 98/100 · 98.0% here.", [_claim("{correct}/{n} · {accuracy:.1%}", ["cell"])], DATA)
    [r] = verify_claims(path)
    assert r.ok, r.problem


def test_a_stale_number_fails(tmp_path: Path) -> None:
    path = _repo(tmp_path, "It scored 97/100 · 97.0% here.", [_claim("{correct}/{n} · {accuracy:.1%}", ["cell"])], DATA)
    [r] = verify_claims(path)
    assert not r.ok and "98/100" in (r.problem or "")


def test_percentage_points_wrapping_and_minus_signs(tmp_path: Path) -> None:
    doc = "a gap of +3.0 points,\n   lower bound −2.0"
    tpl = "{mean!p:+.1f} points, lower bound {lo!p:+.1f}"
    path = _repo(tmp_path, doc, [_claim(tpl, "diff")], DATA)
    [r] = verify_claims(path)
    assert r.ok, r.problem


def test_a_scalar_is_value(tmp_path: Path) -> None:
    path = _repo(tmp_path, "N is 100.", [_claim("N is {value}.", ["cell", "n"])], DATA)
    assert verify_claims(path)[0].ok


def test_a_missing_key_is_a_failed_claim_not_a_crash(tmp_path: Path) -> None:
    path = _repo(tmp_path, "x", [_claim("{correct}", ["nope"])], DATA)
    [r] = verify_claims(path)
    assert not r.ok and "KeyError" in (r.problem or "")


def test_a_source_inside_a_synthetic_run_is_refused(tmp_path: Path) -> None:
    """CLAUDE.md rule 2: a synthetic episode is never a result."""
    run = tmp_path / "runs" / "r1"
    run.mkdir(parents=True)
    (run / "manifest.json").write_text(json.dumps({"synthetic": True}), encoding="utf-8")
    (run / "results.json").write_text(json.dumps({"n": 5}), encoding="utf-8")
    claim = {"id": "c", "file": "README.md", "template": "{n}",
             "source": {"json": "runs/r1/results.json"}}
    path = _repo(tmp_path, "5", [claim], {})
    [r] = verify_claims(path)
    assert not r.ok and "synthetic" in (r.problem or "")


def test_a_call_source(tmp_path: Path) -> None:
    (tmp_path / "facts_mod.py").write_text("def facts():\n    return {'k': 7}\n", encoding="utf-8")
    claim = {"id": "c", "file": "README.md", "template": "k={k}", "source": {"call": "facts_mod:facts"}}
    path = _repo(tmp_path, "k=7", [claim], {})
    assert verify_claims(path)[0].ok


@pytest.mark.parametrize(
    "claims",
    [
        [{"id": "c", "file": "README.md", "template": "x"}],
        [_claim("x"), _claim("y")],
        [{"id": "c", "file": "README.md", "template": "x", "source": {"json": "a", "call": "b:c"}}],
    ],
    ids=["missing source", "duplicate id", "two sources"],
)
def test_a_malformed_file_is_refused(tmp_path: Path, claims: list[dict[str, object]]) -> None:
    path = _repo(tmp_path, "x", claims, DATA)
    with pytest.raises(ClaimsError):
        verify_claims(path)


def test_the_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = _repo(tmp_path, "98/100", [_claim("{correct}/{n}", ["cell"])], DATA)
    assert main(["verify-claims", "--claims", str(good)]) == 0
    (tmp_path / "README.md").write_text("97/100", encoding="utf-8")
    assert main(["verify-claims", "--claims", str(good)]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_the_repository_claims_all_verify() -> None:
    """Every number registered in docs/claims.yaml re-derives and appears verbatim."""
    results = verify_claims(Path("docs/claims.yaml"))
    failed = [f"{r.claim_id}: {r.problem}" for r in results if not r.ok]
    assert not failed, "\n".join(failed)
    assert len(results) >= 40
