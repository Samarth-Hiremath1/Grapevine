"""Every example runs, offline, from a clean interpreter."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = sorted(Path("examples").glob("[0-9][0-9]_*.py"))


def test_there_are_examples() -> None:
    assert len(EXAMPLES) >= 3


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example_runs(path: Path, tmp_path: Path) -> None:
    """Run from a temporary directory, so an example cannot lean on the repo's cwd."""
    result = subprocess.run(
        [sys.executable, str(path.resolve())],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip()
