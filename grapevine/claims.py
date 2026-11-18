"""Machine-checked claims: every number in the prose, re-derived from its source.

A claims file lists, for each quantitative statement in the documentation, the
document it appears in, a template for its exact wording, and where its numbers
come from. :func:`verify_claims` renders each template from the source and
requires the result to appear in the document. A typo, a stale number or a
result that changed underneath the prose all fail.

Example entry::

    - id: v0.condition-A.no-rule
      file: README.md
      template: "{correct}/{n} · {accuracy:.1%}"
      source: {json: studies/underspecification/figures/results_tables.json,
               path: [no_rule, A]}

Sources:

* ``json`` -- a JSON file in the repository and a ``path`` of keys into it.
* ``call`` -- ``"module:function"``, a deterministic function in the repository
  called with no arguments, and an optional ``path`` into what it returns.

Templates use :meth:`str.format` over the value at ``path``: a mapping's keys
are fields, and a scalar is ``{value}``. One extra conversion, ``!p``,
multiplies by 100, so a difference of proportions ``0.03`` written as
percentage points is ``{mean_difference!p:+.1f}`` -> ``+3.0``.

A claim may also carry ``expect``, a mapping of keys to values the source
must hold, for what the sentence asserts but the template does not render: "all
200 tasks share **one** support pattern" renders 200 and expects
``distinct_support_patterns: 1``.

Matching ignores line wrapping, repeated whitespace, and the difference between
``-`` and the typographic minus ``−``. Nothing else.

A source that sits inside a run directory whose ``manifest.json`` says
``synthetic: true`` is refused: a synthetic episode is never a result
(``CLAUDE.md`` rule 2).
"""

from __future__ import annotations

import importlib
import json
import re
import string
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

__all__ = ["ClaimResult", "ClaimsError", "load_claims", "verify_claims"]


class ClaimsError(ValueError):
    """Raised when the claims file itself is malformed."""


@dataclass(frozen=True)
class ClaimResult:
    """The outcome of checking one claim.

    Attributes:
        claim_id (str): The claim's id.
        file (str): The document it is checked against.
        rendered (str | None): The text the source produces, or None if it
            could not be produced.
        ok (bool): True when the rendered text appears in the document.
        problem (str | None): Why it failed, when it did.
    """

    claim_id: str
    file: str
    rendered: str | None
    ok: bool
    problem: str | None = None


class _Formatter(string.Formatter):
    """``str.format`` with one extra conversion, ``!p``: multiply by 100."""

    def convert_field(self, value: Any, conversion: str | None) -> Any:
        if conversion == "p":
            return float(value) * 100
        return super().convert_field(value, conversion)


_FORMATTER = _Formatter()
_MINUS = str.maketrans({"−": "-", " ": " "})


def _normalise(text: str) -> str:
    """Collapse whitespace and unify minus signs, for matching only."""
    return re.sub(r"\s+", " ", text.translate(_MINUS)).strip()


def load_claims(path: Path) -> list[dict[str, Any]]:
    """Read and validate a claims file.

    Args:
        path (Path): The YAML file.

    Returns:
        list[dict[str, Any]]: The claims, in file order.

    Raises:
        ClaimsError: If an entry is missing a field, uses an unknown source,
            or repeats an id.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    claims = data.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ClaimsError(f"{path}: expected a non-empty 'claims' list")
    seen: set[str] = set()
    for i, claim in enumerate(claims):
        where = f"{path}: claim {i}"
        if not isinstance(claim, dict):
            raise ClaimsError(f"{where}: not a mapping")
        for key in ("id", "file", "template", "source"):
            if key not in claim:
                raise ClaimsError(f"{where}: missing '{key}'")
        if claim["id"] in seen:
            raise ClaimsError(f"{where}: duplicate id {claim['id']!r}")
        seen.add(claim["id"])
        source = claim["source"]
        if not isinstance(source, dict) or len({"json", "call"} & set(source)) != 1:
            raise ClaimsError(f"{where} ({claim['id']}): source needs exactly one of 'json' or 'call'")
    return claims


def _walk(value: Any, path: Sequence[Any] | str | None) -> Any:
    """Follow ``path`` (a list of keys, or a dotted string) into ``value``."""
    if path is None:
        return value
    keys = path.split(".") if isinstance(path, str) else list(path)
    for key in keys:
        if isinstance(value, list):
            value = value[int(key)]
        else:
            value = value[key]
    return value


def _synthetic_run(file: Path, root: Path) -> Path | None:
    """The nearest ``manifest.json`` above ``file``, if it marks a synthetic run.

    Only directories inside ``root`` are searched, and the search stops at the
    first manifest found: that is the run the file belongs to.
    """
    for parent in file.parents:
        if parent != root and root not in parent.parents:
            return None
        manifest = parent / "manifest.json"
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            return manifest if data.get("synthetic") else None
        if parent == root:
            return None
    return None


def _resolve(source: Mapping[str, Any], root: Path, cache: dict[str, Any]) -> Any:
    """Load a claim's source value."""
    if "json" in source:
        file = (root / source["json"]).resolve()
        synthetic = _synthetic_run(file, root.resolve())
        if synthetic is not None:
            raise ValueError(f"source is inside a synthetic run ({synthetic.relative_to(root.resolve())})")
        key = f"json:{file}"
        if key not in cache:
            cache[key] = json.loads(file.read_text(encoding="utf-8"))
    else:
        key = f"call:{source['call']}"
        if key not in cache:
            module_name, _, function = str(source["call"]).partition(":")
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            cache[key] = getattr(importlib.import_module(module_name), function)()
    return _walk(cache[key], source.get("path"))


def _render(template: str, value: Any) -> str:
    fields = dict(value) if isinstance(value, Mapping) else {"value": value}
    return _FORMATTER.vformat(template, (), fields)


def verify_claims(claims_path: Path, root: Path | None = None) -> list[ClaimResult]:
    """Check every claim in a claims file against its document.

    Args:
        claims_path (Path): The claims YAML.
        root (Path | None): The repository root that ``file`` and ``json`` paths
            are relative to, and that ``call`` modules are imported from.
            Defaults to the parent of the claims file's directory.

    Returns:
        list[ClaimResult]: One result per claim, in file order.

    Raises:
        ClaimsError: If the claims file is malformed.
    """
    root = (root or claims_path.resolve().parent.parent).resolve()
    claims = load_claims(claims_path)
    cache: dict[str, Any] = {}
    docs: dict[str, str] = {}
    results: list[ClaimResult] = []
    for claim in claims:
        cid, file = str(claim["id"]), str(claim["file"])
        try:
            if file not in docs:
                docs[file] = _normalise((root / file).read_text(encoding="utf-8"))
            value = _resolve(claim["source"], root, cache)
            rendered = _render(str(claim["template"]), value)
        except Exception as exc:  # noqa: BLE001 -- reported per claim, not raised
            results.append(ClaimResult(cid, file, None, False, f"{type(exc).__name__}: {exc}"))
            continue
        wrong = {
            key: (want, _walk(value, [key]) if isinstance(value, Mapping) else value)
            for key, want in dict(claim.get("expect") or {}).items()
            if (_walk(value, [key]) if isinstance(value, Mapping) else value) != want
        }
        if wrong:
            detail = ", ".join(f"{k}: expected {w!r}, source has {h!r}" for k, (w, h) in wrong.items())
            results.append(ClaimResult(cid, file, rendered, False, detail))
            continue
        ok = _normalise(rendered) in docs[file]
        results.append(ClaimResult(
            cid, file, rendered, ok, None if ok else f"{rendered!r} does not appear in {file}"
        ))
    return results
