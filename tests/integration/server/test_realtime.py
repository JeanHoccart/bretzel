"""End-to-end realtime tests — ``@refreshable`` + SSE wire.

Validates the full round-trip on a single uvicorn worker :

1. A page rendering a zone that reads a shared state produces HTML
   carrying ``data-bz-subscribe-state`` + ``data-bz-subscribe-url`` attrs
   the runtime will pick up; a zone reading only a ``PageState`` carries
   none.
2. Subscriber bookkeeping lands on the broker so a future dep-change
   fan-out knows whose queue to push to.
3. Mutating a dep inside an action puts a ``state-dirty`` event on every
   subscribed connection's queue (the automatic broadcast).
4. The ``/_bretzel/refetch/<zone>`` route re-renders the
   zone in the requesting client's RenderContext and returns an
   OOB-wrapped HTML fragment.
5. The ``/_bretzel/sse`` route streams events from the broker over a
   real HTTP/EventSource-shaped connection.

The app + decorated zone live at MODULE level on purpose : the
realtime route resolves the zone callable via ``sys.modules`` lookup
(same scheme as action handlers), which rejects anything with
``<locals>`` in its qualname. A factory-built app inside a test
function would defeat that, so we build one ``_app`` here and reset
the State between tests via the ``_reset_store`` fixture.
"""

from __future__ import annotations

import asyncio  # used by the backend-seed helper

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.render.decorators.refreshable import state_qualname
from bretzel.runtime.protocol import (
    DATA_SUBSCRIBE_STATE,
    DATA_SUBSCRIBE_URL,
)
from bretzel.state import AppState, PageState, field
from tests._session import session_of
from tests.integration.server._refetch import refetch_url

_SECRET = "x" * 32


class IssueStore(AppState):
    items: list[str] = field(default_factory=list)


_app = Bretzel(secret_key=_SECRET, mode="dev")


@refreshable
def issue_list_zone() -> None:
    for it in IssueStore().items:
        ui.text(it)


def add_issue() -> None:
    # In-place append — caught by the snapshot-diff, which then fans out
    # to the other clients because issue_list_zone reads it.
    IssueStore().items.append("fresh")


class PageView(PageState):
    """What one tab looks at: no other tab can change it."""

    scope: str = field(default="all")


@refreshable
def page_only_zone() -> None:
    ui.text(PageView().scope)


@page("/")
def home() -> None:
    issue_list_zone()


@page("/page-only")
def page_only() -> None:
    page_only_zone()


_app.include(home)
_app.include(page_only)


@pytest.fixture(autouse=True)
def _reset_store():
    """Clear IssueStore from the backend + the broker's tables between
    tests so a mutation or publish from one test doesn't leak into the
    next."""
    yield
    if _app.state_backend is not None:

        async def _wipe() -> None:
            await _app.state_backend.save(
                "app", "IssueStore:default", {"items": []}, ttl=None
            )

        asyncio.new_event_loop().run_until_complete(_wipe())
    if _app.sse_broker is not None:
        _app.sse_broker.reset()


# ───────────────────────────────────────────────────────────────────────────
# Initial render emits the subscribe data-attrs
# ───────────────────────────────────────────────────────────────────────────


class TestInitialRender:
    def test_zone_carries_subscribe_attrs(self) -> None:
        with TestClient(_app) as client:
            response = client.get("/")
        assert response.status_code == 200
        body = response.text
        assert DATA_SUBSCRIBE_STATE in body
        assert DATA_SUBSCRIBE_URL in body
        assert state_qualname(IssueStore) in body

    def test_zone_url_targets_refetch_route(self) -> None:
        with TestClient(_app) as client:
            response = client.get("/")
        assert "/_bretzel/refetch/" in response.text

    def test_a_zone_reading_only_its_page_opens_no_stream(self) -> None:
        with TestClient(_app) as client:
            response = client.get("/page-only")
        assert response.status_code == 200
        assert DATA_SUBSCRIBE_STATE not in response.text


