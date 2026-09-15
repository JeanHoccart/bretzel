"""Bench app for the Select V3 probe (port 8951).

Single + multi select — Tier-1 user code only.
Run :  py tests/probes/bench_select.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-select-bench-secret-key",
    title="Bretzel · Select V3 bench",
    mode="dev",
)

COUNTRIES = ["France", "Italy", "Spain", "Germany", "Portugal"]


@page("/")
def home() -> None:
    with ui.vstack(gap="xl", align="start", classes="p-8"):
        ui.text("Select V3 bench", size="2xl", weight="bold")

        ui.text("Single", weight="semibold")
        ui.select(
            COUNTRIES, value="France", name="country",
            placeholder="Pick one", id="single",
        )

        ui.text("Multiple", weight="semibold")
        ui.select(
            COUNTRIES, multiple=True, value=["Italy"], name="countries",
            placeholder="Pick several", id="multi",
        )


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8951))
