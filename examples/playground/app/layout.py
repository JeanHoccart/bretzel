"""The application shell: sidebar on the left, page in the outlet.

The same skeleton as ``examples/flat/features/shell.py`` (the reference
that renders correctly): ``h-screen`` in the flow, ``sidebar_title`` +
``sidebar_footer`` + ``sidebar_footer_item``, and the content shifted
under the mobile top bar through ``max-md:pt-[5.5rem]``.
"""

from bretzel import ui
from bretzel.theme import ColorScheme

#: The three modes, in the order they are read.
THEME_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("light", 'Light theme', "sun"),
    ("dark", 'Dark theme', "moon"),
    ("system", 'System theme', "monitor"),
)

from examples.playground.app.nav import NAV


def shell() -> None:
    # ``ui.viewport`` carries the frame — full screen, out of the flow,
    # regions in a row and never a scroll of its own. The thirty lines of
    # comment that lived here (why `fixed inset-0` and not `h-screen`,
    # why `align="stretch"`, why the stacking context is harmless) are in
    # the component's theme:
    # `bretzel/components/layout/viewport/theme.py`. They were copied
    # into nine shells, each free to drift.
    with ui.viewport():
        with ui.sidebar(collapsible="rail"):
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
                name="Jean Hoccart",
                subtitle="jean.hoccart@gmail.com",
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
        # The REGION: the child pages render HERE (outlet_shell).
        # ``min-h-0`` lets the flex child shrink below its content height
        # so ``overflow-y-auto`` triggers a scrollbar instead of pushing
        # the panel beyond the viewport.
        # ``max-md:pt-[5.5rem]`` shifts the content under the mobile top
        # bar (``position: fixed``, h-14 = 3.5rem, frosted
        # ``bg-surface/80``) — 5.5rem = 3.5rem (the bar) + 2rem of
        # breathing room. Desktop (md+): no bar, the ``p-8`` takes over.
        # The same line as flat.
        with ui.pane(gap="none", padding="lg",
                     classes="max-md:pt-[5.5rem]"):
            ui.outlet()
