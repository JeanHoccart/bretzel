"""features/contacts_data — data : le repo contacts, activités et notes.

Sert les écrans 3 (maître-détail) et 4 (fiche). 120 000 contacts : toute
lecture est paginée ou bornée, jamais « tout puis on filtre en Python ».

Le jeton :class:`ContactsRev` est la poignée de réactivité de la donnée
externe — une écriture SQLite ne touche aucun ``State`` typé, donc rien ne se
re-rendrait sans lui.
"""

from __future__ import annotations

from bretzel import Feature
from bretzel.state import AppState, field
from examples.crm.core.db import execute, owner_scope, query, scalar
from examples.crm.core.domain import STATUS_KEYS


class ContactsRev(AppState):
    """Révision contacts — bumpée à chaque écriture."""

    rev: int = field(default=0, merge="add")


#: Le fragment qui dit « ce contact appartient au portefeuille ».
#: Écrit UNE fois : les deux écritures de contact le posent, et une
#: écriture cadrée à moitié ne se voit pas.
_CONTACT_IN_SCOPE = " AND owner = ?"


def search_clause(
    needle: str, status: str, owner: str | None
) -> tuple[str, list]:
    """La clause commune.

    ⚠️ Le cadrage lit ``c.owner``, la colonne dénormalisée, et **pas**
    ``a.owner``. Un contact n'a pourtant pas de propriétaire à lui — il a
    celui de son compte — donc passer par la jointure serait la forme
    « juste ». Elle coûte : elle force le ``JOIN`` dans le COUNT et fait
    conduire SQLite depuis ``accounts``, soit **100,5 ms** contre
    **0,08 ms** sur la page 1. Le semis recopie la colonne, donc les deux
    ne peuvent pas diverger (cf. le schéma dans ``core/db.py``).
    """
    clauses: list[str] = []
    params: list = []
    if owner is not None:
        clauses.append("c.owner = ?")
        params.append(owner)
    if needle:
        clauses.append(
            "(c.last_name LIKE ? OR c.first_name LIKE ? OR c.email LIKE ? "
            "OR a.name LIKE ?)"
        )
        params.extend([f"%{needle}%"] * 4)
    if status in STATUS_KEYS:
        clauses.append("c.status = ?")
        params.append(status)
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def search_contacts(
    needle: str, status: str, page: int, per_page: int, owner: str | None
) -> tuple[list[dict], int]:
    """Une page de contacts + le total, avec le nom du compte.

    ``(page, total)`` et non ``page`` seule : sans le total, la pagination ne
    sait pas combien de pages proposer, et l'écran ne peut pas dire « 412
    contacts » — ce qui est la seule preuve que le filtre a mordu.
    """
    needle = needle.strip()
    where, params = search_clause(needle, status, owner)
    # La jointure n'entre dans le COMPTE que si la recherche vise le nom du
    # compte. Sans cette condition, compter les 120 000 contacts fait 120 000
    # accès par rowid dans ``accounts`` pour un chiffre que la jointure ne
    # peut pas changer : 26,4 ms contre 0,1 ms, sur le chargement par défaut.
    join = "JOIN accounts a ON a.id = c.account_id " if needle else ""
    total = int(scalar(
        f"SELECT COUNT(*) FROM contacts c {join}{where}", tuple(params)
    ))
    offset = max(0, (max(1, page) - 1) * per_page)
    rows = query(
        f"SELECT c.*, a.name AS account_name, a.city AS account_city "
        f"FROM contacts c JOIN accounts a ON a.id = c.account_id {where} "
        f"ORDER BY c.last_name, c.first_name, c.id LIMIT ? OFFSET ?",
        (*params, per_page, offset),
    )
    return rows, total


def get_contact(contact_id: int, owner: str | None) -> dict | None:
    """Un contact et son compte, ou ``None`` — l'appelant décide du 404.

    Cadré pour la même raison que :func:`accounts_data.get_account` : une
    fiche atteignable par son URL est une fiche qui fuit.
    """
    scope, scope_params = owner_scope(owner, " AND c.owner = ?")
    params = (contact_id, *scope_params)
    rows = query(
        "SELECT c.*, a.name AS account_name, a.city AS account_city, "
        "a.industry AS account_industry, a.id AS account_id "
        "FROM contacts c JOIN accounts a ON a.id = c.account_id "
        f"WHERE c.id = ?{scope}",
        params,
    )
    return rows[0] if rows else None


