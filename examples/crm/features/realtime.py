"""features/realtime — écran 11 : ce qu'un autre onglet fait arriver ici.

Ce que cet écran met sous contrainte : le **SSE**. Une zone
``@refreshable(deps=[DealsRev, ViewerPrefs], broadcast=[DealsRev])`` :
deux dépendances, une seule diffusée — le pipeline est global, le
portefeuille regardé est personnel. Quand le pipeline écrit
dans un onglet, `DealsRev` bouge, et le socle pousse un signal aux AUTRES
onglets, qui refont leur requête. Aucune ligne de JavaScript ici, aucune
URL — la zone porte son `data-bz-subscribe-url`, le runtime la lit.

**Le test à faire à deux onglets** : ouvrir cette page à gauche, le pipeline
à droite, glisser une carte. Les chiffres de gauche bougent sans qu'on les
touche. Un onglet seul ne prouve rien — il aurait de toute façon re-rendu
sa propre zone.

``LiveConnection().connected`` est l'état de la connexion, tenu par le runtime et
lu ici : c'est un ``ClientState``, donc l'afficher ne coûte pas une zone —
la valeur redescend dans un patch et le navigateur écrit dans le nœud.
"""

from __future__ import annotations

from bretzel import Feature, LiveConnection, page, refreshable, ui
from examples.crm.core.domain import (
    OPEN_STAGES,
    STAGE_COLOR,
    STAGE_LABEL,
    euros,
)
from examples.crm.core.ui import kpi
from examples.crm.features.access import ViewerPrefs, visible_owner
from examples.crm.features.deals_data import (
    DealsRev,
    column_heads,
    live_board,
)
from examples.crm.features.shell import shell


@refreshable(deps=[DealsRev, ViewerPrefs], broadcast=[DealsRev])
def board_pulse() -> None:
    """L'état du pipeline, tous porteurs confondus — poussé aux autres onglets.

    Deux dépendances, **une seule diffusée**, et c'est tout le sujet :

    - ``DealsRev`` est une propriété de la BASE. Deux onglets ouverts
      doivent voir le même chiffre, et celui qui n'a rien fait doit
      bouger aussi — donc il est diffusé ;
    - ``ViewerPrefs`` est le portefeuille que CETTE direction regarde.
      Il re-rend la zone ici, et il n'a rien à faire chez les autres.

    ⚠️ Cette écriture n'existait pas avant le 2026-08-23. ``broadcast``
    était un booléen, donc ``deps`` servait deux rôles à la fois : ajouter
    ``ViewerPrefs`` aurait fait refetcher le monde entier dès qu'une seule
    personne change SON réglage. La zone ne suivait donc pas le changement
    de portefeuille — pas par oubli, faute de pouvoir l'écrire.
    """
    rows = live_board(visible_owner())
    total = sum(r["total"] or 0 for r in rows.values())
    with ui.vstack(gap="md"):
        with ui.grid(cols={"base": 2, "md": 4}, gap="md"):
            for stage in OPEN_STAGES:
                row = rows.get(stage, {})
                kpi(f"{STAGE_LABEL[stage]} · {row.get('n', 0)}",
                    euros(row.get("total") or 0), "folder-open",
                    STAGE_COLOR[stage])
        with ui.hstack(justify="between", align="center"):
            ui.text("Total ouvert", color="muted", size="sm")
            ui.heading(euros(total), level=3, size="md")


@refreshable(deps=[DealsRev, ViewerPrefs], broadcast=[DealsRev])
def recent_moves() -> None:
    """Les dix affaires en tête de leurs colonnes, dans l'ordre du kanban.

    C'est la liste qui bouge quand quelqu'un réordonne : le rang est la
    seule chose que le glisser-déposer écrit, donc la seule qui témoigne.

    Même partage que ``board_pulse`` : le rang est global et se diffuse,
    le portefeuille regardé est personnel et reste ici.
    """
    rows = column_heads(visible_owner(), limit=12)
    with ui.vstack(gap="sm"):
        ui.heading("En tête de colonne", level=2, size="md")
        if not rows:
            ui.text("Aucune affaire ouverte.", color="muted", size="sm")
        for row in ui.each(rows, key="id"):
            with ui.card(padding="sm"), ui.hstack(gap="sm", align="center"):
                ui.badge(STAGE_LABEL[row["stage"]],
                         color=STAGE_COLOR[row["stage"]], variant="soft",
                         size="xs")
                with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                    ui.text(row["account_name"], size="sm",
                            weight="medium", truncate=True)
                    ui.text(f"{row['name']} · {row['owner']}",
                            color="muted", size="xs", truncate=True)
                ui.text(euros(row["amount"]), color="muted", size="xs")


def connection_badge() -> None:
    """L'état de la connexion SSE, lié — donc sans zone.

    S'il était une zone ``@refreshable``, il ajouterait du HTML à chacune
    des réponses qu'il prétend décrire.
    """
    live = LiveConnection()
    with ui.hstack(gap="sm", align="center"):
        ui.icon("radio", color="success", size="sm",
                visible=live.connected)
        ui.icon("radio", color="muted", size="sm",
                visible=~live.connected)
        ui.text("Flux temps réel", color="muted", size="sm")


@page("/temps-reel", layout=shell, title="Temps réel")
def realtime_page() -> None:
    with ui.vstack(gap="lg"):
        with ui.hstack(justify="between", align="center", wrap=True):
            ui.heading("Temps réel", level=1, size="2xl")
            connection_badge()
        ui.alert(
            "Ouvre le Pipeline dans un second onglet et glisse une carte : "
            "les chiffres de cette page bougent sans être rechargés.",
            color="info", icon="info",
        )
        board_pulse()
        recent_moves()


feature = Feature(
    name="realtime",
    kind="page",
    provides=[realtime_page],
    uses=["deals_data", "access"],
)
