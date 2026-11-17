"""Audit a bundled environment and read its Validity Card.

    python examples/01_audit_an_environment.py

Offline, no API key, about a second. It audits the environment this
repository's first result was built on, and the one built to replace it, and
prints what each check found.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from grapevine import Status, audit, get_environment


def main() -> None:
    """Audit two environments and print every check that did not pass."""
    for name in ("hidden_profile", "hidden_profile_v2"):
        env = get_environment(name)
        # The environment's own eval seeds when it declares a split, else 0.
        split = env.seed_split()
        seed = split.eval.start if split else 0
        card = audit(env, n_tasks=100, seed=seed)

        print(f"{name}: {card.verdict.value} on {card.n_tasks} tasks from seed {seed}")
        for result in card.results:
            if result.status is not Status.PASS:
                print(f"  {result.status.value:7} {result.check_id}: {result.summary}")
        print()

    # A card is a file you can commit next to the environment it describes.
    with tempfile.TemporaryDirectory() as out:
        path = Path(out) / "validity_card.md"
        path.write_text(card.to_markdown(), encoding="utf-8")
        print(f"wrote a {len(path.read_text(encoding='utf-8').splitlines())}-line card for {card.environment}")


if __name__ == "__main__":
    main()
