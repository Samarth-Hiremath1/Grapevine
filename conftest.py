"""Make the repository root importable so tests can reach ``studies``.

With pytest's default ``prepend`` import mode and no ``__init__.py`` under
``tests/``, pytest puts ``tests/`` on ``sys.path`` but not the repository root,
so ``import studies...`` would fail. The studies are not installed with the
package (they are evidence, not API), so this is the hook that lets their
regression tests run.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
for _path in (_ROOT, _ROOT / "tests"):
    # tests/ as well as the root, so `from fixtures.flawed_envs import ...` works
    # from any test module regardless of which one pytest collects first.
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
