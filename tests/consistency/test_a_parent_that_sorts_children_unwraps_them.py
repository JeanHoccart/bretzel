"""Gate — un parent qui trie ses enfants par TYPE déballe les enveloppes.

Le défaut qu'elle ferme (2026-08-23)
--------------------------------------
Neuf fonctions de rendu traitent leurs enfants **selon leur type** :
``ui.tabs`` cherche des ``Tab``, ``ui.stepper`` des ``Step``,
``ui.sidebar`` son titre et son pied, etc. Or un enfant est très souvent
ENVELOPPÉ, et aucune enveloppe n'est une instance de ce qu'elle
contient :

- ``@refreshable`` rend un ``_RefreshableSection`` ;
- ``ui.fragment`` rend un ``Fragment``.

L'enveloppe était déjà transparente à la **disposition** (la zone se
fusionne dans son enfant unique, ou se rend en ``display:contents`` —
``render/fusion.py``, gaté par ``test_zone_box_is_transparent``). Elle ne
l'était pas à l'**identité**, et ça coûtait — presque toujours en
silence. Mesuré, même contenu, nu contre enveloppé :

===================  ==========================================
``ui.tabs``          l'onglet **disparaît** (2 268 → 1 353 car.)
``ui.stepper``       l'étape **disparaît** (4 022 → 2 185)
``ui.tree``          le nœud **disparaît** (2 211 → 1 249)
``ui.breadcrumb``    le segment **disparaît** (723 → 192)
``ui.accordion``     perd **en-tête et libellé** (2 boutons → 1)
``ui.resizable``     perd ses **contraintes** (``_mins`` [25,0] → [0,0])
``ui.sidebar``       le pied tombe **dans la zone qui défile**
``ui.toggle_group``  **lève** — le seul à être bruyant
===================  ==========================================

Le point d'entrée est ``examples/crm`` : son pied de barre DOIT être une
zone (il affiche le compte connecté). Le playground écrit le sien nu, et
c'est lui qu'on regarde en développant un composant — le défaut n'existe
que dans la forme réaliste.

L'invariant
-----------
Toute fonction de rendu qui touche ``_children`` **et** qui fait un
``isinstance`` sur une classe de composant précise appelle
``base/_wiring.unwrap_transparent``.

Pourquoi cette forme et pas un test de comportement par composant : le
comportement est vérifié ci-dessous aussi, mais un test par composant ne
dit rien du **dixième**. Le balayage, lui, rougit le jour où quelqu'un
écrit un nouveau conteneur qui trie.

⚠️ Ce qu'elle n'affirme PAS : que l'appel soit BIEN placé (déballer sans
ré-habiller ferait perdre le ``bz-id`` de la zone, donc un enfant correct
qui ne se rafraîchit plus). C'est ce que mesure la seconde moitié du
fichier, sur les cas réels.
"""

from __future__ import annotations

import ast
import re

import pytest

from bretzel import refreshable, ui
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.state import SessionState, field
from tests.consistency._discovery import COMPONENTS_DIR, parsed_sources

#: Les types trop GÉNÉRIQUES pour signaler un tri d'enfants. Un
#: ``isinstance(x, Component)`` distingue « composant ou chaîne », ce qui
#: n'a rien à voir : il ne rate pas une enveloppe, il l'accepte.
_GENERIC = frozenset({"Component", "Node", "Element"})

#: Le plancher, mesuré le 2026-08-23.
_SORTERS_FLOOR = 9
_SOURCES_FLOOR = 200


def _component_class_names() -> set[str]:
    """Les noms de classe du catalogue, lus dans les sources."""
    return {
        node.name
        for src in parsed_sources(COMPONENTS_DIR, floor=_SOURCES_FLOOR)
        for node in ast.walk(src.tree)
        if isinstance(node, ast.ClassDef)
    }


