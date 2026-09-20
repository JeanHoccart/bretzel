"""features/tools_data — data: the repo of the tools and their failures.

Two questions, two queries:

- **which tools, and which ones fail** — that is "where it breaks";
- **do the FRAMEWORK's tools serve** — ``describe``, ``check``,
  ``probe`` were built to avoid round trips; if they are never called,
  they can avoid nothing.

The second is the one that motivated the app: one can ship a whole layer
7 and carry on opening files by hand.

⚠️ Every read goes through the VIEWS (``tasks_era``, ``calls_era``,
``sessions_era``), never the tables — cf. :mod:`core.era`. Gated by
``test_atelier_era``.
"""

from __future__ import annotations

from bretzel import Feature
from examples.atelier.core.db import query, scalar

#: Layer 7's three doors, recognised inside a command. The pattern is
#: the one really typed: ``py -m bretzel.cli.main describe …``.
FRAMEWORK_TOOLS = {
    "describe": "%cli.main describe%",
    "check": "%cli.main check%",
    "probe": "%cli.main probe%",
}


def by_tool() -> list[dict]:
    """Each tool: how many calls, how many failures, what share."""
    rows = query(
        "SELECT tool, COUNT(*) n, SUM(error) e FROM calls_era "
        "GROUP BY tool ORDER BY n DESC"
    )
    return [
        {
            "tool": r["tool"],
            "calls": r["n"],
            "errors": r["e"] or 0,
            "rate": round(100 * (r["e"] or 0) / r["n"], 1) if r["n"] else 0.0,
        }
        for r in rows
    ]


def failures(limit: int = 60) -> list[dict]:
    """The latest failed calls — "where you break", literally."""
    return [
        dict(r)
        for r in query(
            "SELECT c.tool, c.phase, c.command, c.detail, c.task_id, "
            "t.session_id FROM calls_era c JOIN tasks_era t ON t.id = c.task_id "
            "WHERE c.error = 1 ORDER BY c.id DESC LIMIT ?",
            (limit,),
        )
    ]


def framework_usage() -> list[dict]:
    """How many times each layer-7 tool served.

    Compared to the number of TASKS and not of calls: the question is not
    "how many times" in the absolute, it is "on what share of the work do
    I use it".
    """
    tasks = scalar("SELECT COUNT(*) FROM tasks_era") or 1
    out = []
    for name, pattern in FRAMEWORK_TOOLS.items():
        calls = scalar(
            "SELECT COUNT(*) FROM calls_era WHERE command LIKE ?", (pattern,)
        ) or 0
        touched = scalar(
            "SELECT COUNT(DISTINCT task_id) FROM calls_era WHERE command LIKE ?",
            (pattern,),
        ) or 0
        out.append({
            "tool": name,
            "calls": calls,
            "tasks": touched,
            "share": round(100 * touched / tasks, 1),
        })
    return out


def replayed(limit: int = 25) -> list[dict]:
    """The commands re-run IDENTICALLY within one task.

    It is the clearest trace of trial and error: re-running the same
    thing hoping for another verdict. A second run after a correction is
    normal; five are not.
    """
    return [
        dict(r)
        for r in query(
            "SELECT command, task_id, COUNT(*) n FROM calls_era "
            "WHERE command <> '' GROUP BY task_id, command "
            "HAVING n >= 3 ORDER BY n DESC LIMIT ?",
            (limit,),
        )
    ]


def session_profile() -> list[dict]:
    """One row per session: enough to see whether the rhythm improves.

    ⚠️ The totals are RECOMPUTED on the era's tasks, not read from
    ``sessions``' columns: those count the whole session, so a session
    straddling the milestone would show forty tasks for five visible
    rows.
    """
    return [
        dict(r)
        for r in query(
            "SELECT s.id, s.started, s.minutes, s.exchanges, "
            "(SELECT COUNT(*) FROM tasks_era WHERE session_id = s.id) tasks, "
            "(SELECT SUM(calls) FROM tasks_era WHERE session_id = s.id) calls, "
            "(SELECT SUM(errors) FROM tasks_era WHERE session_id = s.id) errors, "
            "(SELECT AVG(cycles) FROM tasks_era WHERE session_id = s.id) cycles, "
            "(SELECT COUNT(*) FROM tasks_era WHERE session_id = s.id "
            " AND verdict = 'first time') first "
            "FROM sessions_era s ORDER BY s.started DESC"
        )
    ]


feature = Feature(
    name="tools_data",
    kind="data",
    uses=["db"],
    provides=[by_tool, failures, framework_usage, replayed, session_profile],
)
