"""features/search_data — data: the global search, three tables in one.

Serves screen 8. Each table is queried separately then capped: a
``UNION`` over three different schemas would require flattening them into
common columns, and the result would no longer be able to say what it
shows.

**The prefix, not the substring.** A global search is typed letter by
letter: ``LIKE '%word%'`` forbids any index and scans 170 000 rows at
every keystroke. ``LIKE 'word%'`` can be an index range. What it costs is
real and accepted: "geneva" no longer finds "Bordeaux-Geneva". A
substring search at these volumes needs an FTS index, not a ``LIKE``.

⚠️ **"Can be", not "is"** — and the nuance is worth a factor of 20.
SQLite only applies the optimisation if the index has the SAME collation
as ``LIKE``, which is case-insensitive by default. With the binary
indexes alone, the three queries below planned a ``SCAN``: 898 ms per
keystroke on the contacts. ``core/db.py``'s ``COLLATE NOCASE`` indexes
are what makes the sentence true — 43.7 ms. Writing "it is an index
range" without looking at ``EXPLAIN QUERY PLAN`` was a belief, not a
measurement.
"""

from __future__ import annotations

from bretzel import Feature
from examples.crm.core.db import owner_scope, query

#: One cap per family. A global search shows the best, not all — and
#: three lists of ten fit in a screen, three lists of a hundred are a
#: disguised pagination.
PER_KIND = 8


def search_accounts(needle: str, owner: str | None,
                    limit: int = PER_KIND) -> list[dict]:
    scope, scope_params = owner_scope(owner, " AND owner = ?")
    return query(
        "SELECT id, name, city, industry, arr FROM accounts "
        f"WHERE name LIKE ?{scope} ORDER BY name LIMIT ?",
        (f"{needle}%", *scope_params, limit),
    )


#: A contact read, without its ``WHERE``. Both branches of
#: :func:`search_contacts_by_name` must project EXACTLY the same columns
#: — a ``UNION`` diverging by one column raises at run time, and only
#: when somebody searches.
_CONTACT_SELECT = (
    "SELECT c.id, c.first_name, c.last_name, c.email, c.status, "
    "a.name AS account_name FROM contacts c "
    "JOIN accounts a ON a.id = c.account_id "
)


def search_contacts_by_name(needle: str, owner: str | None,
                            limit: int = PER_KIND) -> list[dict]:
    """Surname OR email — the two keys by which one searches for
    somebody, and the two that have an index usable on a prefix.

    ⚠️ **A ``UNION`` of two reads, not an ``OR``.** SQLite can serve
    ``last_name LIKE 'x%' OR email LIKE 'x%'`` through a
    ``MULTI-INDEX OR`` — but it CANNOT combine that plan with an equality
    predicate on ``owner``. Scoped, the ``OR`` fell back to a scan:
    **93.7 ms**. Two scoped reads united, each on its
    ``(owner, column COLLATE NOCASE)`` index: **6.1 ms**.

    ⚠️ The ``LIMIT`` is set TWICE per branch and once on the union:
    without the inner ones, each branch would return everything before we
    threw any away; without the outer one, the union would return twice
    too many.
    """
    scope, scope_params = owner_scope(owner, " AND c.owner = ?")
    pattern = f"{needle}%"
    return query(
        f"SELECT * FROM ({_CONTACT_SELECT}"
        f"  WHERE c.last_name LIKE ?{scope}"
        f"  ORDER BY c.last_name, c.first_name LIMIT ?) "
        f"UNION "
        f"SELECT * FROM ({_CONTACT_SELECT}"
        f"  WHERE c.email LIKE ?{scope}"
        f"  ORDER BY c.email LIMIT ?) "
        f"ORDER BY last_name, first_name LIMIT ?",
        (pattern, *scope_params, limit,
         pattern, *scope_params, limit, limit),
    )


def search_deals(needle: str, owner: str | None,
                 limit: int = PER_KIND) -> list[dict]:
    """The deals, by THEIR ACCOUNT's name.

    A deal is called "Renouvellement annuel" at everybody's: searching it
    by its own name would return twelve indistinguishable rows.
    """
    scope, scope_params = owner_scope(owner, " AND a.owner = ?")
    return query(
        "SELECT d.id, d.name, d.stage, d.amount, d.close_date, "
        "a.name AS account_name, a.id AS account_id FROM deals d "
        "JOIN accounts a ON a.id = d.account_id "
        f"WHERE a.name LIKE ?{scope} ORDER BY d.close_date DESC LIMIT ?",
        (f"{needle}%", *scope_params, limit),
    )


def search_everywhere(needle: str,
                      owner: str | None) -> dict[str, list[dict]]:
    """All three families at once. Empty below two characters.

    The floor is not cosmetic: at one letter, each family returns its cap
    and the ranking means nothing.
    """
    needle = needle.strip()
    if len(needle) < 2:
        return {"accounts": [], "contacts": [], "deals": []}
    return {
        "accounts": search_accounts(needle, owner),
        "contacts": search_contacts_by_name(needle, owner),
        "deals": search_deals(needle, owner),
    }


feature = Feature(
    name="search_data",
    kind="data",
    # ``PER_KIND`` is NOT declared: a ``provides`` files its entries by
    # ``__name__``, which an ``int`` does not have — the app map showed a
    # node named "int", and the import guard reduced to the identity of
    # the small integer interned by CPython.
    provides=[search_everywhere],
    uses=["db"],
)
