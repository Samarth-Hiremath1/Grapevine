"""How often the battery fails a clean environment, and how often it misses a planted flaw.

    python -m studies.battery_calibration.false_fail            # regenerate
    python -m studies.battery_calibration.false_fail --check    # verify; CI runs this

Deterministic: every audit is seeded, so the output is identical on every run.

* **Stability and false positives.** The test suite's clean control and the
  example in ``examples/02_write_an_environment.py`` are audited on 40 disjoint
  ranges of 200 seeds each, and the overall verdict and the status of each check
  are counted. ``solo_solvability`` and ``reward_hacking`` measure the
  single-view lean every such task has (``docs/validity-card.md``); they should
  report ``measured`` on every range, whatever the zero-information diagnostic
  says.
* **Missed defects.** Every planted-flaw fixture, ``hidden_profile_v2`` and the
  v0 ``hidden_profile`` are audited on 10 disjoint ranges, and each run counts as
  a detection when the check responsible reports the expected status.

The two clean environments draw their random numbers in the same order, so
their results on the same seed range are correlated; the review pointed this
out (``docs/review-v0.2.md``, m5). They are reported separately, not pooled.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from grapevine import Environment, audit, get_environment
from grapevine.audit.checks import minimum_detectable_accuracy

ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = Path(__file__).resolve().parent / "README.md"
JSON_PATH = Path(__file__).resolve().parent / "results.json"
N_RANGES = 40
N_DETECTION_RANGES = 10
N_TASKS = 200
POWER_LIMITED = ("solo_solvability", "reward_hacking")


def _fixtures() -> Any:
    sys.path.insert(0, str(ROOT / "tests"))
    import fixtures.flawed_envs as fixtures  # type: ignore[import-not-found]

    return fixtures


def _environments() -> list[Environment]:
    """The two clean environments, loaded from the test fixtures and the example."""
    spec = importlib.util.spec_from_file_location(
        "venue_example", ROOT / "examples" / "02_write_an_environment.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["venue_example"] = module
    spec.loader.exec_module(module)
    venue: Environment = module.VenueChoice()
    control: Environment = _fixtures().CLEAN_CONTROL
    return [control, venue]


def measure() -> dict[str, Any]:
    """Audit each clean environment on every seed range.

    Returns:
        dict[str, Any]: Per environment, failing audits overall, failing audits
        outside the power-limited checks, and failures by check.
    """
    out: dict[str, Any] = {}
    for env in _environments():
        failed = 0
        failed_elsewhere = 0
        by_check: Counter[str] = Counter()
        verdicts: Counter[str] = Counter()
        power_limited: dict[str, Counter[str]] = {c: Counter() for c in POWER_LIMITED}
        diagnostic_rejected: Counter[str] = Counter()
        for k in range(N_RANGES):
            card = audit(env, n_tasks=N_TASKS, seed=k * N_TASKS)
            failed += not card.passed
            failed_elsewhere += any(c not in POWER_LIMITED for c in card.flagged_checks)
            by_check.update(card.flagged_checks)
            verdicts[card.verdict.value] += 1
            for c in POWER_LIMITED:
                result = card.get(c)
                power_limited[c][result.status.value] += 1
                diagnostic_rejected[c] += bool(result.detail["zero_information_diagnostic"]["rejected"])
        out[env.name] = {
            "audits": N_RANGES, "failed": failed, "failed_outside_power_limited": failed_elsewhere,
            "by_check": dict(sorted(by_check.items())),
            "verdicts": dict(sorted(verdicts.items())),
            "power_limited_statuses": {c: dict(sorted(v.items())) for c, v in power_limited.items()},
            "zero_information_rejected": dict(sorted(diagnostic_rejected.items())),
        }
    return out


def detection() -> dict[str, Any]:
    """Audit every negative control on disjoint seed ranges.

    Returns:
        dict[str, Any]: Per fixture, the responsible check, and detections out of runs.
    """
    fixtures = _fixtures()
    cases: list[tuple[str, Environment, str, str]] = [
        (name, env, d.expected_check, d.expected_status)
        for name, (env, d) in sorted(fixtures.FLAWED_ENVS.items())
    ]
    cases.append(("hidden_profile_v2", get_environment("hidden_profile_v2"), "solo_solvability", "fail"))
    cases.append(("hidden_profile (v0)", get_environment("hidden_profile"), "shortcuts", "fail"))
    out: dict[str, Any] = {}
    for name, env, check, status in cases:
        hits = sum(
            audit(env, n_tasks=N_TASKS, seed=50_000 + k * N_TASKS).get(check).status.value == status
            for k in range(N_DETECTION_RANGES)
        )
        out[name] = {"check": check, "status": status, "detected": hits, "runs": N_DETECTION_RANGES}
    return out


def detection_floor() -> dict[str, int]:
    """The worst detection rate over every negative control, from the committed results.

    Returns:
        dict[str, int]: ``detected`` and ``runs`` of the least-detected fixture.
    """
    caught = json.loads(JSON_PATH.read_text(encoding="utf-8"))["detection"]
    worst = min(caught.values(), key=lambda r: r["detected"] / r["runs"])
    return {"detected": worst["detected"], "runs": worst["runs"]}


def markdown(clean: dict[str, Any], caught: dict[str, Any]) -> str:
    """The measurement as a report.

    Args:
        clean (dict[str, Any]): Output of :func:`measure`.
        caught (dict[str, Any]): Output of :func:`detection`.

    Returns:
        str: Markdown text.
    """
    family = 6 * 3 + 1  # solo_solvability's probes x agents, plus the learned probe
    mda = minimum_detectable_accuracy(N_TASKS, 0.25, 0.05 / family)
    lines = [
        "# Battery calibration: false positives and missed defects",
        "",
        "Generated by `python -m studies.battery_calibration.false_fail`. Do not edit by hand.",
        "",
        "## Clean environments",
        "",
        f"Each audited on {N_RANGES} disjoint ranges of {N_TASKS} seeds "
        f"(seeds 0 to {N_RANGES * N_TASKS - 1}).",
        "",
        "| Environment | Audits | Overall verdicts | Failing checks | `solo_solvability` | `reward_hacking` | Zero-information diagnostic rejected (solo / reward) |",
        "|---|---:|---|---|---|---|---|",
    ]
    def counts(d: dict[str, int]) -> str:
        return ", ".join(f"{k} ×{v}" for k, v in d.items()) or "none"
    for name, row in clean.items():
        checks = ", ".join(f"`{c}` ×{n}" for c, n in row["by_check"].items()) or "none"
        pl = row["power_limited_statuses"]
        zr = row["zero_information_rejected"]
        lines.append(f"| `{name}` | {row['audits']} | {counts(row['verdicts'])} | {checks} | "
                     f"{counts(pl['solo_solvability'])} | {counts(pl['reward_hacking'])} | "
                     f"{zr['solo_solvability']} / {zr['reward_hacking']} |")
    lines += [
        "",
        "The zero-information diagnostic rejects on some ranges and not others, because",
        "these environments really do lean towards the answer from one view and the lean",
        f"is near what {N_TASKS} tasks can detect (a per-agent probe usually misses a true",
        f"single-view accuracy below {mda:.1%}). The statuses do not follow it.",
        "",
        "## Negative controls",
        "",
        f"Each audited on {N_DETECTION_RANGES} disjoint ranges of {N_TASKS} seeds, from seed 50000.",
        "",
        "| Fixture | Responsible check | Expected | Detected |",
        "|---|---|---|---:|",
    ]
    for name, row in caught.items():
        lines.append(f"| `{name}` | `{row['check']}` | {row['status']} | {row['detected']}/{row['runs']} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Regenerate the report, or verify it with ``--check``.

    Args:
        argv (list[str] | None): Command-line arguments.

    Returns:
        int: Exit code.
    """
    parser = argparse.ArgumentParser(prog="python -m studies.battery_calibration.false_fail")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    clean, caught = measure(), detection()
    text = markdown(clean, caught)
    data = json.dumps({"clean": clean, "detection": caught,
                       "minimum_detectable_accuracy": minimum_detectable_accuracy(N_TASKS, 0.25, 0.05 / 19)},
                      indent=2) + "\n"
    if args.check:
        same = all(path.exists() and path.read_text(encoding="utf-8") == fresh
                   for path, fresh in ((OUT_PATH, text), (JSON_PATH, data)))
        print("battery_calibration/README.md and results.json " + ("unchanged" if same else "have drifted"))
        return 0 if same else 1
    OUT_PATH.write_text(text, encoding="utf-8")
    JSON_PATH.write_text(data, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
