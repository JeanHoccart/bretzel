"""core/db — infra: the SQLite file, its schema, its indexes and its seed.

A ``kind="infra"`` feature: it renders nothing and carries no Bretzel
``State`` — it OWNS an external resource (the SQLite file) and exposes
the access doors (``query`` / ``scalar`` for reads, ``execute`` for
writes). The ``*_data`` features query on top of it; the pages never
touch it.

This example uses ``sqlite3`` and synchronous functions. That choice is
not a limit of ``@refreshable``: the framework also supports
asynchronous zone bodies.

**Volumes.** ~262 000 rows seeded once (see ``seed.py``), not 20: below
that, the datatable in callable mode has no reason to exist and no
layout is under constraint.

**The user accounts live in the same database**, table ``users``. The
framework does not model a user beyond their identifier — it only knows
"this request belongs to X", in a signed cookie — so the profile, the
role and the password belong to the app. ``owner`` there is the join key
with the data: it is the name read in ``accounts.owner``.

No mutable global state (anti-rule 2): ``connect()`` opens a fresh
connection per call.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from bretzel import Feature

DB_PATH = Path(__file__).with_name("crm.db")

#: Bumped when the schema or the seed changes — ``init_db`` then rebuilds
#: the file. Without this marker, seeding 262 000 rows at every startup
#: would make ``reload=True`` unusable.
SEED_VERSION = 7


def connect() -> sqlite3.Connection:
    """A fresh connection to the SQLite file (rows with dict-like access)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def owner_scope(owner: str | None, clause: str) -> tuple[str, tuple]:
    """``(SQL fragment, parameters)`` to scope a read — or nothing.

    Eleven of the CRM's reads carried the same two lines, the second of
    which was **identical to the character** everywhere. What varies —
    the column qualifier, the ``AND`` or the ``WHERE`` — stays written
    OUT IN THE OPEN at the call site, on purpose: the scoping must show
    in the query one re-reads, not hide behind a function name.

    ``owner=None`` means **every owner**, and it is a privilege
    (``access.visible_owner``). ``""`` matches nobody.
    """
    return ("", ()) if owner is None else (clause, (owner,))


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Run a SELECT and return a list of dicts — the READ door."""
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def scalar(sql: str, params: tuple = ()) -> Any:
    """The first column of the first row — for the ``COUNT(*)``.

    A separate door rather than a ``query(...)[0]["count"]`` copied
    everywhere: the datatable's callable mode asks for a total at EVERY
    render, and it is the place where a ``dict`` built for an integer
    would show.
    """
    conn = connect()
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row is not None else None
    finally:
        conn.close()


#: The SQL verbs for which ``lastrowid`` means something.
_ROWID_VERBS = frozenset({"INSERT", "REPLACE"})


def execute(sql: str, params: tuple = ()) -> int:
    """Run an INSERT / UPDATE / DELETE, commit, and return the
    ``lastrowid`` (INSERT) or the number of rows touched — the WRITE door.

    ⚠️ **The verb is read explicitly**, and it is a fix. The code said
    ``lastrowid if lastrowid is not None else rowcount``, which looks
    reasonable and is not: after an ``UPDATE``, sqlite3 leaves
    ``lastrowid`` at ``0`` on a fresh connection — never ``None``. So an
    ``UPDATE`` always returned ``0``, and the first function using it to
    say "refused" (``update_contact``) also refused what it had just
    written. The bug had been latent since slice 1: nobody read an
    ``UPDATE``'s return.

    Reactivity note: a DB write touches NO typed ``State``, so the
    re-render engine does not "see" it. The repos bump a revision token
    on an ``AppState`` afterwards — that is what the
    ``@refreshable(deps=[…Rev])`` zones observe.
    """
    verb = sql.lstrip().split(None, 1)[0].upper()
    conn = connect()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid if verb in _ROWID_VERBS else cur.rowcount
    finally:
        conn.close()


_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value INTEGER);

CREATE TABLE users (
    id            INTEGER PRIMARY KEY,
    login         TEXT    NOT NULL UNIQUE,
    display_name  TEXT    NOT NULL,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL,
    owner         TEXT    NOT NULL
);

CREATE TABLE accounts (
    id         INTEGER PRIMARY KEY,
    name       TEXT    NOT NULL,
    industry   TEXT    NOT NULL,
    country    TEXT    NOT NULL,
    city       TEXT    NOT NULL,
    size       TEXT    NOT NULL,
    arr        INTEGER NOT NULL,
    owner      TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE TABLE contacts (
    id         INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    first_name TEXT    NOT NULL,
    last_name  TEXT    NOT NULL,
    email      TEXT    NOT NULL,
    phone      TEXT    NOT NULL,
    title      TEXT    NOT NULL,
    status     TEXT    NOT NULL,
    -- Denormalised from ``accounts.owner``, the way ``activities``
    -- already carries its own ``account_id``. ⚠️ This is NOT comfort:
    -- scoping contacts by ``a.owner`` forces the join into the COUNT AND
    -- into the SELECT, and SQLite then starts driving from ``accounts``
    -- and sorting the survivors. Measured on page 1 of screen 3:
    -- **4.8 ms → 100.5 ms**. With the column here and its index:
    -- **0.08 ms**. The seed fills it from the account, so the two cannot
    -- diverge.
    owner      TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE TABLE deals (
    id         INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    name       TEXT    NOT NULL,
    stage      TEXT    NOT NULL,
    amount     INTEGER NOT NULL,
    owner      TEXT    NOT NULL,
    close_date TEXT    NOT NULL,
    position   INTEGER NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE TABLE activities (
    id         INTEGER PRIMARY KEY,
    contact_id INTEGER NOT NULL REFERENCES contacts(id),
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    kind       TEXT    NOT NULL,
    subject    TEXT    NOT NULL,
    at         TEXT    NOT NULL,
    owner      TEXT    NOT NULL
);

CREATE TABLE notes (
    id         INTEGER PRIMARY KEY,
    contact_id INTEGER NOT NULL REFERENCES contacts(id),
    body       TEXT    NOT NULL,
    author     TEXT    NOT NULL,
    at         TEXT    NOT NULL
);
"""

