"""features/shell — layout : la coque, et la seule région que les pages remplissent.

Feature ``kind="layout"`` : elle n'a pas de route à elle, elle EXPOSE une
région (``ui.outlet()``) que les pages viennent remplir.

Document GELÉ (``ui.viewport`` + ``ui.pane``) : c'est un outil, pas un
document qu'on fait défiler. La barre latérale reste, seule la région
change — donc une navigation ne repeint pas l'écran entier.
"""

from __future__ import annotations

from bretzel import Feature, layout, ui

#: Les écrans, dans l'ordre où on les lit : d'abord le rythme (la
#: question posée), puis ce qui l'explique.
NAV = (
    ("/", "Tâches", "activity"),
    ("/phases", "Phases", "layers"),
    ("/outils", "Outils", "wrench"),
    ("/sessions", "Sessions", "calendar"),
)


@layout
def shell() -> None:
    """Rail à gauche, région à droite."""
    with ui.viewport():
        with ui.sidebar(collapsible="rail"):
            ui.sidebar_title("Atelier", icon="activity")
            with ui.sidebar_section(label="Mesures"):
                for href, libelle, icone in NAV:
                    ui.sidebar_item(libelle, icon=icone, href=href)
        with ui.pane(classes="flex-1 min-w-0 p-6"):
            ui.outlet()


feature = Feature(name="shell", kind="layout", provides=[shell])
