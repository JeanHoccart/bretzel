"""Getting started — checking application code."""

from __future__ import annotations

from bretzel import page, ui
from bretzel.lint import rule_summaries

from examples.docs.features.shell import shell

PATH = "/check"


def rule_rows() -> list[dict[str, str]]:
    """Return live rule summaries through the linter's public API."""
    return [
        {"regle": slug, "refuse": phrase}
        for slug, phrase in rule_summaries().items()
    ]


@page(PATH, layout=shell, title="Check your code")
def check_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Check your code", level=1, size="3xl")
            ui.text(
                "`describe` tells you what exists; `check` evaluates how you use it. "
                "Both read installed code, so they stay aligned with your version.",
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Run it", level=2)
                    ui.code(
                        "py -m bretzel.cli.main check my_app/\n"
                        "py -m bretzel.cli.main check --deep my_app.main:app\n",
                        lang="bash",
                    )
                    ui.text(
                        "The first pass is static: it reads files, mounts nothing, and needs "
                        "no running application. `--deep` also mounts the real app and compares "
                        "its declared features with what they actually do.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Why another linter?", level=2)
                    ui.text(
                        "Ruff and mypy assess Python. Neither knows that an unknown keyword "
                        "passed to `ui.button` becomes an inert HTML attribute: it does not raise, "
                        "display, or stand out in review. These rules catch those silent failures.",
                        color="muted", size="sm",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="md"):
                    rows = rule_rows()
                    with ui.hstack(align="center", gap="sm"):
                        ui.heading("What it can see", level=2)
                        ui.badge(str(len(rows)), color="muted",
                                 variant="outline")
                    ui.text(
                        "Read live through `rule_summaries()`: the table executed by the CLI. "
                        "A new rule appears here without editing this page.",
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("regle", label="Rule"),
                            ui.column("refuse", label="It rejects…"),
                        ],
                        rows=rows,
                        size="sm",
                    )
