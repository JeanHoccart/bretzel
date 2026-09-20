"""The workshop — the framework watches itself work.
``py -m examples.atelier.main``.

Its mechanic, in one sentence: **make visible how a task was carried
out**. Not what was produced — the repository already shows that — but
the GESTURE: how many reads before writing, how many times the suite was
re-run, which commands were replayed identically, which tools failed.

Why it exists
--------------
Asked for on 2026-09-12: "I would like a way of seeing the describe,
lint… methods to evaluate the performance of what you use, where you
break, where you are slow, why you do not get it right first time".

An impression cannot be argued with. A measurement can. The app reads the
session transcripts — what Claude Code already writes, with nothing
instrumented — and draws one reading per TASK: a user message through to
the final answer.

The rule it measures
---------------------
Set the same day: "you read, you understand, then you code everything,
you run the check, you correct, and one last one — two global checks, no
more, no endless back-and-forth". It is ``core/phases.CYCLES_MAX``, and
every task is judged on it.

What it exercises of the framework
-----------------------------------
A ``ui.datatable`` in callable mode over 1 856 tasks and 34 000 calls, a
parameter-routed page that shares, a frozen document, and addressable
states. Like ``crm``, it serves twice: it answers a real question and it
puts the framework under constraint.

``main`` is the only file that knows the instance: it ``include``s the
features and seeds the database at first startup.
"""

from __future__ import annotations

from bretzel import Bretzel
from examples.atelier.core import db, era, ingest, phases, scope
from examples.atelier.core.db import init_db, is_seeded
from examples.atelier.core.theme import THEME

# Some feature declarations query their filter choices while they are imported.
# Ensure a fresh checkout has the empty schema before importing those modules.
init_db()

from examples.atelier.features import (
    phases_page,
    sessions,
    shell,
    task_detail,
    tasks,
    tasks_data,
    tools,
    tools_data,
)

app = Bretzel(
    title="Bretzel · Atelier",
    secret_key="dev-atelier-secret-change-me",
    mode="dev",
    theme=THEME,
)

app.include(
    db,                       # infra — the SQLite file and its doors
    phases,                   # logic — a call's classification
    era,                      # logic — since when a task counts
    scope,                    # logic — WHAT the task worked on
    ingest,                   # job — pulling in the transcripts
    shell,                    # layout — the shell and its region
    tasks_data, tools_data,                            # data
    tasks, task_detail, phases_page, tools, sessions,  # pages
)


@app.startup
async def prepare() -> None:
    """Create the schema, and ingest if the database is empty.

    ⚠️ We ingest ONLY if nothing is there. Re-reading 516 MB at every
    startup would make `reload=True` unusable, and the database does not
    go stale: a session already read never changes again. To refresh
    after some work, it is ``py -m examples.atelier.core.ingest``,
    explicitly.
    """
    init_db()
    if not is_seeded():
        from examples.atelier.core.ingest import ingest_all

        ingest_all(reset=False)


def main() -> None:
    app.run(port=8018, reload=True)


if __name__ == "__main__":
    main()
