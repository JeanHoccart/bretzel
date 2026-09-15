"""Bench app for the Drawer V3 Playwright probe (port 8947).

Tier-1 user code only. Run :  py tests/probes/bench_drawer.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-drawer-bench-secret-key",
    title="Bretzel · Drawer V3 bench",
    mode="dev",
)


@page("/")
def home() -> None:
    with ui.vstack(gap="md", align="start"):
        ui.text("Drawer V3 bench", size="2xl", weight="bold")
        for side in ("left", "right", "top", "bottom"):
            with ui.drawer(title=f"Drawer {side}", side=side) as drw:
                ui.text(f"Content of the {side} drawer.")
                ui.button(f"Close {side}", on_click=drw.close())
            ui.button(f"Open {side}", id=f"trigger-{side}", on_click=drw.open())
        for i in range(40):
            ui.text(f"Filler line {i}")


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8947))
