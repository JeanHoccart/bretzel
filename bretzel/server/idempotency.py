"""Opt-in handler idempotency (HMAC v2 — the "C" half).

``@idempotent`` collapses a double-submit of the **same signed request**
into a single execution. The dedup key is the signed
``(action_id | args_blob | render-ts)`` triple plus the acting user — the
exact bytes the client replays on a double-click of one *rendered* button.
A click of a **re-rendered** button carries a fresh ``ts`` → a new key →
a legitimately new operation that runs normally. So only same-render
double-submits are folded; nothing that should run twice is suppressed.

This lives on top of the B half (the signed render timestamp, cf.
``handlers.sign_action``) — without a per-render ``ts`` every click of a
button would share one key and the second would always be a no-op, which
is wrong. The two compose: B makes each render uniquely addressable, C
dedups within that address.

The store is opt-in-scoped: only ``@idempotent`` handlers touch it, and
entries carry a short TTL, so it stays small. Single-process apps use the
in-memory store; multi-worker apps (``redis_url`` set) use the Redis
store, whose ``SET NX EX`` gives the atomic claim two concurrent
double-clicks need (a plain check-then-set would race).
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Callable
from typing import Any, TypeVar

from bretzel.server.handlers import action_hmac_payload

__all__ = [
    "idempotent",
    "idempotent_ttl",
    "idempotency_key",
    "MemoryIdempotencyStore",
    "RedisIdempotencyStore",
]

F = TypeVar("F", bound=Callable[..., Any])

_TTL_ATTR = "_bz_idempotent_ttl"


def idempotent(fn: F | None = None, *, ttl: int = 60) -> Any:
    """Mark a handler idempotent for ``ttl`` seconds.

    A replay of the same signed request (same ``action_id|args|ts`` and
    same user) within the window runs the handler **once** ; the replay
    returns a no-op ``204`` instead of executing again.

    Usage ::

        @idempotent
        def create_order(...): ...

        @idempotent(ttl=300)
        def charge_card(...): ...
    """

    def wrap(f: F) -> F:
        setattr(f, _TTL_ATTR, int(ttl))
        return f

    return wrap(fn) if callable(fn) else wrap


def idempotent_ttl(fn: Callable[..., Any]) -> int | None:
    """The handler's idempotency TTL (seconds), or ``None`` if not marked."""
    return getattr(fn, _TTL_ATTR, None)


def idempotency_key(
    user_id: str | None, action_id: str, args_blob: str, ts: str
) -> str:
    """Compact, injection-safe dedup key for one signed request + user.

    Reuses ``action_hmac_payload`` (the exact signed identity) so the
    dedup key can't drift from what the signature covers.
    """
    raw = f"{user_id or ''}|{action_hmac_payload(action_id, args_blob, ts)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class MemoryIdempotencyStore:
    """Single-process store — a dict + lock with lazy expiry.

    Correct only within one worker ; multi-worker deployments must use
    :class:`RedisIdempotencyStore` (config validation already forces a
    ``redis_url`` when ``workers > 1``).
    """

    def __init__(self) -> None:
        self._seen: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def claim(self, key: str, ttl: int) -> bool:
        """``True`` if newly claimed (proceed) ; ``False`` if already
        claimed within its TTL (skip — it's a replay)."""
        now = time.monotonic()
        async with self._lock:
            exp = self._seen.get(key)
            if exp is not None and exp > now:
                return False
            if len(self._seen) > 1024:  # opportunistic prune of expired keys
                self._seen = {k: v for k, v in self._seen.items() if v > now}
            self._seen[key] = now + ttl
            return True


class RedisIdempotencyStore:
    """Multi-worker store — an atomic ``SET key 1 NX EX ttl``."""

    _PREFIX = "bz:idem:"

    def __init__(self, client: Any) -> None:
        self._client = client

    @classmethod
    def from_url(cls, url: str) -> RedisIdempotencyStore:
        import redis.asyncio as redis  # lazy — redis is an optional-ish dep

        return cls(redis.from_url(url))

    async def claim(self, key: str, ttl: int) -> bool:
        # ``SET … NX`` returns truthy only when the key did NOT exist.
        ok = await self._client.set(f"{self._PREFIX}{key}", "1", nx=True, ex=ttl)
        return bool(ok)
