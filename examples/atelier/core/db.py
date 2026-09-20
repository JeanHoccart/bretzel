"""core/db — infra: the workshop's database, its schema and its doors.

A ``kind="infra"`` feature: it renders nothing and carries no ``State``.
It OWNS the SQLite file and exposes ``query`` / ``scalar`` / ``execute``.
The ``*_data`` features query on top of it; the pages never touch it. The
same split as ``examples/crm``, and for the same reason.

Why a database and not a direct read
-------------------------------------
The transcripts are **516 MB over 70 sessions**. Re-reading them at every
display would make every screen unusable, and above all: the question
being asked is not "how did this task go" but "is this improving".
Comparing needs everything at hand, hence indexed.

It is also what makes this app a useful instrument for the framework: a
``ui.datatable`` in callable mode over tens of thousands of rows, which
is the tier the datatable exists to serve.

⚠️ Sync, not ``aiosqlite`` — for the reason measured in
``examples/crm/core/db.py``: a ``@refreshable`` zone cannot be ``async``,
and in a real app every read lives in a zone. Two data layers would be
exactly the "work around it" these instruments forbid.

No mutable global state (anti-rule 2): ``connect()`` opens a fresh
connection per call.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from bretzel import Feature
from examples.atelier.core.era import MILESTONE

DB_PATH = Path(__file__).with_name("atelier.db")

#: Bumped when the schema changes: ``init_db`` then rebuilds the tables
#: rather than migrating. An OBSERVATION database rebuilds from its source
#: in a few minutes — writing migrations for it would be work that
#: measures nothing.
SCHEMA_VERSION = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    name  TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- A session = a transcript file = a working window.
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    file       TEXT NOT NULL,
    started    TEXT,
    ended      TEXT,
    minutes    REAL    NOT NULL DEFAULT 0,
    tasks      INTEGER NOT NULL DEFAULT 0,
    -- The conversation turns that TRIGGERED no tool: "ok", "go ahead", a
    -- question answered from memory. They are not tasks, and counting
    -- them as such diluted every average — 345 out of 1 857 before they
    -- were separated. We count them here rather than throw them away:
    -- knowing how many exchanges a given piece of work took is
    -- information, simply not the same one.
    exchanges  INTEGER NOT NULL DEFAULT 0,
    calls      INTEGER NOT NULL DEFAULT 0,
    errors     INTEGER NOT NULL DEFAULT 0,
    tokens_in  INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0
);

-- A task = a user message through to the final answer. It is the unit of
-- judgement: it is at that scale that one asks "was this done first
-- time".
CREATE TABLE IF NOT EXISTS tasks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    rank       INTEGER NOT NULL,
    started    TEXT,
    -- ⚠️ The WORKING minutes: from the first tool call to the last.
    -- NOT the wall time between the request and the answer, which
    -- included the time the user was away — measured up to 3 223
    -- minutes, that is 53 hours, on a task that took a quarter of an
    -- hour. A column that lies by two orders of magnitude is no longer
    -- read, it is ignored.
    minutes    REAL    NOT NULL DEFAULT 0,
    request    TEXT    NOT NULL DEFAULT '',
    calls      INTEGER NOT NULL DEFAULT 0,
    errors     INTEGER NOT NULL DEFAULT 0,
    cycles     INTEGER NOT NULL DEFAULT 0,
    strip      TEXT    NOT NULL DEFAULT '',
    verdict    TEXT    NOT NULL DEFAULT '',
    tokens     INTEGER NOT NULL DEFAULT 0,
    -- WHAT the task worked on. It is what separates "building the base
    -- layer" from "writing an app", and without which the two are judged
    -- by the same yardstick — which makes sense for neither.
    scope      TEXT    NOT NULL DEFAULT 'other',
    -- Did we READ before writing? Time 1 of the four-times rule.
    read_first INTEGER NOT NULL DEFAULT 0,
    -- Did we ask for the SURFACE (`describe`) before writing? That is the
    -- question "do I consult, or do I invent".
    surface    INTEGER NOT NULL DEFAULT 0,
    -- Did we have the app CONTRACT judged (`check --deep`)? That is the
    -- question "is `Feature()` an asset or cosmetics".
    contract   INTEGER NOT NULL DEFAULT 0
);

-- A tool call, with its phase. This is the detail table: it carries a
-- task's strip and the ranking by tool.
CREATE TABLE IF NOT EXISTS calls (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id  INTEGER NOT NULL,
    rank     INTEGER NOT NULL,
    at       TEXT,
    tool     TEXT NOT NULL,
    phase    TEXT NOT NULL,
    command  TEXT NOT NULL DEFAULT '',
    error    INTEGER NOT NULL DEFAULT 0,
    detail   TEXT NOT NULL DEFAULT '',
    target   TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
CREATE INDEX IF NOT EXISTS idx_tasks_verdict ON tasks(verdict);
CREATE INDEX IF NOT EXISTS idx_tasks_scope   ON tasks(scope);
CREATE INDEX IF NOT EXISTS idx_calls_task    ON calls(task_id, rank);
CREATE INDEX IF NOT EXISTS idx_calls_tool    ON calls(tool);
CREATE INDEX IF NOT EXISTS idx_calls_phase   ON calls(phase);
"""