#: The indexes the screens really ask for, measured with
#: ``EXPLAIN QUERY PLAN`` rather than guessed.
#:
#: **One index per sortable column of the accounts datatable.** Without
#: them, ``ORDER BY city`` plans ``SCAN accounts`` + ``USE TEMP B-TREE``:
#: 50 000 rows sorted to return 25, measured at 12-16 ms per sort click
#: against 0.3 ms with. The list must stay equal to ``SORTABLE`` in
#: ``accounts_data`` — a sortable column without an index is a silent
#: scan.
#:
#: **``activities(at, kind, owner)``** serves screen 6, which always
#: reads by date window: the per-contact index cannot serve a ``BETWEEN``
#: on ``at``, it is ordered by ``contact_id`` first. Three columns, not
#: two — the screen offers a filter by owner, and without it in the index
#: the three zones lose the covering: 1.6 ms measured against 24 ms.
#:
#: **The three ``COLLATE NOCASE`` indexes** are the global search's, and
#: they are not duplicates of their binary twins. ``LIKE`` is
#: case-insensitive by default in SQLite (``case_sensitive_like`` OFF),
#: so the optimisation turning ``LIKE 'word%'`` into an index range needs
#: a NOCASE index — a BINARY index cannot serve it, and the plan falls
#: back to ``SCAN``. Measured: the contact search goes from **898 ms to
#: 43.7 ms**, the account one from 7.65 ms to 0.05 ms. The binary indexes
#: stay, for their part, for the ``ORDER BY``, which are indeed binary.
#:
#: **``contacts(status, last_name, first_name)`` is composite**, and the
#: order of the three columns is the point: filtering by status then
#: sorting by name used ``idx_contacts_status`` and re-sorted 30 000 rows
#: in memory — 147 ms. The composite covers the filter AND the order:
#: 0.2 ms.
#:
#: **The seven indexes prefixed by ``owner``** date from the arrival of
#: accounts, and they repair a regression the scoping had introduced: as
#: soon as an ``owner = ?`` predicate sits beside an ``ORDER BY`` or a
#: ``LIKE``, the single-column index can no longer serve both, and the
#: plan falls back to a temporary sort or a scan. Measured, scoped,
#: before → after:
#:
#: - contacts list, page 1: 100.5 ms → 0.08 ms;
#: - contact prefix search: 93.7 ms → 6.1 ms;
#: - account prefix search: 5.0 ms → 0.62 ms;
#: - accounts datatable sorted by name: 9.04 ms → 0.08 ms.
#:
#: The ``owner`` prefix comes FIRST in each: it is the equality, and an
#: index only serves an ``ORDER BY`` if the equality columns precede it.
#: The unscoped twins stay — the directorate uses them.
_INDEXES = """
CREATE INDEX idx_accounts_name      ON accounts(name);
CREATE INDEX idx_accounts_arr       ON accounts(arr);
CREATE INDEX idx_accounts_industry  ON accounts(industry);
CREATE INDEX idx_accounts_country   ON accounts(country);
CREATE INDEX idx_accounts_city      ON accounts(city);
CREATE INDEX idx_accounts_size      ON accounts(size);
CREATE INDEX idx_accounts_owner     ON accounts(owner);
CREATE INDEX idx_accounts_created   ON accounts(created_at);
CREATE INDEX idx_contacts_account   ON contacts(account_id);
CREATE INDEX idx_contacts_last      ON contacts(last_name, first_name);
CREATE INDEX idx_contacts_status    ON contacts(status, last_name, first_name);
CREATE INDEX idx_deals_stage        ON deals(stage, position);
CREATE INDEX idx_deals_owner        ON deals(owner, stage, position);
CREATE INDEX idx_deals_account      ON deals(account_id);
CREATE INDEX idx_activities_contact ON activities(contact_id, at);
CREATE INDEX idx_activities_at      ON activities(at, kind, owner);
CREATE INDEX idx_notes_contact      ON notes(contact_id, at);

CREATE INDEX idx_accounts_name_ci   ON accounts(name COLLATE NOCASE);
CREATE INDEX idx_contacts_last_ci   ON contacts(last_name COLLATE NOCASE);
CREATE INDEX idx_contacts_email_ci  ON contacts(email COLLATE NOCASE);

CREATE INDEX idx_accounts_own_name  ON accounts(owner, name);
CREATE INDEX idx_accounts_own_arr   ON accounts(owner, arr);
CREATE INDEX idx_accounts_own_ci    ON accounts(owner, name COLLATE NOCASE);
CREATE INDEX idx_contacts_own       ON contacts(owner, last_name, first_name);
CREATE INDEX idx_contacts_own_stat  ON contacts(owner, status, last_name,
                                                first_name);
CREATE INDEX idx_contacts_own_last  ON contacts(owner, last_name COLLATE NOCASE);
CREATE INDEX idx_contacts_own_mail  ON contacts(owner, email COLLATE NOCASE);
"""


