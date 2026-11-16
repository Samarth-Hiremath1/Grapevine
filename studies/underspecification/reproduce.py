"""Reproduce this study. One command, no API key, no network.

    python -m studies.underspecification.reproduce

Recomputes every number the write-up reports from the committed episodes under
``runs/``, writes ``figures/results_tables.json``, redraws
``figures/accuracy_by_condition.{png,svg,csv}``, and prints the main tables and
the total spend. It is deterministic: CI runs it and fails if any generated
file changes.

``--rerun`` prints the commands that would re-collect the episodes from the
API, with the cost each one actually incurred. It does not run them; those are
paid calls, and the committed runs are immutable (see ``CLAUDE.md``).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from grapevine.experiments.figure import make_two_panel_figure
from studies.underspecification.tables import _rounded, build, markdown

#: This study's directory. Every path the study uses is relative to it.
STUDY_DIR = Path(__file__).resolve().parent

#: Where the configs live now, relative to the repository root. The manifests
#: record the path as it was when the run happened, before Step 2 moved them.
_CONFIG_DIR = "studies/underspecification/configs"


def _rerun_command(manifest: dict[str, Any]) -> str:
    """Reconstruct the command that produced a run, from its own manifest.

    Only values the manifest recorded are used, so the printed command is not a
    guess about what was typed.
    """
    resolved = dict(manifest.get("resolved") or {})
    config = Path(str(manifest["config_path"])).name
    parts = [
        "uv run python -m grapevine.experiments.run",
        f"--config {_CONFIG_DIR}/{config}",
        f"--label {manifest['label']}",
        f"--n-episodes {resolved['n_episodes']}",
        f"--seed-start {resolved['seed_start']}",
    ]
    conditions = resolved.get("conditions_run") or sorted(
        dict(manifest.get("summaries") or {})
    )
    parts.append(f"--conditions {','.join(str(c) for c in conditions)}")
    return " \\\n    ".join(parts)


def _print_rerun(root: Path) -> None:
    """Print the paid commands behind the committed runs, oldest first."""
    print(
        "These produced the committed runs, reconstructed from each run's own\n"
        "manifest. They are NOT run here: each one spends money, answers vary\n"
        "because this model will not accept a temperature, and committed runs are\n"
        "immutable (CLAUDE.md rule 6). A rerun writes a new timestamped directory\n"
        "under runs/ and overwrites nothing.\n"
    )
    total = 0.0
    for path in sorted(root.glob("runs/*/manifest.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        cost = float(manifest["total_cost_usd"])
        calls = manifest["client_totals"]["n_calls"]
        total += cost
        print(f"# {path.parent.name} — ${cost:.4f}, {int(calls)} calls")
        print(f"{_rerun_command(manifest)}\n")
    print(f"Total if every run above were repeated: ${total:.4f}")


def main(argv: list[str] | None = None) -> int:
    """Rebuild this study's tables and figure from its committed runs."""
    parser = argparse.ArgumentParser(
        prog="python -m studies.underspecification.reproduce",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--root",
        default=str(STUDY_DIR),
        help="the study directory (default: this file's directory)",
    )
    parser.add_argument(
        "--out-dir", default="figures", help="output directory, relative to --root"
    )
    parser.add_argument(
        "--rerun",
        action="store_true",
        help="print the paid commands that produced the committed runs, and exit",
    )
    args = parser.parse_args(argv)

    root = Path(args.root)
    out = root / args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    if args.rerun:
        _print_rerun(root)
        return 0

    result = _rounded(build(root))

    (out / "results_tables.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )

    panels = [
        (
            "Task and rule not stated\n(seeds 1000-1199, n=200 each)",
            [(label, result["no_rule"][label]) for label in ("A", "B", "C", "D")],
        ),
        (
            "Task question and scoring rule stated\n(seeds 1000-1099, n=100 each)",
            [
                (label, result["rule"][label])
                for label in ("A", "A (matched)", "B", "C", "D")
            ],
        ),
    ]
    make_two_panel_figure(panels, out, stem="accuracy_by_condition")

    print(markdown(result))
    print(f"\nwrote {out / 'results_tables.json'} and accuracy_by_condition.png/.svg/.csv")
    print(f"total spend across all committed runs: ${result['total_cost_usd']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
