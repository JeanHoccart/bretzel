"""RÉFÉRENCE — Catalogue ui.*.

Toute la surface ``ui.*`` lue en direct dans le code. Chaque composant
est introspecté au render (``describe_ui_symbol``) : signature, props
bindables, events, slots, méthodes impératives — la page ne peut pas se
désynchroniser du framework.

Le namespace ``ui.*`` est hétérogène : à côté des composants vivent des
helpers (itération ``ui.each``, toast ``ui.notification``, descripteur
``ui.column``). Ils n'ont ni props ni events — listés à part.
"""

from __future__ import annotations

from bretzel import page, ui

from examples.docs.features.shell import shell
from examples.docs.lib.blocks import component_mirror, helper_mirror
from bretzel.introspect import (
    ComponentInfo,
    HelperInfo,
    describe_ui_symbol,
    ui_symbol_names,
)

PATH = "/components"

# Reading order for the families + a lucide icon each.
_FAMILY_ORDER: list[tuple[str, str, str]] = [
    ("primitives", "Primitives", "box"),
    ("layout", "Layout", "layout"),
    ("actions", "Actions", "mouse-pointer-click"),
    ("inputs", "Inputs", "keyboard"),
    ("feedback", "Feedback", "bell"),
    ("data", "Data", "table"),
    ("charts", "Charts", "trending-up"),
    ("navigation", "Navigation", "navigation"),
    ("overlay", "Overlay", "layers"),
    ("meta", "Meta", "settings"),
]


def family_card(label: str, icon: str, components: list[ComponentInfo]) -> None:
    with ui.card():
        with ui.vstack(gap="sm"):
            with ui.hstack(align="center", gap="sm"):
                ui.icon(icon, color="muted")
                ui.heading(label, level=2)
                ui.badge(str(len(components)), color="muted", variant="outline")
            with ui.accordion(multiple=True):
                for info in sorted(components, key=lambda c: c.ui_name):
                    with ui.accordion_item(info.ui_name, label=f"ui.{info.ui_name}"):
                        component_mirror(info)


@page(PATH, layout=shell, title="Catalogue ui.*")
def components_page() -> None:
    infos = [describe_ui_symbol(n) for n in ui_symbol_names()]
    components = [i for i in infos if isinstance(i, ComponentInfo)]
    helpers = [i for i in infos if isinstance(i, HelperInfo)]

    by_family: dict[str, list[ComponentInfo]] = {}
    for comp in components:
        by_family.setdefault(comp.family, []).append(comp)

    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Catalogue ui.*", level=1, size="3xl")
            ui.text(
                "Toute la surface `ui.*` lue en direct dans le code — "
                "signature, props bindables, events, slots, méthodes "
                "impératives. Cette page introspecte les classes au render : "
                "elle ne peut pas se désynchroniser du framework.",
                color="muted", size="lg",
            )
            with ui.hstack(gap="sm", wrap=True):
                ui.badge(f"{len(components)} composants", color="primary",
                         variant="soft")
                ui.badge(f"{len(helpers)} helpers", color="warning",
                         variant="soft")

            with ui.card(color="surface"):
                with ui.vstack(gap="xs"):
                    ui.heading("Composant ou helper ?", level=3)
                    ui.text(
                        "`ui.*` n'est pas homogène. Un composant se rend et "
                        "porte un contrat (props bindables, events, slots, "
                        "méthodes impératives). Un helper — `ui.each` "
                        "(itération), `ui.notification` (toast), `ui.column` "
                        "(descripteur de colonne) — n'est qu'une fonction. "
                        "Les deux sont listés, mais pas mélangés.",
                        color="muted", size="sm",
                    )

            for fam_key, fam_label, fam_icon in _FAMILY_ORDER:
                fam = by_family.get(fam_key)
                if fam:
                    family_card(fam_label, fam_icon, fam)

            with ui.card():
                with ui.vstack(gap="sm"):
                    with ui.hstack(align="center", gap="sm"):
                        ui.icon("wrench", color="muted")
                        ui.heading("Helpers", level=2)
                        ui.badge(str(len(helpers)), color="muted",
                                 variant="outline")
                    ui.text(
                        "Ces symboles vivent dans `ui.*` mais ne sont PAS des "
                        "composants — pas de props, pas d'events.",
                        color="muted", size="sm",
                    )
                    with ui.accordion(multiple=True):
                        for info in helpers:
                            with ui.accordion_item(info.ui_name,
                                                   label=f"ui.{info.ui_name}"):
                                helper_mirror(info)
