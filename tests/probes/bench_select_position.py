"""Bench for the Select panel-positioning probe (port 8957).

Reproduces the user's report : a Select sitting in a horizontal layout
on a scrollable page. Before the fix the panel kept the V2
``absolute left-0 right-0`` anchors, so under the V3 ``floating``
(``position: fixed``) helper the leftover ``right: 0`` stretched the
panel to the viewport's right edge — it looked "tout à droite", far
wider than the trigger, and drifted left on scroll because the clamp
``Math.min(left, vw - w - 4)`` fought the oversized width.

Run :  py tests/probes/bench_select_position.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-select-pos-bench-secret-key",
    title="Bretzel · Select position bench",
    mode="dev",
)

SIZES = ["sm", "md", "lg", "xl", "2xl", "3xl", "4xl"]
WEIGHTS = ["thin", "light", "normal", "medium", "semibold", "bold"]


@page("/")
def home() -> None:
    with ui.vstack(gap="xl", align="start", classes="p-8"):
        ui.text("Select position bench", size="2xl", weight="bold")
        # Tall spacer above so the control sits mid-page and a scroll
        # genuinely moves it within the viewport.
        with ui.vstack(gap="md", classes="w-full"):
            for i in range(8):
                ui.text(f"filler row {i} — the quick brown fox jumps")
        # The two-up row the screenshot showed : a labelled Select next
        # to another control, each in a fixed-width column.
        with ui.hstack(gap="lg", align="start", classes="w-full"):
            with ui.vstack(gap="xs", classes="w-64"):
                ui.text("size", size="sm", color="muted")
                ui.select(SIZES, value="md", id="size-select")
            with ui.vstack(gap="xs", classes="w-64"):
                ui.text("weight", size="sm", color="muted")
                ui.select(WEIGHTS, value="normal", id="weight-select")
        # Tall spacer below so there's room to scroll the page down.
        with ui.vstack(gap="md", classes="w-full"):
            for i in range(20):
                ui.text(f"filler row {i} — lazy dog letter-spacing 0.05em")


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8957))
