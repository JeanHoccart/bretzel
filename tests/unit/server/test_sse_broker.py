"""Unit tests for :class:`bretzel.server.sse.MemoryBroker` and
:class:`bretzel.server.sse.RedisBroker`."""

from __future__ import annotations

import asyncio

import pytest

from bretzel.runtime.protocol import SSE_EVENT_STATE_DIRTY
from bretzel.server.sse import MemoryBroker, RedisBroker, SSEBroker, _format_event


def _run(coro):
    return asyncio.run(coro)


class TestProtocolConformance:
    def test_memory_broker_satisfies_protocol(self) -> None:
        # ``runtime_checkable`` Protocol gives us a duck-type guard the
        # lifecycle wiring relies on (``app._sse_broker: SSEBroker``).
        assert isinstance(MemoryBroker(), SSEBroker)


class TestSubscribePublish:
    def test_subscribe_then_publish_pushes_to_queue(self) -> None:
        broker = MemoryBroker()
        broker.subscribe("sess-A", "module::IssueStore")

        async def collect():
            gen = broker.connect("sess-A")
            # Drain the hello + one event.
            hello = await anext(gen)
            broker.publish("module::IssueStore")
            event = await anext(gen)
            return hello, event

        hello, event = _run(collect())
        assert hello.startswith(":")  # SSE comment
        assert SSE_EVENT_STATE_DIRTY in event
        assert "module::IssueStore" in event

    def test_publish_with_no_subscribers_is_noop(self) -> None:
        broker = MemoryBroker()
        # Doesn't raise, doesn't deadlock — we just exit silently.
        broker.publish("module::Nobody")

    def test_publish_only_to_subscribed_sessions(self) -> None:
        broker = MemoryBroker()
        broker.subscribe("sess-A", "module::Foo")
        broker.subscribe("sess-B", "module::Bar")

        async def open_streams():
            gen_a = broker.connect("sess-A")
            gen_b = broker.connect("sess-B")
            # Drain hellos so subsequent ``anext`` blocks on real events.
            await anext(gen_a)
            await anext(gen_b)
            broker.publish("module::Foo")
            # ``sess-A`` should receive ; ``sess-B`` must NOT — we time
            # it out short to assert "no event arrives".
            a_event = await asyncio.wait_for(anext(gen_a), timeout=1.0)
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(anext(gen_b), timeout=0.05)
            return a_event

        a_event = _run(open_streams())
        assert "module::Foo" in a_event

    def test_subscribe_is_idempotent(self) -> None:
        broker = MemoryBroker()
        broker.subscribe("sess-A", "module::Foo")
        broker.subscribe("sess-A", "module::Foo")
        broker.subscribe("sess-A", "module::Foo")
        # The set semantics dedup ; publish still fires exactly once
        # for sess-A.
        assert broker._subscribers["module::Foo"] == {"sess-A"}

    def test_empty_inputs_skipped(self) -> None:
        broker = MemoryBroker()
        broker.subscribe("", "module::Foo")
        broker.subscribe("sess-A", "")
        broker.publish("")
        assert "module::Foo" not in broker._subscribers


# ───────────────────────────────────────────────────────────────────────────
# Wire format
# ───────────────────────────────────────────────────────────────────────────


class TestWireFormat:
    def test_event_format(self) -> None:
        chunk = _format_event(SSE_EVENT_STATE_DIRTY, "module::IssueStore")
        assert chunk == f"event: {SSE_EVENT_STATE_DIRTY}\ndata: module::IssueStore\n\n"

    def test_multiline_data_splits_per_line(self) -> None:
        # SSE spec : multi-line data emits one ``data:`` line per source
        # line. We use this for a single-segment State qualname today,
        # but the helper must hold the contract for future event types.
        chunk = _format_event("x", "line1\nline2")
        assert chunk == "event: x\ndata: line1\ndata: line2\n\n"

    def test_empty_data_still_emits(self) -> None:
        chunk = _format_event("ping", "")
        assert chunk == "event: ping\ndata: \n\n"


# ───────────────────────────────────────────────────────────────────────────
# Hello frame
# ───────────────────────────────────────────────────────────────────────────


