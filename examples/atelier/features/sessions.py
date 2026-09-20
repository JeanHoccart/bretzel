"""features/sessions — page: a working window, seen from above.

The tasks screen answers "how did that one go". This one answers "is this
improving", which is the other half of the question asked — and the only
one that needs the whole history at hand.
"""

from __future__ import annotations

from bretzel import Feature, page, ui
from examples.atelier.features.phases_page import (
    SESSION_COLUMNS,
    session_rows,
)
from examples.atelier.features.shell import shell


@page("/sessions", title="Sessions", layout=shell)
def sessions_page() -> None:
    """Every session, the most recent first."""
    rows = session_rows()

    with ui.vstack(gap="lg", classes="h-full min-h-0"):
        ui.heading("The sessions", level=1)
        ui.text(
            "One row per working window. The column that counts is "
            "“mean cycles”: it is the one that says whether the "
            "method holds over time or degrades as the task grows.",
            color="muted",
        )

        if not rows:
            ui.alert(
                "The database is empty. Run "
                "`py -m examples.atelier.core.ingest` to pull in the "
                "transcripts.",
                color="info",
            )
            return

        ui.table(columns=SESSION_COLUMNS, rows=rows, row_key="id")


feature = Feature(
    name="sessions",
    kind="page",
    uses=["phases_page", "shell"],
    provides=[sessions_page],
)
