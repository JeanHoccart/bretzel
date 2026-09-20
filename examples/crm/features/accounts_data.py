"""features/accounts_data — data: the accounts repo, in SQL.

Screen 2's heart is :func:`load_accounts` — ``ui.datatable``'s callable
``rows=``. It receives a ``Query`` (sort, page, search, filters,
``for_export``) and translates it into ONE SQL query. It is the tier the
datatable was designed to serve and that no example exercised: at 50 000
accounts, the list tier would require loading the whole table into Python
at every keystroke.

The two guards that matter:

- ``sort_key`` and the filter keys go through an **allowlist** before
  entering the SQL. A sort key comes from the browser; interpolated as
  is, it is an injection.
- ``filters[key] == []`` (the user unticked everything) must match ZERO
  rows, not "no filter". ``Query`` says so explicitly, and the two cases
  look alike enough to get wrong.
"""

from __future__ import annotations

from typing import Any

from bretzel import Feature

from bretzel.components import Query
from examples.crm.core.db import owner_scope, query, scalar

#: ⚠️ ``owner=None`` means **every owner**, and it is a privilege: only
#: a directorate gets it (``access.visible_owner``). The parameter is
#: explicit rather than read from a global context so the scoping SHOWS
#: at the call site — an unscoped read path must leap out in a review,
#: not hide in a thread-local.

#: The columns a sort is accepted on. An allowlist: the key arrives from
#: the browser and ends up in an ``ORDER BY``.
SORTABLE: frozenset[str] = frozenset(
    {"name", "industry", "country", "city", "size", "arr", "owner", "created_at"}
)

#: The filterable columns, with their declared domain. In callable mode
#: the component holds no row: it cannot derive the unique values, and
#: raises if asked for ``filter=True``.
FILTERABLE: frozenset[str] = frozenset({"industry", "country", "size", "owner"})

#: The columns the global search sweeps.
SEARCHED: tuple[str, ...] = ("name", "city", "industry", "owner")


def where_clause(q: Query, owner: str | None) -> tuple[str, list[Any]]:
    """The ``WHERE`` clause common to the COUNT and the SELECT, and its
    parameters.

    ``owner`` scopes the read to a portfolio — cf. the note at the head of
    the module. It is applied FIRST, before the search and the filters:
    it is not one more facet the user would choose, it is the boundary of
    what they may see.
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
            # Everything unticked: the view is empty. Skipping the key
            # would return the COMPLETE table, that is, the opposite of
            # what was asked.
            clauses.append("1 = 0")
            continue
        clauses.append(f"{key} IN ({','.join('?' * len(values))})")
        params.extend(values)

    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def order_clause(q: Query) -> str:
    """The ``ORDER BY`` clause, or the source order if the sort is
    neutral.

    ``id`` as a second criterion: without it, two accounts of the same
    size come out in an order SQLite does not guarantee from one page to
    the next — a row can then appear twice while paginating, or never.
    """
    if q.sort_key not in SORTABLE:
        return "ORDER BY id"
    direction = "DESC" if q.descending else "ASC"
    return f"ORDER BY {q.sort_key} {direction}, id"


def load_accounts(q: Query, owner: str | None) -> tuple[list[dict], int]:
    """The datatable's callable ``rows=``: ``(the page's rows, total)``.

    ``for_export`` cuts the pagination window — a CSV must contain every
    filtered row, not the twenty on screen.
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
    """An account, or ``None`` — the caller decides the 404.

    Scoped like the rest, and it is here that it matters most: an account
    outside the portfolio must be **not found**, not merely absent from
    the lists. Without that, the URL ``/accounts/1641`` typed by hand
    would give access to the sheet of an account no screen shows — the
    most ordinary leak of a filtered app.
    """
    scope, scope_params = owner_scope(owner, " AND owner = ?")
    rows = query(f"SELECT * FROM accounts WHERE id = ?{scope}",
                 (account_id, *scope_params))
    return rows[0] if rows else None


def account_totals(account_id: int) -> dict:
    """An account sheet header's figures, in TWO queries.

    Contacts and deals live in two tables with no link between them:
    counting them together would need a cartesian product, which would
    multiply every account by every deal before deduplicating.
    """
    contacts = query(
        "SELECT COUNT(*) AS n FROM contacts WHERE account_id = ?",
        (account_id,),
    )[0]
    deals = query(
        "SELECT COUNT(*) AS n, "
        "SUM(CASE WHEN stage NOT IN ('won','lost') THEN amount ELSE 0 END) "
        "  AS open_amount, "
        "SUM(CASE WHEN stage = 'won' THEN amount ELSE 0 END) AS won_amount "
        "FROM deals WHERE account_id = ?",
        (account_id,),
    )[0]
    return {"contacts": contacts["n"], "deals": deals["n"],
            "open": deals["open_amount"] or 0,
            "won": deals["won_amount"] or 0}


def accounts_summary(owner: str | None) -> dict:
    """The header's two figures: number of accounts and cumulative ARR.

    A single query: two separate ``scalar`` would reopen two connections
    for one header row. The number of owners is NOT counted here — a
    ``COUNT(DISTINCT owner)`` plans a temporary b-tree and weighed 11 ms
    of the header's 14.7 ms, to give back the length of ``OWNERS``, which
    is a domain constant.
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
