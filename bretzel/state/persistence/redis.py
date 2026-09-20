"""Redis storage backend for production deployments.

Strict rules:

- **One HASH per state, one Redis field per state field.** That is the
  shape Redis offers for an object, and it is what makes partial writes
  native: ``HSET key filter "red"`` reads nothing, overwrites nothing
  else, and fits in one round trip. The whole-document JSON we used to
  store forced a re-read, a merge and a full rewrite under an optimistic
  lock — three round trips and a retry loop to change one field.

- **Every wait is BOUNDED, and the backend is what bounds it.** A state
  read starts from a pool thread (cf. ``StateRegistry._load_via_loop``),
  and that thread stays blocked until the answer arrives. Without a
  client-side timeout, a Redis that stops answering — not refused, not
  cut: silent — parks the thread forever, with no exception, no log and
  no recovery. Forty parked that way (the ``anyio`` default, cf.
  ``core/invoke.py``) and no synchronous app code runs at all any more.
  Hence ``socket_timeout`` and ``socket_connect_timeout`` set by default
  here: redis-py leaves both at ``None``, that is to say endless
  (measured).

- **JSON-only serialisation.** Bretzel never falls back to ``pickle`` —
  pickle deserialisation is a documented RCE vector when an attacker
  can write to the store. If a state field carries a value
  :func:`json.dumps` cannot encode, we surface :class:`BretzelError`
  at write time with a clear message rather than silently accepting it.

- **Logical key composition is the registry's job.** This backend only
  prepends ``{prefix}:{scope}:`` to whatever the registry hands it.
  The registry is responsible for hashing user IDs (privacy by design,
  see ``.claude/bretzel/state.md``) and embedding the State class name + instance
  key into the logical key.

- **TTL.** ``save(..., ttl=N)`` sets ``EXPIRE N``; ``ttl=None`` leaves no
  expiration at all (the key has just been deleted). ``merge`` renews the
  expiration when given one, and leaves the one in place alone when
  ``ttl`` is ``None`` — cf. its docstring.

⚠️ **What the hash costs, measured on 2026-09-04** — written here because
the winning half is already written above:

- the READ decodes field by field, so N ``json.loads`` calls instead of
  one: **18.3 µs against 3.7** for twenty fields, 63 against 13.7 for
  fifty. To be compared with the milliseconds of a network round trip,
  but it is not free;
- a single field whose JSON exceeds 64 bytes tips the WHOLE hash out of
  Redis's compact encoding (``hash-max-listpack-value``), which costs a
  few dozen bytes per field instead of about fifty for the whole row.

The trade is accepted: those two costs are paid in microseconds and
kilobytes, the lost update was paid in erased data.
"""

from __future__ import annotations

import functools
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import Any
from urllib.parse import urlparse

from redis import asyncio as redis_asyncio
from redis import exceptions as redis_exceptions

# Canonical framework error — one class, so a serialisation failure here
# is caught by the server's ``except BretzelError`` / FastAPI handler
# (previously a *distinct* local class silently escaped into a bare 500).
# Re-exported so ``redis.BretzelError`` keeps resolving.
from bretzel.core.errors import BretzelError

#: The ceiling of an operation and that of a connection, in seconds.
#:
#: **Five**, because both errors are expensive in opposite directions:
#: too short, a load spike fails requests that would have completed; too
#: long, every blocked request holds a pool thread, and there are forty
#: of them. Five seconds is already an eternity for a UI — it is a
#: FAILURE ceiling, not a latency budget.
#:
#: Changed through the URL (``redis://host?socket_timeout=2``), which
#: wins over this default: redis-py applies the URL options AFTER the
#: kwargs (verified on 2026-09-04 — a ``socket_timeout=9`` kwarg lost
#: against the URL's ``1.5``). That is indeed the direction we want: the
#: framework's value is a default, the operator's wins.
_DEFAULT_TIMEOUT_SECONDS = 5.0

