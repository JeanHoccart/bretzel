"""core/ui — the interface bricks shared BY the app.

A single inhabitant for now: the KPI card. It lived in five copies — four
identical and one divergent — before being moved up here, which is
exactly the story of ``examples/mad/core/ui.py``, whose docstring says it
exists "because the KPI card lived in duplicate".

It is not a dumping ground: if it grows, it is holding a feature that has
not been named (cf. ``app-structure.md`` § 6).
"""

from __future__ import annotations

from bretzel import ui


def kpi(label: str, value: str, icon: str, color: str) -> None:
    """The app's key-figure card: icon pill, label, value.

    A single template for the five rows that place one (accounts, account
    sheet, activities, reports) — otherwise two neighbouring KPI rows
    show at different heights and weights, for no reason.
    """
    with ui.card(padding="md"):
        with ui.hstack(gap="md", align="center"):
            with ui.flex(align="center", justify="center",
                         classes="w-10 h-10 rounded-lg bg-text/5 shrink-0"):
                ui.icon(icon, color=color)
            with ui.vstack(gap="none"):
                ui.text(label, color="muted", size="xs")
                ui.heading(value, level=3, size="lg")
