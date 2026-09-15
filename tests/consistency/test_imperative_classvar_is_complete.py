"""Gate G5 — ``IMPERATIVE`` déclare TOUTES les méthodes impératives, pas
seulement celles dont on s'est souvenu.

``IMPERATIVE`` est la source unique introspectable de l'API write-only
(``.open()`` / ``.set(v)`` / …) : le catalogue ``ui.*`` de la doc la lit
pour énumérer les méthodes d'un composant. Une méthode absente est donc
livrée mais **invisible**.

``tests/unit/components/test_imperative_classvar.py`` garde le sens
aller : tout nom déclaré résout vers un callable. Le sens **retour**
n'était pas gardé — d'où Calendar, qui expose ``next_month()`` /
``prev_month()`` pleinement câblées sans les déclarer (audit F20/F21) :
la ClassVar sous-comptait l'API de deux méthodes et la doc les taisait.

Marqueur retenu : ``self._dispatch_command(...)``. C'est le primitive
par lequel passe **toute** commande impérative (il émet l'événement DOM
que la root du composant écoute) — un faux négatif demanderait d'écrire
la commande à la main, ce que d'autres gates interdisent déjà.

⚠️ Portée : les méthodes visibles à l'AST dans le corps de la classe.
Les overlays installent les leurs par instance dans ``__init__``
(``install_open_close_toggle``, pour ne pas masquer un ``reactive_prop``
nommé ``open``) ; celles-là sont couvertes par la gate aller.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from tests.consistency._discovery import (
    parsed_sources,
    public_component_classes,
    source_of,
)

_COMPONENTS_DIR = pathlib.Path("bretzel/components").resolve()

#: 272 fichiers sous bretzel/components le 2026-08-19.
_COMPONENTS_FLOOR = 200
_MARKER = "_dispatch_command"

_BY_NAME = {c.__name__: c for c in public_component_classes()}


def _modules_with_components() -> list[pathlib.Path]:
    return [
        s.path
        for s in parsed_sources(_COMPONENTS_DIR, floor=_COMPONENTS_FLOOR)
        if s.path.name not in ("__init__.py", "theme.py")
    ]


def _dispatching_public_methods(cls_node: ast.ClassDef) -> list[str]:
    out = []
    for node in cls_node.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue
        dispatches = any(
            isinstance(n, ast.Attribute) and n.attr == _MARKER
            for n in ast.walk(node)
        )
        if dispatches:
            out.append(node.name)
    return out


_MODULES = _modules_with_components()
_IDS = [str(p.relative_to(_COMPONENTS_DIR)) for p in _MODULES]


@pytest.mark.parametrize("path", _MODULES, ids=_IDS)
def test_every_dispatching_method_is_declared(path: pathlib.Path) -> None:
    tree = source_of(path).tree
    missing: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        cls = _BY_NAME.get(node.name)
        if cls is None:
            continue
        declared = set(getattr(cls, "IMPERATIVE", ()) or ())
        for method in _dispatching_public_methods(node):
            if method not in declared:
                missing.append(f"{node.name}.{method}()")

    assert not missing, (
        f"{path.relative_to(_COMPONENTS_DIR)} : méthode(s) impérative(s) "
        f"livrée(s) mais absente(s) de la ClassVar `IMPERATIVE` — "
        f"{missing}.\n\n"
        f"`IMPERATIVE` est la seule source que le catalogue `ui.*` de la doc "
        f"énumère : une méthode qui n'y est pas est livrée et invisible. "
        f"Ajoute-la (et la ligne correspondante dans `imperative-api.md`)."
    )


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : les modules de composant sont bien découverts."""
    assert len(_MODULES) >= 90, (
        f"seulement {len(_MODULES)} modules de composant balayés (108 le "
        f"2026-08-19) — la découverte est cassée, et « aucun IMPERATIVE "
        f"incomplet » ne vaut plus rien."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : une méthode publique qui dispatche est encore reconnue.

    ``IMPERATIVE`` doit lister exactement ce qui se pilote de
    l'extérieur. Si le détecteur cessait de voir l'appel de dispatch,
    une méthode livrée mais non déclarée resterait invisible à
    ``describe`` — donc introuvable pour qui lit la fiche.
    """
    fautif = ast.parse(
        "class C:\n"
        "    def open(self):\n"
        "        return self._dispatch_command('open')\n"
    ).body[0]
    assert _dispatching_public_methods(fautif) == ["open"]

    licite = ast.parse(
        "class C:\n"
        "    def _open(self):\n"
        "        return self._dispatch_command('open')\n"
        "    def render(self):\n"
        "        return None\n"
    ).body[0]
    assert _dispatching_public_methods(licite) == [], (
        "une méthode privée ne s'expose pas — faux positif"
    )
