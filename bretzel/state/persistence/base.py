"""Storage backend protocol.

The :class:`Backend` :class:`~typing.Protocol` defines the minimal async
interface every concrete backend (memory, Redis, …) must implement. The
state registry talks to backends through this protocol exclusively, so
swapping implementations is a single-line config change.

The protocol is intentionally *narrow* — nine methods, no inheritance,
no abstract base class. Pydantic-style serialisation lives one layer
up: the registry hands backends already-serialised :class:`dict`
payloads.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Backend(Protocol):
    """Async key-value store with scope-aware key namespacing.

    Implementations are responsible for:

    - **Composing the storage key** from ``scope`` + ``key`` in their own
      namespace (e.g., ``bretzel:session:<sid>:<state_class>:<state_key>``
      for the Redis backend). The registry passes the logical pieces
      separately; the backend formats them.
    - **Honouring TTLs** on ``save`` (``EX <seconds>`` for Redis, expiry
      check at read time for in-memory).
    - **Returning JSON-friendly dicts** on ``load`` — never custom Python
      objects. Validation / casting is the registry's job.
    - **Bounding their own waits.** A backend talking to a remote service
      MUST set a timeout — ``RedisBackend`` does it when building the
      client. The reason is not politeness: a state read is called from a
      pool thread (``StateRegistry._load_via_loop``), which stays blocked
      until it returns. A silent service parks that thread forever; forty
      parked that way (the ``anyio`` default) and no synchronous app code
      runs at all any more.

      ⚠️ The registry does NOT double that timeout with a ceiling of its
      own, and that is a choice: two stacked limits force the innermost
      one to stay strictly shorter, failing which the framework's fires
      first and masks the right error — the one that names the
      unreachable service. Responsibility therefore stays where the I/O
      lives.
    """

    async def load(self, scope: str, key: str) -> dict[str, Any] | None:
        """Return the stored payload, or ``None`` if not present.

        ``key`` is the State instance's logical key (``"default"``,
        ``"basket"``, …). ``scope`` is one of ``"session"`` / ``"user"``
        / ``"app"`` / ``"page"``. Page-scope IS persisted, keyed by ``page_id`` with a 1h TTL (cf. registry).
        """
        ...

    async def save(
        self,
        scope: str,
        key: str,
        data: dict[str, Any],
        *,
        ttl: int | None = None,
    ) -> None:
        """Persist ``data`` under ``(scope, key)``.

        ``ttl`` is in seconds. ``None`` means no expiration, and the
        replacement takes the expiration with the rest: the row written
        carries none.

        An EMPTY document means "no row": it is deleted, not created
        empty. A Redis hash cannot exist without a field, and the
        registry reads "absent" and "empty" the same way — both return
        the defaults.
        """
        ...

    async def merge(
        self,
        scope: str,
        key: str,
        changes: dict[str, Any],
        *,
        add: dict[str, Any] | None = None,
        ttl: int | None = None,
    ) -> None:
        """Apply ``changes`` ON TOP of what is stored, atomically.

        This is the path the end of a request goes through, not
        :meth:`save` — which rewrites the whole document and therefore
        erases what a concurrent request had just put in it.

        **Atomically, and per FIELD**: a field written by one request
        cannot be erased by another writing different ones — value and
        expiration included. That is the minimal promise, and it is
        stronger than it looks: an implementation that reads the
        document, merges it and rewrites it does NOT hold it, unless that
        sequence is made indivisible.

        An absent key is created with ``changes`` alone: the fields not
        written take their default on read-back.

        ``add`` carries the fields to INCREMENT — ``{field: delta}`` —
        instead of replacing them. That is what makes a counter correct
        under concurrency: two requests that read the same number each
        send "add 1", and the store lands on two. A backend that merely
        read, summed and rewrote would lose exactly what this parameter
        exists to save — the addition must be done BY the store, or under
        a lock it holds.

        ``ttl`` renews the expiration; ``None`` leaves the existing one in
        place. That is where the merge differs from :meth:`save` — a
        partial write has no business deciding the fate of a duration it
        did not set.
        """
        ...

    async def acquire(
        self, scope: str, key: str, token: str, *, ttl: int
    ) -> bool:
        """Take the lock on ``(scope, key)``. ``True`` if obtained.

        Does NOT block: returns ``False`` immediately when somebody else
        already holds it. The caller decides whether to wait, and for how
        long — a backend has no business knowing a request's patience.

        ``token`` identifies the holder, and it is not decorative:
        :meth:`release` only releases when the token matches. Without it,
        a holder whose ``ttl`` expired would release a SUCCESSOR's lock,
        who would believe itself alone when there would be two of them.

        ``ttl`` is a FAILURE ceiling, in seconds: without it, a process
        that dies holding the lock keeps it forever.

        ⚠️ The limit is inherent to every time-bounded lock: if the work
        exceeds the ``ttl``, a second holder gets in. The token prevents
        cross-release, not the overlap.
        """
        ...

    async def release(self, scope: str, key: str, token: str) -> None:
        """Release the lock, IF ``token`` is indeed the holder's.

        The check and the deletion must be indivisible: reading then
        deleting leaves room for an expiration in between.
        """
        ...

    async def delete(self, scope: str, key: str) -> None:
        """Remove the entry. No-op when missing."""
        ...

    def scan(self, pattern: str) -> AsyncIterator[str]:
        """Yield logical keys matching ``pattern``.

        Pattern grammar follows Redis SCAN globs (``*``, ``?``, ``[set]``).
        Use cases : admin listing, debug introspection. Returns the
        backend-prefixed keys as strings — callers parse them.
        """
        ...

    async def clear_scope(
        self,
        scope: str,
        *,
        pattern: str | None = None,
    ) -> int:
        """Delete every entry in ``scope`` (optionally narrowed by pattern).

        Returns the count of removed entries. Used on logout (``"session"``
        scope), account deletion (``"user"``), admin operations.
        """
        ...

    async def health(self) -> bool:
        """Quick connection check. Return ``True`` if the backend is
        reachable and writable. Called once at app startup."""
        ...
