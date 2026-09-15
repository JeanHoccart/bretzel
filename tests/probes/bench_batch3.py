"""Bench app for the batch-3 (scoped) V3 ports probe (port 8950).

Tabs, ToggleGroup, Accordion, Pagination, Slider, NumberInput.
(Sidebar lives in a layout shell — probed separately via its own page.)

Run :  py tests/probes/bench_batch3.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-batch3-bench-secret-key",
    title="Bretzel · Batch 3 V3 bench",
    mode="dev",
)


@page("/")
def home() -> None:
    with ui.vstack(gap="xl", align="start", classes="p-8"):
        ui.text("Batch 3 (scoped) V3 bench", size="2xl", weight="bold")

        # Tabs — sliding indicator
        with ui.tabs(value="one", id="bench-tabs"):
            ui.tab("one", label="One")
            ui.tab("two", label="Two")
            ui.tab("three", label="Three")
            with ui.tab_panel("one"):
                ui.text("Panel one content", id="panel-one")
            with ui.tab_panel("two"):
                ui.text("Panel two content", id="panel-two")
            with ui.tab_panel("three"):
                ui.text("Panel three content", id="panel-three")

        # ToggleGroup — segmented
        ui.toggle_group(
            options=[("Day", "Day"), ("Week", "Week"), ("Month", "Month")],
            value="Day",
            id="bench-toggle",
        )

        # Accordion
        with ui.accordion(value="a", id="bench-accordion"):
            with ui.accordion_item("a", label="Section A"):
                ui.text("Body A", id="acc-body-a")
            with ui.accordion_item("b", label="Section B"):
                ui.text("Body B", id="acc-body-b")

        # Pagination
        ui.pagination(value=1, total_pages=10, id="bench-pagination")

        # Slider
        ui.slider(value=40, min=0, max=100, id="bench-slider")

        # NumberInput
        ui.number_input(value=5, min=0, max=20, id="bench-number")

        # Sidebar — collapse via imperative toggle
        sb = ui.sidebar(collapsible="rail", id="bench-sidebar")
        with sb:
            ui.sidebar_item("Home", icon="home", href="/")
            ui.sidebar_item("Settings", icon="settings", href="/settings")
        ui.button("Collapse sidebar", id="sb-toggle", on_click=sb.toggle())


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8950))
