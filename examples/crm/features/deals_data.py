"""features/deals_data — data : le repo des opportunités, et le réordonnancement.

Sert l'écran 1 (le pipeline). Deux choses y vivent :

- :func:`pipeline_deals`, la fenêtre de lecture — les affaires OUVERTES d'un
  propriétaire dont l'échéance tombe dans l'horizon, groupées par étape ;
- :func:`move_deal`, l'écriture — ce qu'un drop applique.

**Pourquoi une fenêtre.** 12 000 affaires, dont ~9 400 ouvertes : un kanban
qui rendrait tout ferait 9 400 cartes. Un commercial regarde SON pipeline sur
un horizon. La fenêtre est donc le geste métier, pas un pansement de perf —
et c'est elle qui donne des colonnes à ~100 cartes, celles qui défilent.

**Le rang.** ``position`` est un entier par étape, semé avec un pas de 64.
Insérer entre deux cartes prend le MILIEU des deux rangs voisins ; quand il
n'y a plus de milieu (deux rangs consécutifs), on renumérote l'étape entière
et on recommence. C'est l'algorithme de liste ordonnée classique : il évite
de réécrire 2 000 lignes à chaque geste, sans jamais laisser deux cartes se
disputer un rang.
"""

from __future__ import annotations

from bretzel import Feature
from bretzel.components import Move
from bretzel.state import AppState, field
from examples.crm.core.db import execute, owner_scope, query
from examples.crm.core.domain import OPEN_STAGES, POSITION_STEP, TODAY


class DealsRev(AppState):
    """Révision des affaires — bumpée à chaque écriture."""

    rev: int = field(default=0, merge="add")


def horizon_date(days: int) -> str:
    from datetime import timedelta

    return (TODAY + timedelta(days=days)).isoformat()


#: Le plafond de cartes par colonne. Mesuré : sans lui, la fenêtre à 90 jours
#: du premier propriétaire rend **1 093 cartes** et une page de **1,2 Mo**.
#: Le rang manuel EST l'ordre de priorité, donc couper par le haut coupe au
#: bon endroit — et l'en-tête de colonne dit toujours « 50 sur 564 ».
PER_COLUMN = 50


def pipeline_deals(
    owner: str | None, horizon_days: int, *, limit: int = PER_COLUMN
) -> dict[str, list[dict]]:
    """Les affaires ouvertes d'``owner`` échéant sous ``horizon_days`` jours.

    Une seule requête pour les quatre colonnes, jointe au nom du compte : une
    requête par étape, c'est quatre connexions pour un écran. Le plafond
    s'applique PAR étape (``ROW_NUMBER`` partitionné), pas au total — sinon la
    première colonne mangerait la fenêtre des trois autres.
    """
    placeholders = ",".join("?" * len(OPEN_STAGES))
    scope, scope_params = owner_scope(owner, " AND d.owner = ?")
    rows = query(
        f"SELECT * FROM ("
        f"  SELECT d.*, a.name AS account_name, a.city AS account_city,"
        f"         ROW_NUMBER() OVER ("
        f"           PARTITION BY d.stage ORDER BY d.position, d.id) AS rn"
        f"  FROM deals d JOIN accounts a ON a.id = d.account_id"
        f"  WHERE d.stage IN ({placeholders}){scope}"
        f"  AND d.close_date <= ?"
        f") WHERE rn <= ? ORDER BY position, id",
        (*OPEN_STAGES, *scope_params, horizon_date(horizon_days), limit),
    )
    grouped: dict[str, list[dict]] = {stage: [] for stage in OPEN_STAGES}
    for row in rows:
        grouped[row["stage"]].append(row)
    return grouped


def pipeline_totals(owner: str | None, horizon_days: int) -> dict[str, dict]:
    """Le compte et le montant de chaque étape DANS la fenêtre, sans plafond.

    Sert le « 50 sur 393 » d'un en-tête de colonne : sans lui, un plafond
    laisserait croire que le pipeline s'arrête à ce qu'il montre — et la somme
    affichée ne serait que celle des cartes visibles.
    """
    scope, scope_params = owner_scope(owner, " AND owner = ?")
    rows = query(
        "SELECT stage, COUNT(*) AS n, SUM(amount) AS total FROM deals "
        f"WHERE stage IN ({','.join('?' * len(OPEN_STAGES))}){scope} "
        "AND close_date <= ? GROUP BY stage",
        (*OPEN_STAGES, *scope_params, horizon_date(horizon_days)),
    )
    return {r["stage"]: r for r in rows}