def _bounded[T](
    method: Callable[..., Awaitable[T]],
) -> Callable[..., Awaitable[T]]:
    """Translate a TRANSPORT failure into a readable :class:`BretzelError`.

    Without it, a mute Redis surfaces a bare
    ``redis.exceptions.TimeoutError``: a 500 with no sentence, in a trace
    where nothing says the wait was bounded on purpose nor how to loosen
    it. The refusal is a help — that is this repository's norm.

    Covers the transport ONLY. A ``ResponseError`` (WRONGTYPE, refused
    script…) speaks about the content and must keep surfacing as-is:
    :meth:`RedisBackend.load` handles one itself, and swallowing it here
    would break its recovery.
    """

    @functools.wraps(method)
    async def wrapper(self: RedisBackend, *args: Any, **kwargs: Any) -> T:
        try:
            return await method(self, *args, **kwargs)
        except redis_exceptions.TimeoutError as exc:
            raise BretzelError(
                f"Redis did not answer {method.__name__!r} within the "
                f"allotted time ({exc}). The wait is bounded ON PURPOSE: a "
                f"state read starts from a pool thread, and an endless "
                f"wait would keep it forever. If your instance is "
                f"legitimately slow, loosen the ceiling in the URL "
                f"(`redis://…?socket_timeout=15`)."
            ) from exc
        except redis_exceptions.ConnectionError as exc:
            raise BretzelError(
                f"Redis is unreachable during {method.__name__!r} ({exc}). "
                f"This request's state could not be read or written."
            ) from exc

    return wrapper