class TestConnect:
    def test_hello_frame_first(self) -> None:
        broker = MemoryBroker()

        async def first():
            gen = broker.connect("sess-A")
            return await anext(gen)

        chunk = _run(first())
        # Comment frame opens the stream so the browser fires `onopen`
        # before any real event lands.
        assert chunk.startswith(":")

    def test_disconnect_drops_only_its_connection(self) -> None:
        broker = MemoryBroker()
        broker.subscribe("sess-A", "module::Foo")

        async def open_and_drop():
            gen = broker.connect("sess-A")
            await anext(gen)  # hello → registers the connection
            assert broker._session_conns["sess-A"]  # one live tab
            await gen.aclose()  # client disconnect

        _run(open_and_drop())
        # The connection's queue is gone and the session has no live tabs…
        assert broker._queues == {}
        assert "sess-A" not in broker._session_conns
        # …but the SUBSCRIPTION persists : a tab closing must not
        # unsubscribe its sibling tabs. Stale subs age out via the TTL
        # sweep, not on disconnect.
        assert "sess-A" in broker._subscribers["module::Foo"]

    def test_two_tabs_same_session_get_independent_queues(self) -> None:
        # The multi-tab fix : two connections of ONE session each receive
        # the published event on their OWN queue — no shared queue, no
        # destructive teardown of the sibling on reconnect.
        broker = MemoryBroker()
        broker.subscribe("sess-A", "module::Foo")

        async def two_tabs():
            gen1 = broker.connect("sess-A")
            gen2 = broker.connect("sess-A")
            await anext(gen1)  # hellos
            await anext(gen2)
            assert len(broker._session_conns["sess-A"]) == 2
            broker.publish("module::Foo")
            e1 = await asyncio.wait_for(anext(gen1), timeout=1.0)
            e2 = await asyncio.wait_for(anext(gen2), timeout=1.0)
            return e1, e2

        e1, e2 = _run(two_tabs())
        assert "module::Foo" in e1
        assert "module::Foo" in e2


# ───────────────────────────────────────────────────────────────────────────
# Backpressure — bounded queue + per-session connection cap
# ───────────────────────────────────────────────────────────────────────────


class TestBackpressure:
    def test_enqueue_drops_oldest_when_full(self) -> None:
        # A stalled consumer can't grow its queue past the cap : the
        # oldest pending chunk is dropped to make room for the newest.
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=2)
        MemoryBroker._enqueue(queue, "a")
        MemoryBroker._enqueue(queue, "b")
        MemoryBroker._enqueue(queue, "c")  # full → drop "a", keep b,c
        assert queue.qsize() == 2
        assert queue.get_nowait() == "b"
        assert queue.get_nowait() == "c"

    def test_connection_queue_is_bounded(self) -> None:
        # A never-drained connection queue caps at ``_MAX_QUEUE_CHUNKS``
        # no matter how many publishes land on it.
        from bretzel.server import sse as sse_mod

        broker = MemoryBroker()
        broker.subscribe("sess-A", "module::Foo")

        async def flood():
            gen = broker.connect("sess-A")
            await anext(gen)  # hello → registers the queue, never drained
            for _ in range(sse_mod._MAX_QUEUE_CHUNKS * 3):
                broker.publish("module::Foo")
            (conn_id,) = tuple(broker._session_conns["sess-A"])
            return broker._queues[conn_id].qsize()

        assert _run(flood()) == sse_mod._MAX_QUEUE_CHUNKS

    def test_session_cap_evicts_oldest_tab(self, monkeypatch) -> None:
        # Opening more than ``_MAX_CONNS_PER_SESSION`` tabs of one session
        # evicts the OLDEST — the count never exceeds the cap, and the
        # evicted stream ends.
        monkeypatch.setattr("bretzel.server.sse._MAX_CONNS_PER_SESSION", 2)
        broker = MemoryBroker()

        async def scenario():
            g1 = broker.connect("sess-A")
            g2 = broker.connect("sess-A")
            await anext(g1)
            await anext(g2)
            assert len(broker._session_conns["sess-A"]) == 2

            g3 = broker.connect("sess-A")
            await anext(g3)  # opening the 3rd evicts the oldest (g1)
            assert len(broker._session_conns["sess-A"]) == 2

            # g1 was force-closed : its stream ends on the next pull.
            with pytest.raises(StopAsyncIteration):
                await asyncio.wait_for(anext(g1), timeout=1.0)
            # g2 + g3 stay live and still receive events.
            broker.subscribe("sess-A", "module::Foo")
            broker.publish("module::Foo")
            e2 = await asyncio.wait_for(anext(g2), timeout=1.0)
            e3 = await asyncio.wait_for(anext(g3), timeout=1.0)
            return e2, e3

        e2, e3 = _run(scenario())
        assert "module::Foo" in e2
        assert "module::Foo" in e3


# ───────────────────────────────────────────────────────────────────────────
# RedisBroker — cross-worker fanout over a Pub/Sub channel
# ───────────────────────────────────────────────────────────────────────────
#
# We stand in a tiny in-memory Pub/Sub *hub* for Redis so two RedisBroker
# instances (standing in for two workers sharing ONE Redis) can exchange
# the ``state_qualname`` signal without a live server. The hub routes a
# ``publish`` to every subscribed fake ``pubsub`` — exactly what Redis does
# (including delivery to the publisher's own connection).