# ───────────────────────────────────────────────────────────────────────────
# Subscriber bookkeeping on the broker
# ───────────────────────────────────────────────────────────────────────────


class TestSubscriptionBookkeeping:
    def test_page_render_registers_session_on_broker(self) -> None:
        with TestClient(_app) as client:
            response = client.get("/")
            assert response.status_code == 200
            session_id = session_of(client)
            qn = state_qualname(IssueStore)
            assert session_id in _app.sse_broker._subscribers[qn]


# ───────────────────────────────────────────────────────────────────────────
# /_bretzel/realtime route — re-render of a zone
# ───────────────────────────────────────────────────────────────────────────


def _seed_issue_store(items: list[str]) -> None:
    """Plant items into the AppState backend without going through a
    request scope (the metaclass shortcut only consults the registry
    inside a render / action ; bare ``IssueStore()`` in a test creates
    a throwaway instance that never reaches storage)."""

    async def _save() -> None:
        await _app.state_backend.save(
            "app", "IssueStore:default", {"items": items}, ttl=None
        )

    asyncio.new_event_loop().run_until_complete(_save())


class TestRealtimeRoute:
    def test_zone_refetch_returns_oob_fragment(self) -> None:
        with TestClient(_app) as client:
            client.get("/")
            _seed_issue_store(["one", "two"])
            url = refetch_url(_app, client, issue_list_zone.zone_qualname)
            response = client.get(url)
        assert response.status_code == 200
        body = response.text
        assert "one" in body
        assert "two" in body
        # The realtime response is an OOB-wrapped fragment so the
        # runtime morph hook can apply it by id.
        assert "hx-swap-oob" in body

    def test_unknown_zone_returns_404(self) -> None:
        with TestClient(_app) as client:
            client.get("/")
            response = client.get(refetch_url(_app, client, "missing.module::nope"))
        assert response.status_code == 404

# ───────────────────────────────────────────────────────────────────────────
# /_bretzel/sse route
# ───────────────────────────────────────────────────────────────────────────
#
# We don't drive the SSE stream through ``TestClient`` here — httpx
# buffers the full response before returning, which deadlocks on a
# long-poll. The broker-level tests in ``tests/unit/server/test_sse_broker.py``
# exercise the wire path directly. Sprint 2 will add an async-aware
# integration harness that exercises the route's streaming response
# end-to-end.


class TestBroadcastFanout:
    """Mutating a state a zone reads inside an action fans out an
    SSE ``state-dirty`` to every subscribed CONNECTION — a second tab of
    the acting session AND another browser both receive it (per-connection
    broker). The acting tab additionally has its local OOB swap."""

    def test_action_fans_out_to_every_connection(self) -> None:
        from bretzel.server.handlers import encode_action_id, sign_action

        qn = state_qualname(IssueStore)
        with TestClient(_app) as client:
            # The broker is wired during lifespan startup — capture it
            # INSIDE the ``with`` so it is the same instance the action uses.
            broker = _app.sse_broker
            client.get("/")  # renders the zone → subscribes the actor session
            actor = session_of(client)
            # Simulate a SECOND tab of the actor's session (conn 101) and a
            # DIFFERENT browser / session (conn 202), each with a live queue.
            broker._session_conns.setdefault(actor, set()).add(101)
            broker._queues[101] = asyncio.Queue()
            broker.subscribe("other-browser", qn)
            broker._session_conns.setdefault("other-browser", set()).add(202)
            broker._queues[202] = asyncio.Queue()

            action_id = encode_action_id(add_issue)
            sig = sign_action(_app.config._action_key, action_id, "", session_id=session_of(client))
            resp = client.post(
                f"/_bretzel/action/{action_id}",
                headers={"X-Bz-Sig": sig},
                data={"_args": ""},
            )
        # Actor got a local OOB swap (200) ; the second tab AND the other
        # browser each got the SSE state-dirty on their own queue.
        assert resp.status_code == 200
        assert broker._queues[101].qsize() == 1
        assert broker._queues[202].qsize() == 1
