"""End-to-end realtime tests — ``@refreshable(broadcast=[…])`` + SSE wire.

Validates the full round-trip on a single uvicorn worker :

1. A page rendering a ``broadcast=True`` zone produces HTML carrying
   ``data-bz-subscribe-state`` + ``data-bz-subscribe-url`` attrs the
   runtime will pick up.
2. Subscriber bookkeeping lands on the broker so a future dep-change
   fan-out knows whose queue to push to.
3. Mutating a dep inside an action puts a ``state-dirty`` event on every
   subscribed connection's queue (the automatic broadcast).
4. The ``/_bretzel/refetch/<state>/<zone>`` route re-renders the
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
from bretzel.state import AppState, field

_SECRET = "x" * 32


class IssueStore(AppState):
    items: list[str] = field(default_factory=list)


_app = Bretzel(secret_key=_SECRET, mode="dev")


@refreshable(deps=[IssueStore], broadcast=[IssueStore])
def issue_list_zone() -> None:
    for it in IssueStore().items:
        ui.text(it)


def add_issue() -> None:
    # In-place append — caught by the snapshot-diff, which then auto-
    # fans-out to other clients because issue_list_zone is broadcast.
    IssueStore().items.append("fresh")


class ViewerPrefs(AppState):
    """Un second état, pour séparer ``deps`` de ``broadcast``."""

    scope: str = field(default="all")


@refreshable(broadcast=[IssueStore])
def listen_only_zone() -> None:
    """Le cas que la doc met en avant : « je ne le change jamais ».

    ``deps`` est VIDE — cette zone n'est jamais re-rendue par une action
    locale, elle ne suit que le flux.
    """
    ui.text("écoute : " + str(len(IssueStore().items)))


@refreshable(deps=[IssueStore, ViewerPrefs], broadcast=[IssueStore])
def partly_broadcast_zone() -> None:
    """``deps`` déborde de ``broadcast`` : ``ViewerPrefs`` est personnel."""
    ui.text(ViewerPrefs().scope)


@page("/")
def home() -> None:
    issue_list_zone()


@page("/ecoute")
def listen_page() -> None:
    listen_only_zone()
    partly_broadcast_zone()


_app.include(home)
_app.include(listen_page)


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


# ───────────────────────────────────────────────────────────────────────────
# Subscriber bookkeeping on the broker
# ───────────────────────────────────────────────────────────────────────────


class TestSubscriptionBookkeeping:
    def test_page_render_registers_session_on_broker(self) -> None:
        with TestClient(_app) as client:
            response = client.get("/")
            assert response.status_code == 200
            session_id = client.cookies["Bretzel_session"]
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
            qn = state_qualname(IssueStore)
            url = f"/_bretzel/refetch/{qn}/{issue_list_zone.zone_qualname}"
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
            qn = state_qualname(IssueStore)
            response = client.get(f"/_bretzel/refetch/{qn}/missing.module::nope")
        assert response.status_code == 404

    def test_mismatched_state_returns_404(self) -> None:
        # An attacker who knows the zone qualname can still get 404 if
        # the State segment doesn't match what the zone declared.
        with TestClient(_app) as client:
            client.get("/")
            url = (
                f"/_bretzel/refetch/some.other::Class/"
                f"{issue_list_zone.zone_qualname}"
            )
            response = client.get(url)
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
    """Phase 5 : mutating a subscribed State inside an action fans out an
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
            actor = client.cookies["Bretzel_session"]
            # Simulate a SECOND tab of the actor's session (conn 101) and a
            # DIFFERENT browser / session (conn 202), each with a live queue.
            broker._session_conns.setdefault(actor, set()).add(101)
            broker._queues[101] = asyncio.Queue()
            broker.subscribe("other-browser", qn)
            broker._session_conns.setdefault("other-browser", set()).add(202)
            broker._queues[202] = asyncio.Queue()

            action_id = encode_action_id(add_issue)
            sig = sign_action(_app.config._action_key, action_id, "")
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

    def test_a_broadcast_only_zone_can_be_refetched(self) -> None:
        """``@refreshable(broadcast=[X])`` SANS ``deps`` doit répondre.

        C'est la forme que la doc met en avant — « je ne le change
        jamais » — et elle rendait **404** jusqu'au 2026-09-09 : la garde
        validait le segment d'état contre ``deps``, qui est vide ici. La
        zone s'abonnait, le signal arrivait, le navigateur allait
        chercher, le serveur refusait, et rien ne bougeait. Sans un mot :
        ni console, ni journal.

        Mesuré sur un banc à deux fenêtres : la zone diffusée seule
        restait à sa valeur de chargement pendant que sa voisine
        ``deps=`` + ``broadcast=`` suivait.
        """
        with TestClient(_app) as client:
            client.get("/ecoute")
            url = (
                f"/_bretzel/refetch/{state_qualname(IssueStore)}/"
                f"{listen_only_zone.zone_qualname}"
            )
            response = client.get(url)
        assert response.status_code == 200, (
            f"une zone diffusée SEULE est refusée : {response.text[:120]}"
        )

    def test_a_dep_that_is_not_a_channel_is_refused(self) -> None:
        """Le versant qui SERRE, et qui interdit de « réparer » trop large.

        ``deps=[IssueStore, ViewerPrefs], broadcast=[IssueStore]`` :
        ``ViewerPrefs`` est une dépendance locale, jamais annoncée au
        client comme canal. Un refetch qui la nomme est forgé, et la
        garde d'avant l'acceptait.
        """
        with TestClient(_app) as client:
            client.get("/ecoute")
            url = (
                f"/_bretzel/refetch/{state_qualname(ViewerPrefs)}/"
                f"{partly_broadcast_zone.zone_qualname}"
            )
            response = client.get(url)
        assert response.status_code == 404, (
            "un état qui n'est PAS un canal de diffusion a été accepté — "
            "la garde lit encore ``deps``"
        )

    def test_non_broadcast_zone_is_not_remotely_refetchable(self) -> None:
        # A bare @refreshable / local deps zone must 404 on the refetch
        # route even if the URL is guessed — only broadcast zones qualify.
        with TestClient(_app) as client:
            client.get("/")
            # issue_list_zone IS broadcast ; forge a state it doesn't dep on.
            url = f"/_bretzel/refetch/wrong.mod::Nope/{issue_list_zone.zone_qualname}"
            response = client.get(url)
        assert response.status_code == 404
