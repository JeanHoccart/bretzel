"""features/shell — shell: the root frame, the permanent sidebar.

*"A permanent sidebar on the left: the classes, the search, the
settings, the lesson log. The old version stacked everything into a
horizontal toolbar that overflowed"* (§ 8 of the specification).

For now it carries only one entry: batch 1 delivers one screen. The
others arrive with their batches — a nav announcing routes that do not
exist is worse than a short nav.

**The scrolling model: the FROZEN document** — ``ui.viewport`` +
``ui.pane``. It is the tools' model, and this app is one: *"the tablet is
a workstation, not a consultation"* (EF-U3). It is paid for with a
continuous chain of heights from the root to the region, and it buys
independently scrolling regions — which batch 3's grid will need, with
its header of dates that must not go up out of view when one scrolls down
to the evening slots.

⚠️ **This file's two zones are ``@refreshable``, and it is not
decorative.** A ``@layout`` is rendered ONCE per page load: anything
reading a mutable state there without being a zone is frozen forever. So
the year selector would show the new year while the banner kept saying
the old one — the screen would show the contradiction without flagging
it. It is ``livrer-une-app.md``'s silence B2, paid for twice elsewhere.
"""

from __future__ import annotations

from bretzel import Feature, Screen, fullscreen, layout, refreshable, ui
from bretzel.theme import ColorScheme
from examples.ecole.features.annees import (
    AnneeVue,
    annee_regardee,
    bandeau_consultation,
    selecteur_annee,
)

#: The nav. It grows from one batch to the next: home and settings
#: (batches 1-2), then the timetable, the lesson log, the search. An
#: entry only appears there when its route exists — it is the
#: specification's trap no. 14, "writing a screen before its routes",
#: seen from the nav.
NAV: tuple[tuple[str, str, str], ...] = (
    ("Emploi du temps", "calendar-days", "/"),
    ("Mes classes", "layout-grid", "/classes"),
    ("Cahier de texte", "notebook-pen", "/cahier"),
    ("Chercher un élève", "search", "/recherche"),
)

#: What is set once a year, apart from the daily work.
OUTILS: tuple[tuple[str, str, str], ...] = (
    ("Import et archives", "upload", "/import"),
    ("Réglages", "settings", "/reglages"),
)

#: The three colour modes and their icon.
THEMES: tuple[tuple[str, str, str], ...] = (
    ("light", "Thème clair", "sun"),
    ("dark", "Thème sombre", "moon"),
    ("system", "Thème système", "monitor"),
)


@refreshable(deps=[AnneeVue], name="annee_picker")
def zone_annee() -> None:
    selecteur_annee()


@refreshable(deps=[AnneeVue], name="bandeau_annee")
def zone_bandeau() -> None:
    bandeau_consultation()


@layout
def shell() -> None:
    # ``is_touch`` and not ``is_mobile``: EF-U4 says full screen only
    # shows where it works, and the counter-example named is Safari on a
    # tablet — a question of engine, not of width. An iPad in landscape
    # is wide and cannot do it.
    #
    # ⚠️ **It is an approximation, and it is noted as a finding.** The
    # real test is ``document.fullscreenEnabled``, which lives in the
    # browser; Bretzel exposes no client capability to read from Python.
    # The coarse pointer is the closest substitute the server has, and it
    # is wrong on an Android tablet — where full screen works and where
    # the button will be hidden.
    plein_ecran_utile = not Screen().is_touch

    with ui.viewport():
        with ui.sidebar(collapsible="rail"):
            ui.sidebar_title(
                "École",
                icon=ui.icon("flask-conical", color="primary", size="lg"),
            )
            for section, entrees in (("SUIVI", NAV), ("OUTILS", OUTILS)):
                with ui.sidebar_section(label=section):
                    for label, icon, href in entrees:
                        ui.sidebar_item(label, icon=icon, href=href)
            with ui.sidebar_footer(name="Physique-chimie",
                                   subtitle=annee_regardee()["libelle"]):
                # EF-U2: the year is changed from the sidebar, and the
                # FOOTER is the only place that survives collapsing to a
                # rail (cf. `selecteur_annee`'s docstring). Its subtitle
                # carries the year being looked at, so the information
                # stays readable even when the menu is closed.
                zone_annee()
                ui.divider()
                for valeur, label, icon in THEMES:
                    ui.sidebar_footer_item(label=label, icon_left=icon,
                                           on_click=ColorScheme.set(valeur))
                if plein_ecran_utile:
                    ui.sidebar_footer_item(
                        label="Plein écran", icon_left="expand",
                        on_click=fullscreen(),
                    )
        # ``padding="md"`` and not ``lg``: the app's most constrained
        # screen is a grid of SIX days that must fit in width, and the
        # frame is what can be given back to it.
        with ui.pane(gap="md", padding="md"):
            zone_bandeau()
            ui.outlet()


feature = Feature(name="shell", kind="shell", provides=[shell],
                  uses=["annees"])
