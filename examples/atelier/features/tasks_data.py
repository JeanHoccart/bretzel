"""features/tasks_data — data: the tasks repo, in SQL.

The heart is :func:`load_tasks`, the ``ui.datatable``'s callable
``rows=``: it receives a ``Query`` (sort, page, search, filters) and
translates it into ONE query. 1 856 tasks and 34 000 calls, so the list
tier — which loads everything into Python at every keystroke — would not
hold.

The two guards, the same as in the CRM and for the same reasons:

- ``sort_key`` and the filter keys go through an **allowlist** before
  entering the SQL. A sort key comes from the browser; interpolated as
  is, it is an injection;
- ``filters[key] == []`` (everything unticked) must match ZERO rows, not
  "no filter". The two cases look alike enough to get wrong.

⚠️ Every read goes through the VIEWS (``tasks_era``, ``calls_era``,
``sessions_era``), never the tables: that is where :mod:`core.era`'s
cut-off lives, and a query addressing the table would silently count
tasks from before the instruments. Gated by ``test_atelier_era``.
"""

from __future__ import annotations

from typing import Any

from bretzel import Feature
from bretzel.components import Query
from examples.atelier.core.db import query, scalar
from examples.atelier.core.phases import PHASES
from examples.atelier.core.scope import APP

#: The columns we accept to sort on. Everything else falls back on the
#: default — an unknown key must not reach the SQL.
SORTABLE = {
    "started", "minutes", "calls", "errors", "cycles", "tokens",
    "verdict", "session_id", "rank", "scope",
}

#: ⚠️ The clause that reduces everything to the APPS. It lives here,
#: once: it is the question asked — "I do not want to evaluate the time
#: spent on the framework, I want your performance on the apps" — and two
#: copies would end up no longer saying the same thing.
APPS_ONLY = f"scope LIKE '{APP}%'"

#: The possible verdicts, for the filter. Copied from
#: :func:`phases.verdict` — if one changes, the examples' consistency
#: gate will say so before the screen does.
VERDICTS = ("first time", "corrected", "back-and-forth")


def where_clause(q: Query) -> tuple[str, list[Any]]:
    """The ``WHERE`` and its parameters — never a value interpolation."""
    clauses: list[str] = []
    params: list[Any] = []
    if q.search:
        clauses.append("(request LIKE ? OR session_id LIKE ?)")
        pattern = f"%{q.search}%"
        params += [pattern, pattern]
    scopes = q.filters.get("scope")
    if scopes is not None:
        if not scopes:
            return "WHERE 1 = 0", []
        clauses.append(f"scope IN ({','.join('?' * len(scopes))})")
        params += list(scopes)
    verdicts = q.filters.get("verdict")
    if verdicts is not None:
        if not verdicts:
            # Everything unticked = no rows. Without this case, an
            # empty filter would read as "no filter" and return the whole
            # table.
            return "WHERE 1 = 0", []
        clauses.append(f"verdict IN ({','.join('?' * len(verdicts))})")
        params += list(verdicts)
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), params


def load_tasks(q: Query) -> tuple[list[dict], int]:
    """One page of tasks, and the total that situates it."""
    where, params = where_clause(q)
    key = q.sort_key if q.sort_key in SORTABLE else "started"
    direction = "ASC" if q.sort_dir == "asc" else "DESC"
    total = scalar(f"SELECT COUNT(*) FROM tasks_era {where}", tuple(params)) or 0

    limit = "" if q.for_export else "LIMIT ? OFFSET ?"
    bounds = [] if q.for_export else [q.per_page, (q.page - 1) * q.per_page]
    rows = query(
        f"SELECT id, session_id, rank, started, minutes, request, calls, "
        f"errors, cycles, strip, verdict, tokens, scope, read_first, "
        f"surface, contract FROM tasks_era {where} "
        f"ORDER BY {key} {direction}, id {direction} {limit}",
        tuple(params + bounds),
    )
    return [dict(r) for r in rows], int(total)


def task(task_id: int) -> dict | None:
    """A task by its identifier — ``None`` if it does not exist."""
    rows = query("SELECT * FROM tasks_era WHERE id = ?", (task_id,))
    return dict(rows[0]) if rows else None


