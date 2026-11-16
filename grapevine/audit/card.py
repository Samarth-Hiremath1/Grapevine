"""The Validity Card: what an audit produces.

A card is a verdict plus one result per check, with the numbers behind each one.
It is written as JSON (``validity_card.json``, for machines and for run
manifests to reference by hash) and as Markdown (for people and for commits).

The statuses are deliberately four, not two:

``pass``
    The check ran and found nothing.
``warn``
    The check ran and found a real limitation. The environment still measures
    something, but narrower than it may appear. Reported with its numbers.
``fail``
    The check ran and found that the environment does not measure what it
    claims. A coordination result from it would not mean what it says.
``skipped``
    The check could not run, because the environment does not provide what it
    needs. **Not** the same as passing, and never presented as such.

The overall verdict is the worst status present, with ``skipped`` not counting
toward it but always listed.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

__all__ = ["CheckResult", "Status", "ValidityCard"]


class Status(StrEnum):
    """Outcome of one check. See the module docstring."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIPPED = "skipped"

    @property
    def symbol(self) -> str:
        """A one-character marker for the Markdown card."""
        return {"pass": "✅", "warn": "⚠️", "fail": "❌", "skipped": "⊘"}[self.value]

    @property
    def rank(self) -> int:
        """Severity order, used to pick a card's overall verdict."""
        return {"skipped": 0, "pass": 1, "warn": 2, "fail": 3}[self.value]


@dataclass(frozen=True)
class CheckResult:
    """What one check found.

    Attributes:
        check_id: Stable short id, e.g. ``"leak"``. Referenced by docs and by
            ``--allow-flagged`` in the training entry point.
        title: One-line human name.
        status: See :class:`Status`.
        summary: One or two sentences stating what was found, with numbers. This
            is what a reader sees first, so it says the finding, not the method.
        detail: The numbers behind the summary, JSON-serialisable.
        audit_findings: Ids of findings in ``docs/audit.md`` this check exists to
            catch, e.g. ``("L3",)``. Keeps the battery honest about its
            provenance: every check here came from a mistake that was actually
            made.
    """

    check_id: str
    title: str
    status: Status
    summary: str
    detail: Mapping[str, Any] = field(default_factory=dict)
    audit_findings: tuple[str, ...] = ()

    @property
    def flagged(self) -> bool:
        """True when this result should block a training run by default."""
        return self.status is Status.FAIL


