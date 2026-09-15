"""Ce qu'une règle rend, et ce que la commande en fait.

Séparé des règles pour une raison de fond : une règle ne décide **ni** de
la gravité globale, **ni** du format, **ni** du code de sortie. Elle
constate. C'est ce qui permet au même jeu de règles de servir une gate
pytest, un CLI, et un consommateur en process.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class Finding:
    """Un constat, localisé, avec de quoi agir.

    ``hint`` n'est pas décoratif : dans ce dépôt la norme d'un refus est
    « le refus est une aide, pas un mur » (cf. ``reject_dead_alpine_attr``,
    qui pointe l'équivalent ``bz-``). Un findings sans issue proposée fait
    perdre le même temps que l'absence de message.
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
    """L'agrégat d'un passage. ``exit_code`` est la seule traduction en
    verdict, et elle vit ici — pas dans une règle."""

    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    rules_run: tuple[str, ...] = ()

    @property
    def exit_code(self) -> int:
        return 1 if self.findings else 0

    def format(self, *, root: Path | None = None) -> str:
        if not self.findings:
            return (
                f"OK — {self.files_scanned} fichiers, {len(self.rules_run)} règles, aucun constat."
            )
        body = "\n".join(f.format(root=root) for f in self.findings)
        return (
            f"{body}\n\n{len(self.findings)} constat(s) sur "
            f"{self.files_scanned} fichiers ({len(self.rules_run)} règles)."
        )
