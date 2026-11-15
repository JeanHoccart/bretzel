"""SQLite storage backend: the states survive a restart, in one file.

Chosen by ``Bretzel(state_url="sqlite:///path/to/state.db")``. The need
it serves is DURATION on one machine: a ``UserState`` preference, the
``SessionState`` of a tab left open, the ``AppState`` of a single-user
app — none of which should reset because the process restarted (and
``bretzel dev`` restarts it on every save). ``sqlite3`` is in the
standard library: nothing to install, no service to run.

What it does NOT serve: several processes of one app. The states
themselves would stay correct (SQLite's write lock is shared between
processes), but the SSE relay and the ``@idempotent`` store stay in each
process — ``BretzelConfig`` refuses ``workers > 1`` here.

Strict rules, the same as Redis's where they apply:

- **One row per state, the document as JSON.** Never ``pickle`` (an RCE
  vector the day someone else can write the file). A value JSON cannot
  hold is refused at write time with a :class:`BretzelError`.
- **A write is indivisible.** ``merge`` reads, merges and rewrites under
  ``BEGIN IMMEDIATE``: SQLite's write lock is taken before the read, so
  no other connection — in this process or another — can slip between
  the two. That is what the protocol demands of a read-modify-write, and
  what makes ``add`` a counter rather than a "last one wins".
- **Calls run where they are made, on the loop included.** A read costs
  about 15 µs, a write 30 to 45 µs; a hop to a thread costs ~290 µs on
  Windows (measured). So, like :class:`MemoryBackend`: one
  connection per process, a ``threading.Lock`` around it, and
  :meth:`load_sync` exposed — hydration from a pool thread reads directly.
- **Every wait is bounded**: ``busy_timeout`` of five seconds, the ceiling
  the Redis backend uses, and a locked file then surfaces as a sentence.
- **Durability: ``synchronous=NORMAL`` in WAL mode.** A crash or a kill
  of the app loses nothing; a power cut may lose the last writes. ``FULL``
  costs ten times more per request (an ``fsync`` per commit) for screen
  state: not worth it.

Expired rows are hidden on read and swept on write at most once a minute
— :class:`MemoryBackend`'s rule, for the same reason: what makes the
store grow is writes, so no background task is needed.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from bretzel.core.errors import BretzelError

#: The scheme of a ``state_url`` that names a SQLite file.
SCHEME = "sqlite"

#: The ceiling of a wait for the file's write lock, in milliseconds. The
#: Redis backend's five seconds: a FAILURE ceiling, not a latency budget.
_BUSY_TIMEOUT_MS = 5000

#: The minimum time between two sweeps of the expired rows — cf.
#: ``memory._SWEEP_INTERVAL_SECONDS``, same reasoning.
_SWEEP_INTERVAL_SECONDS = 60.0

#: ``bretzel_`` prefixed: the file may be the app's own database.
_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS bretzel_state ("
    " scope TEXT NOT NULL, key TEXT NOT NULL, doc TEXT NOT NULL,"
    " expires REAL, PRIMARY KEY (scope, key)) WITHOUT ROWID",
    "CREATE INDEX IF NOT EXISTS bretzel_state_expires"
    " ON bretzel_state (expires) WHERE expires IS NOT NULL",
    "CREATE TABLE IF NOT EXISTS bretzel_lock ("
    " scope TEXT NOT NULL, key TEXT NOT NULL, token TEXT NOT NULL,"
    " expires REAL NOT NULL, PRIMARY KEY (scope, key)) WITHOUT ROWID",
)


def path_of(url: str) -> Path:
    """The file a ``sqlite:///…`` URL names — SQLAlchemy's convention.

    Everything after ``sqlite:///`` is the path: ``sqlite:///state.db`` is
    relative to the working directory, ``sqlite:///C:/apps/state.db`` and
    ``sqlite:////srv/app/state.db`` are absolute.
    """
    prefix = f"{SCHEME}:///"
    if not url.startswith(prefix) or not url[len(prefix):]:
        raise BretzelError(
            f"state_url {url!r} does not name a file: write "
            f"'sqlite:///state.db' (relative to the working directory) or "
            f"'sqlite:///C:/path/to/state.db' (absolute)."
        )
    return Path(url[len(prefix):])


class SqliteBackend:
    """:class:`Backend` implementation backed by one SQLite file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        # A declared but missing folder RAISES: it is a path typo, and
        # SQLite would answer it with a bare "unable to open database
        # file" (same rule as ``static_dir``).
        if not self._path.parent.is_dir():
            raise BretzelError(
                f"state_url names {self._path}, whose folder "
                f"{self._path.parent} does not exist. Create it, or fix the "
                f"path."
            )
        self._db = sqlite3.connect(
            self._path, check_same_thread=False, isolation_level=None
        )
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()
        with self._guard("open"):
            # ``busy_timeout`` FIRST: switching to WAL takes the write
            # lock, and two processes opening the file at once collided
            # on it without a wait (measured).
            self._db.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
            for statement in _SCHEMA:
                self._db.execute(statement)

    @classmethod
    def from_url(cls, url: str) -> SqliteBackend:
        """Build a backend from a ``sqlite:///…`` URL."""
        return cls(path_of(url))

    # ── Plumbing ────────────────────────────────────────────────────────

    @contextmanager
    def _guard(self, what: str) -> Iterator[None]:
        """The connection, held alone; a locked file as a sentence."""
        with self._lock:
            try:
                yield
            except sqlite3.OperationalError as exc:
                raise BretzelError(
                    f"The state file {self._path} could not serve {what!r} "
                    f"({exc}). Another process holds it longer than the "
                    f"{_BUSY_TIMEOUT_MS // 1000} s allowed, or the file is "
                    f"not writable."
                ) from exc

    @contextmanager
    def _write(self, what: str) -> Iterator[None]:
        """A transaction that holds the write lock from its first read."""
        with self._guard(what):
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")

    def _sweep_if_due(self, now: float) -> None:
        """Remove expired rows and locks, at most once per interval.

        Called inside a write transaction, from the paths that make the
        store grow.
        """
        tick = time.monotonic()
        if tick - self._last_sweep < _SWEEP_INTERVAL_SECONDS:
            return
        self._last_sweep = tick
        self._db.execute("DELETE FROM bretzel_state WHERE expires <= ?", (now,))
        self._db.execute("DELETE FROM bretzel_lock WHERE expires <= ?", (now,))

    def _read(self, scope: str, key: str, now: float) -> tuple[dict[str, Any], float | None] | None:
        """The live row — its document and its expiry — or ``None``."""
        row = self._db.execute(
            "SELECT doc, expires FROM bretzel_state WHERE scope = ? AND key = ?",
            (scope, key),
        ).fetchone()
        if row is None or (row[1] is not None and row[1] <= now):
            return None
        try:
            return json.loads(row[0]), row[1]
        except json.JSONDecodeError as exc:
            raise BretzelError(
                f"Stored state {scope}:{key} in {self._path} is not valid "
                f"JSON: {exc}. A foreign writer touched the file."
            ) from exc

    def _put(self, scope: str, key: str, doc: dict[str, Any], expires: float | None) -> None:
        try:
            encoded = json.dumps(doc)
        except (TypeError, ValueError) as exc:
            raise BretzelError(
                f"State at {scope}:{key} is not JSON-serialisable: {exc}. "
                "Bretzel does NOT fall back to pickle (RCE risk). Make sure "
                "your fields hold JSON-friendly types (str, int, float, "
                "bool, None, list, dict)."
            ) from exc
        self._db.execute(
            "INSERT INTO bretzel_state (scope, key, doc, expires) VALUES (?, ?, ?, ?)"
            " ON CONFLICT (scope, key) DO UPDATE"
            " SET doc = excluded.doc, expires = excluded.expires",
            (scope, key, encoded, expires),
        )

    # ── Read / write ────────────────────────────────────────────────────

    async def load(self, scope: str, key: str) -> dict[str, Any] | None:
        return self.load_sync(scope, key)

    def load_sync(self, scope: str, key: str) -> dict[str, Any] | None:
        """Synchronous read — a primary-key lookup, cheaper than a thread
        hop. Cf. :meth:`MemoryBackend.load_sync` for why it exists."""
        with self._guard("load"):
            row = self._read(scope, key, time.time())
        return None if row is None else row[0]

    async def save(
        self,
        scope: str,
        key: str,
        data: dict[str, Any],
        *,
        ttl: int | None = None,
    ) -> None:
        """Replace the whole document. An EMPTY document deletes the row —
        the protocol's rule, which Redis cannot do otherwise."""
        now = time.time()
        with self._write("save"):
            self._sweep_if_due(now)
            if not data:
                self._db.execute(
                    "DELETE FROM bretzel_state WHERE scope = ? AND key = ?",
                    (scope, key),
                )
                return
            self._put(scope, key, dict(data), None if ttl is None else now + ttl)

    async def merge(
        self,
        scope: str,
        key: str,
        changes: dict[str, Any],
        *,
        add: dict[str, Any] | None = None,
        ttl: int | None = None,
    ) -> None:
        """Apply ``changes`` and ``add`` on top of what is stored.

        Read, merge and rewrite under ``BEGIN IMMEDIATE``: the write lock
        is held from the read on, so the sequence is indivisible across
        connections and processes, and ``add`` sums like ``HINCRBY``.

        ``ttl=None`` keeps the stored expiry; an empty merge with a
        ``ttl`` renews a LIVE row and creates none.
        """
        now = time.time()
        if not changes and not add:
            if ttl is not None:
                with self._guard("merge"):
                    self._db.execute(
                        "UPDATE bretzel_state SET expires = ? WHERE scope = ?"
                        " AND key = ? AND (expires IS NULL OR expires > ?)",
                        (now + ttl, scope, key, now),
                    )
            return
        with self._write("merge"):
            self._sweep_if_due(now)
            row = self._read(scope, key, now)
            document, expires = row if row is not None else ({}, None)
            document.update(changes)
            for field, delta in (add or {}).items():
                document[field] = document.get(field, 0) + delta
            self._put(scope, key, document, now + ttl if ttl is not None else expires)

    # ── Lock ────────────────────────────────────────────────────────────

    async def acquire(
        self, scope: str, key: str, token: str, *, ttl: int
    ) -> bool:
        """One statement: insert, or take over a lock whose time is up.

        The ``WHERE`` of the upsert is what makes it a take and not an
        overwrite — a held lock leaves the row untouched, and
        ``rowcount`` says which happened.
        """
        now = time.time()
        with self._guard("acquire"):
            taken = self._db.execute(
                "INSERT INTO bretzel_lock (scope, key, token, expires) VALUES (?, ?, ?, ?)"
                " ON CONFLICT (scope, key) DO UPDATE"
                " SET token = excluded.token, expires = excluded.expires"
                " WHERE bretzel_lock.expires <= ?",
                (scope, key, token, now + ttl, now),
            ).rowcount
        return taken == 1

    async def release(self, scope: str, key: str, token: str) -> None:
        """Release IF ``token`` is the holder's — check and delete in one
        statement, so no expiry can fall between them."""
        with self._guard("release"):
            self._db.execute(
                "DELETE FROM bretzel_lock WHERE scope = ? AND key = ? AND token = ?",
                (scope, key, token),
            )

    async def delete(self, scope: str, key: str) -> None:
        with self._guard("delete"):
            self._db.execute(
                "DELETE FROM bretzel_state WHERE scope = ? AND key = ?", (scope, key)
            )

    # ── Bulk operations ─────────────────────────────────────────────────

    async def scan(self, pattern: str) -> AsyncIterator[str]:
        """Live logical keys (``scope:key``) matching a Redis-style glob —
        SQLite's ``GLOB`` has the same grammar (``*``, ``?``, ``[set]``)."""
        with self._guard("scan"):
            rows = self._db.execute(
                "SELECT scope || ':' || key FROM bretzel_state"
                " WHERE scope || ':' || key GLOB ?"
                " AND (expires IS NULL OR expires > ?)",
                (pattern, time.time()),
            ).fetchall()
        for (logical,) in rows:
            yield logical

    async def clear_scope(
        self,
        scope: str,
        *,
        pattern: str | None = None,
    ) -> int:
        with self._guard("clear_scope"):
            return self._db.execute(
                "DELETE FROM bretzel_state WHERE scope = ? AND key GLOB ?",
                (scope, pattern or "*"),
            ).rowcount

    async def health(self) -> bool:
        try:
            with self._guard("health"):
                self._db.execute("SELECT 1").fetchone()
        except BretzelError:
            return False
        return True

    # ── Lifecycle ───────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the connection. Called on app shutdown."""
        with self._lock:
            self._db.close()