class _FakePubSub:
    """Mimics the subset of ``redis.asyncio.client.PubSub`` we exercise."""

    def __init__(self, hub: _FakeHub) -> None:
        self._hub = hub
        self._queue: asyncio.Queue[dict] = asyncio.Queue()
        self._channels: set[str] = set()

    async def subscribe(self, channel: str) -> None:
        self._channels.add(channel)
        self._hub._subscribers.append(self)

    async def listen(self):
        while True:
            yield await self._queue.get()

    async def aclose(self) -> None:
        if self in self._hub._subscribers:
            self._hub._subscribers.remove(self)

    def _deliver(self, channel: str, data: str) -> None:
        if channel in self._channels:
            self._queue.put_nowait(
                {"type": "message", "channel": channel, "data": data}
            )


class _FakeRedis:
    """Mimics the ``publish`` / ``pubsub`` / ``aclose`` surface RedisBroker
    touches. Multiple clients share one :class:`_FakeHub` to simulate a
    single Redis instance seen by several workers."""

    def __init__(self, hub: _FakeHub) -> None:
        self._hub = hub

    async def publish(self, channel: str, data: str) -> None:
        self._hub.publish(channel, data)

    def pubsub(self) -> _FakePubSub:
        return _FakePubSub(self._hub)

    async def aclose(self) -> None:
        pass


class _FakeHub:
    """The shared Pub/Sub bus every fake client of one 'Redis' publishes to."""

    def __init__(self) -> None:
        self._subscribers: list[_FakePubSub] = []

    def publish(self, channel: str, data: str) -> None:
        for sub in list(self._subscribers):
            sub._deliver(channel, data)


class TestRedisBrokerProtocol:
    def test_satisfies_protocol(self) -> None:
        broker = RedisBroker(_FakeRedis(_FakeHub()))
        assert isinstance(broker, SSEBroker)


class TestRedisBrokerCrossWorker:
    def test_publish_on_one_worker_reaches_a_tab_on_another(self) -> None:
        # THE guarantee the RedisBroker exists for : a mutation handled on
        # worker A must wake an SSE tab held open on worker B. The signal
        # travels A → Redis channel → B's listener → B's local queue.
        hub = _FakeHub()
        worker_a = RedisBroker(_FakeRedis(hub))
        worker_b = RedisBroker(_FakeRedis(hub))

        async def scenario():
            await worker_a.start()
            await worker_b.start()
            # The browser tab is connected to WORKER B and subscribed there.
            worker_b.subscribe("sess-1", "app::Store")
            gen = worker_b.connect("sess-1")
            await anext(gen)  # hello → registers the connection on B
            # The mutation is handled on WORKER A.
            worker_a.publish("app::Store")
            event = await asyncio.wait_for(anext(gen), timeout=1.0)
            await worker_a.aclose()
            await worker_b.aclose()
            return event

        event = _run(scenario())
        assert SSE_EVENT_STATE_DIRTY in event
        assert "app::Store" in event

    def test_publish_only_reaches_subscribed_states(self) -> None:
        # A worker that holds a tab subscribed to a DIFFERENT state must not
        # receive the signal, even though the channel is shared.
        hub = _FakeHub()
        worker_a = RedisBroker(_FakeRedis(hub))
        worker_b = RedisBroker(_FakeRedis(hub))

        async def scenario():
            await worker_a.start()
            await worker_b.start()
            worker_b.subscribe("sess-1", "app::Other")
            gen = worker_b.connect("sess-1")
            await anext(gen)  # hello
            worker_a.publish("app::Store")  # not what sess-1 subscribed to
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(anext(gen), timeout=0.1)
            await worker_a.aclose()
            await worker_b.aclose()

        _run(scenario())

    def test_publisher_own_tab_still_receives(self) -> None:
        # Redis delivers a message to the publishing connection too : a tab
        # on the SAME worker that published still gets the signal (its own
        # refetch idempotently diffs to a no-op if already applied).
        hub = _FakeHub()
        worker = RedisBroker(_FakeRedis(hub))

        async def scenario():
            await worker.start()
            worker.subscribe("sess-1", "app::Store")
            gen = worker.connect("sess-1")
            await anext(gen)  # hello
            worker.publish("app::Store")
            event = await asyncio.wait_for(anext(gen), timeout=1.0)
            await worker.aclose()
            return event

        event = _run(scenario())
        assert "app::Store" in event

    def test_empty_qualname_is_noop(self) -> None:
        # An empty signal never hits the wire (mirrors MemoryBroker).
        hub = _FakeHub()
        worker = RedisBroker(_FakeRedis(hub))

        async def scenario():
            await worker.start()
            worker.subscribe("sess-1", "app::Store")
            gen = worker.connect("sess-1")
            await anext(gen)  # hello
            worker.publish("")  # no-op
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(anext(gen), timeout=0.1)
            await worker.aclose()

        _run(scenario())


class TestRedisBrokerFromUrl:
    def test_from_url_builds_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import redis.asyncio as redis_asyncio

        hub = _FakeHub()
        monkeypatch.setattr(
            redis_asyncio, "from_url", lambda url, **kw: _FakeRedis(hub)
        )
        broker = RedisBroker.from_url("redis://localhost:6379")
        assert isinstance(broker, RedisBroker)
        assert isinstance(broker, SSEBroker)
