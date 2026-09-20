"""The lock an app asks for, around a read-modify-write.

What it repairs
---------------

The per-field commit (cf. ``registry.commit``) saves what combines: two
requests writing DIFFERENT fields no longer erase each other, and a field
declared ``merge="add"`` sums. What remains is what does not combine — a
gesture that COMPUTES from what it read ::

    store.tasks = [t for t in store.tasks if t["id"] != target]

Two simultaneous deletions read the same list, each removes one element,
and the second write reintroduces the one the first had just taken out.
No store operation can resolve that: not ``RPUSH`` (it is not an append),
not a delta (it is not a number). The only general answer is to **not let
them overlap** ::

    def delete(target: str) -> None:
        with Kanban.lock() as store:
            store.tasks = [t for t in store.tasks if t["id"] != target]

What the block guarantees
-------------------------

It is a small transaction on this state's row:

1. **entry** — the lock is taken, then the state is RE-READ. What you read
   inside is therefore fresh, even if you had already read it before the
   block;
2. **exit** — the modified fields are written, then the lock is released.

The write is INSIDE the block, and that is not a detail: if we merely
blocked and let the end-of-request commit write later, another request
would slip in between the release and the write — the lock would have
protected nothing.

``with`` and not ``async with``
-------------------------------

The handlers of this framework are written ``def`` (measured: 1 659
against 16), because a synchronous body is offloaded to a thread and
freezes nothing. An ``async with`` would force them all into ``async
def``, that is to say onto the loop, where the slightest blocking call
costs the whole worker. The same object accepts both forms — ``async
with`` works in an ``async def`` body — but the normal one is
synchronous.

What a time-bounded lock cannot do
----------------------------------

It carries a ``ttl``, without which a process killed while holding it
would keep it forever. The counterpart is inherent: **if your block
exceeds the ``ttl``, a second holder gets in**. The token prevents
cross-release — you will never release someone else's lock — not the
overlap. Keep the block short, and put neither a slow network call nor a
render in it.

And it serialises: two requests on the SAME key wait for each other. That
is the price asked, and it is only paid where it was asked for.
"""

from __future__ import annotations

import secrets
import time
from types import TracebackType
from typing import TYPE_CHECKING, Any

import anyio
import anyio.from_thread

from bretzel.core.errors import BretzelError

if TYPE_CHECKING:
    from bretzel.state.registry import StateRegistry
    from bretzel.state.scopes.server import ServerState

#: How long a holder keeps the lock if it dies without releasing. Five
#: seconds: a protected block does a read, an in-memory computation and a
#: write — never a slow call. Beyond that it is no longer a critical
#: section, it is background work.
DEFAULT_LOCK_TTL = 5

#: How long we WAIT for our turn before giving up. Distinct from the
#: ``ttl``: one bounds a holder's failure, the other a follower's
#: patience. Three seconds fits in an HTTP request's budget.
DEFAULT_LOCK_TIMEOUT = 3.0

#: Between two attempts. Short, because protected sections are brief; not
#: zero, so as not to hammer the store.
_RETRY_DELAY = 0.02


class LockTimeoutError(BretzelError):
    """Raised when a state lock cannot be acquired before its deadline."""


class StateLock:
    """The context manager returned by ``MyState.lock()``.

    Synchronous AND asynchronous: ``__enter__`` serves ``def`` bodies (the
    common case, running on a pool thread) by having the backend calls
    executed BY the loop; ``__aenter__`` serves ``async def`` bodies by
    awaiting them directly.
    """

    __slots__ = ("_cls", "_key", "_registry", "_storage_key", "_timeout", "_token", "_ttl")

    def __init__(
        self,
        registry: StateRegistry,
        cls: type[ServerState],
        key: str,
        *,
        ttl: int,
        timeout: float,
    ) -> None:
        self._registry = registry
        self._cls = cls
        self._key = key
        self._ttl = ttl
        self._timeout = timeout
        self._token = secrets.token_hex(8)
        self._storage_key: str | None = None

    # ── The work, written once in async ─────────────────────────────────

    async def _acquire(self) -> ServerState:
        scope = self._cls.__scope__
        self._storage_key = self._registry._compose_storage_key(
            scope, self._cls.__name__, self._key
        )
        backend = self._registry._backend
        deadline = time.monotonic() + self._timeout
        while True:
            if await backend.acquire(
                scope, self._storage_key, self._token, ttl=self._ttl
            ):
                break
            if time.monotonic() >= deadline:
                raise LockTimeoutError(
                    f"{self._cls.__name__}.lock() did not get the lock in "
                    f"{self._timeout} s. Another request is holding the "
                    f"same key longer than expected: look at what the "
                    f"protected block does — it must read, compute and "
                    f"write, never wait on the network."
                )
            await anyio.sleep(_RETRY_DELAY)
        # RE-READ under the lock: what we read before may be stale.
        return await self._registry.reload(self._cls, self._key)

    async def _release(self) -> None:
        instance = self._registry.get_cached(self._cls, self._key)
        try:
            if instance is not None:
                await self._registry.write_one(self._cls, self._key, instance)  # type: ignore[arg-type]
        finally:
            # Release EVEN if the write raises: keeping the lock on top
            # of the error would punish the following requests for a
            # fault that is not theirs.
            assert self._storage_key is not None
            await self._registry._backend.release(
                self._cls.__scope__, self._storage_key, self._token
            )

    # ── The two doors ───────────────────────────────────────────────────

    def __enter__(self) -> Any:
        return _via_loop(self._acquire)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        _via_loop(self._release)

    async def __aenter__(self) -> Any:
        return await self._acquire()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._release()


def _via_loop(coro_fn: Any) -> Any:
    """Have ``coro_fn`` executed BY the loop, from a pool thread.

    The exact counterpart of ``StateRegistry._load_via_loop``: a ``def``
    body runs on a thread where waiting is allowed, and
    ``anyio.from_thread.run`` works ONLY from such a thread. A call left
    on the loop therefore falls into the ``except`` — and there, blocking
    would have frozen the worker.
    """
    try:
        return anyio.from_thread.run(coro_fn)
    except anyio.from_thread.NoEventLoopError:
        raise BretzelError(
            "`with MyState.lock()` was used in an `async def` body, where "
            "it cannot wait on the store without freezing the loop. Write "
            "`async with MyState.lock()` here — or put this body back to "
            "`def`, which the framework will offload to a thread."
        ) from None
