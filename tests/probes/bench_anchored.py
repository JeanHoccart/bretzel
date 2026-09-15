"""Bench app for the anchored overlays V3 probe (port 8949).

Popover, Dropdown, Tooltip — Tier-1 user code only.
Run :  py tests/probes/bench_anchored.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-anchored-bench-secret-key",
    title="Bretzel · Anchored V3 bench",
    mode="dev",
)


@page("/")
def home() -> None:
    with ui.vstack(gap="xl", align="start", classes="p-24"):
        ui.text("Anchored overlays V3 bench", size="2xl", weight="bold")

        # Popover
        with ui.popover(
            trigger=ui.button("Open popover", id="pop-trigger"),
            position="bottom",
        ):
            ui.text("Popover panel content.", id="pop-content")

        # Dropdown
        with ui.dropdown(
            trigger=ui.button("Open menu", id="dd-trigger"),
            position="bottom",
        ):
            ui.dropdown_item(label="Edit", id="dd-edit")
            ui.dropdown_item(label="Duplicate", id="dd-dup")
            ui.dropdown_item(label="Delete", color="error", id="dd-del")

        # Tooltip
        with ui.tooltip("Tooltip text here", position="bottom", delay=0):
            ui.button("Hover me", id="tip-trigger")


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8949))
