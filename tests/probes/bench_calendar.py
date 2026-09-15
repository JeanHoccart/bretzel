"""Bench app for the Calendar / DatePicker V3 probe (port 8953).

Run :  py tests/probes/bench_calendar.py
"""

from __future__ import annotations

import datetime as dt

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-calendar-bench-secret-key",
    title="Bretzel · Calendar V3 bench",
    mode="dev",
)


@page("/")
def home() -> None:
    with ui.vstack(gap="xl", align="start", classes="p-8"):
        ui.text("Calendar V3 bench", size="2xl", weight="bold")

        ui.text("Standalone calendar", weight="semibold")
        ui.calendar(value=dt.date(2026, 6, 15), id="cal")

        ui.text("Date picker", weight="semibold")
        ui.date_picker(value=dt.date(2026, 6, 15), name="d", id="picker")


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8953))
