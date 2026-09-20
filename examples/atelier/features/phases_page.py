"""features/phases_page — page: where the time goes, by phase.

One question only: **is the work split up, or mixed?** The breakdown by
phase says it in four bars, and the "unclassified" rate says how far it
can be believed.

⚠️ The share of OTHER is shown at the same rank as the others, not filed
in a footnote. It is the heuristic's admission rate: if it grows, it is
the classification that needs fixing, not the measurement that should be
believed.
"""

from __future__ import annotations

from bretzel import Feature, page, ui
from examples.atelier.core.phases import CYCLES_MAX, LABELS, OTHER
from examples.atelier.core.scope import label as scope_label
from examples.atelier.features.shell import shell
from examples.atelier.features.tasks_data import by_phase, by_scope
from examples.atelier.features.tools_data import session_profile


def cycles_cell(value, _row):
    """A session's average cycles, painted by the rule."""
    return ui.text(f"{value:.1f}", size="sm",
                   color="error" if value > CYCLES_MAX else "success")


#: Shared with the sessions screen: a single definition of what is shown
#: of a session, otherwise the two screens diverge.
SESSION_COLUMNS = [
    ui.column("short", label="Session"),
    ui.column("started", label="Start"),
    ui.column("tasks", label="Tasks", align="right"),
    ui.column("exchanges", label="Exchanges", align="right"),
    ui.column("calls", label="Calls", align="right"),
    ui.column("errors", label="Errors", align="right"),
    ui.column("cycles", label="Mean cycles", align="right",
              render=cycles_cell),
    ui.column("success", label="First time", align="right"),
]


def session_rows(limit: int | None = None) -> list[dict]:
    """The sessions, shaped for :data:`SESSION_COLUMNS`."""
    rows = session_profile()
    if limit is not None:
        rows = rows[:limit]
    return [
        {
            "id": row["id"],
            "short": row["id"][:8],
            "started": (row["started"] or "")[:16].replace("T", " "),
            "tasks": row["tasks"],
            "exchanges": row["exchanges"],
            "calls": row["calls"],
            "errors": row["errors"],
            "cycles": row["cycles"] or 0,
            "success": f"{row['first']}/{row['tasks']}",
        }
        for row in rows
    ]


COLOURS = {
    "reading": "info",
    "writing": "primary",
    "verifying": "warning",
    "delivering": "success",
    "other": "muted",
}


@page("/phases", title="Phases", layout=shell)
def phases_page() -> None:
    """The work profile, and how it changes from session to session."""
    breakdown = by_phase()

    with ui.vstack(gap="lg"):
        ui.heading("The phases", level=1)
        ui.text(
            "Every tool call is filed under a phase. It is from that "
            "classification that the strip comes, and therefore the "
            "judgement passed on each task.",
            color="muted",
        )

        with ui.vstack(gap="sm"):
            for row in breakdown:
                with ui.hstack(gap="md", align="center"):
                    ui.text(row["phase"], size="sm", weight="medium",
                            classes="w-32")
                    ui.progress(value=row["share"], max=100,
                                color=COLOURS.get(row["phase"], "muted"),
                                classes="flex-1")
                    ui.text(f"{row['share']} %", size="sm",
                            classes="w-16 text-right")
                    ui.text(f"{row['calls']} calls", size="xs",
                            color="muted", classes="w-28 text-right")
                ui.text(LABELS[row["phase"]], size="xs", color="muted",
                        classes="pl-36")

        other_share = next(
            (block["share"] for block in breakdown if block["phase"] == OTHER),
            0.0,
        )
        if other_share >= 15:
            ui.alert(
                f"{other_share} % of the calls are unclassified. Beyond a "
                "few per cent, the strip stops being believable: it is "
                "`core/phases.py`'s heuristic that needs fixing, not the "
                "measurement that should be believed.",
                color="warning",
            )

        ui.heading("By scope", level=3)
        ui.text(
            "The question asked: building the base layer requires reading "
            "it whole and verifying often — healthy work that looks like "
            "back-and-forth. An app written WITH the framework should "
            "demand almost nothing. The gap between the two rows is the "
            "useful measurement.",
            size="sm", color="muted",
        )
        ui.table(
            columns=[
                ui.column("name", label="Scope"),
                ui.column("tasks", label="Tasks", align="right"),
                ui.column("cycles", label="Mean cycles", align="right",
                          render=cycles_cell),
                ui.column("first", label="First time", align="right"),
                ui.column("surface", label="`describe` first", align="right"),
                ui.column("contract", label="`check --deep`", align="right"),
            ],
            rows=[
                {
                    "name": scope_label(r["scope"]),
                    "tasks": r["tasks"],
                    "cycles": r["cycles"] or 0,
                    "first": f"{r['first']}/{r['tasks']}",
                    "surface": f"{r['surface']}/{r['tasks']}",
                    "contract": f"{r['contract']}/{r['tasks']}",
                }
                for r in by_scope()
            ],
            row_key="name",
        )

        ui.heading("By session", level=3)
        ui.text(
            "The same measurement over time: is the rhythm improving?",
            size="sm", color="muted",
        )
        ui.table(columns=SESSION_COLUMNS, rows=session_rows(30),
                 row_key="id")


feature = Feature(
    name="phases_page",
    kind="page",
    uses=["tasks_data", "tools_data", "shell", "phases", "scope"],
    provides=[phases_page],
)
