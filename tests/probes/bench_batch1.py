"""Bench app for the batch-1 V3 ports probe (port 8948).

Exercises the interactive surface of the simple components ported in
batch 1 : Alert dismiss (bz-data/bz-show/bz-on), the imperative
command listeners of Checkbox / Switch / Input (inputs/_wiring), and
Progress reactive width/text (bz-attr:style + bz-text on a binding).

Run :  py tests/probes/bench_batch1.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui
from bretzel.state import ClientState, field

app = Bretzel(
    secret_key="dev-batch1-bench-secret-key",
    title="Bretzel · Batch 1 V3 bench",
    mode="dev",
)


class BenchUI(ClientState, persist="memory"):
    pct: int = field(default=30)


@page("/")
def home() -> None:
    state = BenchUI()
    with ui.vstack(gap="md", align="start"):
        ui.text("Batch 1 V3 bench", size="2xl", weight="bold")

        ui.alert(
            "Dismiss me with the X.",
            title="Dismissible alert",
            dismissible=True,
            id="bench-alert",
        )

        chk = ui.checkbox(label="Imperative checkbox")
        ui.button("Check it", id="btn-check", on_click=chk.set(True))

        sw = ui.switch(label="Imperative switch")
        ui.button("Toggle it", id="btn-toggle", on_click=sw.toggle())

        inp = ui.input(placeholder="imperative target", id="bench-input")
        with ui.hstack(gap="sm"):
            ui.button("Fill", id="btn-fill", on_click=inp.set("hello V3"))
            ui.button("Clear", id="btn-clear", on_click=inp.clear())

        ui.progress(value=state.pct, show_label=True, id="bench-progress")
        ui.button("Set 80%", id="btn-pct", on_click=state.pct.set(80))


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8948))
