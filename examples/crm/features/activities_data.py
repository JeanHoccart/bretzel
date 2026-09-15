"""features/activities_data — data : le journal d'activité, filtré en SQL.

Sert l'écran 6. 60 000 activités : la fenêtre de lecture est toujours bornée
par une période ET par un plafond, jamais « tout puis on filtre en Python ».

Les dates voyagent en **ISO**, et c'est structurel : ``'2026-08-19'`` se
compare lexicographiquement comme chronologiquement, donc un ``BETWEEN`` sur
du texte SQLite ordonne juste, et l'index sur ``at`` sert.
"""

from __future__ import annotations

from bretzel import Feature
from bretzel.state import AppState, field
from examples.crm.core.db import execute, owner_scope, query
from examples.crm.core.domain import ACTIVITY_KEYS


class ActivitiesRev(AppState):
    """Révision du journal — bumpée à chaque écriture."""

    rev: int = field(default=0, merge="add")


def filter_clause(
    start: str, end: str, kind: str, owner: str | None
) -> tuple[str, list]:
    """La clause commune aux trois lectures de l'écran.

    Écrite une fois : la liste, les compteurs et l'agenda doivent regarder
    exactement la même fenêtre, sinon le nombre affiché ne décrit pas la
    liste qui est en dessous.
    """
    clauses = ["a.at BETWEEN ? AND ?"]
    params: list = [start, end]
    if kind in ACTIVITY_KEYS:
        clauses.append("a.kind = ?")
        params.append(kind)
    if owner is not None:
        clauses.append("a.owner = ?")
        params.append(owner)
    return "WHERE " + " AND ".join(clauses), params


def activities_between(
    start: str, end: str, kind: str, owner: str | None, *, limit: int = 60
) -> list[dict]:
    """Les activités de la fenêtre, la plus récente d'abord, plafonnées."""
    where, params = filter_clause(start, end, kind, owner)
    return query(
        f"SELECT a.*, c.first_name, c.last_name, ac.name AS account_name "
        f"FROM activities a "
        f"JOIN contacts c ON c.id = a.contact_id "
        f"JOIN accounts ac ON ac.id = a.account_id {where} "
        f"ORDER BY a.at DESC, a.id DESC LIMIT ?",
        (*params, limit),
    )


def activity_counts(
    start: str, end: str, kind: str, owner: str | None
) -> dict:
    """``{type: nombre}`` sur la fenêtre — sans jointure, sans plafond.

    Pas de ``JOIN`` ici : compter n'a besoin d'aucune colonne des deux autres
    tables, et la jointure ferait 60 000 accès par rowid pour rien.
    """
    where, params = filter_clause(start, end, kind, owner)
    rows = query(
        f"SELECT a.kind, COUNT(*) AS n FROM activities a {where} "
        f"GROUP BY a.kind",
        tuple(params),
    )
    return {r["kind"]: r["n"] for r in rows}


def busiest_days(start: str, end: str, kind: str, owner: str | None,
                 *, limit: int = 8) -> list[dict]:
    """Les journées les plus chargées de la fenêtre.

    ⚠️ Cette liste existe parce que ``ui.calendar`` ne sait PAS marquer un
    jour : il n'a ni prop d'événements ni slot de cellule (cf. le journal du
    chantier). L'agenda de l'écran sert donc à CHOISIR un jour, et c'est ce
    tableau qui dit lesquels sont chargés — deux contrôles pour ce qu'un
    calendrier annoté ferait seul.
    """
    where, params = filter_clause(start, end, kind, owner)
    return query(
        f"SELECT a.at AS jour, COUNT(*) AS n FROM activities a {where} "
        f"GROUP BY a.at ORDER BY n DESC, a.at DESC LIMIT ?",
        (*params, limit),
    )


def add_activity(contact_id: int, kind: str, subject: str, at: str,
                 owner: str, scope: str | None) -> int:
    """Journalise une activité. Le compte est DÉRIVÉ du contact, pas demandé.

    La table le porte en double (dénormalisation assumée pour que la fiche
    compte agrège sans jointure) ; le laisser saisir permettrait d'écrire une
    activité rattachée à un compte qui n'est pas celui du contact.

    ⚠️ **Deux propriétaires, et ce n'est pas une redondance.** ``owner``
    est celui qu'on ÉCRIT sur la ligne ; ``scope`` est celui qui a le
    droit d'écrire. Pour un commercial ils sont égaux ; pour la direction
    ``scope`` vaut ``None`` et ``owner`` est le porteur choisi. Les
    confondre, c'était laisser un commercial journaliser sur le contact
    d'un collègue en forgeant un identifiant — ``contact_id`` arrive du
    navigateur.
    """
    scope_sql, scope_params = owner_scope(scope, " AND owner = ?")
    rows = query(
        f"SELECT account_id FROM contacts WHERE id = ?{scope_sql}",
        (contact_id, *scope_params),
    )
    if not rows:
        return 0
    activity_id = execute(
        "INSERT INTO activities (contact_id, account_id, kind, subject, at, "
        "owner) VALUES (?, ?, ?, ?, ?, ?)",
        (contact_id, rows[0]["account_id"], kind, subject, at, owner),
    )
    ActivitiesRev().rev += 1
    return activity_id


feature = Feature(
    name="activities_data",
    kind="data",
    provides=[ActivitiesRev, activities_between, activity_counts,
              busiest_days, add_activity],
    uses=["db"],
)
