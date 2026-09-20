"""features/task_detail — page: ONE task's strip, call by call.

The list says a task cost fifteen cycles. This screen says which ones,
and on what. It is here that the gesture reads: three reads, one write, a
suite launched, a red, a two-line write, the suite re-launched — and so
on.

⚠️ The page is routed by a parameter (``/task/{task_id}``), so it
shares: that is what allows pointing at a precise task rather than
describing it.
"""

from __future__ import annotations

from bretzel import Feature, page, ui
from examples.atelier.core.phases import (
    COLOURS,
    CYCLES_MAX,
    LABELS,
    strip_prelude,
)
from examples.atelier.features.shell import shell
from examples.atelier.features.tasks_data import calls_of, task

#: Each phase's colour. It carries the meaning on this screen: it is
#: through colour that the ping-pong shows without reading a line.
#: Imported, not copied: the legend, the list's strip and the sheet's
#: must say the SAME thing.


def call_row(call: dict) -> None:
    """A call: its phase, its tool, what it launched, its verdict."""
    with ui.hstack(gap="sm", align="center", classes="py-1"):
        ui.text(str(call["rank"]), size="xs", color="muted",
                classes="w-8 text-right font-mono")
        ui.badge(call["phase"], color=COLOURS.get(call["phase"], "muted"),
                 variant="soft", size="xs")
        ui.text(call["tool"], size="xs", weight="medium", classes="w-28")
        # ⚠️ Without the preamble. Every command in this repository
        # starts with the same 45 characters of ``cd "…/bretzel" &&``,
        # which pushed the useful verb out of the column. We already
        # strip it to CLASSIFY the call; not doing it for the display was
        # an asymmetry, not a decision.
        ui.text(strip_prelude(call["command"]) or "—", size="xs",
                color="muted", classes="flex-1 min-w-0 truncate font-mono")
        if call["error"]:
            ui.badge("error", color="error", variant="soft", size="xs")


@page("/task/{task_id}", title="Task", layout=shell)
def task_detail(task_id: int) -> None:
    """A task's complete unfolding."""
    sheet = task(task_id)
    if sheet is None:
        ui.alert("This task does not exist.", color="error")
        ui.link("Back to the rhythm", href="/")
        return

    calls = calls_of(task_id)

    with ui.vstack(gap="lg", classes="h-full min-h-0"):
        ui.link("← Back to the rhythm", href="/")
        # ⚠️ Cut: a request can be pasted code, and a three-line title
        # of `Bretzel(title=…, secret_key=…)` does not read.
        request = (sheet["request"] or "(empty request)").replace("\n", " ")
        ui.heading(
            request[:110].rstrip() + " …" if len(request) > 110 else request,
            level=2,
        )

        with ui.hstack(gap="md", wrap=True):
            ui.badge(sheet["verdict"], variant="soft",
                     color="error" if sheet["cycles"] > CYCLES_MAX
                     else "success")
            ui.text(f"{sheet['calls']} calls", size="sm", color="muted")
            ui.text(f"{sheet['cycles']} verification cycles", size="sm",
                    color="muted")
            ui.text(f"{sheet['minutes']} min", size="sm", color="muted")
            ui.text(f"{sheet['errors']} errors", size="sm", color="muted")

        with ui.card(), ui.vstack(gap="xs"):
            ui.text("The strip", size="sm", weight="medium")
            ui.text(sheet["strip"] or "—", classes="font-mono text-sm")
            ui.text(
                " · ".join(f"{letter} = {LABELS[phase]}" for phase, letter in (
                    ("reading", "R"), ("writing", "W"),
                    ("verifying", "V"), ("delivering", "D"),
                )),
                size="xs", color="muted",
            )

        # No `ui.pane`: the shell already places one, and two nested
        # regions make two scrollbars.
        with ui.vstack(gap="none"):
            for call in calls:
                call_row(call)


feature = Feature(
    name="task_detail",
    kind="page",
    uses=["tasks_data", "shell", "phases"],
    provides=[task_detail],
)