def calls_of(task_id: int) -> list[dict]:
    """A task's calls, in the order they were made."""
    return [
        dict(r)
        for r in query(
            "SELECT rank, at, tool, phase, command, error, detail "
            "FROM calls_era WHERE task_id = ? ORDER BY rank",
            (task_id,),
        )
    ]


def summary(apps_only: bool = False) -> dict[str, Any]:
    """The numbers at the top of the screen, for everything or for the
    APPS alone.

    ⚠️ The flag is not a display comfort: mixing the two makes the figure
    wrong in both directions. Building the base layer requires reading it
    whole and verifying often — healthy work that looks like
    back-and-forth. Writing an app with the framework should demand
    almost nothing; if it does demand, it is the framework's promise that
    is not holding, or me not using it.
    """
    where = f"WHERE {APPS_ONLY}" if apps_only else ""
    total = scalar(f"SELECT COUNT(*) FROM tasks_era {where}") or 0
    if not total:
        return {"tasks": 0, "first_time": 0, "first_time_share": 0,
                "mean_cycles": 0.0, "calls": 0, "errors": 0,
                "sessions": 0, "surface": 0, "contract": 0, "read_first": 0}
    andor = "AND" if where else "WHERE"
    first = scalar(
        f"SELECT COUNT(*) FROM tasks_era {where} {andor} verdict = 'first time'"
    ) or 0
    return {
        "sessions": scalar("SELECT COUNT(*) FROM sessions_era") or 0,
        "tasks": total,
        "calls": scalar(f"SELECT SUM(calls) FROM tasks_era {where}") or 0,
        "errors": scalar(f"SELECT SUM(errors) FROM tasks_era {where}") or 0,
        "first_time": first,
        "first_time_share": round(100 * first / total),
        "mean_cycles": round(
            scalar(f"SELECT AVG(cycles) FROM tasks_era {where}") or 0, 1
        ),
        # The three METHOD gestures, as a share of tasks. It is the
        # answer to "do the tools serve, or decorate".
        "read_first": round(
            100 * (scalar(f"SELECT SUM(read_first) FROM tasks_era {where}") or 0)
            / total
        ),
        "surface": round(
            100 * (scalar(f"SELECT SUM(surface) FROM tasks_era {where}") or 0)
            / total
        ),
        "contract": round(
            100 * (scalar(f"SELECT SUM(contract) FROM tasks_era {where}") or 0)
            / total
        ),
    }


def by_scope() -> list[dict]:
    """One row per scope — the comparison the user asks for."""
    return [
        dict(r)
        for r in query(
            "SELECT scope, COUNT(*) tasks, ROUND(AVG(cycles), 2) cycles, "
            "SUM(verdict = 'first time') first, "
            "SUM(surface) surface, SUM(contract) contract, "
            "SUM(read_first) read_first "
            "FROM tasks_era GROUP BY scope HAVING tasks >= 2 "
            "ORDER BY tasks DESC"
        )
    ]


def known_scopes() -> list[str]:
    """The scopes really present — for the table's filter."""
    return [
        r["scope"]
        for r in query(
            "SELECT scope, COUNT(*) n FROM tasks_era GROUP BY scope "
            "HAVING n >= 2 ORDER BY n DESC"
        )
    ]


def by_phase() -> list[dict]:
    """The breakdown of calls by phase — the work profile.

    ⚠️ ``other`` is part of it and is not hidden: it is the heuristic's
    admission rate. If it grows, it is the classification that needs
    fixing, not the measurement that should be believed.
    """
    total = scalar("SELECT COUNT(*) FROM calls_era") or 1
    counts = {
        r["phase"]: r["n"]
        for r in query("SELECT phase, COUNT(*) n FROM calls_era GROUP BY phase")
    }
    return [
        {
            "phase": phase,
            "calls": counts.get(phase, 0),
            "share": round(100 * counts.get(phase, 0) / total, 1),
        }
        for phase in PHASES
    ]


feature = Feature(
    name="tasks_data",
    kind="data",
    uses=["db", "phases", "scope"],
    provides=[load_tasks, task, calls_of, summary, by_phase,
              by_scope, known_scopes],
)
