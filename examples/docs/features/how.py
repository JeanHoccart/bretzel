"""Foundations — how Bretzel works."""

from bretzel import page, ui

from examples.docs.features.shell import shell


_CYCLE = [
    ("mouse-pointer-click", "An interaction occurs (a click or input)."),
    ("server", "If it changes the source of truth, it goes to the server: "
               "a Python function runs."),
    ("database", "That function changes state."),
    ("refresh-cw", "The part of the interface that depends on that state is "
                   "rendered again and sent back to the browser."),
]


@page("/how", layout=shell, title="How Bretzel works")
def how_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("How Bretzel works", level=1, size="3xl")
            ui.text(
                "Every web app has two halves: the browser (the client) and "
                "the server. Knowing where code runs—and when it crosses that "
                "boundary—makes the rest of Bretzel easier to understand.",
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("The two halves", level=2)
                    ui.table(
                        columns=[
                            ui.column("side", label="Side"),
                            ui.column("what", label="What it is"),
                        ],
                        rows=[
                            {"side": "Client",
                             "what": "the browser on the user's device—it "
                                     "displays and responds"},
                            {"side": "Server",
                             "what": "where your Python code runs—it owns "
                                     "the source of truth"},
                        ],
                        size="sm",
                    )

            with ui.card(color="primary"):
                with ui.vstack(gap="sm"):
                    ui.heading("Why the server", level=2)
                    ui.text(
                        "A basic rule of the web: the client is never trusted. "
                        "Anything sent from a browser can be altered. Keep what "
                        "matters on the server:",
                    )
                    with ui.vstack(gap="xs"):
                        for t in [
                            "Security — validation that protects your app runs here.",
                            "Source of truth — data belongs to the server, not a tab.",
                            "Private logic — pricing and business rules stay out of "
                            "the browser.",
                            "Sharing — server state can be seen by several users or "
                            "tabs; client state cannot.",
                        ]:
                            with ui.hstack(align="baseline", gap="sm"):
                                ui.icon("check", color="primary", size="sm")
                                ui.text(t, size="sm")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Why the client", level=2)
                    ui.text(
                        "Going through the server costs a network request. For a "
                        "purely visual interaction (opening a menu, ticking a "
                        "checkbox), that would be wasteful. Staying on the client means:",
                        color="muted", size="sm",
                    )
                    with ui.vstack(gap="xs"):
                        for t in [
                            "No request — it is immediate, with no round trip.",
                            "Less server work — the user's device does the work.",
                        ]:
                            with ui.hstack(align="baseline", gap="sm"):
                                ui.icon("check", color="success", size="sm")
                                ui.text(t, size="sm")

            with ui.card(color="surface"):
                with ui.vstack(gap="xs"):
                    ui.heading("UI = f(state)", level=2)
                    ui.text(
                        "The interface is a function of state. You do not modify "
                        "the DOM by hand: describe the UI for a given state, change "
                        "that state, and Bretzel computes the UI again.",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("The Bretzel cycle", level=2)
                    with ui.vstack(gap="sm"):
                        for i, (icon, text) in enumerate(_CYCLE, start=1):
                            with ui.hstack(align="center", gap="sm"):
                                ui.badge(str(i), color="primary", variant="soft")
                                ui.icon(icon, color="primary")
                                ui.text(text, size="sm")
                    ui.text(
                        "An interaction that does not change the source of truth "
                        "(such as opening a panel) skips the server and stays in "
                        "the browser.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("An event's paths", level=2)
                    ui.text(
                        "In practice, an event takes one of these paths:",
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("what", label="The event…"),
                            ui.column("where", label="runs on"),
                            ui.column("roundtrip", label="round trip?"),
                        ],
                        rows=[
                            {"what": "calls a Python function",
                             "where": "the server", "roundtrip": "yes"},
                            {"what": "controls a component or client state",
                             "where": "the client", "roundtrip": "no"},
                        ],
                        size="sm",
                    )
                    ui.text(
                        "It is the same boundary everywhere: state, actions, and "
                        "reactivity each have a server side and a client side. The "
                        "rest of the documentation follows that map.",
                        color="muted", size="sm",
                    )