def contact_activities(contact_id: int, limit: int = 25) -> list[dict]:
    """Les dernières activités d'un contact, la plus récente d'abord."""
    return query(
        "SELECT * FROM activities WHERE contact_id = ? "
        "ORDER BY at DESC, id DESC LIMIT ?",
        (contact_id, limit),
    )


def contact_notes(contact_id: int, limit: int = 25) -> list[dict]:
    return query(
        "SELECT * FROM notes WHERE contact_id = ? "
        "ORDER BY at DESC, id DESC LIMIT ?",
        (contact_id, limit),
    )


def account_contacts(account_id: int, limit: int = 25) -> list[dict]:
    """Les contacts rattachés à un compte — la sous-table de l'écran 5.

    Bornée : un grand compte en porte des dizaines, et une sous-table qui
    déroule tout fait défiler la page au lieu de la carte qui la contient.
    """
    return query(
        "SELECT * FROM contacts WHERE account_id = ? "
        "ORDER BY last_name, first_name LIMIT ?",
        (account_id, limit),
    )


def update_contact(contact_id: int, fields: dict,
                   owner: str | None) -> bool:
    """Écrit les champs autorisés, DANS le portefeuille. ``False`` = refusé.

    Deux gardes, et elles ne protègent pas de la même chose :

    - la **liste blanche** de colonnes est ici et pas au call-site : un
      ``UPDATE`` construit depuis les clés d'un dict de formulaire
      écrirait n'importe quelle colonne, ``id`` comprise ;
    - le **cadrage** est dans le ``WHERE``. ⚠️ Il manquait, et c'était le
      trou le plus grave de la tranche : ``contact_id`` est un champ
      déclaré du ``PageState`` du formulaire, donc le socle l'hydrate
      depuis le corps de la requête même si aucun input ne le rend. La
      signature HMAC couvre l'identifiant d'action et ses arguments, pas
      le reste du corps — n'importe quel commercial connecté pouvait
      donc éditer n'importe quel contact en ajoutant un champ au POST.
      Vingt-trois LECTURES avaient été cadrées et zéro écriture.

    Le refus est « zéro ligne touchée », pas une exception : hors
    portefeuille et « identifiant inexistant » doivent être le même
    événement, sinon la réponse dit lequel des deux c'était.
    """
    allowed = ("first_name", "last_name", "email", "phone", "title", "status")
    changes = {k: v for k, v in fields.items() if k in allowed}
    if not changes:
        return False
    assignments = ", ".join(f"{k} = ?" for k in changes)
    scope, scope_params = owner_scope(owner, _CONTACT_IN_SCOPE)
    touched = execute(
        f"UPDATE contacts SET {assignments} WHERE id = ?{scope}",
        (*changes.values(), contact_id, *scope_params),
    )
    if not touched:
        return False
    ContactsRev().rev += 1
    return True


def add_note(contact_id: int, body: str, author: str, at: str,
             owner: str | None) -> int:
    """Ajoute une note. ``0`` quand le contact est hors portefeuille.

    L'``INSERT`` ne peut pas porter de ``WHERE``, donc le cadrage est un
    ``SELECT`` préalable — c'est la seule forme disponible, et elle doit
    être écrite ici plutôt qu'au call-site pour la même raison que
    :func:`update_contact` : une écriture cadrée par son appelant est
    une écriture non cadrée le jour où quelqu'un l'appelle ailleurs.
    """
    if get_contact(contact_id, owner) is None:
        return 0
    note_id = execute(
        "INSERT INTO notes (contact_id, body, author, at) VALUES (?, ?, ?, ?)",
        (contact_id, body, author, at),
    )
    ContactsRev().rev += 1
    return note_id


feature = Feature(
    name="contacts_data",
    kind="data",
    provides=[ContactsRev, search_contacts, get_contact, contact_activities,
              contact_notes, account_contacts, update_contact, add_note],
    uses=["db"],
)
