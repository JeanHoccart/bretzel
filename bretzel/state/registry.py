"""Per-request state registry.

Holds three responsibilities :

1. **Per-request instance cache.** Calling ``CartState()`` twice during
   the same request must return the same instance — otherwise mutations
   in one place wouldn't be visible in another. The metaclass
   :class:`bretzel.state.base._StateMeta` intercepts construction and
   delegates to the registry when one is active.

2. **Backend orchestration.** :py:meth:`resolve` async-loads a
   :class:`~bretzel.state.scopes.server.ServerState` from the
   :class:`~bretzel.state.persistence.base.Backend` ; :py:meth:`commit`
   saves every dirty server-side state at end of request.

3. **Client-side hydration.** When the request's client-state payload
   has been parsed from namespaced form-data in the POST body, ``ClientState``
   instances pick up the client-supplied values automatically on
   construction.

The registry is bound to the active async task via
:class:`~contextvars.ContextVar` ; concurrent requests have isolated
registries with no manual plumbing.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

import anyio.from_thread

# Canonical definitions live in ``core`` so the state and server layers use
# the same exception classes without violating the import DAG.
from bretzel.core.errors import AuthRequiredError, BretzelError
from bretzel.core.tracking import TRACKER
from bretzel.state._wire_name import wire_name
from bretzel.state.base import State
from bretzel.state.persistence.base import Backend
from bretzel.state.scopes.client import ClientState
from bretzel.state.scopes.server import ServerScope, ServerState
from bretzel.state.types import encode_value
from bretzel.state.url import apply_url_params, collect_url_params

if TYPE_CHECKING:
    from bretzel.state.locking import StateLock

# Sentinel for "field absent from a snapshot" — distinct from any real
# field value (including ``None``) so an added/removed field diffs as a
# change.
_ABSENT: Any = object()

# ───────────────────────────────────────────────────────────────────────────
# Errors
# ───────────────────────────────────────────────────────────────────────────


class ScopeConfigError(RuntimeError):
    """Raised when scope-specific identity is missing (no session id …)."""


class StateHydrationError(BretzelError):
    """Raised when server state cannot be hydrated safely."""


# ───────────────────────────────────────────────────────────────────────────
# Default TTLs per scope (seconds). Overridable via Bretzel(...) config.
# ───────────────────────────────────────────────────────────────────────────


# TTL per scope:
DEFAULT_TTLS: dict[str, int | None] = {
    "session": 24 * 3600,  # 24 hours (independent of the session cookie, which defaults to 30 days — cf. config.session_max_age_days)
    "user": None,  # account-scoped, no expiry
    "app": None,  # process-lived defaults
    # ``page`` lives as long as the user stays on the same render of
    # the page ; we cap it at 1 hour as a safety net (long-idle tabs
    # whose UUIDs the server has long forgotten).
    "page": 3600,
}


# ───────────────────────────────────────────────────────────────────────────
# Context-var binding
# ───────────────────────────────────────────────────────────────────────────


_CURRENT: ContextVar[StateRegistry | None] = ContextVar(
    "bretzel_current_registry", default=None
)


def current_registry() -> StateRegistry | None:
    """Return the registry bound to the active async task, if any.

    Used by the metaclass to intercept state construction. Returns
    ``None`` outside of a request — direct ``CartState()`` then behaves
    as a vanilla constructor (useful in tests).
    """
    return _CURRENT.get()


@contextmanager
def use_registry(registry: StateRegistry) -> Iterator[None]:
    """Bind a registry as the active one for the current task."""
    token = _CURRENT.set(registry)
    try:
        yield
    finally:
        _CURRENT.reset(token)


# ───────────────────────────────────────────────────────────────────────────
# Registry
# ───────────────────────────────────────────────────────────────────────────


class StateRegistry:
    """Per-request resolver, hydrator and committer."""

    def __init__(
        self,
        backend: Backend,
        *,
        client_payload: dict[str, dict[str, Any]] | None = None,
        form_data: dict[str, Any] | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        page_id: str | None = None,
        url_params: dict[str, str] | None = None,
        ttls: dict[str, int | None] | None = None,
    ) -> None:
        self._backend = backend
        self._client_payload: dict[str, dict[str, Any]] = client_payload or {}
        # ``form_data`` is set by the request middleware after parsing the
        # body (multipart / urlencoded) and exposed to user code via
        # :func:`bretzel.state.form_value`.
        self.form_data: dict[str, Any] = form_data or {}
        self._session_id = session_id
        self._user_id = user_id
        # Page-scope identity : the ``bz-page-<uuid>`` stamp generated
        # at full-document render and echoed back via the
        # ``X-Bretzel-Page-ID`` header on every action POST. Identical
        # uuid across actions on the same page → state continuity ;
        # F5 / navigate → fresh uuid → fresh PageState.
        self._page_id = page_id
        #: The parameters of the CURRENT URL, by value. The ``state``
        #: layer sits below ``render`` and ``server`` in the DAG: it
        #: cannot reach back up to read the request, so the caller passes
        #: them in — exactly like ``page_id`` and ``session_id``.
        self._url_params: dict[str, str] = dict(url_params or {})
        self._ttls = {**DEFAULT_TTLS, **(ttls or {})}
        self._instances: dict[tuple[type[State], str], State] = {}
        #: The PAGE rows this request found in the store or wrote — the
        #: ones the page's witness lists (:meth:`save_page_witness`). A
        #: state left at its defaults has no row: it cannot expire, so it
        #: is not listed.
        self._page_rows: set[str] = set()
        #: ``{class: {modified fields}}``, filled by
        #: :meth:`diff_and_notify`. Empty as long as no diff has run — so
        #: empty on a full page render, which is the right default: "we
        #: do not know what changed" must re-render everything.
        self.changed_fields: dict[type[State], set[str]] = {}
        #: The field names an action set to something else than what its
        #: own submission carried — the browser still shows the
        #: submission. Filled by :meth:`diff_and_notify`.
        self.overridden_fields: set[str] = set()
        #: Set by :meth:`commit`. An action and a page commit themselves;
        #: the render-context middleware commits for every other route
        #: — an app's JSON API — and reads this to do it only once.
        self.committed = False

    def discard(self) -> None:
        """Forget every state resolved so far, unsaved writes included.

        An error page renders after the code that raised: what that code
        half-wrote must not be committed with the page. The next
        ``MyState()`` reads the store again.
        """
        self._instances.clear()
        self.changed_fields = {}
        self.overridden_fields = set()

    def rebind(self, *, session_id: str | None, user_id: str | None) -> None:
        """The request changed identity — ``auth.login`` / ``auth.logout``.

        The registry is built with the identity the request ARRIVED with.
        Without this call, after a login, a ``SessionState`` written in
        the same handler would land in the PRE-login session — the one an
        attacker who planted a session cookie knows, so the rotation would
        protect nothing — and a ``UserState`` would raise
        ``AuthRequiredError``.

        The session and user instances resolved so far belong to the old
        identity: they are forgotten, so the next ``MyState()`` reads the
        new one's store. The others (app, page, client) do not depend on
        who the caller is.
        """
        self._session_id = session_id
        self._user_id = user_id
        for cls, key in list(self._instances):
            if getattr(cls, "__scope__", None) in ("session", "user"):
                del self._instances[(cls, key)]

    # ── Cache primitives — used by the metaclass on every State() call ──

    def get_cached(self, cls: type[State], key: str = "default") -> State | None:
        return self._instances.get((cls, key))

    def register(self, instance: State, key: str = "default") -> None:
        self._instances[(type(instance), key)] = instance
        if isinstance(instance, ServerState):
            # ── TWO snapshots, and the URL seeding goes BETWEEN them ──
            #
            # ``deepcopy`` on both sides: ``_field_values`` returns live
            # references, so a shallow copy would alias an in-place
            # mutation and the diff would see nothing.

            # ① what comes FROM STORAGE. The commit uses it to write
            # only the modified fields, and therefore not to overwrite
            # what a concurrent request put in the others. Taken BEFORE
            # the seeding: otherwise a ``?sort=name`` reads as "already
            # stored", is never written, and the next action — whose URL
            # carries no query — finds the old sort again.
            instance._bz_stored = copy.deepcopy(instance._field_values())

            # "Absent = nothing is touched": that is what makes the
            # mechanism work on an action too, whose URL carries no
            # query — the state keeps what it had.
            apply_url_params(instance, self._url_params)

            # ② the MUTATION reference, taken AFTER the seeding:
            # before, the seeding would read as a mutation, the state
            # would leave ``dirty``, and the first rendered page would
            # push a URL when nothing had moved. ``diff_and_notify``
            # takes it again on every action — that is why it cannot
            # serve the commit, which needs a fixed point.
            instance._bz_baseline = copy.deepcopy(instance._field_values())

    # ── Sync-load fast path (called from the State metaclass) ──────────

    def try_sync_resolve(
        self,
        cls: type[State],
        key: str = "default",
    ) -> State | None:
        """Hydrate a ``ServerState`` from the backend synchronously.

        Used by :meth:`bretzel.state.base._StateMeta.__call__` to keep
        ``MyState()`` synchronous whatever the backend. Two paths, and
        the second one is the reason this comment exists:

        - the backend exposes ``load_sync`` (memory) → direct read;
        - it does not (Redis) → :meth:`_load_via_loop` has the async
          ``load`` executed BY the loop and awaits its result from the
          pool thread.

        ⚠️ The second path depends on the offload of app code onto the
        threadpool (``core/invoke.py``), which gives a thread where
        waiting is ALLOWED. Returning ``None`` for such a backend would
        give the default values, and — the commit only looking at the
        ``_dirty`` flag — the first mutation would overwrite what is
        stored.

        Returns the hydrated instance (already registered in the
        cache) or ``None`` when the backend holds no entry for it.
        """
        scope = getattr(cls, "__scope__", None)
        if scope is None:
            # Bare ``State`` has no scope — nothing to look up.
            return None

        try:
            storage_key = self._compose_storage_key(
                scope, cls.__name__, key  # type: ignore[arg-type]
            )
        except ScopeConfigError:
            # No identity for this scope (e.g. user-scope without auth) —
            # leave the metaclass to construct a fresh defaults instance.
            return None

        load_sync = getattr(self._backend, "load_sync", None)
        if callable(load_sync):
            raw = load_sync(scope, storage_key)
        else:
            raw = self._load_via_loop(cls, scope, storage_key)
        if raw is None:
            return None

        return self._build(cls, key, raw)

    def _build(
        self,
        cls: type[State],
        key: str,
        raw: dict[str, Any] | None,
    ) -> State:
        """Build the hydrated instance and register it in the cache.

        ⚠️ ``type.__call__`` and not ``cls(...)``: the metaclass
        intercepts the second form and RESTARTS a hydration, so a call
        from :meth:`resolve` — which has just read the backend — would
        fall back into :meth:`try_sync_resolve`. On the loop, that
        re-entry raises instead of returning the object we already hold:
        ``await MyState.load()`` would fail with the error recommending
        ``await MyState.load()``.

        The same gesture serves both read paths, sync and async: two
        concurrent constructions would end up diverging, and the version
        that stayed in ``resolve`` (``cls.from_dict``) also went through
        the metaclass.
        """
        instance = type.__call__(cls, key=key)
        if raw is not None:
            self._note_page_row(cls, key)
            instance._apply_fields(raw)
            # We have just READ: this is not a user mutation.
            instance._dirty = False
        self.register(instance, key)
        return instance

    def _load_via_loop(
        self,
        cls: type[State],
        scope: str,
        storage_key: str,
    ) -> dict[str, Any] | None:
        """Have the async-only backend read BY the loop, and wait.

        Called from a pool thread — that is where all ``def`` app code
        runs since the offload. Blocking that thread freezes nothing: the
        loop keeps serving the other requests, and it is even the loop
        that executes the ``load``.

        It is the exact INVERSE of
        :func:`bretzel.core.call_without_blocking`, and that is why there
        is no hand-written discriminant here: ``anyio.from_thread.run``
        works ONLY from a thread ``anyio.to_thread.run_sync`` opened, and
        it says so with an exception of its own. A call left on the loop
        — ``async def`` app code — therefore falls into the ``except``,
        where blocking would have frozen the worker.

        Raising is deliberately harsher than the old ``return None``,
        which returned defaults the commit then rewrote over the stored
        value.
        """
        try:
            return anyio.from_thread.run(self._backend.load, scope, storage_key)
        except anyio.from_thread.NoEventLoopError:
            raise StateHydrationError(
                f"{cls.__name__}() cannot hydrate here: the "
                f"{type(self._backend).__name__} backend reads "
                f"asynchronously, and this code runs on the loop — waiting "
                f"there would freeze it for everyone. Write "
                f"`state = await {cls.__name__}.load()`, or put this body "
                f"back to `def` (the framework will offload it to a thread, "
                f"where `{cls.__name__}()` works as-is)."
            ) from None

    # ── Server-side resolution ──────────────────────────────────────────

    async def resolve(
        self,
        cls: type[ServerState],
        key: str = "default",
    ) -> ServerState:
        """Return a hydrated instance of ``cls``, loading from backend if
        needed.

        Cached after the first call : two ``await registry.resolve(...)``
        on the same ``(cls, key)`` return the same instance.
        """
        cached = self._instances.get((cls, key))
        if cached is not None:
            assert isinstance(cached, cls)
            return cached

        scope = cls.__scope__

        # ``page`` scope persists keyed by ``page_id`` — same uuid
        # across actions on one rendered page, fresh uuid on
        # reload / navigation.
        storage_key = self._compose_storage_key(scope, cls.__name__, key)
        raw = await self._backend.load(scope, storage_key)
        return self._build(cls, key, raw)  # type: ignore[return-value]

    # ── Client-side hydration ───────────────────────────────────────────

    def hydrate_client(self, instance: ClientState) -> None:
        """Apply the request's parsed client-state payload (V3 :
        namespaced form-data from the POST body) to ``instance`` if a
        matching entry exists.

        Hydration is direct attribute assignment, which goes through
        ``Field.__set__`` → field validators run, dirty flag flips. We
        reset ``_dirty`` afterwards : an inbound payload is not a user
        mutation that should propagate back as a save.
        """
        envelope_key = f"{type(instance).__name__}.{instance._key}"
        data = self._client_payload.get(envelope_key)
        if data is None:
            return
        instance._apply_fields(data)
        instance._dirty = False

    async def reload(self, cls: type[State], key: str = "default") -> State:
        """Re-read this state FROM the store, and refresh the instance.

        Mutate the instance in place rather than setting down a fresh
        one: a variable taken before the block (``store = Kanban()``)
        must see the fresh values too, otherwise the lock would protect
        an object the caller does not use.

        The fields ABSENT from the store go back to their default — a
        deleted row must read as deleted, not as what we had in memory.

        Both snapshots are retaken: what we have just read IS the store's
        state, so the write on exit must send only what the block will
        have changed.
        """
        scope = cls.__scope__  # type: ignore[attr-defined]
        storage_key = self._compose_storage_key(scope, cls.__name__, key)
        raw = await self._backend.load(scope, storage_key)

        instance = self._instances.get((cls, key))
        if instance is None:
            return self._build(cls, key, raw)

        for name, fld in type(instance)._all_fields().items():
            if raw is not None and name in raw:
                continue
            # Not in the store: removing the value we set makes the
            # declared default reappear.
            instance.__dict__.pop(fld._storage_key, None)
        if raw:
            instance._apply_fields(raw)
        instance._dirty = False
        photo = copy.deepcopy(instance._field_values())
        instance._bz_stored = photo
        instance._bz_baseline = copy.deepcopy(photo)
        return instance

    def lock(
        self,
        cls: type[State],
        key: str = "default",
        *,
        ttl: int | None = None,
        timeout: float | None = None,
    ) -> StateLock:
        """The context manager behind ``MyState.lock()``."""
        from bretzel.state.locking import (
            DEFAULT_LOCK_TIMEOUT,
            DEFAULT_LOCK_TTL,
            StateLock,
        )

        return StateLock(
            self,
            cls,  # type: ignore[arg-type]
            key,
            ttl=DEFAULT_LOCK_TTL if ttl is None else ttl,
            timeout=DEFAULT_LOCK_TIMEOUT if timeout is None else timeout,
        )

    # ── End-of-request commit ───────────────────────────────────────────

    async def commit(self) -> None:
        """Persist every dirty :class:`ServerState` to the backend.

        ``ClientState`` is not committed — its mutations are emitted via
        the response delta and applied client-side. Every server scope
        (``session`` / ``user`` / ``app`` / ``page``) flows through
        ``_compose_storage_key`` and gets its own row.

        **We write the modified FIELDS, not the document.** Rewriting the
        whole document would erase what a concurrent request has just
        written into the other fields: two tabs, request A changes the
        filter, request B the cart, and the last to commit would make the
        other change invisible — with no error, no trace. The registry
        knows the touched fields (the snapshot taken at read time) and the
        backend applies the merge atomically, so B cannot erase A.

        ⚠️ Two requests modifying THE SAME field still lose one write,
        and it is a test that holds that limit rather than a sentence:
        ``tests/unit/state/test_a_commit_keeps_a_concurrent_field.py``.

        ⚠️ Atomicity is **per row, not per request**: a request touching
        three states makes three independent atomic writes, and a failure
        leaves part of it persisted. True before the grouping, true
        after — but the grouping changes WHICH part, and for the better:
        cf. below.

        A state marked dirty whose fields have not moved writes NOTHING:
        that happens when a mutation comes back to its original value
        within the same request.

        **A state READ and not written still pushes back its expiration.**
        If the duration of a scope (``page``: one hour) were only set
        again on a write, a tab whose clicks only read — open a detail,
        change nothing — would lose its ``PageState`` an hour after the
        last write, and the next click would find the defaults: a
        selection or a draft gone, with no word, since an absent row reads
        like an empty one. A state in use lives; the duration counts from
        its last request, as a session cookie does. Same commit, same
        grouped round trip: a read costs one ``EXPIRE``, on a row that
        exists — an absent one is not created.

        **The writes go out TOGETHER.** An ``await`` loop would pay one
        network round trip per state, in series: N RTT windows against a
        single one once grouped, so the gain is ``(N-1) × RTT`` by
        construction. The number of calls does not change — what changes
        is their overlap.

        ⚠️ ``asyncio.gather`` and **not** an anyio task group, and it is
        the failure mode that settles it, not the style. A task group
        cancels its siblings on the first error, so it would persist LESS
        than the sequential loop it replaces. ``gather`` lets the writes
        already in flight complete: on a failure, the other N-1 states are
        still recorded, and that is strictly better than the old
        behaviour where everything after the error was lost. The
        exception surfaces just the same.

        Each ``write_one`` touches only ITS instance (its delta, its
        snapshot); nothing is shared between the coroutines, apart from
        the backend, which is built for it.
        """
        # ``gather`` accepts zero and one coroutine: a shortcut for
        # those two cases lived for the length of one re-read, and it cost
        # a SECOND call site of ``write_one`` to keep in agreement with
        # the first — in the method whose docstring says precisely that a
        # duplicated computation "would have diverged at the first
        # change". What it saved, one ``Task`` (~µs), is three orders of
        # magnitude below the RTT this grouping exists to hide.
        self.committed = True
        await asyncio.gather(
            *(
                self.write_one(cls, key, instance)
                for (cls, key), instance in self._instances.items()
                if isinstance(instance, ServerState)
            )
        )

    async def write_one(
        self, cls: type[State], key: str, instance: ServerState
    ) -> None:
        """Write ONE state: the fields modified since its snapshot.

        Extracted from :meth:`commit` so that the lock (:meth:`lock`)
        writes in exactly the same way when leaving its block. Two
        separate delta computations would have diverged at the first
        change — and it is the computation that carries the whole
        lost-update fix.
        """
        scope = cls.__scope__  # type: ignore[attr-defined]
        try:
            storage_key = self._compose_storage_key(scope, cls.__name__, key)
        except ScopeConfigError:
            # No identity available (e.g. page-scope without a
            # page_id, or user-scope without auth) — skip rather
            # than crash. Mutations land in-memory only.
            return
        ttl = self._ttls.get(scope)
        current = instance.to_dict() if instance._dirty else {}
        stored = instance._bz_stored
        # We walk ``current``, NOT the union of the two: the snapshot
        # carries the effective values (defaults included) and
        # ``to_dict`` only the fields that were set, so a key present
        # on one side and not the other is normal, and is not a
        # change. ``diff_and_notify``, which compares two snapshots of
        # the SAME shape, takes the union — each is right for its own
        # question.
        fields = type(instance)._all_fields()
        changes: dict[str, Any] = {}
        deltas: dict[str, Any] = {}
        for name, value in current.items():
            stored_value = stored.get(name, _ABSENT)
            if stored_value == value:
                continue
            fld = fields.get(name)
            if fld is not None and fld.merge == "add" and stored_value is not _ABSENT:
                # An additive field is written as a DELTA, not as a
                # value: the store applies it without reading, so two
                # requests that read the same number both count. A zero
                # delta writes nothing.
                delta = value - stored_value
                if delta:
                    deltas[name] = delta
            else:
                changes[name] = value
        if not changes and not deltas:
            # Read, not written: the row's expiration still moves back
            # (cf. :meth:`commit`). An empty merge creates no row.
            if ttl is not None:
                await self._backend.merge(scope, storage_key, {}, ttl=ttl)
        else:
            # Encoded HERE, and not in the backends: that is what keeps
            # memory and Redis from diverging. Before, memory kept the
            # live Python object, so a ``date`` field worked in dev and
            # raised the day Redis was plugged in.
            await self._backend.merge(
                scope,
                storage_key,
                {n: encode_value(v) for n, v in changes.items()},
                add=deltas,
                ttl=ttl,
            )
            # The snapshot follows what we have just set down — the
            # written fields only, not the whole state: a second commit
            # in the same request must not rewrite them, and
            # deep-copying the whole state would copy every row for
            # one field that moves.
            #
            # For an additive field, the snapshot takes the LOCAL value
            # and not the true total: the store may have counted the
            # contributions of other requests, which we do not read
            # back. That is accepted — the page displays what this
            # request computed, and the next refresh will show the
            # total.
            applied = {**changes, **{n: current[n] for n in deltas}}
            instance._bz_stored = {**stored, **copy.deepcopy(applied)}
            self._note_page_row(cls, key)
        instance._dirty = False

    # ── An expired page says so ───────────────────────────────────────────
    #
    # A ``PageState`` lives an hour (``DEFAULT_TTLS["page"]``). A tab left
    # open longer, then clicked, finds its states gone: the registry gives
    # the defaults back, and the click would act on a selection reset to
    # zero, without a word. The registry cannot tell « never written » from
    # « expired » — a state at its defaults has no row. So each response
    # leaves a WITNESS of the rows its page holds, living longer than them,
    # and an action checks it first.

    #: The witness outlives the rows it lists, so their expiry can be seen.
    PAGE_WITNESS_TTL: int = 24 * 3600

    def _note_page_row(self, cls: type[State], key: str) -> None:
        if getattr(cls, "__scope__", None) == "page" and self._page_id is not None:
            self._page_rows.add(self._compose_storage_key("page", cls.__name__, key))

    def _witness_key(self) -> str:
        return f"{self._page_owner()}:__witness__"

    def _page_owner(self) -> str:
        """A page's rows belong to the session that rendered it.

        ⚠️ Keyed by ``page_id`` alone, a page's state would be readable
        and writable by ANY session presenting that id in
        ``X-Bretzel-Page-ID`` — an id that sits in the page's own HTML,
        and leaks through a screenshot, a shared screen or a log.
        """
        return f"{self._session_id or ''}|{self._page_id}"

    async def page_expired(self) -> bool:
        """``True`` when a row this page held has gone from the store."""
        if self._page_id is None:
            return False
        witness = await self._backend.load("page", self._witness_key())
        rows = (witness or {}).get("rows") or []
        self._page_rows.update(rows)
        for row in rows:
            if await self._backend.load("page", row) is None:
                return True
        return False

    async def save_page_witness(self) -> None:
        """Write (and prolong) the witness of the rows this page holds."""
        if self._page_id is None or not self._page_rows:
            return
        await self._backend.merge("page", self._witness_key(),
                                  {"rows": sorted(self._page_rows)},
                                  ttl=self.PAGE_WITNESS_TTL)

    # ── End-of-action change detection ───────────────────────────────────

    def diff_and_notify(self) -> set[type[State]]:
        """Detect ``ServerState`` mutations since resolve, fire the change
        signal for each changed field, and return the set of changed
        ``ServerState`` CLASSES (so the caller can refresh the zones that
        read them).

        Value-based : compares each instance's current :meth:`_field_values`
        against the baseline snapshot taken in :meth:`register`, so it catches
        EVERY mutation form — reassignment AND in-place list/dict/set ops
        (``state.items.append(...)``, ``state.d[k] = v``, …) and nested
        mutations — that :meth:`Field.__set__` alone never sees. On a change
        it flips ``_dirty`` (so :meth:`commit` persists the in-place mutation,
        which it otherwise skips) and calls ``TRACKER.notify_change`` — the
        exact signal ``Field.__set__`` fires on reassignment — then re-baselines.

        Call end-of-action, BEFORE the refresh drain, so the change reaches
        the current response's re-render. ClientState is skipped : it rides
        the ``<bz-patch>`` delta, not this diff.
        """
        changed_classes: set[type[State]] = set()
        # The NAMES of the fields, by class. The loop already knows
        # them; returning only the classes would throw away the most useful
        # information — "what changed", not just "who". A partial render
        # can use it to avoid re-emitting what cannot have moved (cf. the
        # datatable's toolbar). An attribute rather than a return value:
        # callers read the set of classes.
        self.changed_fields = {}
        for instance in list(self._instances.values()):
            if not isinstance(instance, ServerState):
                continue
            baseline = getattr(instance, "_bz_baseline", None)
            if baseline is None:
                continue
            current = instance._field_values()
            moved = {name for name in set(current) | set(baseline)
                     if current.get(name, _ABSENT) != baseline.get(name, _ABSENT)}
            # The SUBMISSION is a second reference: the browser shows what
            # it sent, not what the store held, so a submitted field put
            # back to its stored value has changed on screen.
            overridden = {name for name, sent in instance.__dict__.pop("_bz_posted", {}).items()
                          if current.get(name, _ABSENT) != sent}
            # The CONTROLS' names, which the zone diff looks for: the wire
            # name a bound control carries (``State.field``), and the bare
            # field of one the app named itself (``state/_wire_name.py``).
            self.overridden_fields |= overridden | {
                wire_name(type(instance).__name__, instance._key, name)
                for name in overridden
            }
            if moved:
                instance._dirty = True
            for name in moved | overridden:
                TRACKER.notify_change(instance, name)
                self.changed_fields.setdefault(type(instance), set()).add(name)
            changed = bool(moved or overridden)
            if changed:
                instance._bz_baseline = copy.deepcopy(current)
            # A REFUSED submission is a change too, of what the form
            # shows: its messages. Every value may be unchanged (all
            # refused, or resubmitted as is), and the diff above then saw
            # nothing — the action answered 204 and no error ever
            # appeared. Not ``_dirty``: nothing to persist.
            errors = instance.__dict__.get("_bz_errors")
            if errors and errors != instance.__dict__.get("_bz_errors_shown"):
                instance.__dict__["_bz_errors_shown"] = dict(errors)
                for name in errors:
                    if name in current:
                        TRACKER.notify_change(instance, name)
                self.changed_fields.setdefault(type(instance), set()).update(
                    name for name in errors if name in current)
                changed = True
            if changed:
                changed_classes.add(type(instance))
        return changed_classes

    # ── Addressable state ───────────────────────────────────────────────

    def addressable_params(self) -> dict[str, str]:
        """``{parameter: value}`` for every ``URL``-declared field this request.

        Reads only the ALREADY-resolved states: the ones the page really
        mounted. A state that was never built has nothing to say about
        the URL, and guessing its value would make a parameter appear for
        a view that is not on screen.
        """
        return collect_url_params(list(self._instances.values()))

    def addressable_param_names(self) -> set[str]:
        """ALL the declared parameter names, at their default value or not.

        ``addressable_params`` returns only what is NOT at its default —
        that is what keeps the URL readable. But recomposing an address
        also requires knowing what to REMOVE: a field back at its default
        disappears from the first list, and without this one it would
        stay stale in the URL.

        Without it, sorting by one column then returning to the default
        sort would leave ``?sort=sector`` in place. The URL being
        authoritative on the next action, it would re-seed
        ``sort_key=sector`` and overwrite the click. A stale address does
        not merely lie: it DRIVES.
        """
        from bretzel.state.url import addressable_fields

        out: set[str] = set()
        for instance in self._instances.values():
            out.update(addressable_fields(type(instance)).values())
        return out

    def addressable_changed(self, changed: dict[type[State], set[str]]) -> bool:
        """Has an ADDRESSABLE field moved in this diff?

        That is the question deciding whether to push a URL, and it is
        narrower than "the state changed": paginating a table whose sort
        alone is declared must push nothing. Otherwise every action would
        stack a history entry identical to the previous one, and the back
        button would need ten clicks to leave a page.
        """
        from bretzel.state.url import addressable_fields

        return any(
            names & set(addressable_fields(cls))
            for cls, names in changed.items()
        )

    # ── Storage-key composition ─────────────────────────────────────────

    def _compose_storage_key(
        self,
        scope: ServerScope,
        class_name: str,
        state_key: str,
    ) -> str:
        """Compose the logical key handed to the backend.

        The backend prepends its own ``{prefix}:{scope}:`` ; this function
        produces only the per-(scope, identity) tail.
        """
        if scope == "session":
            if self._session_id is None:
                raise ScopeConfigError(
                    "Session-scoped state needs a session id ; the "
                    "session middleware must populate one before resolve()."
                )
            return f"{self._session_id}:{class_name}:{state_key}"

        if scope == "user":
            if self._user_id is None:
                raise AuthRequiredError(
                    f"User-scoped state {class_name!r} requires an "
                    "authenticated user."
                )
            hashed = hashlib.sha256(self._user_id.encode("utf-8")).hexdigest()
            return f"{hashed}:{class_name}:{state_key}"

        if scope == "app":
            return f"{class_name}:{state_key}"

        if scope == "page":
            if self._page_id is None:
                raise ScopeConfigError(
                    "Page-scoped state needs a page id ; the render "
                    "context middleware must populate one before resolve()."
                )
            return f"{self._page_owner()}:{class_name}:{state_key}"

        raise ScopeConfigError(f"Unknown server scope {scope!r}")
