"""Bench : boot cost on a DENSE page — attribute the 'load' handler.

Replicates a heavy playground page (~50 interactive components, lots of
``bz-data`` scopes + directives) so we can measure where the boot time
goes. Toggled by env so the probe can compare the two regimes :

  BENCH_DEBUG=1 (default) → in-browser Tailwind compiler runs (debug)
  BENCH_DEBUG=0           → no Tailwind-in-browser (prod-like) ; the
                            ``$bz._scan`` boot cost is IDENTICAL, so the
                            delta isolates the Tailwind compile.

Run :  py tests/probes/bench_load_perf.py
"""

from __future__ import annotations

import os

from bretzel import Bretzel, page, ui

DEBUG = os.environ.get("BENCH_DEBUG", "1") == "1"

app = Bretzel(
    secret_key="dev-load-perf-bench-secret-key",
    title="Bretzel · load perf bench",
    debug=DEBUG,
)

OPTIONS = ["Apple", "Banana", "Cherry", "Date", "Fig"]


@page("/")
def home() -> None:
    with ui.vstack(gap="md", align="start", classes="p-8 w-[900px]"):
        ui.text("load perf bench (dense)", size="2xl", weight="bold")
        # ~10 of each → ~50 interactive components, each a bz-data scope.
        for i in range(10):
            with ui.hstack(gap="md", align="center"):
                ui.number_input(value=float(i), min=0, max=100, step=1,
                                id=f"ni{i}")
                ui.slider(value=float(i * 10), min=0, max=100, step=10,
                          id=f"sl{i}")
                ui.select(OPTIONS, value=OPTIONS[i % len(OPTIONS)],
                          placeholder="Pick", id=f"se{i}")
                ui.combobox(OPTIONS, value=OPTIONS[i % len(OPTIONS)],
                            placeholder="Search", id=f"cb{i}")
                ui.switch(value=bool(i % 2), id=f"sw{i}")


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8971))
