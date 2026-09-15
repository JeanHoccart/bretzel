"""Public entry point for Bretzel documentation."""

from bretzel import page, ui

from examples.docs.features.shell import shell


@page("/", layout=shell, title="Introduction")
def home_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="xl"):
            with ui.hstack(align="center", gap="sm", wrap=True):
                ui.badge("Documentation", color="primary", variant="soft")
                ui.badge("v0.1.0a1 · Early alpha", color="warning", variant="outline")

            with ui.hstack(align="center", justify="between", gap="xl", wrap=True):
                with ui.vstack(gap="md", classes="max-w-3xl"):
                    ui.heading(
                        "Build reactive web applications in Python.",
                        level=1, size="4xl",
                    )
                    ui.text(
                        "Bretzel brings components, typed state and server logic "
                        "together in one model. The browser stays synchronized, "
                        "without a separate JavaScript application or npm pipeline.",
                        color="muted", size="lg",
                    )
                    with ui.hstack(gap="sm", wrap=True):
                        ui.button(
                            "Start in 5 minutes", href="/quickstart",
                            icon_right="arrow-right", size="lg",
                        )
                        ui.button(
                            "Understand the model", href="/how",
                            variant="outline", size="lg",
                        )
                ui.image(
                    "/_bretzel/favicon.svg", alt="Logo Bretzel", fit="contain",
                    classes="w-64 max-md:w-44 bg-transparent",
                    attrs={"loading": "eager"},
                )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    with ui.hstack(align="center", justify="between", gap="md", wrap=True):
                        ui.text("Try the early alpha", weight="bold")
                        ui.badge("Python 3.12–3.13", color="muted", variant="outline")
                    ui.code(
                        'pip install "bretzel @ git+https://github.com/JeanHoccart/bretzel.git"\n'
                        "bretzel new mon-app\n"
                        "cd mon-app && bretzel dev",
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
                            "Interactions call Python handlers without writing "
                            "a second application on the client.",
                            color="muted",
                        )
                with ui.card():
                    with ui.vstack(gap="sm"):
                        ui.icon("zap", color="warning", size="xl")
                        ui.heading("A reactive UI", level=3)
                        ui.text(
                            "When state changes, Bretzel updates only the fragments "
                            "that depend on it.",
                            color="muted",
                        )

            with ui.card(color="primary"):
                with ui.vstack(gap="sm"):
                    ui.heading("The one idea to remember", level=2)
                    ui.text(
                        "UI = f(state). Describe the interface, change state, "
                        "and let Bretzel keep the browser up to date.",
                        size="lg",
                    )
                    ui.button(
                        "See how Bretzel works",
                        href="/how",
                        icon_right="arrow-right",
                        color="background",
                        size="sm",
                    )
