"""features/activities_data — data: the activity log, filtered in SQL.

Serves screen 6. 60 000 activities: the read window is always bounded by
a period AND by a cap, never "everything then filter in Python".

The dates travel in **ISO**, and that is structural: ``'2026-08-19'``
compares lexicographically as chronologically, so a ``BETWEEN`` on SQLite
text orders correctly, and the index on ``at`` serves.
"""

from __future__ import annotations

from bretzel import Feature
from bretzel.state import AppState, field
from examples.crm.core.db import execute, owner_scope, query
from examples.crm.core.domain import ACTIVITY_KEYS


class ActivitiesRev(AppState):
    """Log revision — bumped at every write."""

    rev: int = field(default=0, merge="add")


def filter_clause(
    start: str, end: str, kind: str, owner: str | None
) -> tuple[str, list]:
    """The clause common to the screen's three reads.

    Written once: the list, the counters and the calendar must look at
    exactly the same window, otherwise the number shown does not describe
    the list below it.
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
    """The window's activities, most recent first, capped."""
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
    """``{type: count}`` over the window — no join, no cap.

    No ``JOIN`` here: counting needs no column from the other two tables,
    and the join would make 60 000 rowid lookups for nothing.
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
    """The window's busiest days.

    ⚠️ This list exists because ``ui.calendar`` CANNOT mark a day: it has
    neither an events prop nor a cell slot (cf. the work's journal). So
    the screen's calendar serves to CHOOSE a day, and it is this table
    that says which ones are busy — two controls for what an annotated
    calendar would do alone.
    """
    where, params = filter_clause(start, end, kind, owner)
    return query(
        f"SELECT a.at AS day, COUNT(*) AS n FROM activities a {where} "
        f"GROUP BY a.at ORDER BY n DESC, a.at DESC LIMIT ?",
        (*params, limit),
    )


def add_activity(contact_id: int, kind: str, subject: str, at: str,
                 owner: str, scope: str | None) -> int:
    """Log an activity. The account is DERIVED from the contact, not
    asked for.

    The table carries it twice (denormalisation accepted so the account
    sheet aggregates without a join); letting it be entered would allow
    writing an activity attached to an account that is not the contact's.

    ⚠️ **Two owners, and it is not a redundancy.** ``owner`` is the one
    WRITTEN on the row; ``scope`` is the one entitled to write. For a
    salesperson they are equal; for the directorate ``scope`` is ``None``
    and ``owner`` is the chosen holder. Confusing them was letting a
    salesperson log on a colleague's contact by forging an identifier —
    ``contact_id`` arrives from the browser.
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
