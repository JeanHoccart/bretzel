"""Gate : un clic qui porte l'identité d'un ÉLÉMENT s'appelle ``item_click``.

Le défaut qu'elle ferme
-----------------------
Le catalogue nommait le même concept de trois façons, et la troisième
était la pire ::

    ui.table(on_row_click=…)        une ligne
    ui.diagram(on_node_click=…)     un nœud
    ui.bar_chart(on_click=…)        une BARRE — le nom du composant
    ui.pie_chart(on_click=…)        une PART — entier, pour un élément

Les deux graphiques réutilisaient le nom que onze autres composants
emploient pour le clic **du composant lui-même** (``ui.button``,
``ui.card``, ``ui.icon_button``, les quatre ``*_item``…). Lire
``on_click`` ne disait donc plus ce qu'on recevait : rien, ou bien un
``(label, value)``.

Arbitré le 2026-09-06 : un seul nom pour le clic par élément,
``on_item_click``, sur les cinq composants concernés.

La règle, en une ligne
----------------------
``on_click`` = le composant. ``on_item_click`` = un élément dedans.
Aucun troisième nom.

Ce que la gate NE dit pas
-------------------------
Qu'un composant DEVRAIT avoir un clic par élément — c'est du sens,
aucune machine ne le décide. Elle ne mesure que le nom de ceux qui en
ont un, et l'accord entre le paramètre et ``EVENTS``.
"""

from __future__ import annotations

import inspect
import re

import pytest

from tests.consistency._discovery import (
    component_sources,
    public_component_classes,
    ui_name_of,
)

#: Les deux seuls noms admis dans la famille.
ADMITTED = frozenset({"on_click", "on_item_click"})

#: La marque du clic par élément : le routeur partagé. Un composant qui
#: l'appelle a, par construction, un event posé sur un élément interne.
ROUTER = "item_action_attrs"

CLICKY = re.compile(r"^on_\w*click$")


def click_params() -> list[tuple[str, str]]:
    """Chaque (composant, paramètre) de la famille clic."""
    found = []
    for cls in sorted(public_component_classes(), key=ui_name_of):
        for param in inspect.signature(cls.__init__).parameters:
            if CLICKY.match(param):
                found.append((ui_name_of(cls), param))
    return found


def files_using_the_router() -> list[str]:
    return [
        path.name
        for path in component_sources()
        if ROUTER in path.read_text(encoding="utf-8-sig")
    ]


# ── Les planchers ─────────────────────────────────────────────────────


def test_the_sweep_finds_the_click_family() -> None:
    """Sans lui, une signature illisible viderait le balayage."""
    found = click_params()
    assert len(found) >= 10, (
        f"seulement {len(found)} paramètre(s) de clic trouvé(s) — il y en "
        f"avait 13 le 2026-09-06. La lecture des signatures est cassée."
    )


def test_the_router_is_still_the_mark() -> None:
    """Second plancher : ``item_action_attrs`` est encore la marque.

    Si plus aucun composant ne l'appelle, le second versant de cette
    gate ne regarde plus rien — et resterait vert.
    """
    users = files_using_the_router()
    assert len(users) >= 3, (
        f"seulement {len(users)} fichier(s) appellent `{ROUTER}` : "
        f"{users}. Le routeur partagé du clic par élément a changé de "
        f"nom, ou les composants sont repartis chacun de leur côté."
    )


# ── L'assertion ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "param"), click_params(), ids=lambda v: v
)
def test_a_click_param_uses_one_of_the_two_names(
    name: str, param: str
) -> None:
    assert param in ADMITTED, (
        f"`ui.{name}` expose `{param}=`.\n"
        f"  La famille n'a que deux noms : `on_click` pour le clic DU "
        f"composant, `on_item_click` pour le clic d'un ÉLÉMENT dedans "
        f"(une ligne, un nœud, une barre, une part).\n"
        f"  Un troisième nom oblige à lire le composant pour savoir ce "
        f"que le handler reçoit."
    )


@pytest.mark.parametrize(
    "name",
    [ui_name_of(c) for c in public_component_classes()
     if "item_click" in tuple(getattr(c, "EVENTS", ()) or ())],
    ids=lambda v: v,
)
def test_a_declared_item_click_has_its_param(name: str) -> None:
    """L'accord entre ``EVENTS`` et la signature.

    Le socle route un event déclaré vers la RACINE ; ces composants-là
    routent à la main, donc le paramètre doit exister nommément — sans
    quoi la déclaration promet une prop qui n'est pas là.
    """
    cls = next(c for c in public_component_classes() if ui_name_of(c) == name)
    params = inspect.signature(cls.__init__).parameters
    assert "on_item_click" in params, (
        f"`ui.{name}` déclare `item_click` dans `EVENTS` mais son "
        f"`__init__` n'a pas de `on_item_click=`.\n"
        f"  Ces composants routent à la main (`{ROUTER}`) parce que "
        f"l'`hx-post` vit sur l'ÉLÉMENT, pas sur la racine : le socle "
        f"ne verra jamais passer le handler, donc il faut le nommer."
    )


# ── La morsure ────────────────────────────────────────────────────────


def test_the_detector_catches_a_third_name() -> None:
    """Mutation : le détecteur reconnaît la forme fautive, et elle seule."""
    assert CLICKY.match("on_row_click")
    assert CLICKY.match("on_node_click")
    assert CLICKY.match("on_click")
    assert CLICKY.match("on_item_click")

    # Le versant licite — il ne doit pas ramasser toute la surface.
    assert not CLICKY.match("on_change")
    assert not CLICKY.match("on_clicked_away")
    assert not CLICKY.match("click")
    assert not CLICKY.match("onclick")

    assert "on_row_click" not in ADMITTED
    assert "on_node_click" not in ADMITTED
