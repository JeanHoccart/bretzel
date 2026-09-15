"""Bench pour la sonde « mémoire de session + adresse juste » (port 8973).

Une table dont l'état est de portée ``session`` ET adressable : elle se
souvient d'un tri par-delà les navigations, donc arriver sur ``/table``
nu rend une vue triée sous une adresse qui n'en dit rien. C'est
exactement la combinaison où l'adresse mentirait sans correction.

Deux pages, parce que le sujet EST la navigation : on trie ici, on va
ailleurs, on revient.

Run :  py tests/probes/bench_url_memory.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import field
from bretzel.components import DatatableState

app = Bretzel(
    secret_key="dev-url-memory-bench-secret-key",
    title="Bretzel · URL memory bench",
    mode="dev",
)

ROWS = [{"id": i, "nom": f"n{i:02}", "score": (i * 7) % 100} for i in range(20)]
COLUMNS = [
    ui.column("nom", label="Nom", sortable=True),
    ui.column("score", label="Score", sortable=True),
]


class Remembered(DatatableState, scope="session", addressable=True):
    per_page: int = field(default=5)


@refreshable(deps=[Remembered])
def table_zone() -> None:
    ui.datatable(state=Remembered, columns=COLUMNS, rows=ROWS)


@page("/table")
def table_page() -> None:
    with ui.vstack(gap="lg", classes="p-8"):
        ui.text("Table mémorisée", size="2xl", weight="bold")
        ui.link("aller ailleurs", href="/ailleurs", id="vers-ailleurs")
        table_zone()


@page("/ailleurs")
def elsewhere() -> None:
    with ui.vstack(gap="lg", classes="p-8"):
        ui.text("Ailleurs", size="2xl", weight="bold")
        ui.link("revenir à la table", href="/table", id="vers-table")


app.include(table_page, elsewhere)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8973))
