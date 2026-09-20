"""features/deals_data — data: the opportunities repo, and the reordering.

Serves screen 1 (the pipeline). Two things live there:

- :func:`pipeline_deals`, the read window — an owner's OPEN deals whose
  due date falls inside the horizon, grouped by stage;
- :func:`move_deal`, the write — what a drop applies.

**Why a window.** 12 000 deals, of which ~9 400 open: a kanban rendering
everything would make 9 400 cards. A salesperson looks at THEIR pipeline
over a horizon. The window is therefore the business gesture, not a
performance plaster — and it is what gives columns of ~100 cards, the
ones that scroll.

**The rank.** ``position`` is an integer per stage, seeded with a step of
64. Inserting between two cards takes the MIDPOINT of the two
neighbouring ranks; when there is no midpoint left (two consecutive
ranks), the whole stage is renumbered and we start again. It is the
classic ordered-list algorithm: it avoids rewriting 2 000 rows at every
gesture, without ever letting two cards fight over a rank.
"""

from __future__ import annotations

from bretzel import Feature
from bretzel.components import Move
from bretzel.state import AppState, field
from examples.crm.core.db import execute, owner_scope, query
from examples.crm.core.domain import OPEN_STAGES, POSITION_STEP, TODAY


class DealsRev(AppState):
    """Deals revision — bumped at every write."""

    rev: int = field(default=0, merge="add")


def horizon_date(days: int) -> str:
    from datetime import timedelta

    return (TODAY + timedelta(days=days)).isoformat()


#: The cap on cards per column. Measured: without it, the first owner's
#: 90-day window returns **1 093 cards** and a **1.2 MB** page. The manual
#: rank IS the priority order, so cutting from the top cuts in the right
#: place — and the column header still says "50 out of 564".
PER_COLUMN = 50


def pipeline_deals(
    owner: str | None, horizon_days: int, *, limit: int = PER_COLUMN
) -> dict[str, list[dict]]:
    """``owner``'s open deals due within ``horizon_days`` days.

    A single query for the four columns, joined to the account's name: a
    query per stage is four connections for one screen. The cap applies
    PER stage (partitioned ``ROW_NUMBER``), not on the total — otherwise
    the first column would eat the other three's window.
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
    """Each stage's count and amount INSIDE the window, with no cap.

    Serves a column header's "50 out of 393": without it, a cap would
    suggest the pipeline stops at what it shows — and the sum displayed
    would only be that of the visible cards.
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
    """``{stage: {n, total}}`` over the open deals, WITHOUT a horizon.

    Serves the real-time screen. It ignores the horizon — what a second
    tab must see move is a stage's total, not one screen's 90-day window.
    It cannot ignore the owner for all that: a global counter would tell
    a salesperson the others' deal volume, and the fact that it is
    aggregated does not make it public data.
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
    """The first deals of each column, in kanban order.

    The rank is the only thing drag and drop writes — hence the only
    thing that testifies, in another tab, that somebody has just moved
    something.

    **``UNION ALL`` and not ``ROW_NUMBER``**, unlike
    :func:`pipeline_deals`. The partitioned window numbers ALL the open
    deals and joins each to its account before throwing 99 % away:
    ``EXPLAIN QUERY PLAN`` shows a ``USE TEMP B-TREE FOR ORDER BY`` there,
    and the measurement says **32 ms for twelve rows**. Four stacked
    ``LIMIT`` let the ``(stage, position)`` index do its work: **0.1 ms**.
    The difference comes from the cap being tiny here — over there it is
    50 per column and the partition pays for itself.
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
    """A deal, scoped. A deal identifier arrives from the BROWSER (it is
    a drop's ``item_key``): without scoping, one could move somebody
    else's deal by forging a key."""
    scope, scope_params = owner_scope(owner, " AND owner = ?")
    rows = query(f"SELECT * FROM deals WHERE id = ?{scope}",
                 (deal_id, *scope_params))
    return rows[0] if rows else None


def account_deals(account_id: int, limit: int = 25) -> list[dict]:
    """An account's deals, FURTHEST due date first.

    ``DESC`` on ISO dates brings the future up: what is still in play
    comes before what is overdue, and that is what one wants to read on
    an account sheet.
    """
    return query(
        "SELECT * FROM deals WHERE account_id = ? "
        "ORDER BY close_date DESC LIMIT ?",
        (account_id, limit),
    )


def renumber_stage(stage: str) -> None:
    """Re-space a stage's ranks with a step of :data:`POSITION_STEP`.

    Called only when two neighbours have no midpoint left — so rarely. A
    single query: reading 2 000 rows into Python to rewrite them one by
    one would cost 2 000 round trips.
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
    """The rank to give between two neighbours, or ``None`` if there is
    none left."""
    if before is None and after is None:
        return POSITION_STEP
    if before is None:
        # No positivity guard: nothing requires a positive rank (the
        # order is ``ORDER BY position, id`` on 64-bit integers), and
        # refusing negatives renumbered the whole stage from the second
        # insertion at the head — the very gesture a kanban list receives
        # most.
        return after - POSITION_STEP
    if after is None:
        return before + POSITION_STEP
    if after - before < 2:
        return None                       # no midpoint left: renumber
    return (before + after) // 2


def move_deal(m: Move, *, owner: str | None, horizon_days: int) -> bool:
    """Apply a drop. Returns ``False`` when the move is refused.

    Refusing is mutating nothing: the browser has already moved the card,
    so the server render that contradicts it puts it back on its own
    (``Move``).

    The target zone's window is RE-READ here, from the caller's view —
    not received from them. The neighbouring ranks must be those of the
    cards the reader had before their eyes; a caller passing the whole
    stage would compute invisible neighbours and drop the card in the
    wrong place, with no error. The invariant belongs to this function.
    """
    if m.to_zone not in OPEN_STAGES:
        return False
    window = pipeline_deals(owner, horizon_days).get(m.to_zone, [])
    deal = (get_deal(int(m.item_key), owner)
            if m.item_key.isdigit() else None)
    if deal is None:
        return False

    # The window as it will be AFTER the drop, without the card moved:
    # in an internal reorder it is still there, in a transfer it never
    # was.
    others = [d for d in window if d["id"] != deal["id"]]
    index = max(0, min(m.to_index, len(others)))
    before = others[index - 1]["position"] if index > 0 else None
    after = others[index]["position"] if index < len(others) else None

    slot = slot_between(before, after)
    if slot is None:
        renumber_stage(m.to_zone)
        # The ranks have changed: re-read the two neighbours by their id,
        # not by their old value.
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
