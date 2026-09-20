"""features/shell — shell: the root frame, and screen 12 (responsive
shell).

``ui.viewport`` + ``ui.pane`` carry the frame and its scrolling region —
no class string left to copy here, and no load-bearing ``min-h-0`` to
remember. The WHY lives in the two components' themes; cf. also
``app-structure.md`` § 5.

**The responsive is a SERVER `if`**, not CSS: ``Screen().is_mobile`` is a
real `bool` read from the `bz_screen` cookie at render time, so **a
single tree exists in the DOM**. It is the escape hatch designed for a
STRUCTURAL swap — a rail on the left and a tab bar at the bottom are not
the same nav dressed differently, and no media query swaps them cleanly
(``screen-responsive-nav.md``).

What the CRM puts under constraint here and no app had: **eleven
routes**. A rail carries them all; a tab bar carries five — so mobile
must CHOOSE, and the choice is code, not a stylesheet.

⚠️ No live resize, by design: the correction happens at load. Crossing
768 px while resizing requires a reload.
"""

from __future__ import annotations

from bretzel import Feature, Screen, layout, refreshable, ui
from bretzel.theme import ColorScheme

from examples.crm.core.domain import ROLES
from examples.crm.features.access import (
    ViewerPrefs,
    current_profile,
    is_director,
    portfolio_options,
    set_portfolio,
    sign_out,
)

#: The full nav — label, icon, route. The rail renders it whole.
NAV: tuple[tuple[str, str, str], ...] = (
    ("Pipeline", "columns-3", "/"),
    ("Accounts", "building-2", "/accounts"),
    ("Contacts", "users", "/contacts"),
    ("Activities", "calendar-days", "/activities"),
)
PILOTAGE: tuple[tuple[str, str, str], ...] = (
    ("Reports", "chart-column", "/reports"),
    ("Search", "search", "/search"),
    ("Realtime", "radio", "/realtime"),
)
OUTILS: tuple[tuple[str, str, str], ...] = (
    ("Import", "upload", "/import"),
    ("Settings", "settings", "/settings"),
    ("App map", "network", "/_map"),
)

#: Mobile's five tabs. They are the five daily gestures, not the rail's
#: first five: an equal-width tab bar becomes unreadable beyond that, and
#: "App map" is not a daily gesture.
TABS: tuple[tuple[str, str, str], ...] = (
    ("Pipeline", "columns-3", "/"),
    ("Accounts", "building-2", "/accounts"),
    ("Contacts", "users", "/contacts"),
    ("Activities", "calendar-days", "/activities"),
    ("Chercher", "search", "/search"),
)


#: The three colour modes and their icon, for the bar footer's menu. The
#: long label lives in ``settings.py`` — here it is a shortcut, not the
#: setting.
THEME_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("light", "Light theme", "sun"),
    ("dark", "Dark theme", "moon"),
    ("system", "System theme", "monitor"),
)


@refreshable(deps=[ViewerPrefs])
def portfolio_picker() -> None:
    """The portfolio selector — DIRECTORATE only.

    Rendered in the sidebar: elsewhere the choice would have no place —
    it bears on all TWELVE screens, so it belongs to the frame, not to a
    page.

    **It disappears when the sidebar collapses**, section included. The
    bet "a ``ui.select`` in a ``ui.sidebar`` in ``rail`` mode" was
    measured on 2026-08-29 and it is lost on both sides: the PANEL fell
    to 31 px (fixed in the base layer, ``MIN_MATCHED_WIDTH``), and the
    TRIGGER stays a 31 px square with a bare chevron, which says neither
    what it does nor what is chosen. The sidebar's other children have a
    rail form (the entry becomes an icon, the section label becomes a
    line); a select has none.

    The class is set on the SECTION, not on the field: hidden on the
    field alone, the section would still render its ``section_divider``
    — the line that replaces the title in the rail — hence a separator
    with nothing under it.
    """
    if not is_director():
        return
    with ui.sidebar_section(
        label="PORTFOLIO",
        classes="group-data-[open=false]/sidebar:hidden",
    ):
        with ui.vstack(gap="none", classes="px-2 pb-2"):
            ui.select(value=ViewerPrefs().portefeuille,
                      options=portfolio_options(), size="sm",
                      on_change=set_portfolio)


