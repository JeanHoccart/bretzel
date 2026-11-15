"""What only a FILE has to prove: it outlives its process, and several
writers on it lose nothing.

The protocol's contract (empty document, merge, ``add``, TTL, locks) is
played against every backend in ``test_both_backends_agree.py``; this
file holds what the other backends do not have — a URL that names a
path, a store reopened after a close, and concurrency between
CONNECTIONS (each process of an app opens its own).
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
import time
from collections.abc import Awaitable
from pathlib import Path

import pytest

from bretzel.core.errors import BretzelError
from bretzel.state.persistence.sqlite import SqliteBackend, path_of

ROOT = Path(__file__).resolve().parents[4]


def run[T](coro: Awaitable[T]) -> T:
    return asyncio.new_event_loop().run_until_complete(coro)


# ── The URL ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("url", "path"), [
    ("sqlite:///state.db", "state.db"),
    ("sqlite:///data/state.db", "data/state.db"),
    ("sqlite:///C:/apps/state.db", "C:/apps/state.db"),
    ("sqlite:////srv/app/state.db", "/srv/app/state.db"),
])
def test_the_url_names_a_path_like_sqlalchemy(url: str, path: str) -> None:
    assert path_of(url) == Path(path)


@pytest.mark.parametrize("url", ["sqlite:///", "sqlite://state.db", "sqlite:state.db"])
def test_a_url_without_a_file_is_refused(url: str) -> None:
    with pytest.raises(BretzelError, match="does not name a file"):
        path_of(url)


def test_a_missing_folder_is_refused_with_its_path(tmp_path: Path) -> None:
    with pytest.raises(BretzelError, match="does not exist"):
        SqliteBackend(tmp_path / "absent" / "etat.db")


# ── Outliving the process ───────────────────────────────────────────────


def test_a_closed_store_reopens_with_its_rows(tmp_path: Path) -> None:
    """A restart, at the backend's scale: write, close, open anew, read.

    The app-level restart — two real processes, one after the other — is
    ``tests/integration/server/test_a_state_survives_a_restart.py``.
    """
    fichier = tmp_path / "etat.db"
    premier = SqliteBackend(fichier)
    run(premier.merge("user", "u:Panneau:default", {"ouvert": False}))
    run(premier.merge("session", "s:Vue:default", {"fil": "42"}, ttl=3600))
    premier.close()

    second = SqliteBackend(fichier)
    assert second.load_sync("user", "u:Panneau:default") == {"ouvert": False}
    assert second.load_sync("session", "s:Vue:default") == {"fil": "42"}
    second.close()


def test_an_expired_row_is_swept_on_a_later_write(tmp_path: Path) -> None:
    """The sweep is what keeps the file the size of the live states, not
    of every page ever loaded."""
    store = SqliteBackend(tmp_path / "etat.db")
    run(store.merge("page", "p:X:default", {"a": 1}, ttl=1))
    store._db.execute("UPDATE bretzel_state SET expires = 0")
    store._last_sweep = time.monotonic() - 3600
    run(store.merge("app", "Y:default", {"b": 2}))
    (rows,) = store._db.execute("SELECT count(*) FROM bretzel_state").fetchone()
    assert rows == 1


# ── Several writers ─────────────────────────────────────────────────────

_WRITER = """
import asyncio, sys
from bretzel.state.persistence.sqlite import SqliteBackend
store = SqliteBackend(sys.argv[1])
loop = asyncio.new_event_loop()
for _ in range(int(sys.argv[2])):
    loop.run_until_complete(store.merge("app", "Compteur:default", {}, add={"n": 1}))
"""


def test_a_counter_is_exact_across_processes(tmp_path: Path) -> None:
    """Four processes add at once: the total is the sum.

    Each process opens its own connection, as each worker of an app
    would: what makes ``add`` exact here is SQLite's write lock, taken
    before the read (``BEGIN IMMEDIATE``), not a lock of this process.
    """
    fichier = tmp_path / "etat.db"
    SqliteBackend(fichier).close()
    writers = [
        subprocess.Popen([sys.executable, "-c", _WRITER, str(fichier), "150"], cwd=ROOT)
        for _ in range(4)
    ]
    assert [w.wait(timeout=120) for w in writers] == [0, 0, 0, 0]
    assert SqliteBackend(fichier).load_sync("app", "Compteur:default") == {"n": 600}


class _ReadThenWrite(SqliteBackend):
    """The violation, fabricated: the read and the write in two separate
    statements, with no transaction holding them together."""

    async def merge(self, scope, key, changes, *, add=None, ttl=None):
        with self._guard("merge"):
            row = self._read(scope, key, time.time())
        document = row[0] if row else {}
        for field, delta in (add or {}).items():
            document[field] = document.get(field, 0) + delta
        time.sleep(0.001)  # the window another writer falls into
        with self._guard("merge"):
            self._put(scope, key, document, None)


@pytest.mark.parametrize(("backend_class", "exact"), [
    (SqliteBackend, True),
    (_ReadThenWrite, False),
])
def test_the_counter_test_would_catch_a_lost_update(
    tmp_path: Path, backend_class: type[SqliteBackend], exact: bool
) -> None:
    """Both sides of the counter's proof, between connections of ONE
    process (threads stand in for workers: each has its own connection).

    The real merge lands on the sum; a read-then-write merge loses
    additions — so a green ``test_a_counter_is_exact_across_processes``
    says something.
    """
    fichier = tmp_path / "etat.db"
    backend_class(fichier).close()

    def writer() -> None:
        store = backend_class(fichier)
        loop = asyncio.new_event_loop()
        for _ in range(40):
            loop.run_until_complete(store.merge("app", "C:default", {}, add={"n": 1}))
        store.close()

    threads = [threading.Thread(target=writer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total = SqliteBackend(fichier).load_sync("app", "C:default")["n"]
    assert (total == 160) is exact, total


def test_a_lock_is_exclusive_between_connections(tmp_path: Path) -> None:
    """The lock lives in the FILE: a second connection — another worker —
    sees it held."""
    fichier = tmp_path / "etat.db"
    a, b = SqliteBackend(fichier), SqliteBackend(fichier)
    assert run(a.acquire("app", "X:default", "A", ttl=5)) is True
    assert run(b.acquire("app", "X:default", "B", ttl=5)) is False
    run(a.release("app", "X:default", "A"))
    assert run(b.acquire("app", "X:default", "B", ttl=5)) is True
