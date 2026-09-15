"""features/accounts_data — data : le repo comptes, en SQL.

Le cœur de l'écran 2 est :func:`load_accounts` — le ``rows=`` callable de
``ui.datatable``. Il reçoit un ``Query`` (tri, page, recherche, filtres,
``for_export``) et le traduit en UNE requête SQL. C'est le tier que la
datatable a été conçue pour servir et qu'aucun exemple n'exerçait : à 50 000
comptes, le tier liste demanderait de charger la table entière en Python à
chaque frappe.

Les deux gardes qui comptent :

- ``sort_key`` et les clés de filtre passent par une **liste blanche** avant
  d'entrer dans le SQL. Une clé de tri vient du navigateur ; interpolée telle
  quelle, c'est une injection.
- ``filters[key] == []`` (l'utilisateur a tout décoché) doit matcher ZÉRO
  ligne, pas « pas de filtre ». ``Query`` le dit explicitement, et les deux
  cas se ressemblent assez pour qu'on se trompe.
"""

from __future__ import annotations

from typing import Any

from bretzel import Feature

from bretzel.components import Query
from examples.crm.core.db import owner_scope, query, scalar

#: ⚠️ ``owner=None`` veut dire **tous les propriétaires**, et c'est un
#: privilège : seule une direction l'obtient (``access.visible_owner``).
#: Le paramètre est explicite plutôt que lu d'un contexte global pour que
#: le cadrage se VOIE à l'appel — un chemin de lecture non cadré doit
#: sauter aux yeux dans une revue, pas se cacher dans un thread-local.

#: Les colonnes sur lesquelles un tri est accepté. Liste blanche : la clé
#: arrive du navigateur et finit dans un ``ORDER BY``.
SORTABLE: frozenset[str] = frozenset(
    {"name", "industry", "country", "city", "size", "arr", "owner", "created_at"}
)

#: Les colonnes filtrables, avec leur domaine déclaré. En mode callable le
#: composant ne détient aucune ligne : il ne peut pas dériver les valeurs
#: uniques, et lève si on lui demande ``filter=True``.
FILTERABLE: frozenset[str] = frozenset({"industry", "country", "size", "owner"})

#: Les colonnes balayées par la recherche globale.
SEARCHED: tuple[str, ...] = ("name", "city", "industry", "owner")


def where_clause(q: Query, owner: str | None) -> tuple[str, list[Any]]:
    """La clause ``WHERE`` commune au COUNT et au SELECT, et ses paramètres.

    ``owner`` cadre la lecture sur un portefeuille — cf. la note en tête du
    module. Il est appliqué EN PREMIER, avant la recherche et les filtres :
    ce n'est pas une facette de plus que l'utilisateur choisirait, c'est la
    borne de ce qu'il a le droit de voir.
    """
    clauses: list[str] = []
    params: list[Any] = []
    if owner is not None:
        clauses.append("owner = ?")
        params.append(owner)

    if q.search:
        needle = f"%{q.search}%"
        clauses.append(
            "(" + " OR ".join(f"{col} LIKE ?" for col in SEARCHED) + ")"
        )
        params.extend([needle] * len(SEARCHED))

    for key, values in q.filters.items():
        if key not in FILTERABLE:
            continue
        if not values:
            # Tout décoché : la vue est vide. Sauter la clé rendrait la
            # table COMPLÈTE, soit l'inverse de ce qui a été demandé.
            clauses.append("1 = 0")
            continue
        clauses.append(f"{key} IN ({','.join('?' * len(values))})")
        params.extend(values)

    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def order_clause(q: Query) -> str:
    """La clause ``ORDER BY``, ou l'ordre source si le tri est au neutre.

    ``id`` en second critère : sans lui, deux comptes de même taille sortent
    dans un ordre que SQLite ne garantit pas d'une page à l'autre — une ligne
    peut alors apparaître deux fois en paginant, ou jamais.
    """
    if q.sort_key not in SORTABLE:
        return "ORDER BY id"
    direction = "DESC" if q.descending else "ASC"
    return f"ORDER BY {q.sort_key} {direction}, id"


def load_accounts(q: Query, owner: str | None) -> tuple[list[dict], int]:
    """Le ``rows=`` callable de la datatable : ``(lignes de la page, total)``.

    ``for_export`` coupe la fenêtre de pagination — un CSV doit contenir
    toutes les lignes filtrées, pas les vingt à l'écran.
    """
    where, params = where_clause(q, owner)
    total = scalar(f"SELECT COUNT(*) FROM accounts {where}", tuple(params))
    sql = f"SELECT * FROM accounts {where} {order_clause(q)}"
    if q.for_export:
        return query(sql, tuple(params)), int(total)
    rows = query(
        f"{sql} LIMIT ? OFFSET ?", (*params, q.per_page, q.offset)
    )
    return rows, int(total)


def get_account(account_id: int, owner: str | None) -> dict | None:
    """Un compte, ou ``None`` — l'appelant décide du 404.

    Cadré comme le reste, et c'est ici que ça compte le plus : un compte
    hors portefeuille doit être **introuvable**, pas seulement absent des
    listes. Sans ça, l'URL ``/comptes/1641`` tapée à la main donnerait
    accès à la fiche d'un compte qu'aucun écran ne montre — la fuite la
    plus banale d'une app filtrée.
    """
    scope, scope_params = owner_scope(owner, " AND owner = ?")
    rows = query(f"SELECT * FROM accounts WHERE id = ?{scope}",
                 (account_id, *scope_params))
    return rows[0] if rows else None


def account_totals(account_id: int) -> dict:
    """Les chiffres de l'en-tête d'une fiche compte, en DEUX requêtes.

    Contacts et affaires vivent dans deux tables sans lien entre elles : les
    compter ensemble demanderait un produit cartésien, qui multiplierait
    chaque compte par chaque affaire avant de dédupliquer.
    """
    contacts = query(
        "SELECT COUNT(*) AS n FROM contacts WHERE account_id = ?",
        (account_id,),
    )[0]
    deals = query(
        "SELECT COUNT(*) AS n, "
        "SUM(CASE WHEN stage NOT IN ('won','lost') THEN amount ELSE 0 END) "
        "  AS ouvert, "
        "SUM(CASE WHEN stage = 'won' THEN amount ELSE 0 END) AS gagne "
        "FROM deals WHERE account_id = ?",
        (account_id,),
    )[0]
    return {"contacts": contacts["n"], "deals": deals["n"],
            "ouvert": deals["ouvert"] or 0, "gagne": deals["gagne"] or 0}


def accounts_summary(owner: str | None) -> dict:
    """Les deux chiffres de l'en-tête : nombre de comptes et ARR cumulé.

    Une seule requête : deux ``scalar`` séparés rouvriraient deux connexions
    pour une ligne d'en-tête. Le nombre de propriétaires N'est PAS compté ici
    — un ``COUNT(DISTINCT owner)`` planifie un b-tree temporaire et pesait
    11 ms des 14,7 ms de l'en-tête, pour redonner la longueur de ``OWNERS``,
    qui est une constante du domaine.
    """
    scope, scope_params = owner_scope(owner, " WHERE owner = ?")
    return query(
        f"SELECT COUNT(*) AS total, SUM(arr) AS arr FROM accounts{scope}",
        scope_params,
    )[0]


feature = Feature(
    name="accounts_data",
    kind="data",
    provides=[load_accounts, accounts_summary, get_account,
              account_totals],
    uses=["db"],
)
