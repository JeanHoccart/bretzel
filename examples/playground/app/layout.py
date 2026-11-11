"""The application shell: sidebar on the left, page in the outlet.

The skeleton: ``ui.viewport`` + ``ui.pane``, ``sidebar_title`` +
``sidebar_footer`` + ``sidebar_footer_item``.

**On a phone** (``Screen().is_mobile``) the sidebar is an ``overlay``,
closed, opened from a top bar's ``ui.sidebar_trigger`` — the CRM's
recipe. The sidebar has shipped no mobile bar of its own since
2026-08-15: the shell is the one that knows it is on a phone. Until
2026-11-06 this shell still counted on that bar, so at 390 px the
docked sidebar kept its 256 px and left the page 38.
"""

from bretzel import Screen, ui
from bretzel.theme import ColorScheme
from examples.playground.app.nav import NAV

#: The three modes, in the order they are read.
THEME_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("light", 'Light theme', "sun"),
    ("dark", 'Dark theme', "moon"),
    ("system", 'System theme', "monitor"),
)



def shell() -> None:
    # ``ui.viewport`` carries the frame — full screen, out of the flow,
    # regions in a row and never a scroll of its own. The thirty lines of
    # comment that lived here (why `fixed inset-0` and not `h-screen`,
    # why `align="stretch"`, why the stacking context is harmless) are in
    # the component's theme:
    # `bretzel/components/layout/viewport/theme.py`. They were copied
    # into nine shells, each free to drift.
    mobile = Screen().is_mobile
    with ui.viewport():
        # Desktop: a rail. Phone: an overlay that slides over the page — a
        # docked sidebar would eat 256 of 390 px for good.
        sidebar = ui.sidebar(collapsible="overlay" if mobile else "rail",
                             open=not mobile)
        with sidebar:
            # ``sidebar_title`` owns the header: logo + title + collapse
            # toggle (and the automatic mobile top bar). No more manual
            # ``hstack``, no more ``pr-12`` nor
            # ``group-data-[open=false]``.
            ui.sidebar_title(
                "Bretzel · Playground",
                icon=ui.icon("shapes", color="primary", size="lg"),
            )
            for section, items in NAV:
                with ui.sidebar_section(label=section):
                    for label, path, icon in items:
                        ui.sidebar_item(label, icon=icon, href=path)
            # ``sidebar_footer``: a row pinned at the bottom that opens
            # a popover on click. Its children are ``sidebar_footer_item``
            # (the same API as ``dropdown_item``: they close on pick).
            # The theme toggle lives here (the new header has no slot for
            # free actions). ``ColorScheme`` is framework-owned (the app
            # never instantiates it); ``ColorScheme.toggle()`` is a pure
            # client expression — zero server round trips.
            with ui.sidebar_footer(
                name="Alex Martin",
                subtitle="alex@acme.com",
            ):
                # Three entries and not a toggle: ``system`` is a state
                # in its own right — "follow my OS" — and a two-position
                # toggle cannot express it. It is what the CRM already
                # does, and it is smoother: one chooses, one does not
                # guess which way it will flip.
                for value, label, icon in THEME_ITEMS:
                    ui.sidebar_footer_item(
                        label=label,
                        icon_left=icon,
                        checked=ColorScheme().mode == value,
                        on_click=ColorScheme.set(value),
                    )
                # The cross link, symmetrical with the docs'.
                # ``sidebar_title`` already goes back to ``/``, so a
                # "Home" entry would serve nothing. Hard-coded port: the
                # target is ANOTHER server.
                ui.sidebar_footer_item(
                    label="Docs", icon_left="book-open",
                    href="http://localhost:8006/",
                )
        # The REGION: the child pages render HERE (outlet_shell), in the
        # pane that scrolls.
        if mobile:
            with ui.pane(gap="none"):
                # The way back to the sidebar: in ``overlay`` mode it sits
                # off-screen with its own collapse button (cf. the CRM).
                with ui.hstack(justify="between", align="center",
                               classes="sticky top-0 z-20 bg-background "
                                       "px-4 py-2 border-b border-text/10"):
                    ui.sidebar_trigger(sidebar, icon="menu")
                    ui.text("Bretzel · Playground", weight="semibold")
                    ui.icon("shapes", color="primary")
                with ui.vstack(gap="none", classes="p-4"):
                    ui.outlet()
        else:
            with ui.pane(gap="none", padding="lg"):
                ui.outlet()
