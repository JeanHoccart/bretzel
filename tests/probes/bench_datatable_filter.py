"""Bench app for the datatable filter probe (port 8966).

Les colonnes ne sont pas choisies au hasard et ne sont pas le minimum
que le probe interroge : **c'est la table de la capture d'écran qui a
lancé ce travail** (# / Title / Status / Priority / Assignee / Score,
trois filtres et un export). Un bench dont les screenshots se comparent
directement à ce que l'utilisateur a sous les yeux vaut les deux
colonnes qu'aucune assertion ne lit — c'est précisément à ça que servent
les captures que le probe dépose.

Trois filtres, pas un : l'écart mesuré entre le DERNIER filtre et
l'export ne veut dire « pas collé au groupe » que s'il y a un groupe.

``rows=`` est un callable parce que ``exportable=True`` l'exige : le CSV
doit contenir TOUTES les lignes filtrées, donc le serveur doit pouvoir
rejouer la requête hors du rendu qui a produit la page. Effet de bord
utile — les domaines sont déclarés (``filter=STATUSES``) au lieu d'être
dérivés, ce que le tier callable impose de toute façon, et qui évite un
balayage de toutes les lignes par colonne filtrable à chaque rendu.

Ce que le probe mesure : cf. ``probe_datatable_filter.py``.

Run :  py tests/probes/bench_datatable_filter.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import field
from bretzel.components import DatatableState, Query, apply_query

app = Bretzel(
    secret_key="dev-datatable-filter-bench-secret-key",
    title="Bretzel · Datatable filter bench",
    mode="dev",
)


class Issues(DatatableState):
    per_page: int = field(default=8)


STATUSES = ["open", "merged", "closed", "draft", "stale"]
PRIORITIES = ["low", "medium", "high"]
ASSIGNEES = ["ada", "grace", "lise", "alan"]

ROWS = [
    {
        "id": i,
        "title": f"Issue {i}",
        "status": STATUSES[i % len(STATUSES)],
        "priority": PRIORITIES[i % len(PRIORITIES)],
        "assignee": ASSIGNEES[i % len(ASSIGNEES)],
        "score": (i * 7) % 100,
    }
    for i in range(34)
]

COLUMNS = [
    ui.column("id", label="#", sortable=True),
    ui.column("title", label="Title", sortable=True),
    ui.column("status", label="Status", sortable=True, filter=STATUSES),
    ui.column("priority", label="Priority", sortable=True, filter=PRIORITIES),
    ui.column("assignee", label="Assignee", filter=ASSIGNEES),
    ui.column("score", label="Score", sortable=True),
]


def load_rows(q: Query) -> tuple[list, int]:
    """Le tier callable — celui qu'exige ``exportable=True``."""
    return apply_query(ROWS, COLUMNS, q)


@refreshable(deps=[Issues])
def issues_table() -> None:
    # DEUX enfants directs, a dessein : c'est la branche WRAP de
    # `fuse_or_wrap`, celle qui emet une enveloppe `display:contents`.
    # Avec un seul enfant la zone se fusionne et n'emet aucune div, donc
    # le probe ne verrait jamais l'enveloppe, ni ne pourrait verifier
    # qu'un swap HTMX atterrit encore sur un element sans boite (ce que
    # la mesure 6b fait, APRES plusieurs allers-retours).
    ui.text("Issues — un filtre par colonne, appliqué à la fermeture.",
            id="caption", color="muted", size="sm")
    ui.datatable(
        state=Issues, columns=COLUMNS, rows=load_rows,
        exportable=True, export_filename="issues.csv", id="dt",
    )


@page("/")
def home() -> None:
    with ui.vstack(gap="xl", align="start", classes="p-8"):
        ui.text("Datatable filter bench", size="2xl", weight="bold")
        issues_table()


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8966))
