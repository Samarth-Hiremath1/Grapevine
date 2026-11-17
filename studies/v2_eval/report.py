"""Copy the primary run's analysis output into the study README.

    python -m studies.v2_eval.report            # regenerate the block
    python -m studies.v2_eval.report --check    # verify; CI runs this

The tables between the markers in ``README.md`` are ``results.md`` from the
primary run, as the pre-registered analysis wrote it. Nothing inside the block
is typed by hand.
"""

from __future__ import annotations

import argparse
from pathlib import Path

STUDY_DIR = Path(__file__).resolve().parent
README = STUDY_DIR / "README.md"
RESULTS = STUDY_DIR / "runs" / "20261116T091238Z_primary" / "results.md"
BEGIN = "<!-- BEGIN GENERATED: results (python -m studies.v2_eval.report) -->"
END = "<!-- END GENERATED: results -->"


def render(readme: str, results: str) -> str:
    """Replace the generated block in ``readme`` with ``results``.

    Args:
        readme (str): The README text, containing both markers.
        results (str): The analysis output.

    Returns:
        str: The README with the block regenerated.

    Raises:
        ValueError: If either marker is missing.
    """
    if BEGIN not in readme or END not in readme:
        raise ValueError("README.md is missing the generated-block markers")
    head, rest = readme.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    # Demote the analysis headings by one level so they nest under the README's.
    body = "\n".join("#" + line if line.startswith("#") else line
                     for line in results.strip().splitlines())
    return f"{head}{BEGIN}\n\n{body}\n\n{END}{tail}"


def main(argv: list[str] | None = None) -> int:
    """Regenerate the block, or verify it with ``--check``.

    Args:
        argv (list[str] | None): Command-line arguments.

    Returns:
        int: Exit code.
    """
    parser = argparse.ArgumentParser(prog="python -m studies.v2_eval.report")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    current = README.read_text(encoding="utf-8")
    fresh = render(current, RESULTS.read_text(encoding="utf-8"))
    if args.check:
        same = fresh == current
        print("README results block " + ("unchanged" if same else "has drifted from results.md"))
        return 0 if same else 1
    README.write_text(fresh, encoding="utf-8")
    print(f"wrote {README.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