#: ⚠️ WHAT THE SCREENS READ. The tables carry everything that was
#: ingested; the views stop at :mod:`core.era`'s milestone. A view and
#: not a copied clause: the data features make twenty-six reads, hence
#: twenty-six chances to forget the cut-off — and a statistic that
#: silently includes tasks from before the instruments is exactly the
#: wrong figure we are trying to avoid.
#:
#: The ingest, for its part, writes into the TABLES: nothing is lost, and
#: moving the milestone back by a day needs no re-ingest of 516 MB.
VIEWS = f"""
DROP VIEW IF EXISTS tasks_era;
DROP VIEW IF EXISTS calls_era;
DROP VIEW IF EXISTS sessions_era;

CREATE VIEW tasks_era AS
    SELECT * FROM tasks WHERE started >= '{MILESTONE}';

CREATE VIEW calls_era AS
    SELECT c.* FROM calls c
    JOIN tasks t ON t.id = c.task_id
    WHERE t.started >= '{MILESTONE}';

CREATE VIEW sessions_era AS
    SELECT * FROM sessions
    WHERE id IN (SELECT session_id FROM tasks_era);
"""

#: Start over, without touching the FILE. Windows locks an open file: as
#: long as a workshop window is displayed, an ``unlink`` raises
#: ``WinError 32`` and the ingest fails. A job that requires closing the
#: app it feeds is useless — measured on 2026-09-12, two servers open, no
#: re-ingest possible. The indexes fall with their table.
DROP_ALL = """
DROP VIEW IF EXISTS tasks_era;
DROP VIEW IF EXISTS calls_era;
DROP VIEW IF EXISTS sessions_era;
DROP TABLE IF EXISTS calls;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS meta;
"""


def connect() -> sqlite3.Connection:
    """A fresh connection (rows with dict-like access)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    """A SELECT's rows."""
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def scalar(sql: str, params: tuple = ()) -> Any:
    """The first column of the first row — ``None`` if nothing."""
    with connect() as conn:
        row = conn.execute(sql, params).fetchone()
    return None if row is None else row[0]


def execute(sql: str, params: tuple = ()) -> None:
    """A write."""
    with connect() as conn:
        conn.execute(sql, params)


def init_db(*, reset: bool = False) -> None:
    """Create the schema. ``reset`` starts again from empty tables.

    The schema version is re-read at every startup: a database written by
    an earlier version is thrown away rather than migrated, because it
    rebuilds from the transcripts.
    """
    with connect() as conn:
        if reset:
            conn.executescript(DROP_ALL)
        conn.executescript(SCHEMA)
        conn.executescript(VIEWS)
        # ⚠️ The read itself can RAISE, and that is a stale schema too.
        # ``CREATE TABLE IF NOT EXISTS`` leaves an older ``meta`` alone,
        # so a version bump that renamed its columns gets
        # ``no such column`` here — before the comparison below could
        # ever say so. Met on 2026-09-20, renaming the schema to
        # English: the app would not start at all, on a database it was
        # perfectly able to rebuild.
        try:
            current = conn.execute(
                "SELECT value FROM meta WHERE name = 'schema_version'"
            ).fetchone()
        except sqlite3.OperationalError:
            current = (str(SCHEMA_VERSION - 1),)
        if current is not None and int(current[0]) != SCHEMA_VERSION:
            conn.executescript(DROP_ALL)
            conn.executescript(SCHEMA)
            conn.executescript(VIEWS)
        conn.execute(
            "INSERT OR REPLACE INTO meta (name, value) "
            "VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )


def is_seeded() -> bool:
    """Is there anything to look at?

    The app must be able to start on an EMPTY database and say so, rather
    than render hollow screens: the transcript is an external source, it
    may not have been ingested yet.
    """
    return bool(DB_PATH.exists() and (scalar("SELECT COUNT(*) FROM tasks") or 0))


feature = Feature(
    name="db",
    kind="infra",
    uses=["era"],
    provides=[connect, query, scalar, execute, init_db, is_seeded],
)
