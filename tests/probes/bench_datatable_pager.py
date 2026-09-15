"""Bench app for the datatable pagination probe (port 8969).

**Deux tables, deux `per_page` differents, une seule page** — c'est la
forme du playground, et c'est ce que la reproduction demandait : le
symptome rapporte etait « une table a 7 pages n'en affiche que 5, et la
fleche suivante se desactive a la 5e ». Or 5 pages, c'est exactement ce
que donne l'AUTRE table (34 lignes / 8 par page). Une seule table ne
peut donc pas reproduire une confusion entre deux.

Le tier callable pour les deux : c'est celui du playground, et c'est
celui ou `total` traverse la frontiere serveur a chaque requete.

Run :  py tests/probes/bench_datatable_pager.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import field
from bretzel.components import DatatableState, Query, apply_query

app = Bretzel(
    secret_key="dev-datatable-pager-bench-secret-key",
    title="Bretzel · Datatable pager bench",
    mode="dev",
)


class Seven(DatatableState):
    """34 lignes / 5 par page = 7 pages."""

    per_page: int = field(default=5)


class Five(DatatableState):
    """Les MEMES 34 lignes / 8 par page = 5 pages."""

    per_page: int = field(default=8)


ROWS = [{"id": 100 + i, "title": f"Issue {100 + i}", "score": (i * 7) % 100,
         "statut": ["open", "merged", "closed", "draft", "stale"][i % 5]}
        for i in range(34)]

COLUMNS = [
    ui.column("id", label="#", sortable=True),
    ui.column("title", label="Title", sortable=True),
    ui.column("score", label="Score", sortable=True),
]


COLUMNS_FILTRES = [
    ui.column("id", label="#", sortable=True),
    ui.column("title", label="Title", sortable=True),
    ui.column("statut", label="Status", sortable=True,
              filter=["open", "merged", "closed", "draft", "stale"]),
    ui.column("score", label="Score", sortable=True),
]


def load(q: Query) -> tuple[list, int]:
    return apply_query(ROWS, COLUMNS_FILTRES, q)


STATUSES = ["open", "merged", "closed", "draft", "stale"]


@refreshable(deps=[Seven])
def table_seven() -> None:
    # La forme EXACTE de la carte « Edge cases » du playground : dans une
    # `ui.card`, avec un filtre de colonne, une recherche, et un etat vide
    # renseigne. C'est la seule carte ou l'utilisateur a reproduit le bug.
    with ui.card():
        ui.text("per_page=5 → 7 pages", color="muted", size="sm")
        ui.datatable(
            state=Seven, columns=COLUMNS_FILTRES, rows=load,
            empty_text="No issue matches", empty_icon="search",
            empty_description="Clear the search box or widen the filter.",
        )


@refreshable(deps=[Five])
def table_five() -> None:
    with ui.card():
        ui.text("per_page=8 → 5 pages", color="muted", size="sm")
        ui.datatable(state=Five, columns=COLUMNS_FILTRES, rows=load)


# NEUF tables, comme la page /datatable du playground. C'est la seule
# difference qui restait entre un bench propre (2 tables, 1 POST par clic)
# et la page ou l'utilisateur voit DEUX POST pour un clic.
class Extra1(DatatableState): per_page: int = field(default=5)
class Extra2(DatatableState): per_page: int = field(default=5)
class Extra3(DatatableState): per_page: int = field(default=4)
class Extra4(DatatableState): per_page: int = field(default=4)
class Extra5(DatatableState): per_page: int = field(default=4)
class Extra6(DatatableState): per_page: int = field(default=6)
class Extra7(DatatableState): per_page: int = field(default=20)


def extra_zone(state):
    @refreshable(deps=[state])
    def zone() -> None:
        with ui.card():
            ui.datatable(state=state, columns=COLUMNS_FILTRES, rows=load)
    return zone


EXTRAS = [extra_zone(s) for s in
          (Extra1, Extra2, Extra3, Extra4, Extra5, Extra6, Extra7)]


def tables() -> None:
    table_seven()
    table_five()
    for z in EXTRAS:
        z()


@page("/")
def home() -> None:
    with ui.vstack(gap="xl", align="start", classes="p-8"):
        ui.text("Datatable pager bench", size="2xl", weight="bold")
        # Le lien qui compte : la navigation PARTIELLE (hx-boost) est le
        # point aveugle documente du depot — « aucune suite ne NAVIGUE ».
        # L'utilisateur arrive sur la page du playground par la barre
        # laterale, donc par ce chemin-la, jamais par un chargement dur.
        ui.link("aller sur l'autre page", href="/deux", id="vers-deux")
        tables()


@page("/deux")
def deux() -> None:
    with ui.vstack(gap="xl", align="start", classes="p-8"):
        ui.text("Page deux", size="2xl", weight="bold")
        ui.link("revenir", href="/", id="vers-un")
        tables()


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8969))
