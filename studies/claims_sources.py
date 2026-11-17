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