def sorting_functions() -> list[tuple[str, str, tuple[str, ...], bool]]:
    """``(fichier, fonction, types triés, déballe-t-elle ?)``.

    Extrait pour être mutable — c'est le détecteur, pas le balayage.
    """
    names = _component_class_names()
    out = []
    for src in parsed_sources(COMPONENTS_DIR, floor=_SOURCES_FLOOR):
        for fn in ast.walk(src.tree):
            if not isinstance(fn, ast.FunctionDef):
                continue
            body = ast.unparse(fn)
            if "_children" not in body:
                continue
            sorted_types = {
                node.args[1].id
                for node in ast.walk(fn)
                if isinstance(node, ast.Call)
                and getattr(node.func, "id", "") == "isinstance"
                and len(node.args) == 2
                and isinstance(node.args[1], ast.Name)
                and node.args[1].id in names
                and node.args[1].id not in _GENERIC
            }
            if sorted_types:
                out.append((
                    src.path.name, fn.name, tuple(sorted(sorted_types)),
                    "unwrap_transparent" in body,
                ))
    return sorted(out)


def test_the_sweep_is_not_vacuous() -> None:
    """① Le plancher, lu sur LA découverte de cette gate."""
    seen = sorting_functions()
    assert len(seen) >= _SORTERS_FLOOR, (
        f"seulement {len(seen)} fonctions de tri trouvées "
        f"({_SORTERS_FLOOR} le 2026-08-23) : la découverte est cassée et "
        f"la gate ne garde plus rien.\nTrouvées : {[s[:2] for s in seen]}"
    )


@pytest.mark.parametrize(
    "entry", sorting_functions(), ids=lambda e: f"{e[0]}::{e[1]}"
)
def test_a_sorting_render_unwraps_its_children(entry) -> None:
    """② L'interdiction."""
    path, fn, types, unwraps = entry
    assert unwraps, (
        f"{path}::{fn} trie ses enfants sur {list(types)} sans appeler "
        f"`unwrap_transparent`.\n"
        f"  Un enfant ENVELOPPÉ — dans une zone `@refreshable` pour se "
        f"rafraîchir seul, ou dans un `ui.fragment` — n'est pas une "
        f"instance de ces classes. Il tombera dans la branche « étranger », "
        f"et selon le composant il disparaîtra, perdra son habillage, ou "
        f"lèvera.\n"
        f"  Écris :\n"
        f"      child, rewrap = unwrap_transparent(raw)\n"
        f"      ...\n"
        f"      node = rewrap(node)\n"
        f"  Le `rewrap` n'est pas décoratif : sans lui la zone perd son "
        f"`bz-id` et l'enfant s'affiche sans jamais se rafraîchir."
    )


def test_the_detector_still_bites() -> None:
    """③ La mutation, dans les DEUX sens.

    Le versant licite est celui qui compte ici : un détecteur qui
    accepterait ``isinstance(x, Component)`` désignerait une quarantaine
    de fonctions dont aucune ne trie — la gate deviendrait du bruit et on
    la débrancherait.
    """
    seen = sorting_functions()
    found = {(e[0], e[1]) for e in seen}
    # Ce qui DOIT être vu — les huit conteneurs qui trient vraiment.
    for expected in (
        ("tabs.py", "render"), ("stepper.py", "render"),
        ("accordion.py", "render"), ("tree.py", "render"),
        ("breadcrumb.py", "render"), ("sidebar.py", "render"),
        ("toggle_group.py", "render"), ("resizable.py", "render"),
    ):
        assert expected in found, f"{expected} n'est plus vu comme un trieur"
    # Ce qui doit être ÉPARGNÉ — le test générique « composant ou pas ».
    assert "Component" in _GENERIC and "Node" in _GENERIC
    for name, fn, types, _ in seen:
        assert not (set(types) & _GENERIC), (
            f"{name}::{fn} a été retenu pour un type générique {types} : "
            f"le détecteur va noyer la gate."
        )


# ───────────────────────────────────────────────────────────────────────
# La seconde moitié : le COMPORTEMENT, sur les cas réels
# ───────────────────────────────────────────────────────────────────────


class _Prefs(SessionState):
    tick: int = field(default=0)


def _zone(fn):
    return refreshable(deps=[_Prefs])(fn)


def _tabs(wrapped: bool):
    node = ui.tabs()
    with node:
        def one() -> None:
            ui.tab(label="ONGLET_SONDE", id="a")
        _zone(one)() if wrapped else one()
        ui.tab(label="Autre", id="b")
    return node


def _stepper(wrapped: bool):
    node = ui.stepper()
    with node:
        def one() -> None:
            ui.step(label="ETAPE_SONDE")
        _zone(one)() if wrapped else one()
        ui.step(label="Autre")
    return node


