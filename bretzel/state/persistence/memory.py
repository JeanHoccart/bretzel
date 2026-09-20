"""In-memory storage backend for dev / tests.

Plain ``dict`` under the hood. Lost on process restart — production
deployments use the Redis backend instead.

Used as the default when no ``redis_url`` is configured. Sufficient for
single-worker uvicorn dev runs and for the unit / integration test
suite (``MemoryBackend`` removes the need for a live Redis in CI).

What becomes of an expired entry
--------------------------------

It is removed on READ-BACK, and — since 2026-09-04 — by an **amortised
sweep on write**. Read-back alone was not enough, and the reason fits in
one sentence: *an abandoned entry is by definition never read again*. A
session nobody resumes, a ``PageState`` whose tab is closed, a fresh page
key on every F5 — their deadline passed with nobody looking, and nothing
else touched them (``scan`` and ``clear_scope`` purge too, but **no
framework code calls them**: zero sites, verified). The store therefore
tracked the number of pages loaded since startup, not the number of
active users.

The sweep is **on the write**, and that is deliberate: what makes a store
grow is writes. No write, no growth, so nothing to sweep — and above all
no background task to keep alive for a backend whose role is to fit
inside a development process.

⚠️ **What the sweep does NOT bound, and it is not an oversight.** The
``user`` and ``app`` scopes carry ``ttl=None`` by choice (cf.
``DEFAULT_TTLS``): they never expire, so nothing removes them. The store
is bounded by "known users + live sessions + pages seen in the last
hour", which is the size of the app's data — no longer by the process
uptime.
"""

from __future__ import annotations

import fnmatch
import threading
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass
class _Entry:
    """A stored payload with optional Unix-time expiry."""

    data: dict[str, Any]
    expires_at: float | None  # ``None`` → never expires


#: The minimum time between two full sweeps.
#:
#: One minute, and the choice is one of a COST PER UNIT OF TIME rather
#: than per write: a sweep costs ``O(entries)``, so triggering it every N
#: writes would make a burst pay N times. Here, a thousand writes in ten
#: seconds pay for one.
#:
#: A minute of delay on a purge costs nothing: the durations at play are
#: the hour (``page``) and the day (``session``).
_SWEEP_INTERVAL_SECONDS = 60.0


