"""Bench for the Slider factory-refactor probe (port 8965).

Slider's drag/keyboard/clamp/snap/range logic moved to the shared
``$bz.slider.scope`` runtime factory. This bench exercises single,
range, and ClientBinding modes so the probe can confirm identical
behaviour.

Run :  py tests/probes/bench_slider.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui
from bretzel.state import ClientState, field

app = Bretzel(
    secret_key="dev-slider-bench-secret-key",
    title="Bretzel · Slider bench",
    mode="dev",
)


class Form(ClientState, persist="memory"):
    vol: float = field(default=40.0)


@page("/")
def home() -> None:
    f = Form()
    with ui.vstack(gap="xl", align="start", classes="p-10 w-[480px]"):
        ui.text("Slider bench", size="2xl", weight="bold")

        ui.text("single, min0 max100 step10, value 50")
        ui.slider(value=50, min=0, max=100, step=10, id="sl-single")

        ui.text("range [20, 80]")
        ui.slider(value=[20, 80], range=True, min=0, max=100, step=5,
                  id="sl-range")

        ui.text("client-bound (vol)")
        ui.slider(value=f.vol, min=0, max=100, step=10, id="sl-bound")
        ui.text(f.vol, id="bound-readout")

        ui.text("disabled (value 40, must NOT move)")
        ui.slider(value=40, min=0, max=100, step=10, disabled=True,
                  id="sl-disabled")


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8965))