def seeded_version(conn: sqlite3.Connection) -> int | None:
    """The seed version in place, or ``None`` if the file has none."""
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'seed_version'"
        ).fetchone()
    except sqlite3.OperationalError:
        return None                      # pas de table meta = fichier vierge
    return row[0] if row else None


def init_db(*, force: bool = False) -> bool:
    """(Re)create schema + indexes + seed if needed. Returns True if seeded.

    Idempotent and deterministic: the same ``SEED_VERSION`` leaves the
    file intact, including the writes made from the app. It is the
    difference with ``examples/mad``, which re-lays its seed at every
    startup: at 262 000 rows that is no longer free, and a pipeline one
    has just reordered would go back to its place at every ``reload``.
    """
    conn = connect()
    try:
        if not force and seeded_version(conn) == SEED_VERSION:
            return False
    finally:
        conn.close()

    from examples.crm.core.seed import build_seed

    DB_PATH.unlink(missing_ok=True)
    conn = connect()
    try:
        # WAL: concurrent reads during a write. An SDUI app renders
        # several zones per request, each opening its own connection.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        for table, rows in build_seed():
            placeholders = ",".join("?" * len(rows[0]))
            conn.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
        # Indexes placed AFTER the insertion: building them first would
        # make each of the 262 000 rows pay a tree rebalance.
        conn.executescript(_INDEXES)
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('seed_version', ?)",
            (SEED_VERSION,),
        )
        conn.commit()
    finally:
        conn.close()
    return True


feature = Feature(
    name="db", kind="infra",
    provides=[connect, query, scalar, execute, owner_scope, init_db],
)