class MemoryBackend:
    """:class:`Backend` implementation backed by a process-local dict.

    Keys are composed as ``f"{scope}:{key}"``. The same shape as the
    Redis backend produces, so test assertions written against either
    backend translate cleanly.
    """

    def __init__(self) -> None:
        self._data: dict[str, _Entry] = {}
        #: ``{key: (token, deadline)}`` — the held locks. Cf.
        #: :meth:`acquire`.
        self._locks: dict[str, tuple[str, float]] = {}
        #: Serialises the read-modify-write of :meth:`merge`. Cf. its
        #: docstring: the module cannot guarantee that nothing calls it
        #: off the loop, so it does not assume so.
        self._write_lock = threading.Lock()
        #: When the last sweep happened. ``monotonic`` and not
        #: ``time()``: what is measured here is a DURATION, and a wall
        #: clock that goes backwards (NTP, DST) would skip the sweep — or
        #: trigger it in a loop. The expiry dates stay on the wall clock:
        #: they are instants, and they survive comparison across calls.
        self._last_sweep = time.monotonic()

    # ── Read / write ────────────────────────────────────────────────────

    def _sweep_if_due(self) -> None:
        """Remove expired entries, at most once per interval.

        Called under the write lock, from the two paths that make the
        store GROW. That is what makes the cost amortised: the purge does
        not attach to one write in particular, only to the fact that
        there are some.
        """
        now = time.monotonic()
        if now - self._last_sweep < _SWEEP_INTERVAL_SECONDS:
            return
        self._last_sweep = now
        cutoff = time.time()
        for key, entry in list(self._data.items()):
            if entry.expires_at is not None and cutoff >= entry.expires_at:
                self._data.pop(key, None)

    async def load(self, scope: str, key: str) -> dict[str, Any] | None:
        return self.load_sync(scope, key)

    def load_sync(self, scope: str, key: str) -> dict[str, Any] | None:
        """Synchronous read — the in-memory backend has no I/O so this
        is a plain dict lookup. Lets the sync ``State()`` construction
        path hydrate on first use without dragging async into the
        metaclass.

        Redis (and any future I/O-backed backend) won't expose this
        method. Its absence NO LONGER prevents hydration since
        2026-09-04: the registry then has the async ``load`` executed by
        the loop from the pool thread. It is therefore a shortcut — it
        avoids a thread round trip when the read costs nothing — and no
        longer a capability that changes behaviour. The only case it
        still covers ALONE is the call made outside any loop (script,
        synchronous test).
        """
        full_key = f"{scope}:{key}"
        entry = self._data.get(full_key)
        if entry is None:
            return None
        if entry.expires_at is not None and time.time() >= entry.expires_at:
            # Lazy expiry — drop on read.
            self._data.pop(full_key, None)
            return None
        # Defensive copy : mutations on the returned dict mustn't leak
        # back into the store.
        return dict(entry.data)

    async def save(
        self,
        scope: str,
        key: str,
        data: dict[str, Any],
        *,
        ttl: int | None = None,
    ) -> None:
        full_key = f"{scope}:{key}"
        with self._write_lock:
            self._sweep_if_due()
            # An EMPTY document means "no row". Redis CANNOT do
            # otherwise — a hash without a field does not exist —, and
            # two backends diverging on a rare case is this repository's
            # "it works in dev" trap. Cf. ``test_both_backends_agree``.
            if not data:
                self._data.pop(full_key, None)
                return
            expires_at = None if ttl is None else time.time() + ttl
            self._data[full_key] = _Entry(
                data=dict(data), expires_at=expires_at
            )

    async def merge(
        self,
        scope: str,
        key: str,
        changes: dict[str, Any],
        *,
        add: dict[str, Any] | None = None,
        ttl: int | None = None,
    ) -> None:
        """Merge ``changes`` into the entry, creating what is missing.

        **Two protections, because there are two ways to lose the race.**
        No ``await`` between the read and the write: the loop cannot hand
        over to another request in the middle. And a lock, because
        "nobody else touches this dict" is a claim this module CANNOT
        hold: since app code is offloaded onto a threadpool, ``load_sync``
        is called from a pool thread, and it mutates ``_data`` (it purges
        the expired entry). No WRITE path runs off the loop today — both
        callers of ``commit`` are awaited on it — but that is a property
        of two call sites, not of the module. The lock costs a hundred
        nanoseconds or so and makes the guarantee local.

        The read goes through :meth:`load_sync`: it already knows what an
        expired entry is, and that rule already had three definitions in
        this file.

        ``ttl=None`` LEAVES the expiration in place, unlike :meth:`save`
        which replaces everything — same contract as on the Redis side,
        where a merge without a duration simply emits no expiration
        command.

        ``add`` is applied UNDER THE LOCK, between the read and the write
        — that is what makes the addition correct here. The lock stands in
        for Redis's ``HINCRBY``: in both cases it is the store that sums,
        never the caller.
        """
        if not changes and not add:
            return
        full_key = f"{scope}:{key}"
        with self._write_lock:
            self._sweep_if_due()
            document = self.load_sync(scope, key) or {}
            document.update(changes)
            for field, delta in (add or {}).items():
                document[field] = document.get(field, 0) + delta
            # AFTER the read, never before: ``load_sync`` purges an
            # expired entry, and taking back the expiration of an entry
            # it has just thrown away would set an already-past date —
            # the fresh row would be born dead.
            existing = self._data.get(full_key)
            if ttl is not None:
                expires_at = time.time() + ttl
            elif existing is not None:
                expires_at = existing.expires_at
            else:
                expires_at = None
            self._data[full_key] = _Entry(
                data=document, expires_at=expires_at
            )

    # ── Verrou ──────────────────────────────────────────────────────────

    async def acquire(
        self, scope: str, key: str, token: str, *, ttl: int
    ) -> bool:
        """Take the lock, without waiting.

        The ``ttl`` serves as much here as in Redis, and for the same
        reason: a handler that raises while holding the lock would leave
        the key blocked for the life of the process. The context manager
        releases in its ``finally``, but a ``kill -9`` has no ``finally``.
        """
        full_key = f"{scope}:{key}"
        with self._write_lock:
            holder = self._locks.get(full_key)
            if holder is not None and holder[1] > time.time():
                return False
            self._locks[full_key] = (token, time.time() + ttl)
            return True

    async def release(self, scope: str, key: str, token: str) -> None:
        """Release, if the token is indeed the holder's.

        The check and the deletion are under the same lock: between a
        separate ``get`` and ``pop``, expiration could give the key to
        somebody else, whom we would then erase.
        """
        full_key = f"{scope}:{key}"
        with self._write_lock:
            holder = self._locks.get(full_key)
            if holder is not None and holder[0] == token:
                del self._locks[full_key]

    async def delete(self, scope: str, key: str) -> None:
        self._data.pop(f"{scope}:{key}", None)

    # ── Bulk operations ─────────────────────────────────────────────────

    async def scan(self, pattern: str) -> AsyncIterator[str]:
        # Snapshot the keys to make iteration tolerant to concurrent saves.
        for stored_key in list(self._data.keys()):
            if fnmatch.fnmatchcase(stored_key, pattern):
                # Drop any entry that has expired, mirroring ``load``.
                entry = self._data.get(stored_key)
                if (
                    entry is not None
                    and entry.expires_at is not None
                    and time.time() >= entry.expires_at
                ):
                    self._data.pop(stored_key, None)
                    continue
                yield stored_key

    async def clear_scope(
        self,
        scope: str,
        *,
        pattern: str | None = None,
    ) -> int:
        match = f"{scope}:{pattern}" if pattern else f"{scope}:*"
        victims = [k for k in self._data if fnmatch.fnmatchcase(k, match)]
        for k in victims:
            del self._data[k]
        return len(victims)

    async def health(self) -> bool:
        return True
