"""features/accounts — écran 2 : les comptes, 50 000 lignes, mode callable.

Ce que cet écran met sous contrainte : ``ui.datatable`` avec un ``rows=``
**callable**. Tri, recherche, filtres de colonne et export CSV sont traduits
en SQL par :func:`~examples.crm.features.accounts_data.load_accounts` ; la
page ne charge jamais plus de vingt lignes.

Deux choses que le tier liste n'exige pas et que celui-ci impose :

- le domaine de chaque filtre est **déclaré** (``filter=[…]``) — le composant
  ne détient aucune ligne pour le dériver, et lève si on lui passe
  ``filter=True`` ;
- ``exportable=True`` **exige** le tier callable, parce que le CSV rejoue la
  requête hors du rendu qui a jeté les lignes.
"""

from __future__ import annotations

from bretzel import (
    Feature,
    page,
    refreshable,
    ui,
)
from bretzel.state import field
# ``DatatableState`` s'importe depuis ``bretzel.components``, pas depuis
# ``bretzel`` : le fichier est descendu dans ``bretzel/state/`` mais la
# PORTE est restée celle du composant (6baaf918). Les deux autres sites
# du dépôt qui l'utilisent — ``crm/features/import_screen.py`` et
# ``playground/features/datatable.py`` — l'écrivaient déjà comme ça.
from bretzel.components import DatatableState
from examples.crm.core.domain import (
    COUNTRY_KEYS,
    INDUSTRIES,
    OWNERS,
    SIZES,
    euros,
)
from examples.crm.core.ui import kpi
from examples.crm.features.access import ViewerPrefs, visible_owner
from examples.crm.features.accounts_data import accounts_summary, load_accounts
from examples.crm.features.shell import shell


class AccountsTable(DatatableState, scope="session", addressable=True):
    """La requête de CETTE table. Une sous-classe par table : les états sont
    clés par classe, donc partager la base ferait partager tri et page.

    ``addressable=True`` : **la vue a une adresse.** Trier, paginer ou
    chercher réécrit l'URL, donc le lien se partage, se met en favori, et
    les flèches du navigateur font l'aller-retour. Les noms viennent de
    ``DatatableState`` (``tri`` / ``sens`` / ``p`` / ``q``) ; un
    ``URL = {…}`` les renommerait.

    ``filters`` n'est PAS de la partie, et le socle le garantit — il n'a
    pas de nom d'URL, donc l'opt-in ne peut pas l'allumer. Le tri d'une
    liste de comptes n'a rien de sensible ; les filtres posés sur un
    portefeuille client, si.
    """

    per_page: int = field(default=25)
    sort_key: str = field(default='name')


def arr_cell(value, _row):
    return ui.text(euros(value), weight="medium")


def size_cell(value, _row):
    colors = {"TPE": "muted", "PME": "info", "ETI": "primary",
              "Grand compte": "success"}
    return ui.badge(value, color=colors.get(value, "muted"), variant="soft",
                    size="xs")


def name_cell(value, row):
    """Le nom du compte, en LIEN vers sa fiche.

    ⚠️ Un lien, pas un ``on_item_click=`` qui redirige. Les deux ouvrent
    la fiche et ils ne naviguent pas pareil : l'action fait répondre
    ``HX-Redirect``, qu'htmx applique en ``window.location`` — le
    document est détruit, la coque repeinte, en deux requêtes. Mesuré le
    2026-09-12 sur ``examples/atelier`` : un témoin posé sur ``window``
    avant le clic n'y survivait pas. Un ``<a>`` passe par le
    ``hx-boost`` de la coque : une requête, seule la région change.

    C'est ce que dit la docstring de :func:`bretzel.redirect` — « pour
    un menu, une ligne cliquable, un fil d'Ariane, la navigation reste
    un ``ui.link`` ». Elle réserve ``redirect()`` aux adresses qui
    n'existent qu'APRÈS une mutation.
    """
    return ui.link(value, href=f"/comptes/{row['id']}", variant="hover")


COLUMNS = [
    ui.column("name", label="Compte", sortable=True, render=name_cell),
    ui.column("industry", label="Secteur", sortable=True,
              filter=list(INDUSTRIES)),
    ui.column("country", label="Pays", sortable=True,
              filter=list(COUNTRY_KEYS)),
    ui.column("city", label="Ville", sortable=True),
    ui.column("size", label="Taille", sortable=True, filter=list(SIZES),
              render=size_cell),
    ui.column("arr", label="ARR", sortable=True, align="right",
              render=arr_cell),
    ui.column("owner", label="Propriétaire", sortable=True,
              filter=list(OWNERS)),
]


def columns_for(owner: str | None) -> list:
    """Les colonnes de la table, selon le cadrage.

    ⚠️ La colonne « Propriétaire » perd son filtre quand on est cadré :
    cinq de ses six valeurs rendraient zéro ligne et la sixième ne ferait
    rien. C'est le même raisonnement que les trois sélecteurs retirés
    ailleurs — un contrôle qui ne peut prendre qu'une valeur légale n'est
    pas un contrôle — mais il se voyait moins ici, parce que l'affordance
    est une donnée dans une constante, pas un ``ui.select`` dans un corps
    de fonction.
    """
    if owner is None:
        return COLUMNS
    return [c for c in COLUMNS if c.key != "owner"]


# Une seule dep : l'écran 2 ne fait que LIRE. Un jeton de révision déclaré
# ici serait un chemin de réactivité qui n'existe pas — le prochain lecteur
# le recopierait sur une table qui écrit et croirait le bump automatique.
def scoped_rows(q):
    """Le ``rows=`` que la datatable appelle, cadré au portefeuille.

    ⚠️ Le composant appelle son callable avec le SEUL ``Query`` — il n'a
    aucune façon de lui passer un contexte. Un repo cadré prend donc un
    paramètre de plus, et l'écran doit fournir cette fermeture. C'est le
    prix du choix « le cadrage est un paramètre » (cf. ``access.py``), et
    il est payé ici, une fois, visiblement.
    """
    return load_accounts(q, visible_owner())


# ``ViewerPrefs`` dans les ``deps`` : sans lui, changer de portefeuille
# dans la barre latérale laisserait la zone sur la donnée de l'ancien.
@refreshable(deps=[AccountsTable, ViewerPrefs])
def accounts_table() -> None:
    ui.datatable(
        state=AccountsTable,
        columns=columns_for(visible_owner()),
        rows=scoped_rows,
        search_placeholder="Nom, ville, secteur, propriétaire…",
        exportable=True,
        export_filename="comptes.csv",
        max_height="calc(100vh - 20rem)",
        row_key="id",
    )


def summary_header() -> None:
    scope = visible_owner()
    stats = accounts_summary(scope)
    with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
        kpi("Comptes", f"{stats['total']:,}".replace(",", " "),
            "building-2", "primary")
        kpi("ARR cumulé", euros(stats["arr"]), "banknote", "success")
        kpi("Propriétaires", "1" if scope else str(len(OWNERS)),
            "user-round", "info")


@page("/comptes", layout=shell, title="Comptes")
def accounts_page() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("Comptes", level=1, size="2xl")
        summary_header()
        accounts_table()


feature = Feature(
    name="accounts",
    kind="page",
    provides=[accounts_page, AccountsTable],
    uses=["accounts_data", "access"],
)
