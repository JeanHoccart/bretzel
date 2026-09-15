"""Gate : un Component passé dans un SLOT ne se rend qu'UNE fois.

Un composant s'auto-enregistre chez le parent actif pendant son propre
``__init__`` — c'est son seul signal de qui le possède. Quand il est ensuite
adopté comme SLOT (``icon=`` / ``label=`` / ``trigger=`` / ``separator=``),
cet enregistrement doit être annulé **à la construction**
(:meth:`Component.adopt_slot`). Sinon le parent, qui parcourt ses enfants
DANS L'ORDRE, le rend en FRÈRE avant même d'atteindre le consommateur : le
composant peint DEUX fois (l'orphelin).

Détacher dans ``render()`` arrive trop tard — le frère est déjà émis.
``Banner.icon`` et ``Breadcrumb.separator`` avaient exactement ce bug
(détach en render), invisible en tests parce que la forme string marche
par accident : l'``Icon`` y est construite PENDANT le render, où
l'auto-enregistrement est désactivé.

Métrique : ``orphelins = count(conteneur) - count(composant seul)``. Un
simple comptage ne suffit pas — SidebarTitle rend légitimement son icône 2x
(état déployé + état rail, exclusifs en CSS) sans aucun orphelin.

Un nouveau slot qui accepte un Component rejoint la table ``_CASES``.
"""

from __future__ import annotations

import pytest

from bretzel import ui
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "monte un composant dans un slot et compte ses occurrences dans le "
    "rendu : le comptage est direct, il n'y a pas de motif"
)

# Marqueur unique porté par le composant qu'on injecte dans le slot.
_MARK = "lucide:star"


def _slot_value():
    return ui.icon("star")


# (label, build(value) -> le composant construit). ``build`` DOIT retourner
# l'instance : on la rend aussi seule pour compter sa part légitime.
def _popover(v):
    with ui.popover(trigger=v) as p:
        ui.text("body")
    return p


def _dropdown(v):
    with ui.dropdown(trigger=v) as d:
        ui.dropdown_item(label="a")
    return d


_CASES = [
    ("alert.icon",              lambda v: ui.alert("m", icon=v)),
    ("alert.message",           lambda v: ui.alert(v)),
    ("badge.icon_left",         lambda v: ui.badge("b", icon_left=v)),
    ("badge.icon_right",        lambda v: ui.badge("b", icon_right=v)),
    ("banner.icon",             lambda v: ui.banner("m", icon=v)),
    ("breadcrumb.separator",    lambda v: ui.breadcrumb(
        [{"label": "a", "href": "/"}, {"label": "b"}], separator=v)),
    ("button.icon_left",        lambda v: ui.button("b", icon_left=v)),
    ("button.icon_right",       lambda v: ui.button("b", icon_right=v)),
    ("button.label",            lambda v: ui.button(v)),
    ("combobox.trigger",        lambda v: ui.combobox(
        ["a", "b"], multiple=True, trigger=v)),
    ("dropdown.trigger",        _dropdown),
    ("dropdown_item.icon_left", lambda v: ui.dropdown_item(label="x", icon_left=v)),
    ("dropdown_item.icon_right", lambda v: ui.dropdown_item(label="x", icon_right=v)),
    ("dropdown_item.label",     lambda v: ui.dropdown_item(label=v)),
    ("empty_state.icon",        lambda v: ui.empty_state(title="t", icon=v)),
    ("icon_button.icon",        lambda v: ui.icon_button(v)),
    ("input.icon_left",         lambda v: ui.input(icon_left=v)),
    ("input.icon_right",        lambda v: ui.input(icon_right=v)),
    ("input.prefix",            lambda v: ui.input(prefix=v)),
    ("input.suffix",            lambda v: ui.input(suffix=v)),
    ("popover.trigger",         _popover),
    ("sidebar_title.icon",      lambda v: ui.sidebar_title("t", icon=v)),
]


@pytest.mark.parametrize("label,build", _CASES, ids=[c[0] for c in _CASES])
def test_component_slot_renders_once(label, build) -> None:
    # Rendu DANS un conteneur : c'est là que l'orphelin apparaîtrait.
    with render_isolated():
        with ui.vstack() as root:
            build(_slot_value())
        in_container = serialize(root.render()).count(_MARK)

    # Rendu du composant SEUL : sa part légitime (peut valoir >1).
    with render_isolated():
        comp = build(_slot_value())
        solo = serialize(comp.render()).count(_MARK)

    assert solo >= 1, (
        f"{label}: le Component passé au slot n'est PAS rendu (slot perdu)."
    )
    assert in_container == solo, (
        f"{label}: {in_container - solo} orphelin(s) — le Component passé au "
        f"slot se rend AUSSI en frère dans le parent ({in_container}x dans le "
        f"conteneur vs {solo}x en propre). Le slot doit passer par "
        f"`Component.adopt_slot(value)` DANS __init__ : détacher depuis "
        f"render() est trop tard, le parent a déjà émis le frère."
    )
