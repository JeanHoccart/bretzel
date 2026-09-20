"""SSE broker — per-session message queues + state subscription tracking.

The broker is the single point through which ``_publish_broadcast`` → ``broker.publish``
fans out a "state X is dirty" signal to every browser tab currently
viewing a zone that subscribed to X. Two responsibilities:

1. **Subscription bookkeeping** — at page render time, each
   ``@refreshable(deps=[State], broadcast=[State])`` zone records itself
   against the request's session_id +
   ``State.__module__::State.__qualname__`` identifier. Re-renders
   refresh the bookkeeping; idle sessions age out via TTL.

   ⚠️ This line announced an ``@app.subscribe(State)`` decorator until
   2026-08-15, with a cross-reference to
   ``bretzel.render.decorators.subscribe`` — **a module deleted in Phase
   6**. There is **only one** way to subscribe: ``broadcast=[State]`` on
   a refreshable zone. The cost of the gap was not the false line, it is
   that it suggested two competing APIs for one mechanism, in a
   repository whose principle 4 is "one single way to do each thing".

2. **Event dispatch** — :meth:`publish` walks the subscribers for the
   target State and pushes a tiny ``state-dirty`` SSE event onto each
   one's queue. The HTTP route ``/_bretzel/sse`` drains the queue and
   formats it into the wire format the browser's ``EventSource``
   expects. The **payload is empty**: the runtime, on receiving the
   event, fires an HTTP GET against ``/_bretzel/realtime/<state>/<zone>``
   to re-render the zone in the **client's own RenderContext** — auth
   cookies and everything else come along naturally. No data ever
   travels through the SSE pipe except the State identifier.

**Scaling.** Two implementations behind the :class:`SSEBroker` protocol:
the in-process :class:`MemoryBroker` (single process — subscriber state
lives on the worker that rendered the page) and the :class:`RedisBroker`,
which fans the ``state-dirty`` signal across workers over a Redis Pub/Sub
channel. The lifecycle picks the Redis-backed one whenever ``redis_url``
is configured (``server/lifecycle.py``), so **realtime
(``broadcast=[State]``) works across ``workers>1`` and across replicas**.
Without a ``redis_url`` you get the single-process broker — fine for dev
and single-worker deployments (the config already forces a ``redis_url``
when ``workers>1``).

**Backpressure.** Each connection's queue is bounded
(:data:`_MAX_QUEUE_CHUNKS`, drop-oldest) and each session is capped to
:data:`_MAX_CONNS_PER_SESSION` tabs (oldest evicted) so a slow consumer
or a tab-spamming client can't pin unbounded memory. NOT yet bounded:
the GLOBAL connection/session count — a genuine flood still needs a
front-door limit (tracked separately).

"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from bretzel.runtime.protocol import SSE_EVENT_STATE_DIRTY

# Heartbeat cadence — 20s matches what most reverse proxies (nginx,
# Cloudflare) tolerate before timing out an idle SSE connection. Tune
# down if your stack is more aggressive.
_HEARTBEAT_INTERVAL_SECONDS = 20.0

# How long an idle session-subscription survives before the broker
# drops it. Anything beyond this is presumed disconnected (browser
# closed without firing ``beforeunload``, network drop, etc.) ; the
# next ``publish()`` won't waste a queue push on it.
_SESSION_TTL_SECONDS = 600.0  # 10 minutes

# Per-connection backlog cap. Each open tab's queue holds at most this many
# pending ``state-dirty`` chunks ; beyond it the OLDEST is dropped (see
# ``MemoryBroker._enqueue``). A state-dirty signal is idempotent — the tab
# re-fetches the zone on receipt — so discarding a stale one when a fresher
# arrives loses nothing, and it bounds the memory a slow/stalled consumer
# can pin.
_MAX_QUEUE_CHUNKS = 64

# Max simultaneous SSE connections (tabs) per session. A client opening
# dozens of tabs — or a buggy reconnect loop — can't allocate unbounded
# streams : opening the (N+1)-th evicts the OLDEST. Generous for real
# multi-tab use.
_MAX_CONNS_PER_SESSION = 8

# Sentinel wire chunk. Pushing it onto a connection's queue makes that
# connection's ``connect`` loop return and unwind its cleanup — used to
# force-close an evicted tab. The NUL bytes guarantee it never collides with
# a real event (always ``event: …\ndata: …\n\n``) nor a heartbeat comment.
_CLOSE = "\x00bretzel-sse-close\x00"


@runtime_checkable
class SSEBroker(Protocol):
    """Backend-agnostic protocol the framework holds at runtime.

    ``Bretzel._sse_broker`` is set at startup according to the
    ``redis_url`` config — in-process :class:`MemoryBroker` for single
    process / dev, :class:`RedisBroker` (cross-worker Pub/Sub) when a
    ``redis_url`` is set.
    """

    async def connect(self, session_id: str) -> AsyncIterator[str]:
        """Open a long-lived SSE stream for ``session_id``.

        Yields wire-format strings ready to be ``yield``-ed straight
        from a Starlette ``StreamingResponse`` body. The generator
        must end when the client disconnects (Starlette raises
        ``CancelledError`` on the next ``await``) ; cleanup is the
        implementation's responsibility.
        """
        ...

    def subscribe(self, session_id: str, state_qualname: str) -> None:
        """Record that ``session_id`` rendered a zone subscribing to
        ``state_qualname``.

        Idempotent — same session re-rendering the same zone over the
        course of a session won't double-deliver.
        """
        ...

    def publish(self, state_qualname: str, *, except_tab: str = "") -> None:
        """Push a ``state-dirty`` signal to every CONNECTION subscribed
        to ``state_qualname`` (one per open tab). Returns immediately;
        delivery is async via per-connection queues.

        ``except_tab`` skips the tab that has just written — it already
        received its zones in its action's response.
        """
        ...

    async def start(self) -> None:
        """Start any background machinery (e.g. the Redis Pub/Sub
        listener). Called once per worker at startup. The in-process
        :class:`MemoryBroker` has nothing to start — its default is a
        no-op — so the lifecycle can call this uniformly on any broker.
        """
        ...

    async def aclose(self) -> None:
        """Release resources at app shutdown. Idempotent, and a no-op on
        the in-process :class:`MemoryBroker` (it holds no external
        connection), so the lifecycle tears down any broker uniformly.
        """
        ...


class MemoryBroker:
    """In-process :class:`SSEBroker` implementation.

    Suitable for single-process deployments (``workers=1``, no extra
    replicas) and any dev setup. Multi-worker / multi-replica prod needs
    the Redis-backed :class:`RedisBroker` because subscriber state lives
    on the worker that rendered the page, not the worker that handles a
    future POST mutation.
    """

    def __init__(self) -> None:
        # connection_id → asyncio.Queue of pending SSE wire chunks. ONE
        # queue per open EventSource (per TAB), NOT per session — so two
        # tabs of the same browser (same session cookie) each get their
        # own stream and never fight over a shared queue nor tear each
        # other down on reconnect. ``asyncio.Queue`` (not ``deque``) lets
        # the connect-loop await new items without a polling sleep.
        self._queues: dict[int, asyncio.Queue[str]] = {}
        # connection_id → the TAB identity announced when the stream
        # opened. It serves only to exclude oneself from a broadcast
        # (cf. ``publish``). Absent = a mute tab, no exclusion.
        self._conn_tabs: dict[int, str] = {}
        # session_id → the live connection ids opened by that session's
        # tabs. ``publish`` fans a session's signal to every one of them.
        self._session_conns: dict[str, set[int]] = {}
        # state_qualname → set of session_ids that have rendered a zone
        # subscribed to that state. Reverse-indexed so ``publish`` is
        # O(subscribers of this state) instead of O(all sessions).
        self._subscribers: dict[str, set[str]] = {}
        # session_id → last touched timestamp ; drives the subscription
        # TTL sweep so tables don't grow unbounded if browsers vanish.
        self._last_seen: dict[str, float] = {}
        # Monotonic connection-id counter. asyncio is single-threaded, so
        # an increment between awaits needs no lock.
        self._conn_seq: int = 0

    # ── Connection lifecycle ──────────────────────────────────────────

    async def connect(
        self, session_id: str, tab_id: str = ""
    ) -> AsyncIterator[str]:
        """Open a stream for one tab of ``session_id`` and yield
        wire-format events as they arrive on this connection's queue.

        ``tab_id`` is the identity the browser draws per page load. It
        serves :meth:`publish` to EXCLUDE the tab that has just written:
        it already received its zones in its action's response. Empty =
        no exclusion possible, the previous behaviour.

        First yields a small comment line so the browser's EventSource
        transitions from CONNECTING to OPEN before the first publish —
        without it, browsers leave the connection pending and don't fire
        onopen.
        """
        # Cap tabs per session : evict the oldest connection(s) so a client
        # opening dozens of tabs can't pin unbounded streams (§ backpressure).
        self._enforce_session_cap(session_id)

        self._conn_seq += 1
        conn_id = self._conn_seq
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_MAX_QUEUE_CHUNKS)
        self._queues[conn_id] = queue
        if tab_id:
            self._conn_tabs[conn_id] = tab_id
        self._session_conns.setdefault(session_id, set()).add(conn_id)
        self._last_seen[session_id] = time.monotonic()

        # Wrap EVERY yield in the try/finally — including the hello —
        # so an ``aclose()`` from the response-side teardown reliably
        # runs the cleanup even if the client disconnects before the
        # first real event.
        try:
            # SSE comment — server hello, ignored by EventSource
            # parsers but flushes the HTTP headers so the browser
            # fires `onopen`.
            yield ": bretzel-sse-open\n\n"
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        queue.get(), timeout=_HEARTBEAT_INTERVAL_SECONDS
                    )
                except asyncio.TimeoutError:
                    # No traffic for HEARTBEAT — emit a comment line
                    # to keep the connection alive through proxies.
                    yield ": heartbeat\n\n"
                    continue
                if chunk == _CLOSE:
                    # Evicted by the per-session tab cap — unwind cleanly
                    # (the ``finally`` drops this connection).
                    return
                yield chunk
        finally:
            self._drop_connection(session_id, conn_id)

    def _drop_connection(self, session_id: str, conn_id: int) -> None:
        """Tear down ONE connection (tab). Idempotent.

        Only removes this connection's queue — a tab closing must NOT
        unsubscribe its sibling tabs, so subscriptions are left intact
        (they age out via the TTL sweep). This isolation is what stops
        one tab's reconnect from resetting the others.
        """
        self._queues.pop(conn_id, None)
        self._conn_tabs.pop(conn_id, None)
        conns = self._session_conns.get(session_id)
        if conns is not None:
            conns.discard(conn_id)
            if not conns:
                self._session_conns.pop(session_id, None)

    def _enforce_session_cap(self, session_id: str) -> None:
        """Evict the oldest connection(s) of ``session_id`` until there's
        room for one more, honouring :data:`_MAX_CONNS_PER_SESSION`.

        Connection ids are monotonic, so ``min(conns)`` is the oldest tab.
        """
        conns = self._session_conns.get(session_id)
        while conns and len(conns) >= _MAX_CONNS_PER_SESSION:
            self._evict_connection(session_id, min(conns))
            conns = self._session_conns.get(session_id)

    def _evict_connection(self, session_id: str, conn_id: int) -> None:
        """Force-close ONE connection : wake its stream with the close
        sentinel, then drop it from the tables.

        Idempotent with the stream's own ``finally`` — pushing ``_CLOSE``
        makes the ``connect`` loop ``return``, whose ``finally`` calls
        ``_drop_connection`` again (a no-op the second time). The stream
        holds its own queue reference, so dropping it from ``_queues`` here
        doesn't strand the pending sentinel.
        """
        queue = self._queues.get(conn_id)
        if queue is not None:
            self._enqueue(queue, _CLOSE)
        self._drop_connection(session_id, conn_id)

    @staticmethod
    def _enqueue(queue: asyncio.Queue[str], chunk: str) -> None:
        """``put_nowait`` with drop-oldest backpressure.

        On a full queue, discard the OLDEST pending chunk and enqueue the
        newest — a ``state-dirty`` signal is idempotent (the tab re-fetches),
        so freshness beats completeness and a stalled consumer can't grow its
        queue past :data:`_MAX_QUEUE_CHUNKS`.
        """
        try:
            queue.put_nowait(chunk)
        except asyncio.QueueFull:
            with contextlib.suppress(asyncio.QueueEmpty):
                queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(chunk)

    # ── Subscription bookkeeping ──────────────────────────────────────

    def subscribe(self, session_id: str, state_qualname: str) -> None:
        if not session_id or not state_qualname:
            return
        self._subscribers.setdefault(state_qualname, set()).add(session_id)
        self._last_seen[session_id] = time.monotonic()
        self._sweep_stale()

    def _sweep_stale(self) -> None:
        """Drop subscriptions for sessions that haven't checked in
        within :data:`_SESSION_TTL_SECONDS`.

        Called on every ``subscribe`` (cheap) so tables don't grow
        unbounded if browsers vanish without firing disconnect. The TTL
        is permissive — leak protection, not strict GC.
        """
        now = time.monotonic()
        threshold = now - _SESSION_TTL_SECONDS
        stale = [sid for sid, ts in self._last_seen.items() if ts < threshold]
        for sid in stale:
            # A session with a live connection is fresh by definition —
            # an idle long-poll still holds a queue open. Only prune
            # sessions whose tabs have all gone.
            if self._session_conns.get(sid):
                self._last_seen[sid] = now
                continue
            self._drop_session_subscriptions(sid)

    def _drop_session_subscriptions(self, session_id: str) -> None:
        """Forget a session entirely (TTL-expired, no live tabs)."""
        self._last_seen.pop(session_id, None)
        self._session_conns.pop(session_id, None)
        for subscribers in self._subscribers.values():
            subscribers.discard(session_id)

    # ── Lifecycle (Protocol conformance) ──────────────────────────────

    async def start(self) -> None:
        """No background machinery — the in-process broker is ready on
        construction. Present so the lifecycle starts any broker uniformly."""

    async def aclose(self) -> None:
        """Nothing to release — no external connection is held. Present so
        the lifecycle tears down any broker uniformly."""

    # ── Maintenance ───────────────────────────────────────────────────

    def reset(self) -> None:
        """Wipe every internal table. Test-only hook.

        Production code should never call this — connection teardown
        and TTL-driven cleanup keep the broker tidy. Test fixtures
        use it to isolate per-test state without reaching for the
        private dicts directly (which would lock the tests to the
        current schema).
        """
        self._queues.clear()
        self._conn_tabs.clear()
        self._session_conns.clear()
        self._subscribers.clear()
        self._last_seen.clear()
        self._conn_seq = 0

    # ── Publish ───────────────────────────────────────────────────────

    def publish(self, state_qualname: str, *, except_tab: str = "") -> None:
        """Push a ``state-dirty`` event to every CONNECTION of every
        session subscribed to ``state_qualname``.

        The wire payload carries only the State identifier — each tab
        re-fetches the affected zone over HTTP so the re-render runs in
        the right per-client context.

        ``except_tab`` skips the tab that has just written. It already
        received its zones in its action's response, so its re-read
        returns exactly what it is displaying: one round trip PER ZONE
        for an identical render. Measured on ``examples/kanban`` before
        the exclusion — ticking a subtask cost five requests and 354 KB,
        of which 177 KB were re-reads.

        ⚠️ We exclude the TAB, not the session. Two tabs of the same
        person must keep seeing each other.
        """
        if not state_qualname:
            return
        sessions = self._subscribers.get(state_qualname)
        if not sessions:
            return
        chunk = _format_event(SSE_EVENT_STATE_DIRTY, state_qualname)
        # Snapshot with ``list(...)`` : a put_nowait below could race a
        # concurrent teardown mutating these sets.
        for session_id in list(sessions):
            for conn_id in list(self._session_conns.get(session_id, ())):
                if except_tab and self._conn_tabs.get(conn_id) == except_tab:
                    continue
                queue = self._queues.get(conn_id)
                if queue is None:
                    continue
                # Bounded queue with drop-oldest backpressure — a slow tab
                # can't pin unbounded memory (cf. ``_enqueue``).
                self._enqueue(queue, chunk)


class RedisBroker:
    """Cross-worker :class:`SSEBroker` — a local queue engine plus a Redis
    Pub/Sub fanout of the ``state-dirty`` signal.

    **Why a second broker.** An SSE socket is intrinsically local to the
    worker holding it, so its per-tab queue can't be shared. But in a
    multi-process deployment (``workers>1``, or several replicas behind a
    load balancer) the mutation that dirties a State often lands on a
    *different* worker than the one streaming to a given tab. The
    in-process :class:`MemoryBroker` never sees it. This broker closes the
    gap: each worker keeps its OWN subscriber/queue bookkeeping (a private
    ``MemoryBroker``) and only the tiny ``state_qualname`` string crosses
    workers, over one shared Redis Pub/Sub channel.

    **The one delivery path.** ::

        publish(q)  →  redis PUBLISH channel q
                          ↓  (Redis fans out to EVERY worker, self included)
        _listen loop on each worker  →  self._local.publish(q)  →  local queues

    ``publish`` NEVER fans out locally by itself — it only PUBLISHes. The
    listener (which receives the worker's own message too, since Redis
    delivers to the publisher's connection) is the single path to local
    delivery, so a signal is applied exactly once per worker. Dropping the
    direct-local shortcut is what keeps the publishing worker from
    double-delivering to its own tabs.

    **Loss model.** Pub/Sub is fire-and-forget: a worker not connected at
    the instant of a publish misses the signal. That's acceptable here —
    ``state-dirty`` is idempotent (the tab refetches its zone), and a
    freshly (re)connected tab re-renders from scratch anyway, so no state
    is lost, only a redundant refetch is skipped.
    """

    _CHANNEL = "bretzel:sse:state-dirty"

    def __init__(self, client: Any, *, channel: str = _CHANNEL) -> None:
        self._client = client
        self._channel = channel
        # The local engine owns the queue + subscription mechanics unchanged
        # — this broker only adds the cross-worker signal on top.
        self._local = MemoryBroker()
        self._pubsub: Any = None
        self._listener_task: asyncio.Task[None] | None = None
        # Strong refs to in-flight publish tasks : asyncio holds only a weak
        # ref to a bare ``create_task`` result, so without this the task can
        # be GC'd mid-flight before the PUBLISH round-trip completes.
        self._publish_tasks: set[asyncio.Task[None]] = set()

    @classmethod
    def from_url(cls, url: str, *, channel: str = _CHANNEL) -> RedisBroker:
        """Build a broker from a ``redis://`` / ``rediss://`` URL.

        Redis is imported lazily so an app running on the in-memory broker
        never needs the ``redis`` package installed.
        """
        import redis.asyncio as redis_asyncio  # lazy — optional-ish dep

        return cls(redis_asyncio.from_url(url), channel=channel)

    # ── Connection + subscription : purely local ──────────────────────

    async def connect(
        self, session_id: str, tab_id: str = ""
    ) -> AsyncIterator[str]:
        # Delegate the whole stream lifecycle to the local engine — the
        # socket lives on this worker, so does its queue.
        async for chunk in self._local.connect(session_id, tab_id):
            yield chunk

    def subscribe(self, session_id: str, state_qualname: str) -> None:
        # Bookkeeping stays local : this worker records the tabs it holds,
        # and filters incoming signals against them on receipt.
        self._local.subscribe(session_id, state_qualname)

    # ── Publish : cross-worker via Redis Pub/Sub ──────────────────────

    def publish(self, state_qualname: str, *, except_tab: str = "") -> None:
        """PUBLISH the signal to the shared channel. Returns immediately;
        every worker's listener (this one included) does the local fanout.

        Must be called from within the running event loop — the framework
        always publishes from the async action pipeline. The PUBLISH is
        fired as a background task so this stays non-blocking, matching the
        :class:`SSEBroker` contract.

        ``except_tab`` travels WITH the signal, separated by a tab
        character: the tab to exclude may hold its connection on a
        different worker from the publishing one, so the exclusion cannot
        be applied here. A tab character cannot appear in a Python
        qualname nor in a tab identifier, which is hexadecimal.
        """
        if not state_qualname:
            return
        charge = (f"{state_qualname}	{except_tab}" if except_tab
                  else state_qualname)
        task = asyncio.create_task(
            self._client.publish(self._channel, charge)
        )
        self._publish_tasks.add(task)
        task.add_done_callback(self._publish_tasks.discard)

    # ── Listener lifecycle ────────────────────────────────────────────

    async def start(self) -> None:
        """Subscribe to the channel and spin up the background listener.

        Called once per worker at startup (``lifecycle.bretzel_startup``).
        Idempotent — a second call is a no-op.
        """
        if self._listener_task is not None:
            return
        self._pubsub = self._client.pubsub()
        await self._pubsub.subscribe(self._channel)
        self._listener_task = asyncio.create_task(self._listen())

    async def _listen(self) -> None:
        """Drain the Pub/Sub channel forever, doing a LOCAL fanout for each
        received ``state_qualname``. Cancelled on shutdown."""
        async for message in self._pubsub.listen():
            # ``listen`` also yields the subscribe confirmation and any
            # control frames — only ``message`` carries a payload.
            if message.get("type") != "message":
                continue
            data = message.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            if data:
                qualname, _, except_tab = data.partition("	")
                self._local.publish(qualname, except_tab=except_tab)

    async def aclose(self) -> None:
        """Cancel the listener, unsubscribe, and close the client. Called on
        app shutdown. Safe to call more than once."""
        if self._listener_task is not None:
            self._listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener_task
            self._listener_task = None
        if self._pubsub is not None:
            # redis-py >=5 PubSub exposes async ``aclose`` — same discipline
            # as the client teardown just below.
            pubsub_aclose = getattr(self._pubsub, "aclose", None)
            if callable(pubsub_aclose):
                await pubsub_aclose()
            self._pubsub = None
        client_aclose = getattr(self._client, "aclose", None)
        if callable(client_aclose):
            await client_aclose()


# ───────────────────────────────────────────────────────────────────────────
# Wire format helper
# ───────────────────────────────────────────────────────────────────────────


def _format_event(event_name: str, data: str) -> str:
    """Build one SSE event in the text/event-stream wire format.

    Multi-line data is split into one ``data:`` line per source line
    per the EventSource spec ; trailing blank line terminates the
    event. ``event:`` is always emitted so the client can dispatch
    to the right ``addEventListener(name, ...)``.
    """
    lines = data.split("\n") if data else [""]
    body = "".join(f"data: {line}\n" for line in lines)
    return f"event: {event_name}\n{body}\n"