@refreshable(deps=[ViewerPrefs])
def viewer_footer() -> None:
    """Who is signed in, and the only way out.

    The subtitle carries the ROLE. It first carried the effective
    scoping, which gave "Sofia Rossi / Sofia Rossi" on screen for a
    commercial — for whom the two are the same word. A director's
    portfolio, for its part, is already written in their selector just
    above.

    ⚠️ **No ``avatar=``**: the component derives the initials from
    ``name`` on its own (``_footer_initials``), and the four other
    examples that instantiate it let it. Computing them here gave the
    same result on all seven accounts — so it was duplicated work, not a
    setting.
    """
    profile = current_profile()
    if profile is None:
        return
    with ui.sidebar_footer(
        name=profile["display_name"],
        subtitle=ROLES[profile["role"]],
    ):
        # The theme is reachable from ANYWHERE, not only from the
        # settings: it is a reading-comfort setting, and crossing a page
        # to lower the brightness makes no sense. ``ColorScheme.set``
        # returns client-side source — the click does not go to the
        # server.
        for value, label, icon in THEME_ITEMS:
            ui.sidebar_footer_item(label=label, icon_left=icon,
                                   on_click=ColorScheme.set(value))
        ui.sidebar_footer_item(label="Settings", icon_left="settings",
                               href="/settings")
        ui.sidebar_footer_item(label="Sign out", icon_left="log-out",
                               color="error", on_click=sign_out)


@layout
def shell() -> None:
    mobile = Screen().is_mobile
    with ui.viewport():
        # ONE ``ui.sidebar``, the SAME children, two collapse modes.
        # - desktop → ``rail``: collapsed, a strip of icons remains, and
        #   eleven routes are worth a permanent strip.
        # - mobile  → ``overlay``: it leaves the flow and slides over,
        #   dimmed backdrop, Escape. ``rail`` on a phone would eat a
        #   fifth of the width permanently.
        sidebar = ui.sidebar(collapsible="overlay" if mobile else "rail",
                             open=not mobile)
        with sidebar:
            ui.sidebar_title(
                "Bretzel CRM",
                icon=ui.icon("handshake", color="primary", size="lg"),
            )
            for section, items in (("VENTES", NAV), ("PILOTAGE", PILOTAGE),
                                   ("OUTILS", OUTILS)):
                with ui.sidebar_section(label=section):
                    for label, icon, href in items:
                        ui.sidebar_item(label, icon=icon, href=href)
            portfolio_picker()
            viewer_footer()
        with ui.pane(gap="none"):
            if mobile:
                # ⚠️ The hamburger belongs to the APP, not to the
                # component: in ``overlay`` mode the bar is ``fixed``
                # OFF-screen (measured: x = -256), and its own collapse
                # button goes with it (x = -148). Without this trigger,
                # six of the eleven routes become unreachable on mobile —
                # the tab bar carries only five. The framework now
                # REFUSES to render this composition without a way back.
                with ui.hstack(
                    justify="between", align="center",
                    classes="sticky top-0 z-20 bg-background "
                            "px-4 py-2 border-b border-text/10",
                ):
                    # ``ui.sidebar_trigger``: it wires the bar, emits
                    # the ``aria-controls``, and it is what the
                    # reachability guard expects. No more ``attrs=`` for
                    # the accessible name since 2026-08-24: it comes from
                    # ``texts["sidebar.toggle"]``, declared once in
                    # ``main.py`` with the other 46.
                    ui.sidebar_trigger(sidebar, icon="menu")
                    ui.text("Bretzel CRM", weight="semibold")
                    ui.icon("handshake", color="primary")
            with ui.vstack(gap="none", classes="p-8 max-md:px-4 max-md:py-4"):
                ui.outlet()
            if mobile:
                # The tab bar is the LAST child of the scrolling column,
                # not a sibling of the shell. Its theme is
                # ``sticky bottom-0`` and not ``fixed``: it stays in the
                # flow, so it reserves its own height and nothing needs a
                # page bottom. Placed outside, it no longer has a
                # scrolling container to stick to — measured: it rendered
                # AT THE TOP, at y=0, because the ``fixed inset-0`` shell
                # had left it.
                with ui.bottom_bar():
                    for label, icon, href in TABS:
                        ui.bottom_bar_item(label=label, icon=icon, href=href)


feature = Feature(name="shell", kind="shell", provides=[shell],
                  uses=["access"])
