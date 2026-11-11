"""A datatable's toolbar: none without a control, and the export's URL page-free.

Until 2026-10-30 this file gated an empty ``hx-preserve`` shell sent in
place of the toolbar when a partial render could not have changed it.
The zone diff made the shell useless, then harmful (it shipped alone and
emptied the bar on the first sort); it is gone, and what
it guarded in the browser is now
``tests/runtime_js/test_a_datatable_keeps_its_toolbar.py``. What stays
here holds without it.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.components import DatatableState
from bretzel.components.data.datatable import Datatable
from bretzel.runtime import HEADER_PAGE_ID
from bretzel.server.handlers import sign_action
from bretzel.state import field
from tests._session import session_of

_SECRET = "z" * 32

ROWS = [{"id": i, "name": f"n{i}", "status": ["open", "merged", "closed"][i % 3]}
        for i in range(34)]
COLUMNS = [
    ui.column("name", label="Name", sortable=True),
    ui.column("status", label="Status", sortable=True,
              filter=["open", "merged", "closed"]),
]


class Tickets(DatatableState):
    per_page: int = field(default=5)


# ── La table EXPORTABLE ───────────────────────────────────────────────
#
# L'export exige le tier CALLABLE : le CSV doit contenir toutes les
# lignes qui matchent, donc le serveur rejoue la requête hors du rendu
# qui a produit la page — une liste n'existe plus à ce moment-là. Et un
# ``filter=True`` n'a alors plus de rows où découvrir son domaine, d'où
# le domaine explicite.


class Priced(DatatableState):
    per_page: int = field(default=5)


PRICED_COLUMNS = [
    ui.column("name", label="Name", sortable=True),
    ui.column("status", label="Status", sortable=True,
              filter=["open", "merged", "closed"]),
]


def load_priced(query):
    from bretzel.components import apply_query

    return apply_query(ROWS, PRICED_COLUMNS, query)


_app = Bretzel(secret_key=_SECRET, mode="dev")


@refreshable
def tickets_zone() -> None:
    ui.datatable(state=Tickets, columns=COLUMNS, rows=ROWS)


@page("/")
def home() -> None:
    tickets_zone()


@refreshable
def priced_zone() -> None:
    ui.datatable(state=Priced, columns=PRICED_COLUMNS, rows=load_priced,
                 exportable=True)


@page("/exportable")
def exportable_home() -> None:
    priced_zone()


_app.include(home, exportable_home)


# ── Helpers ───────────────────────────────────────────────────────────

def _page_id(html: str) -> str:
    # ``data-bz-page-id`` et pas le JSON d'``hx-headers`` : les
    # deux portent la MÊME valeur, mais l'attribut nu est stable
    # tandis que le JSON dépend de son échappement — quatre copies de
    # cette ligne ont rougi le 2026-08-28 quand ``hx-headers`` est
    # passé en doubles quotes, sans qu'aucun comportement ne change.
    match = re.search(r'data-bz-page-id="([^"]+)"', html)
    assert match, "le shell doit publier l'id de page"
    return match.group(1)


def _action(html: str, handler: str, tag: str) -> tuple[str, str]:
        # La fenêtre s'arrête au PREMIER ``>`` — la fin de la balise —
        # et non à N caractères. Une fenêtre fixe déborde sur le balisage
        # suivant : celle de 2 500 caractères posée ici au départ voyait
        # « SecondQuery » dans la queue du pager de la PREMIÈRE table et
        # rendait son action à sa place. Le test passait par chance, et a
        # rougi le jour où un octet a bougé ailleurs. Les ``>`` des
        # valeurs d'attribut sont échappés en ``&gt;``, donc le premier
        # ``>`` brut est bien la fin de la balise.
    for chunk in html.split(f"<{tag}")[1:]:
        head = chunk.split(">", 1)[0]
        if handler not in head:
            continue
        url = re.search(r'hx-post="([^"]+)"', head)
        args = re.search(r"_args&quot;: &quot;([^&]*)&quot;", head)
        if url and args:
            return url.group(1), args.group(1)
    raise AssertionError(f"pas d'action {handler!r} sur <{tag}>")


def _post(client: TestClient, url: str, args: str, page_id: str, form: dict):
    action_id = url.rsplit("/", 1)[-1]
    return client.post(
        url,
        headers={
            "X-Bz-Sig": sign_action(_app.config._action_key, action_id, args, session_id=session_of(client)),
            HEADER_PAGE_ID: page_id,
        },
        data={"_args": args, **form},
    )


def _go_to_page(client: TestClient, html: str, n: int, state: str = "Tickets"):
    # ``state`` : le nom de champ du pager est suffixé par la classe
    # d'état (``_field()``), pour que deux tables d'une même page ne
    # lisent pas la soumission l'une de l'autre. Le poster en dur ferait
    # lire ``None`` au handler, qui sortirait sans muter — donc un 204 et
    # un corps vide, ce qui ressemble beaucoup à « rien à re-rendre ».
    url, args = _action(html, "go_to_page", "input")
    return _post(client, url, args, _page_id(html),
                 {f"bz_dt_page__{state}": str(n)})


def _built(**kwargs) -> Datatable:
    """Une instance de ``Datatable``, construite dans une VRAIE zone.

    Le composant refuse de se construire hors d'un ``@refreshable`` qui
    surveille son état — c'est son garde central, et le contourner
    testerait autre chose que ce qui tourne.
    """
    box: list[Datatable] = []

    @refreshable
    def zone() -> None:
        box.append(Datatable(**kwargs))

    zone()
    return box[0]


# ── La gate ───────────────────────────────────────────────────────────


def test_the_export_query_does_not_depend_on_the_page() -> None:
    """L'URL du bouton CSV sérialise ``to_query(for_export=True)``. Si elle
    portait la page courante, elle changerait à chaque pagination — et le
    diff de zone renverrait la barre à chaque clic.

    Normaliser à 1 ne change AUCUN comportement : ``Query.offset`` rend
    déjà 0 en mode export. C'est ce qui rend le fix gratuit.
    """
    with TestClient(_app) as client:
        client.get("/")   # ouvre un contexte de rendu + un registre
        state = Tickets()
        state.page = 7
        assert state.to_query().page == 7, "la requête normale garde la page"
        assert state.to_query(for_export=True).page == 1, (
            "l'export sérialise la page courante : l'URL signée du bouton "
            "CSV change alors à chaque pagination, donc la barre d'outils "
            "n'est plus identique d'une page à l'autre et repart à chaque clic."
        )
        assert state.to_query(for_export=True).offset == 0


# ── Le cas sans barre du tout ─────────────────────────────────────────
#
# Une table qui pagine mais n'offre AUCUN contrôle : pas de recherche,
# pas de filtre, pas d'export. Elle est bien « interactive » au sens de
# ``_is_interactive`` (elle a un pager) — mais elle n'a rien à mettre
# dans une barre.


class Bare(DatatableState):
    per_page: int = field(default=5)


@refreshable
def bare_zone() -> None:
    ui.datatable(
        state=Bare,
        columns=[ui.column("name", label="Name")],
        rows=ROWS,
        search=False,
    )


@page("/bare")
def bare_home() -> None:
    bare_zone()


_app.include(bare_home)


def test_a_toolbar_with_no_control_is_not_rendered_at_all() -> None:
    """Ni barre vide au rendu complet, ni au rendu partiel : une
    ``<div>`` morte portant l'``id`` de la barre."""
    with TestClient(_app) as client:
        full = client.get("/bare").text
        assert "bzdt_Bare_toolbar" not in full, (
            "une table sans recherche, sans filtre et sans export ne doit "
            "rendre AUCUNE barre — pas même une <div> vide portant son id."
        )
        partial = _go_to_page(client, full, 3, state="Bare").text
        assert "bzdt_Bare_toolbar" not in partial, (
            "le rendu partiel envoie une barre alors que la table n'a aucun contrôle.")
        # La contre-épreuve : la pagination marche quand même.
        assert 'name="bz_dt_page__Bare"' in partial
