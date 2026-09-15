"""Bench : OVERFLOWS_CONTAINER vestigial ? + Combobox open/close bullants (:8963).

Deux questions de l'audit de cohérence (2026-07-15) à trancher au
navigateur — le SSR ne peut prouver ni l'une ni l'autre :

A. Les panels ancrés (Select & co) sont repositionnés `position:fixed`
   au runtime (``helpers.floating``). Le marker ``OVERFLOWS_CONTAINER``
   — qui fait basculer la Card contenante en ``overflow-visible`` —
   protège-t-il encore quelque chose ? Trois cards :

   - ``card-plain``  : comportement courant ;
   - ``card-hidden`` : ``!overflow-hidden`` forcé ;
   - ``card-hover``  : hoverable + ``!overflow-hidden`` → le hover lift
     (``hover:-translate-y-0.5``) pose un transform, donc un containing
     block : un descendant ``fixed`` se re-ancre sur la card ET devient
     clippable par son overflow. Le cas que le marker protégerait.

B. Combobox émet ``dispatch_root_effect("open")`` mais son ``EVENTS`` ne
   déclare pas open/close : dans un ``ui.dialog(on_open=serveur)``,
   ouvrir le panel du combobox bulle-t-il un ``open`` parasite jusqu'au
   listener du dialog (POST fantôme) ?

Run :  py tests/probes/bench_overflow_card.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import PageState, field

app = Bretzel(
    secret_key="dev-overflow-card-bench-secret-key",
    title="Bretzel · Overflow card bench",
    mode="dev",
)

COUNTRIES = [
    "Italia", "Portugal", "Nederland", "Belgique", "Österreich",
    "Suisse", "Norge", "Sverige", "Danmark", "Ireland",
]


class Ev(PageState):
    log: list = field(default_factory=list)


def log_open() -> None:
    s = Ev()
    s.log = [*s.log, "open"]


def log_close() -> None:
    s = Ev()
    s.log = [*s.log, "close"]


@refreshable(deps=[Ev])
def evlog() -> None:
    s = Ev()
    with ui.vstack(gap="xs", id="evlog"):
        for i, evt in enumerate(s.log, 1):
            ui.text(f"{i}. {evt}", size="sm", classes="font-mono evt")


@page("/")
def home() -> None:
    with ui.vstack(gap="xl", align="start", classes="p-8 pb-[32rem]"):
        ui.text("Overflow card bench", size="2xl", weight="bold")

        with ui.card(id="card-plain", classes="w-80"):
            ui.select(COUNTRIES, id="sel-plain")

        with ui.card(id="card-hidden", classes="w-80 !overflow-hidden"):
            ui.select(COUNTRIES, id="sel-hidden")

        with ui.card(
            id="card-hover", hoverable=True, classes="w-80 !overflow-hidden"
        ):
            ui.select(COUNTRIES, id="sel-hover")

        # Comportement de PROD : hoverable, clipping par défaut.
        # Si le panel est mal positionné ici aussi, le containing block du
        # hover lift est un bug latent qui existe AUJOURD'HUI.
        with ui.card(id="card-hover-prod", hoverable=True, classes="w-80"):
            ui.select(COUNTRIES, id="sel-hover-prod")

        with ui.dialog(
            title="Dialog + combobox", on_open=log_open, on_close=log_close
        ) as dlg:
            ui.combobox(COUNTRIES, id="cb-in-dialog", placeholder="Pick…")
        ui.button("Open dialog", on_click=dlg.open(), id="btn-dialog")

        evlog()


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8963))
