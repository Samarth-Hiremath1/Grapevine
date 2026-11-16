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

_ROOT = str(Path(__file__).resolve().parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
