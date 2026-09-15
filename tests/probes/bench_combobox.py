"""Bench app for the Combobox V3 probe (port 8952).

Single + multi combobox with client-side filter — Tier-1 only.
Run :  py tests/probes/bench_combobox.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-combobox-bench-secret-key",
    title="Bretzel · Combobox V3 bench",
    mode="dev",
)

COUNTRIES = ["France", "Italy", "Spain", "Germany", "Portugal", "Greece"]


@page("/")
def home() -> None:
    with ui.vstack(gap="xl", align="start", classes="p-8"):
        ui.text("Combobox V3 bench", size="2xl", weight="bold")

        ui.text("Single", weight="semibold")
        ui.combobox(
            COUNTRIES, value="France", name="country",
            placeholder="Search…", id="single",
        )

        ui.text("Multiple", weight="semibold")
        ui.combobox(
            COUNTRIES, multiple=True, value=["Italy"], name="countries",
            placeholder="Search…", id="multi",
        )


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8952))
