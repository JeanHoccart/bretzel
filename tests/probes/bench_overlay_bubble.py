"""Banc — un `close`/`open` d'overlay IMBRIQUÉ fuit-il vers l'ancêtre ?

Port 8946 est pris par `bench_dialog` : celui-ci vit sur **8968**.

Trois dialogs, chacun avec `on_open=` / `on_close=` serveur, chacun
contenant un émetteur d'un mécanisme DIFFÉRENT :

- ``racine`` — un ``ui.select`` : ``_dispatch_arm`` fire ``open``/``close``
  SUR la racine de l'overlay (``dispatch_root_effect``) ;
- ``enfant`` — un ``ui.alert(dismissible=True)`` : le ``×`` est un
  DESCENDANT, son ``$dispatch('close')`` doit remonter jusqu'à sa propre
  racine — et ne devrait pas aller plus loin ;
- ``témoin`` — rien dedans : le dialog seul, pour la ligne de base.

Chaque handler serveur pousse une ligne dans le log, donc un POST
fantôme se voit ET se compte.

Lancer :  py tests/probes/bench_overlay_bubble.py   (port 8968)
"""

from __future__ import annotations

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import PageState, field

app = Bretzel(
    secret_key="dev-overlay-bubble-bench-secret-key",
    title="Bretzel · overlay bubble bench",
    mode="dev",
)

COUNTRIES = ["France", "Italy", "Spain", "Portugal"]


class Ev(PageState):
    log: list = field(default_factory=list)


def log_root_open() -> None:
    Ev().log.append("root:open")


def log_root_close() -> None:
    Ev().log.append("root:close")


def log_child_open() -> None:
    Ev().log.append("child:open")


def log_child_close() -> None:
    Ev().log.append("child:close")


def log_witness_open() -> None:
    Ev().log.append("witness:open")


def log_witness_close() -> None:
    Ev().log.append("witness:close")


@refreshable(deps=[Ev])
def evlog() -> None:
    with ui.vstack(gap="xs", id="evlog"):
        for i, evt in enumerate(Ev().log, 1):
            ui.text(f"{i}. {evt}", size="sm", classes="font-mono evt")


@page("/")
def home() -> None:
    with ui.vstack(gap="xl", align="start", classes="p-8"):
        ui.text("Overlay bubble bench", size="2xl", weight="bold")

        # A — l'émetteur dispatche sur SA PROPRE racine.
        with ui.dialog(
            title="root emitter", on_open=log_root_open, on_close=log_root_close
        ) as dlg_root:
            ui.select(COUNTRIES, id="sel-in-root")
        ui.button("open root", on_click=dlg_root.open(), id="btn-root")

        # B — l'émetteur est un DESCENDANT de sa propre racine.
        with ui.dialog(
            title="child emitter", on_open=log_child_open, on_close=log_child_close
        ) as dlg_child:
            ui.alert("Dismiss me", dismissible=True, id="alert-in-child")
        ui.button("open child", on_click=dlg_child.open(), id="btn-child")

        # C — témoin : rien à l'intérieur.
        with ui.dialog(
            title="witness",
            on_open=log_witness_open,
            on_close=log_witness_close,
        ) as dlg_witness:
            ui.text("nothing inside", id="witness-body")
        ui.button("open witness", on_click=dlg_witness.open(), id="btn-witness")

        evlog()


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8968))
