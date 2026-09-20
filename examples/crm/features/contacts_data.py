"""features/contacts_data — data: the contacts, activities and notes repo.

Serves screens 3 (master-detail) and 4 (sheet). 120 000 contacts: every
read is paginated or bounded, never "everything then filter in Python".

The :class:`ContactsRev` token is the external data's reactivity handle —
a SQLite write touches no typed ``State``, so nothing would re-render
without it.
"""

from __future__ import annotations

from bretzel import Feature
from bretzel.state import AppState, field
from examples.crm.core.db import execute, owner_scope, query, scalar
from examples.crm.core.domain import STATUS_KEYS


class ContactsRev(AppState):
    """Contacts revision — bumped at every write."""

    rev: int = field(default=0, merge="add")


#: The fragment saying "this contact belongs to the portfolio".
#: Written ONCE: both contact writes set it, and a half-scoped write does
#: not show.
_CONTACT_IN_SCOPE = " AND owner = ?"


def search_clause(
    needle: str, status: str, owner: str | None
) -> tuple[str, list]:
    """The common clause.

    ⚠️ The scoping reads ``c.owner``, the denormalised column, and **not**
    ``a.owner``. A contact does not have an owner of their own, though —
    they have their account's — so going through the join would be the
    "right" form. It costs: it forces the ``JOIN`` into the COUNT and
    makes SQLite drive from ``accounts``, that is **100.5 ms** against
    **0.08 ms** on page 1. The seed copies the column, so the two cannot
    diverge (cf. the schema in ``core/db.py``).
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
    """One page of contacts + the total, with the account's name.

    ``(page, total)`` and not the page alone: without the total, the
    pagination does not know how many pages to offer, and the screen
    cannot say "412 contacts" — which is the only proof the filter bit.
    """
    needle = needle.strip()
    where, params = search_clause(needle, status, owner)
    # The join only enters the COUNT if the search targets the account's
    # name. Without that condition, counting the 120 000 contacts makes
    # 120 000 rowid lookups in ``accounts`` for a figure the join cannot
    # change: 26.4 ms against 0.1 ms, on the default load.
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
    """A contact and their account, or ``None`` — the caller decides the
    404.

    Scoped for the same reason as :func:`accounts_data.get_account`: a
    sheet reachable by its URL is a sheet that leaks.
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
    """A contact's latest activities, most recent first."""
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
    """The contacts attached to an account — screen 5's sub-table.

    Bounded: a large account carries dozens, and a sub-table unrolling
    them all scrolls the page instead of the card containing it.
    """
    return query(
        "SELECT * FROM contacts WHERE account_id = ? "
        "ORDER BY last_name, first_name LIMIT ?",
        (account_id, limit),
    )


def update_contact(contact_id: int, fields: dict,
                   owner: str | None) -> bool:
    """Write the allowed fields, INSIDE the portfolio. ``False`` =
    refused.

    Two guards, and they do not protect against the same thing:

    - the column **allowlist** is here and not at the call site: an
      ``UPDATE`` built from a form dict's keys would write any column,
      ``id`` included;
    - the **scoping** is in the ``WHERE``. ⚠️ It was missing, and it was
      the slice's most serious hole: ``contact_id`` is a declared field
      of the form's ``PageState``, so the base layer hydrates it from the
      request body even if no input renders it. The HMAC signature covers
      the action identifier and its arguments, not the rest of the body —
      so any signed-in salesperson could edit any contact by adding a
      field to the POST. Twenty-three READS had been scoped and zero
      writes.

    The refusal is "zero rows touched", not an exception: outside the
    portfolio and "identifier does not exist" must be the same event,
    otherwise the answer says which of the two it was.
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
    """Add a note. ``0`` when the contact is outside the portfolio.

    The ``INSERT`` cannot carry a ``WHERE``, so the scoping is a prior
    ``SELECT`` — it is the only form available, and it must be written
    here rather than at the call site for the same reason as
    :func:`update_contact`: a write scoped by its caller is an unscoped
    write the day somebody calls it elsewhere.
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
