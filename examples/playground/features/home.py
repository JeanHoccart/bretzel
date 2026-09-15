"""Playground home — overview of what's inside and how to read it."""

from bretzel import ui

PATH = "/"


def page() -> None:
    with ui.container(width="md"):
        with ui.vstack():
            ui.heading("Bretzel · Playground", level=1, size="3xl")
            ui.text(
                "Interactive showcase of every component shipped in Bretzel v2. "
                "Pick a component in the sidebar.",
                color="muted",
            )

            ui.divider()

            ui.heading("How each page is laid out", level=2, size="lg")
            with ui.vstack(gap="md"):
                ui.text(
                    "Showcase — every variant, size, color and state of the "
                    "component visible at a glance.",
                    size="sm",
                )
                ui.text(
                    "Server-state playground — props bound to a SessionState. "
                    "Flipping a control round-trips to the server and re-renders "
                    "the preview.",
                    size="sm",
                )
                ui.text(
                    "Client-state playground — props bound to a ClientState. "
                    "Same shape, but updates happen purely in the browser via "
                    "the runtime. No network.",
                    size="sm",
                )
                ui.text(
                    "Events — server handlers, client bindings, and the "
                    "[server_fn, client.set] composition on the same event.",
                    size="sm",
                )

            ui.divider()

            ui.heading("Already demonstrated by this page itself", level=2, size="lg")
            with ui.vstack(gap="sm"):
                ui.text(
                    "ui.sidebar / ui.sidebar_section / ui.sidebar_item — the "
                    "collapsible nav rail on the left. Active link tracks the "
                    "current URL automatically.",
                    size="sm",
                )
                ui.text(
                    "ui.outlet — the swappable region that holds the current "
                    "page. Clicking a sidebar item swaps only this region, not "
                    "the chrome.",
                    size="sm",
                )

            ui.divider()

            ui.heading("Run", level=2, size="lg")
            ui.text(
                "py -m examples.playground.main",
                size="sm", color="muted", classes="font-mono",
            )
