"""La découverte des fichiers d'une app, et leur AST — **sans plancher**.

C'est le point qui rend l'outil portable, et il mérite d'être écrit :
les 124 gates de ``tests/consistency/`` fondent *la règle* avec *le corpus
de CE dépôt et son plancher de non-vacuité* (``EXAMPLES_FLOOR`` et
consorts). Une gate a raison de le faire — elle protège un corpus connu.
Un outil qui vise **une app quelconque** ne le peut pas : il ne sait rien
de la taille attendue.

D'où la découpe : ici on découvre et on parse, sans jamais juger de la
population. Les planchers restent du côté des gates, qui deviennent des
**consommateurs** de ce module sur leur propre corpus.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

#: Dossiers qu'on ne descend jamais — ni du code de l'app, ni lisible.
_SKIP_DIRS = frozenset(
    {
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "build",
        "dist",
    }
)


@dataclass(frozen=True)
class Module:
    """Un fichier source et son arbre, parsés une fois."""

    path: Path
    tree: ast.Module
    source: str


def discover(paths: list[Path] | tuple[Path, ...]) -> list[Path]:
    """Les fichiers ``.py`` sous ``paths`` (fichiers ou dossiers)."""
    found: list[Path] = []
    for entry in paths:
        if entry.is_file():
            if entry.suffix == ".py":
                found.append(entry)
            continue
        for candidate in sorted(entry.rglob("*.py")):
            if _SKIP_DIRS.isdisjoint(candidate.parts):
                found.append(candidate)
    return found


def parse(path: Path) -> Module | None:
    """Parse un fichier, ou rend ``None`` s'il est illisible.

    Lu en ``utf-8-sig`` : un BOM avait sorti un fichier de sept gates de ce
    dépôt pendant des mois, et l'échec était silencieux. Un fichier qui ne
    parse pas n'est pas un constat de lint — c'est une erreur de syntaxe
    que l'interpréteur signalera bien mieux que nous.
    """
    try:
        source = path.read_text(encoding="utf-8-sig")
        return Module(path=path, tree=ast.parse(source), source=source)
    except (OSError, SyntaxError, ValueError):
        return None


def modules(paths: list[Path] | tuple[Path, ...]) -> list[Module]:
    """Tout ce qui est lisible sous ``paths``, parsé."""
    return [m for m in (parse(p) for p in discover(paths)) if m is not None]


# ───────────────────────────────────────────────────────────────────────────
# Le corpus du passage — pour les rares règles qui ne peuvent pas juger seules
# ───────────────────────────────────────────────────────────────────────────
#
# Une règle constate sur UN module, et c'est ce qui la garde pure et
# testable. Une seule question échappe à ce cadre :
# ``ui.button(variant="brand")`` est correct **si** un
# ``Theme(components={"button": {"variants": {"brand": …}}})` existe — et
# ce thème vit presque toujours dans un AUTRE fichier. Sans le corpus, la
# règle condamnerait l'échappatoire documentée pour dévier du thème livré,
# c'est-à-dire précisément la forme qu'on recommande.
#
# ``contextvars`` et non une variable de module : l'anti-règle 2 du charter
# interdit l'état global mutable et autorise nommément les registres scopés
# à un appel. Non lié = tuple vide, donc une règle appelée hors ``run`` (un
# test unitaire) dégrade proprement au lieu de casser.

_CORPUS: ContextVar[tuple[Module, ...]] = ContextVar("bretzel_lint_corpus", default=())


# Les dérivations qui coûtent O(corpus) — calculées UNE fois par passage
# ───────────────────────────────────────────────────────────────────────────
#
# Une règle constate sur un module, mais celles qui lisent ``current()``
# calculent la même chose pour chacun. Sans mémoire, ``run`` devient
# quadratique : mesuré le 2026-08-27, ``valeur-hors-table`` reparcourait
# l'AST des 322 fichiers d'``examples/`` pour chacun de ces 322 fichiers,
# soit **56 s** — à lui seul les deux tiers de la baseline de lint, et
# ~110 s des 230 s d'un ``pytest`` nu (il est payé deux fois : la règle
# seule, puis la baseline).
#
# La mémoire vit dans la LIAISON, pas dans un cache global : sa durée de
# vie est exactement celle du passage, donc deux ``run`` sur deux corpus
# ne peuvent pas se contaminer, et l'anti-règle 2 du charter est tenue.
# Hors ``run`` (une règle appelée seule dans un test unitaire), il n'y a
# pas de liaison : on construit sans mémoriser plutôt que d'écrire dans
# un défaut partagé par tous les appelants.
_DERIVED: ContextVar[dict[str, Any] | None] = ContextVar(
    "bretzel_lint_corpus_derived", default=None
)

_T = TypeVar("_T")


@contextmanager
def bound(found: Sequence[Module]) -> Iterator[None]:
    """Expose ``found`` comme corpus du passage courant."""
    token = _CORPUS.set(tuple(found))
    memo_token = _DERIVED.set({})
    try:
        yield
    finally:
        _DERIVED.reset(memo_token)
        _CORPUS.reset(token)


def current() -> tuple[Module, ...]:
    """Le corpus du passage, ou un tuple vide hors ``run``."""
    return _CORPUS.get()


def derived(key: str, build: Callable[[], _T]) -> _T:
    """La dérivation ``key`` du corpus du passage, construite une fois.

    ``build`` ne prend aucun argument : il doit se dériver du corpus
    exposé par :func:`current`, sinon deux appelants sous la même clé
    liraient le résultat de l'autre. Hors ``run``, rien n'est mémorisé —
    ``build`` est appelé à chaque fois, ce qui garde une règle juste
    quand elle est exercée seule.
    """
    memo = _DERIVED.get()
    if memo is None:
        return build()
    if key not in memo:
        memo[key] = build()
    return memo[key]
