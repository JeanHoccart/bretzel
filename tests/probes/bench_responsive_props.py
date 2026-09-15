"""Bench app for the responsive-props probe (port 8996).

``direction=`` / ``gap=`` given a ``{breakpoint: value}`` dict must not
just SERIALIZE the right classes — Tailwind has to compile them and the
browser has to flip at the right width. That is what the probe measures.

Tier-1 user code only. Run :  py tests/probes/bench_responsive_props.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-responsive-props-bench-secret-key",
    title="Bretzel · responsive props bench",
    mode="dev",
)


@page("/", title="Responsive props bench")
def home() -> None:
    with ui.vstack(gap="md", align="start"):
        ui.heading("Responsive props bench", level=2)

        # Stacked below md, side-by-side from md up — the canonical case.
        with ui.flex(
            direction={"base": "col", "md": "row"},
            gap={"base": "sm", "md": "xl"},
            id="flex-responsive",
        ):
            ui.text("panel A")
            ui.text("panel B")

        # Scalar control : must NOT move with the viewport.
        with ui.flex(direction="row", gap="md", id="flex-scalar"):
            ui.text("fixed A")
            ui.text("fixed B")

        # Grid, both graded props at once.
        with ui.grid(cols={"base": 1, "md": 3}, gap={"base": "sm", "md": "xl"}, id="grid-responsive"):
            ui.text("cell 1")
            ui.text("cell 2")
            ui.text("cell 3")

        # The shortcut inherits the responsive gap (but not direction).
        with ui.vstack(gap={"base": "none", "lg": "xl"}, id="vstack-responsive"):
            ui.text("row 1")
            ui.text("row 2")


app.include(home)


if __name__ == "__main__":
    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    app.run(port=bench_port(8996))
