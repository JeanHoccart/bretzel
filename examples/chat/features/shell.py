"""chat/shell — the frame. A feature like any other, exposing a region.

``fixed inset-0`` and not ``h-screen``: that takes the shell out of the
flow, otherwise a scrollable panel inflates ``html.scrollHeight`` and the
viewport ends up with a second scrollbar (cf. ``traps.md`` § *Shell layout
h-screen*). The conversation container scrolls on its own.
"""

from __future__ import annotations

from bretzel import LiveConnection, Screen, layout, ui


@layout
def shell() -> None:
    with ui.viewport():
        # ONE ``ui.sidebar``, the SAME children, two collapse modes. The
        # ternary is all the responsive this app has.
        #
        # - desktop → ``offcanvas``: collapsed, the sidebar vanishes. On a
        #   ONE-page app, a permanent strip of icons (``rail``) would take
        #   width and offer nothing.
        # - mobile  → ``overlay``: it leaves the flow and slides over the
        #   content, dimmed backdrop, Escape, scroll locked. It is the
        #   ONLY mode not gated on ``md:``; ``offcanvas`` on a phone would
        #   simply never close.
        #
        # ``Screen().is_mobile`` is a SERVER ``if`` (cookie read at render
        # time), so a single branch exists in the DOM: one component, one
        # ``open`` state, one ``.toggle()``.
        sidebar = ui.sidebar(
            collapsible="overlay" if Screen().is_mobile else "offcanvas",
            # On mobile the sidebar starts CLOSED — it would cover the
            # conversation. On desktop it starts open.
            open=not Screen().is_mobile,
        )
        with sidebar:
            ui.sidebar_title(
                "Chat",
                icon=ui.icon("message-square", color="primary", size="lg"),
            )
            with ui.sidebar_section(label="DEMO"):
                ui.sidebar_item("Conversation", icon="message-circle", href="/")

        with ui.vstack(gap="none", classes="flex-1 min-w-0 overflow-hidden"):
            with ui.hstack(
                justify="between", align="center", gap="sm",
                classes="px-6 py-3 border-b border-text/10",
            ):
                # The trigger lives IN the app's topbar, not in the
                # component: the sidebar no longer auto-renders a reopen
                # button, it would have placed a second, floating one
                # beside this one. ``ui.sidebar_trigger`` is the piece to
                # place — it wires the bar, emits the ``aria-controls``,
                # and satisfies the reachability guard.
                ui.sidebar_trigger(sidebar, size="sm")
                # ``LiveConnection`` is a framework ClientState: the
                # runtime flips the SSE connection's state in it. We do
                # not drive it, we READ it — the indicator says whether
                # the other tabs will really receive the log live.
                with ui.hstack(align="center", gap="sm"):
                    ui.badge("live", color="success",
                             visible=LiveConnection().connected)
                    ui.badge("hors ligne", color="muted",
                             visible=~LiveConnection().connected)

            # ⚠️ The chain of heights must be CONTINUOUS down to the
            # page, otherwise no inner zone can scroll. Two links are to
            # be placed by hand:
            #
            # 1. ``ui.container`` is a ``block`` by default — so its child
            #    cannot take ``flex-1``. Hence ``flex flex-col``.
            # 2. ``ui.outlet`` renders a **block ``<main>`` with no
            #    height**. It inherits no constraint: measured at 1 888 px
            #    inside an 855 px parent, silently clipped by the
            #    ``overflow-hidden``. The page's ``h-full`` then never
            #    resolved, and its message zone grew instead of scrolling.
            #
            # That is the price of a full-height layout today: the outlet
            # does not pass the constraint on, you have to give it.
            with ui.container(
                width="lg",
                classes="flex-1 min-h-0 overflow-hidden flex flex-col",
            ):
                ui.outlet(classes="flex-1 min-h-0 flex flex-col")
