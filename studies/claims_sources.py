"""Deterministic aggregates for ``docs/claims.yaml`` that no committed file stores.

Each function reads committed files only, calls no model, and returns a dict a
claim's template is rendered from.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def v0_prompt_freeze() -> dict[str, Any]:
    """How many digests freeze the v0 prompts, and how many episodes they cover.

    Returns:
        dict[str, Any]: ``digests`` and ``episodes``.
    """
    golden = json.loads(
        (ROOT / "studies/underspecification/prompts_golden.json").read_text(encoding="utf-8")
    )
    conditions = golden["conditions"]
    return {
        "digests": len(conditions),
        "episodes": sum(int(c["n_episodes"]) for c in conditions.values()),
    }


def v2_luna_no_communication_max() -> dict[str, Any]:
    """The highest ``no_communication`` cell for the two luna models, both objectives.

    Returns:
        dict[str, Any]: ``correct`` and ``n`` of that cell.
    """
    results = json.loads(
        (ROOT / "studies/v2_eval/runs/20261116T091238Z_primary/results.json").read_text(encoding="utf-8")
    )
    cells = [results["cells"][m][f"no_communication/{o}"]
             for m in ("gpt-5.6-luna", "gpt-6-luna") for o in ("stated", "unstated")]
    top = max(cells, key=lambda c: c["correct"])
    return {"correct": top["correct"], "n": top["n"]}


def control_first_option_1200() -> dict[str, Any]:
    """``first_option`` on the clean control at seed range 1200: the one nominal false alarm.

    Returns:
        dict[str, Any]: ``n_correct`` and ``n`` of that shortcut probe.
    """
    import sys

    sys.path.insert(0, str(ROOT / "tests"))
    from fixtures.flawed_envs import CLEAN_CONTROL  # type: ignore[import-not-found]

    from grapevine import audit

    rows = audit(CLEAN_CONTROL, n_tasks=200, seed=1200).get("shortcuts").detail["shortcuts"]
    row = next(r for r in rows if r["name"] == "first_option")
    return {"n_correct": row["n_correct"], "n": row["n"]}
