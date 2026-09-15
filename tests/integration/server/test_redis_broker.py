"""Integration tests for :class:`bretzel.server.sse.RedisBroker` against a
real ``redis.asyncio``-compatible client (``fakeredis``).

The *unit* tests in ``tests/unit/server/test_sse_broker.py`` drive the
broker through a hand-rolled Pub/Sub fake — enough to pin the fanout
logic, but blind to whether the code speaks the actual redis-py async
surface (``client.pubsub()`` → ``await pubsub.subscribe(ch)`` →
``async for message in pubsub.listen()`` with real message dicts,
``bytes`` payloads, subscribe-confirmation frames, ``aclose`` shapes).

``fakeredis.aioredis`` is a faithful in-process implementation of that
surface, so exercising the broker against it proves the real client path
end-to-end without a live server. Two ``RedisBroker`` instances sharing
ONE :class:`fakeredis.FakeServer` stand in for two workers sharing one
Redis — the cross-worker guarantee this broker exists for.

Skipped when ``fakeredis`` isn't installed (it's a ``dev`` extra), so the
default lightweight test run doesn't require it ; CI installs
``.[dev]`` and runs it.
"""

from __future__ import annotations

import asyncio

import pytest

from bretzel.runtime.protocol import SSE_EVENT_STATE_DIRTY
from bretzel.server.sse import RedisBroker

fakeredis = pytest.importorskip("fakeredis")
from fakeredis import aioredis as fake_aioredis  # noqa: E402 — after importorskip


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _worker(server: fakeredis.FakeServer) -> RedisBroker:
    """A broker whose client is a fresh connection onto the shared 'Redis'
    — i.e. a distinct worker seeing the same instance."""
    return RedisBroker(fake_aioredis.FakeRedis(server=server))


class TestRedisBrokerAgainstFakeredis:
    def test_publish_crosses_workers(self) -> None:
        # A mutation handled on worker A wakes a tab streamed by worker B,
        # travelling A → real Pub/Sub channel → B's listener → B's queue.
        server = fakeredis.FakeServer()
        worker_a = _worker(server)
        worker_b = _worker(server)

        async def scenario():
            await worker_a.start()
            await worker_b.start()
            worker_b.subscribe("sess-1", "app::Store")
            gen = worker_b.connect("sess-1")
            await anext(gen)  # hello → registers the connection on B
            worker_a.publish("app::Store")
            event = await asyncio.wait_for(anext(gen), timeout=2.0)
            await gen.aclose()
            await worker_a.aclose()
            await worker_b.aclose()
            return event

        event = _run(scenario())
        assert SSE_EVENT_STATE_DIRTY in event
        assert "app::Store" in event

    def test_publish_is_state_scoped(self) -> None:
        # A tab subscribed to a DIFFERENT state on worker B must not receive
        # the signal, even though the Pub/Sub channel is shared by all states.
        server = fakeredis.FakeServer()
        worker_a = _worker(server)
        worker_b = _worker(server)

        async def scenario():
            await worker_a.start()
            await worker_b.start()
            worker_b.subscribe("sess-1", "app::Other")
            gen = worker_b.connect("sess-1")
            await anext(gen)  # hello
            worker_a.publish("app::Store")  # not what sess-1 subscribed to
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(anext(gen), timeout=0.2)
            await gen.aclose()
            await worker_a.aclose()
            await worker_b.aclose()

        _run(scenario())

    def test_publisher_own_worker_receives(self) -> None:
        # Redis echoes a published message to the publisher's own
        # connection, so a tab on the SAME worker that published still gets
        # the signal — the broker relies on this (no local shortcut fanout).
        server = fakeredis.FakeServer()
        worker = _worker(server)

        async def scenario():
            await worker.start()
            worker.subscribe("sess-1", "app::Store")
            gen = worker.connect("sess-1")
            await anext(gen)  # hello
            worker.publish("app::Store")
            event = await asyncio.wait_for(anext(gen), timeout=2.0)
            await gen.aclose()
            await worker.aclose()
            return event

        event = _run(scenario())
        assert "app::Store" in event

    def test_aclose_stops_the_listener(self) -> None:
        # Teardown cancels the background drain loop and releases the
        # Pub/Sub connection — no task left pending, safe to call twice.
        server = fakeredis.FakeServer()
        worker = _worker(server)

        async def scenario():
            await worker.start()
            listener = worker._listener_task
            assert listener is not None and not listener.done()
            await worker.aclose()
            assert worker._listener_task is None
            assert listener.done()
            # Idempotent — a second close is a no-op, not an error.
            await worker.aclose()
            return True

        assert _run(scenario()) is True

    def test_from_url_builds_a_working_broker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ``from_url`` is what the lifecycle calls. Point its lazy
        # ``redis.asyncio.from_url`` at a fakeredis client on a shared
        # server so the constructed broker is genuinely functional.
        server = fakeredis.FakeServer()
        import redis.asyncio as redis_asyncio

        monkeypatch.setattr(
            redis_asyncio,
            "from_url",
            lambda url, **kw: fake_aioredis.FakeRedis(server=server),
        )
        broker = RedisBroker.from_url("redis://localhost:6379")
        peer = _worker(server)

        async def scenario():
            await broker.start()
            await peer.start()
            broker.subscribe("sess-1", "app::Store")
            gen = broker.connect("sess-1")
            await anext(gen)  # hello
            peer.publish("app::Store")
            event = await asyncio.wait_for(anext(gen), timeout=2.0)
            await gen.aclose()
            await broker.aclose()
            await peer.aclose()
            return event

        event = _run(scenario())
        assert "app::Store" in event
