"""Bench for the NumberInput factory-refactor probe (port 8963).

NumberInput's client logic moved from inline bz-data to the shared
``$bz.numberInput.scope`` runtime factory. This bench exercises both
modes (local + ClientBinding) so the probe can confirm behaviour is
byte-for-byte identical : nudge, clamp, snap, precision, binding sync.

Run :  py tests/probes/bench_number_input.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui
from bretzel.state import ClientState, field

app = Bretzel(
    secret_key="dev-number-input-bench-secret-key",
    title="Bretzel · NumberInput bench",
    mode="dev",
)


class Form(ClientState, persist="memory"):
    qty: float = field(default=3.0)


@page("/")
def home() -> None:
    f = Form()
    with ui.vstack(gap="lg", align="start", classes="p-8 w-96"):
        ui.text("NumberInput bench", size="2xl", weight="bold")

        ui.text("local, min0 max10 step1, value 5")
        ui.number_input(value=5, min=0, max=10, step=1, id="ni-basic")

        ui.text("precision step 0.1, value 0")
        ui.number_input(value=0, step=0.1, id="ni-prec")

        ui.text("client-bound (qty)")
        ui.number_input(value=f.qty, min=0, max=99, step=1, id="ni-bound")
        ui.text(f.qty, id="bound-readout")


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8963))
