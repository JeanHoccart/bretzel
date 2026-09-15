"""Bench for the multi-combobox panel-stretch fix (port 8967)."""
from __future__ import annotations
from bretzel import Bretzel, page, ui
app = Bretzel(secret_key="dev-combobox-width-bench-secret-key", mode="dev")
COUNTRIES = [("c%d" % i, "Country %d very long name here" % i) for i in range(29)]
@page("/")
def home() -> None:
    with ui.vstack(gap="lg", align="start", classes="p-8"):
        ui.text("multi-combobox, all selected, in w-96 container")
        with ui.vstack(classes="w-96"):
            ui.combobox(COUNTRIES, multiple=True, bulk_actions=True,
                        value=[k for k, _ in COUNTRIES],
                        placeholder="Search…", id="cb")
app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8967))
