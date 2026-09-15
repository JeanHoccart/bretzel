"""La largeur d'un wrapper à trigger est une question PARTAGÉE.

Tooltip / Popover / Dropdown enveloppent leur trigger dans une racine
``w-fit``. Un trigger pleine largeur doit faire grandir ce wrapper
(``block w-full``) ou il se rétracte à la largeur du contenu. Parti d'un
fix tooltip-only, le bug s'est révélé identique sur Popover + Dropdown
(même racine ``inline-flex w-fit``) — d'où ``trigger_is_full_width`` /
``expand_fit_wrapper`` dans ``bretzel.components.base._wiring``.

``ui.combobox(trigger=…)`` pose la question SYMÉTRIQUE : sa racine est
``w-full`` (c'est un champ de formulaire), et détachée elle enveloppe le
bouton de l'appelant — donc elle doit RÉTRÉCIR, sauf si quelqu'un
réclame la pleine largeur. Même helper (``trigger_asks_full_width``),
même famille, même fichier de garde : la règle a d'abord été assertée
depuis un test de `datatable`, ce qui la rendait invisible ici et la
faisait disparaître avec le filtre de colonne.

⚠️ Ces assertions lisent le HTML RENDU, pas ``THEME["slots"]["root"]``.
``test_input_root_fills_width`` lit le slot et resterait donc verte sur
une racine qui émet ``w-fit`` — la gate protège l'orthographe, pas la
propriété (cf. la même leçon dans traps.md).
"""

from __future__ import annotations

import pytest

from bretzel import ui
from bretzel.components.base.testing import render_isolated
from bretzel.render import serialize_html
from bretzel.theme import Theme


def _root(html: str) -> str:
    return html[: html.find(">") + 1]


@pytest.mark.parametrize(
    "build",
    [
        lambda: ui.popover(trigger=ui.button("x", classes="w-full")),
        lambda: ui.dropdown(trigger=ui.button("x", classes="w-full")),
    ],
    ids=["popover", "dropdown"],
)
def test_full_width_trigger_expands_wrapper(build) -> None:
    with render_isolated(theme=Theme()):
        root = _root(serialize_html(build()))
    assert "block w-full" in root
    assert "w-fit" not in root


@pytest.mark.parametrize(
    "build",
    [
        lambda: ui.popover(trigger=ui.icon_button("info")),
        lambda: ui.dropdown(trigger=ui.icon_button("more-horizontal")),
    ],
    ids=["popover", "dropdown"],
)
def test_non_full_width_trigger_keeps_fit(build) -> None:
    with render_isolated(theme=Theme()):
        root = _root(serialize_html(build()))
    assert "w-fit" in root


@pytest.mark.parametrize(
    "build,expected",
    [
        (lambda: ui.combobox(["a"], multiple=True,
                             trigger=ui.button("Status")), "w-fit"),
        (lambda: ui.combobox(["a"], multiple=True,
                             trigger=ui.button("Status", classes="w-full")),
         "w-full"),
        (lambda: ui.combobox(["a"], multiple=True, classes="w-full",
                             trigger=ui.button("Status")), "w-full"),
        (lambda: ui.combobox(["a"], multiple=True,
                             attrs={"class": "w-full"},
                             trigger=ui.button("Status")), "w-full"),
        # Sans ``trigger=``, la recherche EST le trigger : un champ, donc
        # pleine largeur, quoi qu'il arrive.
        (lambda: ui.combobox(["a"], multiple=True), "w-full"),
    ],
    ids=["detached-hugs", "trigger-asks-full", "classes-asks-full",
         "attrs-class-asks-full", "attached-fills"],
)
def test_detached_combobox_hugs_unless_asked_otherwise(build, expected) -> None:
    with render_isolated(theme=Theme()):
        root = _root(serialize_html(build()))
    assert expected in root
    other = "w-full" if expected == "w-fit" else "w-fit"
    assert other not in root


def test_tooltip_children_trigger_expands() -> None:
    with render_isolated(theme=Theme()):
        with ui.tooltip(text="t") as t:
            ui.button("z", classes="w-full")
        root = _root(serialize_html(t))
    assert "block w-full" in root