def live_board(owner: str | None) -> dict[str, dict]:
    """``{étape: {n, total}}`` sur les affaires ouvertes, SANS horizon.

    Sert l'écran temps réel. Elle ignore l'horizon — ce qu'un second onglet
    doit voir bouger, c'est le total d'une étape, pas la fenêtre à 90 jours
    d'un écran. Elle ne peut pas ignorer le propriétaire pour autant : un
    compteur global dirait à un commercial le volume d'affaires des autres,
    et le fait que ce soit agrégé n'en fait pas une donnée publique.
    """
    scope, scope_params = owner_scope(owner, " AND owner = ?")
    rows = query(
        "SELECT stage, COUNT(*) AS n, SUM(amount) AS total FROM deals "
        f"WHERE stage IN ({','.join('?' * len(OPEN_STAGES))}){scope} "
        f"GROUP BY stage",
        (*OPEN_STAGES, *scope_params),
    )
    return {r["stage"]: r for r in rows}


def column_heads(owner: str | None, limit: int = 10) -> list[dict]:
    """Les premières affaires de chaque colonne, dans l'ordre du kanban.

    Le rang est la seule chose qu'un glisser-déposer écrit — donc la seule
    qui témoigne, dans un autre onglet, que quelqu'un vient de bouger.

    **``UNION ALL`` et non ``ROW_NUMBER``**, contrairement à
    :func:`pipeline_deals`. La fenêtre partitionnée numérote TOUTES les
    affaires ouvertes et joint chacune à son compte avant d'en jeter 99 % :
    ``EXPLAIN QUERY PLAN`` y montre un ``USE TEMP B-TREE FOR ORDER BY``, et
    la mesure dit **32 ms pour douze lignes**. Quatre ``LIMIT`` empilés
    laissent l'index ``(stage, position)`` faire son travail : **0,1 ms**.
    La différence tient à ce que le plafond est ici minuscule — là-bas il
    vaut 50 par colonne et la partition se rentabilise.
    """
    per_stage = max(1, limit // len(OPEN_STAGES))
    scope, scope_params = owner_scope(owner, " AND d.owner = ?")
    parts = " UNION ALL ".join(
        "SELECT * FROM (SELECT d.id, d.name, d.stage, d.amount, d.owner, "
        "d.position, a.name AS account_name FROM deals d "
        f"JOIN accounts a ON a.id = d.account_id WHERE d.stage = ?{scope} "
        "ORDER BY d.position, d.id LIMIT ?)"
        for _stage in OPEN_STAGES
    )
    params: list = []
    for stage in OPEN_STAGES:
        params.extend([stage, *scope_params, per_stage])
    return query(f"{parts} ORDER BY position, id", tuple(params))


def get_deal(deal_id: int, owner: str | None) -> dict | None:
    """Une affaire, cadrée. Un identifiant d'affaire arrive du NAVIGATEUR
    (c'est l'``item_key`` d'un drop) : sans cadrage, on pourrait déplacer
    l'affaire de quelqu'un d'autre en forgeant une clé."""
    scope, scope_params = owner_scope(owner, " AND owner = ?")
    rows = query(f"SELECT * FROM deals WHERE id = ?{scope}",
                 (deal_id, *scope_params))
    return rows[0] if rows else None


def account_deals(account_id: int, limit: int = 25) -> list[dict]:
    """Les affaires d'un compte, l'échéance la plus LOINTAINE d'abord.

    ``DESC`` sur des dates ISO remonte le futur : ce qui reste à jouer passe
    avant ce qui est échu, et c'est ce qu'on veut lire sur une fiche compte.
    """
    return query(
        "SELECT * FROM deals WHERE account_id = ? "
        "ORDER BY close_date DESC LIMIT ?",
        (account_id, limit),
    )


def renumber_stage(stage: str) -> None:
    """Réétale les rangs d'une étape avec un pas de :data:`POSITION_STEP`.

    Appelé seulement quand deux voisins n'ont plus de milieu — donc rarement.
    Une seule requête : lire 2 000 lignes en Python pour les réécrire une par
    une coûterait 2 000 allers-retours.
    """
    execute(
        "UPDATE deals SET position = ("
        "  SELECT rn * ? FROM ("
        "    SELECT id, ROW_NUMBER() OVER (ORDER BY position, id) AS rn"
        "    FROM deals WHERE stage = ?"
        "  ) ranked WHERE ranked.id = deals.id"
        ") WHERE stage = ?",
        (POSITION_STEP, stage, stage),
    )


def slot_between(before: int | None, after: int | None) -> int | None:
    """Le rang à donner entre deux voisins, ou ``None`` s'il n'y en a plus."""
    if before is None and after is None:
        return POSITION_STEP
    if before is None:
        # Sans garde de positivité : rien n'exige un rang positif (l'ordre est
        # ``ORDER BY position, id`` sur des entiers 64 bits), et refuser le
        # négatif renumérotait l'étape entière dès la deuxième insertion en
        # tête — l'exact geste qu'une liste de kanban reçoit le plus.
        return after - POSITION_STEP
    if after is None:
        return before + POSITION_STEP
    if after - before < 2:
        return None                       # plus de milieu : il faut renuméroter
    return (before + after) // 2


def move_deal(m: Move, *, owner: str | None, horizon_days: int) -> bool:
    """Applique un drop. Renvoie ``False`` quand le déplacement est refusé.

    Refuser, c'est ne rien muter : le navigateur a déjà bougé la carte, donc
    le rendu serveur qui la contredit la remet en place tout seul (``Move``).

    La fenêtre de la zone cible est RELUE ici, à partir de la vue de
    l'appelant — pas reçue de lui. Les rangs voisins doivent être ceux des
    cartes que le lecteur avait sous les yeux ; un appelant qui passerait
    l'étape entière calculerait des voisins invisibles et déposerait la carte
    au mauvais endroit, sans erreur. L'invariant appartient à cette fonction.
    """
    if m.to_zone not in OPEN_STAGES:
        return False
    window = pipeline_deals(owner, horizon_days).get(m.to_zone, [])
    deal = (get_deal(int(m.item_key), owner)
            if m.item_key.isdigit() else None)
    if deal is None:
        return False

    # La fenêtre telle qu'elle sera APRÈS le drop, sans la carte déplacée :
    # dans une réorganisation interne elle y est encore, dans un transfert
    # elle n'y a jamais été.
    others = [d for d in window if d["id"] != deal["id"]]
    index = max(0, min(m.to_index, len(others)))
    before = others[index - 1]["position"] if index > 0 else None
    after = others[index]["position"] if index < len(others) else None

    slot = slot_between(before, after)
    if slot is None:
        renumber_stage(m.to_zone)
        # Les rangs ont changé : relire les deux voisins par leur id, pas par
        # leur ancienne valeur.
        ids = [d["id"] for d in others]
        fresh = {
            r["id"]: r["position"]
            for r in query(
                "SELECT id, position FROM deals "
                f"WHERE id IN ({','.join('?' * len(ids))})", tuple(ids)
            )
        } if ids else {}
        before = fresh.get(others[index - 1]["id"]) if index > 0 else None
        after = fresh.get(others[index]["id"]) if index < len(others) else None
        slot = slot_between(before, after)
        if slot is None:                  # ne devrait plus arriver
            return False

    execute(
        "UPDATE deals SET stage = ?, position = ? WHERE id = ?",
        (m.to_zone, slot, deal["id"]),
    )
    DealsRev().rev += 1
    return True


feature = Feature(
    name="deals_data",
    kind="data",
    provides=[DealsRev, pipeline_deals, pipeline_totals, get_deal,
              account_deals, move_deal, live_board, column_heads],
    uses=["db"],
)