def _accordion(wrapped: bool):
    node = ui.accordion()
    with node:
        def one() -> None:
            with ui.accordion_item(label="ITEM_SONDE", value="un"):
                ui.text("corps")
        _zone(one)() if wrapped else one()
        with ui.accordion_item(label="Autre", value="deux"):
            ui.text("corps")
    return node


def _tree(wrapped: bool):
    node = ui.tree()
    with node:
        def one() -> None:
            ui.tree_node(label="NOEUD_SONDE", value="r")
        _zone(one)() if wrapped else one()
        ui.tree_node(label="Autre", value="a")
    return node


def _breadcrumb(wrapped: bool):
    node = ui.breadcrumb()
    with node:
        def one() -> None:
            ui.breadcrumb_item(label="SEGMENT_SONDE", href="/")
        _zone(one)() if wrapped else one()
        ui.breadcrumb_item(label="Ici")
    return node


def _toggle_group(wrapped: bool):
    node = ui.toggle_group()
    with node:
        def one() -> None:
            ui.toggle_button("a", label="BOUTON_SONDE")
        _zone(one)() if wrapped else one()
        ui.toggle_button("b", label="Autre")
    return node


def _resizable(wrapped: bool):
    node = ui.resizable(sizes=[30, 70])
    with node:
        def one() -> None:
            with ui.resizable_panel(min_size=25):
                ui.text("gauche")
        _zone(one)() if wrapped else one()
        with ui.resizable_panel():
            ui.text("droite")
    return node


#: ``composant -> (fabrique, ce qui doit survivre à l'enveloppement)``.
#: Le témoin est une chaîne DISTINCTIVE et non une longueur : une longueur
#: bouge au moindre changement de thème, un libellé absent est un défaut.
#: Pour ``resizable`` le témoin n'est pas du texte mais la CONTRAINTE, qui
#: est ce qu'il perdait.
_BEHAVIOUR = {
    "tabs": (_tabs, "ONGLET_SONDE"),
    "stepper": (_stepper, "ETAPE_SONDE"),
    "accordion": (_accordion, "ITEM_SONDE"),
    "tree": (_tree, "NOEUD_SONDE"),
    "breadcrumb": (_breadcrumb, "SEGMENT_SONDE"),
    "toggle_group": (_toggle_group, "BOUTON_SONDE"),
    "resizable": (_resizable, "_mins: [25, 0]"),
}


def _html(build, wrapped: bool) -> str:
    with render_isolated():
        return serialize(build(wrapped).render())


@pytest.mark.parametrize("name", sorted(_BEHAVIOUR))
def test_wrapping_a_child_changes_nothing(name: str) -> None:
    """Le témoin survit à l'enveloppement — c'est tout le sujet."""
    build, witness = _BEHAVIOUR[name]
    bare = _html(build, False)
    assert witness in bare, (
        f"ui.{name} : le témoin « {witness} » n'est pas là même SANS "
        f"enveloppe. La sonde est cassée, pas le composant."
    )
    wrapped = _html(build, True)
    assert witness in wrapped, (
        f"ui.{name} : envelopper un enfant dans une zone `@refreshable` "
        f"lui fait perdre « {witness} ».\n"
        f"  {len(bare)} caractères sans enveloppe, {len(wrapped)} avec."
    )


@pytest.mark.parametrize("name", sorted(_BEHAVIOUR))
def test_the_zone_keeps_its_identity(name: str) -> None:
    """Et la zone garde son ``bz-id`` — sinon elle ne se rafraîchit plus.

    C'est la moitié qu'un simple déballage ferait perdre : l'enfant
    s'afficherait correctement, et le bouton qui doit le rafraîchir
    n'aurait plus de cible. Silencieux, et pire que le bug d'origine.
    """
    build, _ = _BEHAVIOUR[name]
    wrapped = _html(build, True)
    assert re.search(r'bz-id="refresh_[0-9a-f]+"', wrapped), (
        f"ui.{name} : la zone a perdu son `bz-id` en passant par le tri "
        f"du parent. L'enfant est bien rendu, et HTMX n'a plus de cible "
        f"pour le rafraîchir.\n"
        f"  `unwrap_transparent` rend un COUPLE — l'enfant et de quoi le "
        f"ré-habiller. Appelle `rewrap(node)` sur le nœud composé."
    )