@dataclass(frozen=True)
class ValidityCard:
    """The result of auditing one environment.

    Attributes:
        environment: The environment's name.
        version: The environment's generation version.
        config: Configuration recorded for reproducibility.
        n_tasks: How many tasks the battery ran over.
        seed: Base seed for those tasks.
        results: One result per check, in registration order.
        grapevine_version: The version of Grapevine that produced the card.
    """

    environment: str
    version: str
    config: Mapping[str, Any]
    n_tasks: int
    seed: int
    results: tuple[CheckResult, ...]
    grapevine_version: str

    @property
    def verdict(self) -> Status:
        """The worst status among checks that ran.

        A card with only skipped checks is ``skipped``: nothing was established.
        """
        ran = [r.status for r in self.results if r.status is not Status.SKIPPED]
        if not ran:
            return Status.SKIPPED
        return max(ran, key=lambda s: s.rank)

    @property
    def passed(self) -> bool:
        """True when no check failed. Warnings do not stop a card passing."""
        return not any(r.status is Status.FAIL for r in self.results)

    @property
    def flagged_checks(self) -> tuple[str, ...]:
        """Ids of the checks that failed."""
        return tuple(r.check_id for r in self.results if r.flagged)

    def by_status(self, status: Status) -> tuple[CheckResult, ...]:
        """Results with the given status, in registration order."""
        return tuple(r for r in self.results if r.status is status)

    def get(self, check_id: str) -> CheckResult:
        """Look up one result by check id.

        Raises:
            KeyError: If no check with that id ran.
        """
        for result in self.results:
            if result.check_id == check_id:
                return result
        raise KeyError(f"no check {check_id!r} in this card")

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready dict. Floats are rounded so the card is stable to commit."""
        payload: dict[str, Any] = _rounded(
            {
                "schema": "grapevine.validity_card/1",
                "environment": self.environment,
                "version": self.version,
                "config": dict(self.config),
                "n_tasks": self.n_tasks,
                "seed": self.seed,
                "grapevine_version": self.grapevine_version,
                "verdict": str(self.verdict),
                "passed": self.passed,
                "flagged_checks": list(self.flagged_checks),
                "results": [
                    {
                        "check_id": r.check_id,
                        "title": r.title,
                        "status": str(r.status),
                        "summary": r.summary,
                        "audit_findings": list(r.audit_findings),
                        "detail": dict(r.detail),
                    }
                    for r in self.results
                ],
            }
        )
        return payload

    def to_json(self) -> str:
        """The card as indented JSON, newline-terminated."""
        return json.dumps(self.to_dict(), indent=2, sort_keys=False) + "\n"

    def content_hash(self) -> str:
        """SHA-256 over the card's content, for run manifests to reference.

        A training run records this so it is always possible to say which
        version of which environment the run trained against, and what the audit
        said about it at the time.
        """
        payload = self.to_dict()
        payload.pop("grapevine_version", None)
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def to_markdown(self) -> str:
        """The card as a Markdown document."""
        verdict_line = {
            Status.PASS: "**PASS** — every check ran and found nothing.",
            Status.WARN: (
                "**PASS WITH LIMITATIONS** — nothing invalidating, but the "
                "warnings below narrow what a result from this environment means."
            ),
            Status.FAIL: (
                "**FAIL** — this environment does not measure what it claims. "
                "A coordination result from it would not mean what it says."
            ),
            Status.SKIPPED: "**NOT ESTABLISHED** — no check was able to run.",
        }[self.verdict]

        lines = [
            f"# Validity Card: `{self.environment}` v{self.version}",
            "",
            f"{self.verdict.symbol} {verdict_line}",
            "",
            f"- Tasks audited: **{self.n_tasks}**, seeds {self.seed}–{self.seed + self.n_tasks - 1}",
            f"- Grapevine: `{self.grapevine_version}` · card hash: `{self.content_hash()[:16]}`",
        ]
        if self.config:
            rendered = ", ".join(f"`{k}={v}`" for k, v in sorted(self.config.items()))
            lines.append(f"- Config: {rendered}")
        counts = ", ".join(
            f"{len(self.by_status(s))} {s.value}"
            for s in (Status.FAIL, Status.WARN, Status.PASS, Status.SKIPPED)
            if self.by_status(s)
        )
        lines += [f"- Checks: {counts}", "", "## Summary", "", "| | Check | Status | Finding |", "|---|---|---|---|"]
        for result in sorted(self.results, key=lambda r: -r.status.rank):
            summary = result.summary.replace("\n", " ").replace("|", "\\|")
            lines.append(
                f"| {result.status.symbol} | `{result.check_id}` | {result.status.value} | {summary} |"
            )

        lines += ["", "## Detail", ""]
        for result in sorted(self.results, key=lambda r: -r.status.rank):
            lines += [
                f"### {result.status.symbol} `{result.check_id}` — {result.title}",
                "",
                f"**{result.status.value}.** {result.summary}",
                "",
            ]
            if result.audit_findings:
                found = ", ".join(result.audit_findings)
                lines += [
                    f"*Exists because of {found} in `docs/audit.md`.*",
                    "",
                ]
            if result.detail:
                lines += [
                    "```json",
                    json.dumps(_rounded(dict(result.detail)), indent=2),
                    "```",
                    "",
                ]

        lines += [
            "---",
            "",
            "A `skipped` check did not run, because this environment does not provide",
            "what it needs. That is not the same as passing, and nothing here should be",
            "read as if it were.",
            "",
            "Regenerate this card with:",
            "",
            "```bash",
            f"grapevine audit {self.environment} --n {self.n_tasks} --seed {self.seed}",
            "```",
            "",
        ]
        return "\n".join(lines)


def _rounded(obj: Any, places: int = 6) -> Any:
    """Round every float in a nested structure.

    Keeps a committed card stable across platforms: without this, last-bit libm
    differences show up as changes to a file CI diffs.
    """
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return round(obj, places)
    if isinstance(obj, Mapping):
        return {k: _rounded(v, places) for k, v in obj.items()}
    if isinstance(obj, StrEnum):
        return str(obj)
    if isinstance(obj, Sequence) and not isinstance(obj, str | bytes):
        return [_rounded(v, places) for v in obj]
    if hasattr(obj, "__dataclass_fields__"):
        return _rounded(asdict(obj), places)
    return obj
