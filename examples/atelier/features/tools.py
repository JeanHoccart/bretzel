"""features/tools — page: which tools serve, which ones fail.

Three blocks, in the order in which they answer:

1. **The layer-7 tools** — ``describe``, ``check``, ``probe`` were built
   to avoid round trips. The share of tasks where they serve says
   whether they manage it. It is the block that motivated the app: one
   can ship a whole layer and carry on opening files by hand.
2. **The failure rate per tool** — "where it breaks".
3. **The commands replayed identically** — the clearest trace of trial
   and error: re-running the same thing hoping for another verdict.
"""

from __future__ import annotations

from bretzel import Feature, page, ui
from examples.atelier.features.shell import shell
from examples.atelier.features.tools_data import (
    by_tool,
    failures,
    framework_usage,
    replayed,
)


def block(title: str, help_: str) -> None:
    ui.heading(title, level=3)
    ui.text(help_, size="sm", color="muted")


def percent_cell(value, _row):
    """A failure rate, painted as soon as it stops being anecdotal."""
    return ui.text(f"{value} %", size="sm",
                   color="error" if value >= 5 else "muted")


@page("/tools", title="Tools", layout=shell)
def tools_page() -> None:
    """What I use, and what resists me."""
    # No `overflow-y-auto`: the shell does it. Two nested regions make
    # two bars, one of them tiny.
    with ui.vstack(gap="lg"):
        ui.heading("The tools", level=1)

        block(
            "Does layer 7 serve?",
            "`describe`, `check` and `probe` exist to avoid round trips. "
            "The share of tasks where they appear says whether they "
            "manage it — a tool never called avoids nothing.",
        )
        with ui.hstack(gap="md", wrap=True):
            for row in framework_usage():
                with ui.card(classes="flex-1 min-w-48"), ui.vstack(gap="xs"):
                    ui.text(row["tool"], size="sm", weight="medium")
                    ui.text(f"{row['share']} %", size="2xl", weight="bold")
                    ui.text(
                        f"{row['calls']} calls, over {row['tasks']} tasks",
                        size="xs", color="muted",
                    )

        block("Where it breaks", "Each tool's failure rate.")
        ui.table(
            columns=[
                ui.column("tool", label="Tool"),
                ui.column("calls", label="Calls", align="right"),
                ui.column("errors", label="Errors", align="right"),
                ui.column("rate", label="Rate", align="right",
                          render=percent_cell),
            ],
            rows=by_tool()[:14],
            row_key="tool",
        )

        block(
            "The replayed commands",
            "The same command re-run three times or more within a single "
            "task. A second run after a correction is normal; five are "
            "not.",
        )
        with ui.vstack(gap="xs"):
            for row in replayed():
                with ui.hstack(gap="sm", align="center"):
                    ui.badge(f"×{row['n']}", color="warning",
                             variant="soft", size="xs")
                    ui.link(f"task {row['task_id']}",
                            href=f"/task/{row['task_id']}")
                    ui.text(row["command"], size="xs", color="muted",
                            classes="flex-1 min-w-0 truncate font-mono")

        block("The latest failures", "What raised, and on what.")
        with ui.vstack(gap="xs"):
            for row in failures(30):
                with ui.hstack(gap="sm", align="center"):
                    ui.badge(row["tool"], color="error", variant="soft",
                             size="xs")
                    ui.link(f"task {row['task_id']}",
                            href=f"/task/{row['task_id']}")
                    ui.text(row["detail"] or row["command"] or "—",
                            size="xs", color="muted",
                            classes="flex-1 min-w-0 truncate font-mono")


feature = Feature(
    name="tools",
    kind="page",
    uses=["tools_data", "shell"],
    provides=[tools_page],
)
