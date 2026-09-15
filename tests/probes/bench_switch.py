"""Bench : switch centering across all sizes (:8977).

Run :  py tests/probes/bench_switch.py
"""

from __future__ import annotations

import examples.playground.main  # noqa: F401
from bretzel import Bretzel, page, ui
from bretzel.components.base import SIZE_SCALE

app = Bretzel(
    secret_key="dev-switch-bench-secret-key",
    title="Bretzel · switch bench",
    mode="dev",
)


@page("/")
def home() -> None:
    with ui.vstack(gap="lg", classes="p-12 min-h-screen bg-background"):
        ui.heading("Switch — thumb centering", level=2)
        for size in SIZE_SCALE:
            with ui.hstack(gap="xl", align="center"):
                ui.text(size, color="muted", classes="w-10 font-mono")
                ui.switch(checked=False, size=size, label="off")
                ui.switch(checked=True, size=size, label="on")
        ui.heading("style= lands on the visible root", level=3)
        ui.switch(checked=True, size="lg", label="styled",
                  style="outline: 3px dashed orange")


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8977))
