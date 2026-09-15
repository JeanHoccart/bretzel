"""Isolate : tooltip inside a @refreshable, across a refresh (:8977)."""

from __future__ import annotations

from bretzel import Bretzel, page, refresh, refreshable, ui
from bretzel.state import SessionState, field

app = Bretzel(secret_key="dev-tipiso-secret-key-32-bytes-xx", mode="dev")


class S(SessionState):
    n: int = field(default=0)


def bump() -> None:
    S().n += 1
    refresh(zone)


@refreshable
def zone() -> None:
    with ui.vstack(gap="md"):
        ui.text(f"n={S().n}")
        ui.icon_button("home", tooltip="ICONTIP")


@page("/")
def home() -> None:
    with ui.vstack(gap="xl", align="start", classes="p-16"):
        ui.button("refresh", id="refresh", on_click=bump)
        zone()


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8977))
