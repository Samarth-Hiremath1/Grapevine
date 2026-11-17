"""The README is also the PyPI page, where relative links do not resolve."""

from __future__ import annotations

import re
from pathlib import Path

REPO = "https://github.com/Samarth-Hiremath1/Grapevine/"
RAW = "https://raw.githubusercontent.com/Samarth-Hiremath1/Grapevine/main/"
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")


def test_every_link_is_absolute_and_points_at_a_file_in_the_repository() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    targets = LINK.findall(text)
    assert targets
    for target in targets:
        if target.startswith("#"):
            continue
        assert target.startswith(("https://", "http://")), f"relative link: {target}"
        for prefix in (REPO + "blob/main/", REPO + "tree/main/", RAW):
            if target.startswith(prefix):
                path = target[len(prefix):].split("#")[0]
                assert Path(path).exists(), f"{target} points at {path}, which does not exist"
