"""Gate : the living-doc introspection engine still covers each framework
surface it documents — nothing added to the framework is silently lost.

``examples/docs/`` renders reference chapters from *live introspection*
(``lib/introspect.py``), never from hand-copied prose. That makes drift
impossible **by construction** : a member the engine enumerates cannot be
omitted from the rendered page. This gate guards the *engine* itself —
the one thing construction can't guarantee — and does it from a **registry**
so a new surface (directives, decorators, …) is one :class:`Surface` entry,
not a new test file.

Per surface it asserts :

- **non-trivial** — the introspection returns at least ``min_count`` members
  (catches an engine that silently returns nothing after a refactor) ;
- **sentinels present** — a few load-bearing members are still seen (catches
  a categoriser that drops a whole class of operators) ;
- **fully classified** — no member falls through to ``CATEGORY_UNCLASSIFIED``
  (the moment someone adds an operator to the framework without teaching the
  doc engine, they must classify it on purpose) ;
- **wired to a page** — the feature page that must render this surface still
  references its mirror (a substring canary : catches a surface that lost its
  home in the docs, without an over-built AST call-check).

Honest scope : this polices *coverage of the surface by the engine*, not the
prose around it — the same "is anything silently missing?" contract as
``test_every_public_symbol_is_describable`` and ``test_python_js_mirror``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pytest

from bretzel.introspect import (
    CATEGORY_UNCLASSIFIED,
    describe_client_algebra,
    describe_toplevel_surface,
)
from examples.docs.lib.runtime_surface import (
    describe_directives,
    describe_magics,
    describe_runtime_api,
    describe_runtime_modules,
)

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "interroge le moteur d'introspection de la doc vivante et compare "
    "des ensembles ; ses sentinelles et `test_surface_non_trivial` "
    "gardent la population"
)

_DOCS = Path(__file__).resolve().parents[2] / "examples" / "docs"


class Classified(Protocol):
    """The shared shape every introspected member exposes — a name and the
    category the doc engine filed it under. ``AlgebraOp`` (and any future
    ``DirectiveOp`` / ``DecoratorOp``) already satisfies it structurally, so
    a new surface plugs in with no adapter code."""

    name: str
    category: str


@dataclass(frozen=True)
class Surface:
    """One introspected framework surface the living doc must cover fully.

    ``describe`` is the surface's live introspection — the SAME function the
    doc page renders — so the gate checks exactly what the reader sees. All
    projections (names, unclassified) are derived from it in the tests, so
    adding a surface is genuinely one entry."""

    name: str
    describe: Callable[[], Sequence[Classified]]  # the live introspection the page renders
    sentinels: frozenset[str]                     # load-bearing members that must survive
    min_count: int                                # non-triviality floor
    doc_page: Path                                # feature page that must render it
    mirror_symbol: str                            # the blocks.* mirror the page references


# ── The registry — add a Surface here, get all four checks for free ──────
SURFACES: list[Surface] = [
    Surface(
        name="ClientBinding→JS algebra",
        describe=describe_client_algebra,
        sentinels=frozenset({
            "__gt__", "__and__", "__invert__", "then_else", "between",
            "toggle", "join",
        }),
        min_count=30,
        doc_page=_DOCS / "features" / "reactivity_client.py",
        mirror_symbol="client_algebra_mirror",
    ),
    # ── Les quatre surfaces du runtime client ────────────────────────────
    # Livrées avec le chapitre ``/runtime`` et rendues par lui, mais
    # absentes de ce registre jusqu'au 2026-08-15 : le mécanisme
    # anti-oubli existait et servait UNE surface sur cinq. Une surface
    # introspectée mais non enregistrée n'a que la moitié de la garantie —
    # la page ne peut pas omettre un membre, mais rien ne dit si le
    # lecteur de la surface a cessé de lire.
    Surface(
        name="Directives bz-*",
        describe=describe_directives,
        sentinels=frozenset({"bz-data", "bz-model", "bz-show", "bz-effect"}),
        min_count=13,
        doc_page=_DOCS / "features" / "runtime.py",
        mirror_symbol="directives_mirror",
    ),
    Surface(
        name="Variables magiques d'expression",
        describe=describe_magics,
        sentinels=frozenset({"$el", "$event", "$refs"}),
        min_count=7,
        doc_page=_DOCS / "features" / "runtime.py",
        mirror_symbol="magics_mirror",
    ),
    Surface(
        name="Surface de l'objet global $bz",
        describe=describe_runtime_api,
        sentinels=frozenset({"signal", "computed", "effect"}),
        min_count=40,
        doc_page=_DOCS / "features" / "runtime.py",
        mirror_symbol="runtime_api_mirror",
    ),
    Surface(
        name="Modules du bundle runtime",
        describe=describe_runtime_modules,
        sentinels=frozenset({"01_signals.js", "02_directives.js"}),
        min_count=20,
        doc_page=_DOCS / "features" / "runtime.py",
        mirror_symbol="runtime_modules_mirror",
    ),
    # ── La surface top-level ─────────────────────────────────────────────
    # La première que le lecteur rencontre, et la moins gardée jusqu'au
    # 2026-08-15 : le catalogue ``ui.*`` avait son inventaire gaté,
    # l'algèbre client le sien, mais « qu'est-ce qui existe au niveau du
    # paquet, et à quel besoin chaque nom répond » ne vivait que dans la
    # prose de ``cheatsheet.py``.
    #
    # Le classement est par BESOIN, pas par type Python — c'est ce qui
    # fait de ``test_surface_fully_classified`` un vrai cran d'arrêt :
    # ajouter un nom à ``bretzel.__all__`` sans dire à quoi il sert fait
    # rougir cette gate. On ne peut plus élargir la surface publique en
    # silence.
    Surface(
        name="Surface top-level bretzel.*",
        describe=describe_toplevel_surface,
        sentinels=frozenset({
            "Bretzel", "page", "ui", "abort", "redirect",
            "background", "idempotent", "refresh",
        }),
        min_count=18,
        doc_page=_DOCS / "features" / "cheatsheet.py",
        mirror_symbol="toplevel_surface_mirror",
    ),
]

_IDS = [s.name for s in SURFACES]


@pytest.mark.parametrize("surface", SURFACES, ids=_IDS)
def test_surface_non_trivial(surface: Surface) -> None:
    members = [op.name for op in surface.describe()]
    assert len(members) >= surface.min_count, (
        f"{surface.name} : introspection returned {len(members)} members "
        f"(< {surface.min_count}). The doc engine likely broke — a reference "
        f"page now renders almost nothing."
    )


@pytest.mark.parametrize("surface", SURFACES, ids=_IDS)
def test_surface_sentinels_present(surface: Surface) -> None:
    members = {op.name for op in surface.describe()}
    missing = surface.sentinels - members
    assert not missing, (
        f"{surface.name} : load-bearing members {sorted(missing)} are no "
        f"longer seen by the introspection — a categoriser or the surface "
        f"reader dropped them. The reference page silently lost them."
    )


@pytest.mark.parametrize("surface", SURFACES, ids=_IDS)
def test_surface_fully_classified(surface: Surface) -> None:
    orphans = [
        op.name for op in surface.describe()
        if op.category == CATEGORY_UNCLASSIFIED
    ]
    assert not orphans, (
        f"{surface.name} : {sorted(orphans)} reached the doc engine but "
        f"aren't classified — someone added to the framework without teaching "
        f"the living doc. Classify them in lib/introspect.py so the reference "
        f"page groups them on purpose (they render, but uncategorised)."
    )


@pytest.mark.parametrize("surface", SURFACES, ids=_IDS)
def test_surface_wired_to_page(surface: Surface) -> None:
    assert surface.doc_page.exists(), (
        f"{surface.name} : doc page {surface.doc_page} is missing."
    )
    source = surface.doc_page.read_text(encoding="utf-8")
    assert surface.mirror_symbol in source, (
        f"{surface.name} : {surface.doc_page.name} no longer calls "
        f"`{surface.mirror_symbol}` — the surface lost its home in the docs. "
        f"An introspection nobody renders documents nothing."
    )
