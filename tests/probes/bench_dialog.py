"""Bench app for the Dialog V3 Playwright probe (port 8946).

Tier-1 user code only : imperative API (`dlg.open()` / `dlg.close()`),
zero manual name=/attrs. Run :

    py tests/probes/bench_dialog.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-dialog-bench-secret-key",
    title="Bretzel · Dialog V3 bench",
    mode="dev",
)


@page("/")
def home() -> None:
    with ui.vstack(gap="md", align="start"):
        ui.text("Dialog V3 bench", size="2xl", weight="bold")
        with ui.dialog(title="Confirm action") as dlg:
            ui.text("Are you sure? This cannot be undone.")
            with ui.hstack(gap="sm", justify="end"):
                ui.button("Cancel", variant="ghost", on_click=dlg.close())
                ui.button("Confirm", color="error", on_click=dlg.close())
        ui.button("Open dialog", id="trigger", on_click=dlg.open())
        with ui.dialog(title="Stubborn", persistent=True) as stubborn:
            ui.text("No escape, no backdrop click.")
            ui.button("Close me", id="stubborn-close", on_click=stubborn.close())
        ui.button("Open persistent", id="trigger-persistent", on_click=stubborn.open())
        # Tall filler so the scroll lock is observable.
        for i in range(40):
            ui.text(f"Filler line {i}")


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8946))
