"""features/reports_data — data: the reports' aggregates, in SQL.

Serves screen 7. Each of these five reads is a ``GROUP BY`` — none loads
rows to count in Python. It is the screen's point: the 17 apps feed their
charts with hand-made lists, so the question "does a chart hold up on a
real aggregate?" had never been asked.

Every read is bounded: a categorical axis no longer reads beyond a dozen
bars, and a scatter of 50 000 points is a smudge.
"""

from __future__ import annotations

from datetime import timedelta

from bretzel import Feature
from examples.crm.core.db import owner_scope, query
from examples.crm.core.domain import OPEN_STAGES, TODAY


def pipeline_by_stage_and_owner(
    owner: str | None, top_owners: int = 3
) -> list[dict]:
    """The open amount by (stage, owner) — the bar chart's matrix.

    Bounded to the ``top_owners`` largest holders: a bar grouped by owner
    becomes unreadable beyond three or four series, and the chart is not
    a table.
    """
    placeholders = ",".join("?" * len(OPEN_STAGES))
    if owner is not None:
        # Scoped: a single series, and the "top" no longer has a point.
        owners = [owner]
    else:
        owners = [
            r["owner"] for r in query(
                f"SELECT owner, SUM(amount) AS total FROM deals "
                f"WHERE stage IN ({placeholders}) "
                f"GROUP BY owner ORDER BY total DESC LIMIT ?",
                (*OPEN_STAGES, top_owners),
            )
        ]
    if not owners:
        return []
    return query(
        f"SELECT stage, owner, SUM(amount) AS total FROM deals "
        f"WHERE stage IN ({placeholders}) "
        f"AND owner IN ({','.join('?' * len(owners))}) "
        f"GROUP BY stage, owner",
        (*OPEN_STAGES, *owners),
    )


def activities_by_month(owner: str | None,
                        months: int = 12) -> list[dict]:
    """The number of activities per month, oldest to most recent.

    ``substr(at, 1, 7)`` rather than ``strftime``: the dates are stored
    in ISO, so the first seven characters ARE the month — and a string
    prefix groups without converting 60 000 rows to dates.
    """
    since = (TODAY - timedelta(days=31 * months)).isoformat()
    # The first of the month is computed BY THE QUERY: the chart needs a
    # date, not the string "2026-08" it would read as a category — and
    # converting 12 rows in Python would have put a presentation helper
    # in a data feature.
    scope, scope_params = owner_scope(owner, " AND owner = ?")
    return query(
        "SELECT substr(at, 1, 7) AS month, substr(at, 1, 7) || '-01' AS day, "
        "COUNT(*) AS n FROM activities "
        f"WHERE at >= ? AND at <= ?{scope} GROUP BY month ORDER BY month",
        (since, TODAY.isoformat(), *scope_params),
    )


def accounts_by_industry(owner: str | None, limit: int = 8) -> list[dict]:
    """The accounts' breakdown by sector, largest first."""
    scope, scope_params = owner_scope(owner, "WHERE owner = ? ")
    return query(
        "SELECT industry, COUNT(*) AS n FROM accounts "
        f"{scope}GROUP BY industry ORDER BY n DESC LIMIT ?",
        (*scope_params, limit),
    )


def arr_versus_contacts(owner: str | None,
                        sample: int = 250) -> list[dict]:
    """A sample (number of contacts, ARR) — the correlation scatter.

    The sample is taken **before** the join, in a subquery: capping after
    the aggregation would group the 50 000 accounts with their 120 000
    contacts only to keep 250 of them.

    ⚠️ It used to be ``WHERE a.id <= ?``, which is a sample only if the
    identifiers have no gaps — and above all, scoped by owner, it
    returned only a sixth of the points. A ``LIMIT`` in the subquery
    keeps the performance property and stays correct in both cases.
    """
    scope, scope_params = owner_scope(owner, "WHERE owner = ? ")
    return query(
        "SELECT a.arr, COUNT(c.id) AS contacts FROM "
        f"(SELECT id, arr FROM accounts {scope}ORDER BY id LIMIT ?) a "
        "LEFT JOIN contacts c ON c.account_id = a.id "
        "GROUP BY a.id",
        (*scope_params, sample),
    )


def weekly_activity(owner: str | None, weeks: int = 12) -> list[int]:
    """The activity volume of the last ``weeks`` weeks, in order.

    Returns a list of integers — the shape ``ui.sparkline`` expects, and
    the only one of the five with no axis: a sparkline shows a shape, not
    values. The empty weeks are REINSERTED at zero: a ``GROUP BY`` does
    not return the gaps, and a curve that skips them shortens time.
    """
    since = TODAY - timedelta(weeks=weeks)
    scope, scope_params = owner_scope(owner, " AND owner = ?")
    rows = query(
        "SELECT strftime('%Y-%W', at) AS semaine, COUNT(*) AS n "
        f"FROM activities WHERE at >= ? AND at <= ?{scope} GROUP BY semaine",
        (since.isoformat(), TODAY.isoformat(), *scope_params),
    )
    counts = {r["semaine"]: r["n"] for r in rows}
    # ``weeks + 1`` buckets: the SQL window starts at
    # ``TODAY - 12 weeks`` and runs to today, so it covers THIRTEEN — the
    # first is partial, the last is the current week. Stopping at twelve
    # threw away 485 activities out of 12 761 measured, and the total
    # shown under the sparkline was exactly that gap.
    out: list[int] = []
    for offset in range(weeks + 1):
        day = since + timedelta(weeks=offset)
        out.append(counts.get(f"{day.year}-{day.strftime('%W')}", 0))
    return out


feature = Feature(
    name="reports_data",
    kind="data",
    provides=[pipeline_by_stage_and_owner, activities_by_month,
              accounts_by_industry, arr_versus_contacts, weekly_activity],
    uses=["db"],
)
