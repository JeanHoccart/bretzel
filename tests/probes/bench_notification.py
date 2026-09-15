"""Bench app for the Notification V3 probe (port 8955).

A button fires a server handler that calls ui.notification(...) — the
toast must appear via the <bz-patch> -> bz:notify -> toaster path.

Run :  py tests/probes/bench_notification.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-notification-bench-secret-key",
    title="Bretzel · Notification V3 bench",
    mode="dev",
)


def fire_success() -> None:
    ui.notification("Saved successfully!", variant="success", title="Done")


def fire_error() -> None:
    ui.notification(
        "Something went wrong.", variant="error", position="bottom-right",
        duration_ms=0,  # persistent
    )


@page("/")
def home() -> None:
    with ui.vstack(gap="md", align="start", classes="p-8"):
        ui.text("Notification V3 bench", size="2xl", weight="bold")
        ui.button("Fire success toast", id="btn-success", on_click=fire_success)
        ui.button("Fire error toast", id="btn-error", on_click=fire_error)


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8955))