class RedisBackend:
    """:class:`Backend` implementation backed by ``redis.asyncio``.

    A state is a **hash** whose every field carries the JSON value of one
    state field. The key on the wire is ``f"{prefix}:{scope}:{key}"``,
    where ``prefix`` is ``"bretzel"`` by default — so two Bretzel apps can
    share one Redis instance under distinct prefixes.
    """

    def __init__(
        self,
        client: redis_asyncio.Redis,
        *,
        prefix: str = "bretzel",
    ) -> None:
        self._client = client
        self._prefix = prefix

    # ── Construction helpers ────────────────────────────────────────────

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        prefix: str = "bretzel",
        **client_kwargs: Any,
    ) -> RedisBackend:
        """Build a backend from a ``redis://`` / ``rediss://`` URL."""
        # ``decode_responses=True`` makes ``hgetall`` / ``scan_iter``
        # return ``str`` instead of ``bytes`` — field names as well as
        # values, and we only store JSON in there anyway.
        client_kwargs.setdefault("decode_responses", True)
        # Both ceilings, and TWO are needed: ``socket_timeout`` bounds
        # an operation on an already-open connection, never its opening.
        # A host that swallows packets without answering — DNS resolving
        # into the void, a closed security group — only meets the second,
        # and that is the one that hung at STARTUP:
        # ``lifecycle._check_state_backend`` awaits a ``health()``, so the
        # boot itself never finished.
        client_kwargs.setdefault("socket_timeout", _DEFAULT_TIMEOUT_SECONDS)
        client_kwargs.setdefault(
            "socket_connect_timeout", _DEFAULT_TIMEOUT_SECONDS
        )
        # Quick sanity check : reject unknown schemes early.
        scheme = urlparse(url).scheme
        if scheme not in {"redis", "rediss", "unix"}:
            raise BretzelError(
                f"Unsupported Redis URL scheme {scheme!r} : "
                "expected one of 'redis', 'rediss', 'unix'."
            )
        client = redis_asyncio.Redis.from_url(url, **client_kwargs)
        return cls(client, prefix=prefix)

    # ── Key composition ─────────────────────────────────────────────────

    def _compose(self, scope: str, key: str) -> str:
        return f"{self._prefix}:{scope}:{key}"

    # ── Read / write ────────────────────────────────────────────────────

    def _decode(self, raw: Any, scope: str, key: str, field: str) -> Any:
        """The value of ONE field, or the error saying why it is not one.

        Redis never looks INSIDE a value: the JSON stays Python ``json``
        end to end, so nothing can confuse an empty list with an empty
        object.
        """
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BretzelError(
                f"Stored field {field!r} at {scope}:{key} is not valid JSON : "
                f"{exc}. This usually indicates a foreign writer or a backend "
                "version mismatch."
            ) from exc

    def _encode(self, value: Any, scope: str, key: str, field: str) -> str:
        try:
            return json.dumps(value)
        except (TypeError, ValueError) as exc:
            raise BretzelError(
                f"State field {field!r} at {scope}:{key} is not "
                f"JSON-serialisable : {exc}. Bretzel does NOT fall back to "
                "pickle (RCE risk). Make sure your fields hold JSON-friendly "
                "types (str, int, float, bool, None, list, dict) or implement "
                "to_dict() on custom values."
            ) from exc

    def _mapping(
        self, data: dict[str, Any], scope: str, key: str
    ) -> dict[str, str]:
        """``{field: JSON value}`` ready for ``HSET``.

        Encodes EVERYTHING before writing anything: a non-serialisable
        field must fail the whole write, not leave it half laid down.
        """
        return {
            field: self._encode(value, scope, key, field)
            for field, value in data.items()
        }

    @_bounded
    async def load(self, scope: str, key: str) -> dict[str, Any] | None:
        composed = self._compose(scope, key)
        try:
            raw = await self._client.hgetall(composed)
        except redis_exceptions.ResponseError as exc:
            if "WRONGTYPE" not in str(exc).upper():
                raise
            # A row written by the PREVIOUS version (a whole-document
            # JSON, not a hash). It is unreadable here, and worse: it
            # would fail every later write on the same key. We remove it
            # and return "absent", which gives the defaults back — once,
            # and then the row rebuilds itself in the current format. The
            # package is in alpha: there is no old state to preserve,
            # only some not to crash on.
            await self.delete(scope, key)
            return None
        if not raw:
            return None
        return {
            field: self._decode(value, scope, key, field)
            for field, value in raw.items()
        }

    @_bounded
    async def save(
        self,
        scope: str,
        key: str,
        data: dict[str, Any],
        *,
        ttl: int | None = None,
    ) -> None:
        """Replace the whole document.

        No caller left in the framework: the commit goes through
        :meth:`merge`. What remains is seeding, tests and tooling, where
        "lay down exactly this" is what we mean.

        The replacement is a ``DEL`` + ``HSET`` transaction: without the
        ``DEL``, a field removed from the document would survive in the
        hash. No ``PERSIST`` when ``ttl`` is ``None`` — the key has just
        been deleted, it can carry no expiration.

        An EMPTY document therefore leaves only the ``DEL``: the row is
        absent, and not present-but-empty. A Redis hash cannot exist
        without a field, and the registry reads "absent" and "empty" the
        same way — both return the defaults.
        """
        mapping = self._mapping(data, scope, key)
        composed = self._compose(scope, key)
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.delete(composed)
            if mapping:
                pipe.hset(composed, mapping=mapping)
                if ttl is not None:
                    pipe.expire(composed, ttl)
            await pipe.execute()

    @_bounded
    async def merge(
        self,
        scope: str,
        key: str,
        changes: dict[str, Any],
        *,
        add: dict[str, Any] | None = None,
        ttl: int | None = None,
    ) -> None:
        """Write the fields of ``changes``, and THOSE ALONE.

        **One single command, and no read.** ``HSET`` is atomic per field
        on the Redis side: two requests writing different fields of the
        same key cannot erase each other, with no lock, no optimistic
        transaction and no retry loop.

        ``add`` goes out as ``HINCRBY`` — or ``HINCRBYFLOAT`` if the delta
        is decimal, Redis having two commands where Python has one
        number. It is REDIS that sums, so two requests that read the same
        total both count. The result stays valid JSON: ``json.dumps(5)``
        writes ``5``, which those commands know how to read, and what
        they return reads back the same (verified).

        With a ``ttl``, the value and the expiration go out in the SAME
        transaction: separated, one request's ``EXPIRE`` could land after
        another's and leave a duration that is no longer the right one.

        ``ttl=None`` does NOT touch the existing expiration — unlike
        :meth:`save`, which replaces everything. A partial write has no
        business deciding the fate of a duration it did not set, and the
        two scopes concerned (``user``, ``app``) never have one anyway.
        """
        if not changes and not add:
            return
        composed = self._compose(scope, key)
        mapping = self._mapping(changes, scope, key) if changes else {}
        # One command stays one command: no pipeline when there is
        # nothing else to put in it.
        if mapping and not add and ttl is None:
            await self._client.hset(composed, mapping=mapping)
            return
        async with self._client.pipeline(transaction=True) as pipe:
            if mapping:
                pipe.hset(composed, mapping=mapping)
            for field, delta in (add or {}).items():
                if isinstance(delta, int):
                    pipe.hincrby(composed, field, delta)
                else:
                    pipe.hincrbyfloat(composed, field, delta)
            if ttl is not None:
                pipe.expire(composed, ttl)
            await pipe.execute()

    # ── Verrou ──────────────────────────────────────────────────────────

    @_bounded
    async def acquire(
        self, scope: str, key: str, token: str, *, ttl: int
    ) -> bool:
        """``SET key token NX EX ttl`` — Redis's atomic take.

        ``NX`` only succeeds if the key does not exist: that is exactly
        "take the lock if nobody holds it", with no prior read and no
        race between the two.
        """
        taken = await self._client.set(
            self._lock_key(scope, key), token, nx=True, ex=ttl
        )
        return bool(taken)

    @_bounded
    async def release(self, scope: str, key: str, token: str) -> None:
        """Release IF the token is ours, with no window in between.

        A separate ``GET`` then ``DEL`` would leave room for an
        expiration in the middle: we would then erase a successor's lock,
        who would believe itself alone. ``WATCH`` closes that window — if
        the key moves between the read and the ``EXEC``, the transaction
        fails and we touch nothing, which is exactly the right behaviour:
        our lock had already expired.

        No retry. A failure here means "it is no longer ours", not "try
        again".

        (A Lua script would do the same in one round trip, but
        ``fakeredis`` does not run it without an extra Lua engine — and a
        guarantee no test can exercise is not one.)
        """
        key = self._lock_key(scope, key)
        async with self._client.pipeline(transaction=True) as pipe:
            await pipe.watch(key)
            if await pipe.get(key) != token:
                await pipe.reset()
                return
            pipe.multi()
            pipe.delete(key)
            try:
                await pipe.execute()
            except redis_exceptions.WatchError:
                # Somebody touched the key while we were looking: our
                # lock was therefore no longer ours. Do nothing.
                return

    def _lock_key(self, scope: str, key: str) -> str:
        """A namespace SEPARATE from the states'.

        The lock and the row it protects must not share a key: a
        ``clear_scope`` would sweep both, and a held lock would vanish
        from under its holder.
        """
        return f"{self._prefix}:lock:{scope}:{key}"

    @_bounded
    async def delete(self, scope: str, key: str) -> None:
        await self._client.delete(self._compose(scope, key))

    # ── Bulk operations ─────────────────────────────────────────────────

    async def scan(self, pattern: str) -> AsyncIterator[str]:
        # ``pattern`` is in the registry's logical space ; prepend the
        # prefix so callers don't need to think about the wire layout.
        wire_pattern = f"{self._prefix}:{pattern}"
        prefix_len = len(self._prefix) + 1  # ``+1`` for the trailing colon
        async for storage_key in self._client.scan_iter(match=wire_pattern):
            # Strip the backend prefix so callers see the same space they
            # write to via ``(scope, key)``.
            yield storage_key[prefix_len:]

    @_bounded
    async def clear_scope(
        self,
        scope: str,
        *,
        pattern: str | None = None,
    ) -> int:
        suffix = pattern if pattern else "*"
        wire_pattern = f"{self._prefix}:{scope}:{suffix}"
        # Stage the matching keys ; ``DEL`` accepts variadic arguments so
        # we can drop them in one round-trip when there are few enough.
        victims: list[str] = []
        async for storage_key in self._client.scan_iter(match=wire_pattern):
            victims.append(storage_key)
        if not victims:
            return 0
        # Chunk to keep the DEL command bounded — Redis supports thousands
        # of args per call but we stay well under typical limits.
        deleted = 0
        for chunk in _chunks(victims, 1024):
            deleted += await self._client.delete(*chunk)
        return deleted

    async def health(self) -> bool:
        try:
            return bool(await self._client.ping())
        except Exception:
            return False

    # ── Lifecycle ───────────────────────────────────────────────────────

    async def close(self) -> None:
        """Tear down the connection pool. Called on app shutdown."""
        await self._client.aclose()


def _chunks(seq: list[str], size: int) -> Iterator[list[str]]:
    """Yield successive ``size``-length slices of ``seq``."""
    for i in range(0, len(seq), size):
        yield seq[i : i + size]
