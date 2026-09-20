"""What a rule returns, and what the command does with it.

Separated from the rules for a fundamental reason: a rule decides
**neither** the overall severity, **nor** the format, **nor** the exit
code. It reports. That is what lets the same set of rules serve a pytest
gate, a CLI, and an in-process consumer.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class Finding:
    """One finding, located, with enough to act on.

    ``hint`` is not decorative: in this repository the norm for a refusal
    is "the refusal is a help, not a wall" (cf.
    ``reject_dead_alpine_attr``, which points at the ``bz-``
    equivalent). A finding with no suggested way out wastes as much time
    as no message at all.
    """

    rule: str
    path: Path
    line: int
    message: str
    hint: str = ""

    def format(self, *, root: Path | None = None) -> str:
        where = self.path
        if root is not None:
            with contextlib.suppress(ValueError):
                where = self.path.relative_to(root)
        head = f"{where.as_posix()}:{self.line}: [{self.rule}] {self.message}"
        return f"{head}\n    → {self.hint}" if self.hint else head


@dataclass
class Report:
    """One pass's aggregate. ``exit_code`` is the only translation into a
    verdict, and it lives here — not in a rule."""

    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    rules_run: tuple[str, ...] = ()

    @property
    def exit_code(self) -> int:
        return 1 if self.findings else 0

    def format(self, *, root: Path | None = None) -> str:
        if not self.findings:
            return (
                f"OK — {self.files_scanned} files, {len(self.rules_run)} rules, no finding."
            )
        body = "\n".join(f.format(root=root) for f in self.findings)
        return (
            f"{body}\n\n{len(self.findings)} finding(s) across "
            f"{self.files_scanned} files ({len(self.rules_run)} rules)."
        )
