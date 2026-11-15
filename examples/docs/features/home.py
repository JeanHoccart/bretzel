"""Accueil public de la documentation Bretzel."""

import re
from importlib.metadata import metadata

from bretzel import __version__, page, ui
from examples.docs.features.mockup import repair_jobs
from examples.docs.features.shell import shell


def python_range() -> str:
    """The Python versions the installed package declares — read, never written."""
    minors = sorted(
        int(c.rsplit(".", 1)[1]) for c in metadata("bretzel").get_all("Classifier") or []
        if re.fullmatch(r"Programming Language :: Python :: 3\.\d+", c)
    )
    return f"Python 3.{minors[0]}–3.{minors[-1]}"


@page("/", layout=shell, title="Bretzel docs — describe a screen, see it, ship it",
      description="Documentation for Bretzel, the Python web framework where the mockup is the app: built with an AI agent, every file checked, typed state, 100+ components and no npm toolchain.")
def home_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="xl"):
            with ui.hstack(align="center", gap="sm", wrap=True):
                ui.badge("Documentation", color="primary", variant="soft")
                ui.badge(f"v{__version__} · Early alpha", color="warning", variant="outline")

            with ui.vstack(gap="md", classes="max-w-3xl"):
                ui.heading(
                    "The mockup is the app.",
                    level=1, size="4xl",
                )
                ui.text(
                    "Ask your AI agent for a screen: it mocks it fast, a throwaway "
                    "page on invented data made of the components the finished "
                    "screen ships. You approve it on screenshots, then say “Build "
                    "it”: the same code is wired to typed state — in Python only, "
                    "with no JavaScript project or npm toolchain to maintain.",
                    color="muted", size="lg",
                )
                with ui.hstack(gap="sm", wrap=True):
                    ui.button(
                        "Start with a mockup", href="/mockup",
                        icon_right="arrow-right", size="lg",
                    )
                    ui.button(
                        "Start in 5 minutes", href="/quickstart",
                        variant="outline", size="lg",
                    )

            with ui.vstack(gap="sm"):
                with ui.hstack(align="center", justify="between", gap="md", wrap=True):
                    ui.text("A live mockup, not a screenshot", weight="bold")
                    ui.link("How it was made", href="/mockup")
                with ui.card(padding="lg"):
                    repair_jobs()

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    with ui.hstack(align="center", justify="between", gap="md", wrap=True):
                        ui.text("Try the early alpha", weight="bold")
                        ui.badge(python_range(), color="muted", variant="outline")
                    ui.code(
                        "python -m pip install bretzel\n"
                        "bretzel new hello-bretzel\n"
                        "cd hello-bretzel\n"
                        "python -m pip install -e .\n"
                        "bretzel dev",
                        lang="bash",
                    )

            ui.heading("The mental model", level=2, size="2xl")
            with ui.grid(cols=3, gap="md", classes="max-lg:grid-cols-1"):
                with ui.card():
                    with ui.vstack(gap="sm"):
                        ui.icon("database", color="primary", size="xl")
                        ui.heading("Typed state", level=3)
                        ui.text(
                            "The server owns the source of truth in explicit, "
                            "testable Python objects.",
                            color="muted",
                        )
                with ui.card():
                    with ui.vstack(gap="sm"):
                        ui.icon("mouse-pointer-click", color="secondary", size="xl")
                        ui.heading("Python actions", level=3)
                        ui.text(
                            "Interactions call handlers without writing a second "
                            "application on the client.",
                            color="muted",
                        )
                with ui.card():
                    with ui.vstack(gap="sm"):
                        ui.icon("zap", color="warning", size="xl")
                        ui.heading("Reactive UI", level=3)
                        ui.text(
                            "When state changes, Bretzel updates only the fragments "
                            "that depend on it.",
                            color="muted",
                        )

            with ui.card(color="primary"):
                with ui.vstack(gap="sm"):
                    ui.heading("Underneath: UI = f(state)", level=2)
                    ui.text(
                        "Describe the interface, change the state, and let "
                        "Bretzel keep the browser current.",
                        size="lg",
                    )
                    ui.button(
                        "See how Bretzel works",
                        href="/how",
                        icon_right="arrow-right",
                        color="background",
                        size="sm",
                    )
