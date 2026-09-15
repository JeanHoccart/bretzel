"""Bench app pour le probe d'échelle Combobox / Select (port 8961).

Un multi-picker par taille, Combobox ET Select, pour mesurer que `size=`
atteint TOUT le composant (pills, chevron, panel, compteur) et pas
seulement le trigger et les options.

Run :  py tests/probes/bench_picker_size.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-picker-size-bench-secret-key",
    title="Bretzel · Picker size bench",
    mode="dev",
)

COUNTRIES = [
    "Italia", "Portugal", "Nederland", "Belgique", "Österreich",
    "Suisse", "Norge", "Sverige", "Danmark", "Ireland",
]
PICKED = ["Italia", "Portugal"]
SIZES = ("xs", "md", "xl")


@page("/")
def home() -> None:
    with ui.vstack(gap="xl", align="start", classes="p-8"):
        ui.text("Picker size bench", size="2xl", weight="bold")

        for size in SIZES:
            ui.text(f"Combobox {size}", weight="semibold")
            ui.combobox(
                COUNTRIES, multiple=True, value=list(PICKED),
                name=f"cb_{size}", size=size, bulk_actions=True,
                placeholder="Search countries…", id=f"cb-{size}",
            )

        for size in SIZES:
            ui.text(f"Select {size}", weight="semibold")
            ui.select(
                COUNTRIES, multiple=True, value=list(PICKED),
                name=f"sel_{size}", size=size, bulk_actions=True,
                id=f"sel-{size}",
            )


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8961))
