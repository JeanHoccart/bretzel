"""A keyed ``ui.table`` redrawn by its ``Topic`` ships one row.

The data lives outside any state, as in a database: a ``Topic`` follows
it, and the zone diff finds what moved. A changed row comes back
alone; a row that left the list, or a new one, rides a list patch on the
table's body; a client copy the server does not know ships the zone whole
— never a silence.
"""

from __future__ import annotations

import re
import time

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, refresh, refreshable, ui
from bretzel.render.decorators.refreshable import state_qualname
from bretzel.runtime.protocol import DATA_ZONE_HASH, HEADER_ZONE_BASES, HEADER_ZONES
from bretzel.server.handlers import encode_action_id, sign_action
from bretzel.state import Topic, reads
from tests._session import session_of
from tests.integration.server._refetch import refetch_url

_SECRET = "x" * 32
_app = Bretzel(secret_key=_SECRET, mode="dev")

#: The "database".
TICKETS: dict[int, str] = {}


TABLE = Topic("keyed_tickets")


@reads(TABLE)
def ticket_rows() -> list[dict[str, object]]:
    return [{"id": k, "status": v} for k, v in sorted(TICKETS.items())]


def reset() -> None:
    TICKETS.clear()
    TICKETS.update({i: "open" for i in range(1, 21)})


def close_seven() -> None:
    TICKETS[7] = "closed"
    refresh(TABLE)


def drop_seven() -> None:
    TICKETS.pop(7, None)
    refresh(TABLE)


def add_one() -> None:
    TICKETS[99] = "open"
    refresh(TABLE)


@refreshable
def tickets() -> None:
    ui.table(columns=[ui.column("id", label="ID"), ui.column("status", label="Status")],
             rows=ticket_rows(), row_key="id")


@page("/")
def home() -> None:
    tickets()


_app.include(home)


@pytest.fixture
def client():
    reset()
    with TestClient(_app) as c:
        yield c


def stamp_of(html: str) -> str:
    found = re.search(rf'{DATA_ZONE_HASH}="([0-9a-f]+)"', html)
    assert found, "the page does not stamp its zone"
    return found.group(1)


def act(client: TestClient, fn, held: str | None):
    action_id = encode_action_id(fn)
    ts = str(int(time.time()))
    sig = sign_action(_app.config._action_key, action_id, "", ts=ts, session_id=session_of(client))
    response = client.post(
        f"/_bretzel/action/{action_id}",
        headers={"X-Bz-Sig": sig, "X-Bz-Ts": ts,
                 HEADER_ZONES: f"{tickets.id}:{held}" if held else tickets.id},
        data={"_args": ""},
    )
    assert response.status_code in (200, 204), response.text[:200]
    return response


def row_ids(html: str) -> list[str]:
    return re.findall(r'<tr[^>]*\bid="[^"]*__row_[^"]*_(\d+)"', html)


def list_ops(html: str) -> list[str]:
    """The ops of the body's list patch: ``#<row id>`` kept, ``n`` new."""
    found = re.search(r'<bz-at[^>]*\blist="([^"]*)"', html)
    assert found, html[:400]
    return [re.sub(r".*_(\d+)$", r"#\1", op) for op in found.group(1).split()]


def test_a_changed_row_comes_back_alone(client) -> None:
    held = stamp_of(client.get("/").text)
    response = act(client, close_seven, held)
    assert "closed" in response.text
    assert set(row_ids(response.text)) <= {"7"}, response.text[:400]
    assert response.text.count("open") == 0, "the other rows were shipped again"
    assert response.headers[HEADER_ZONE_BASES] == f"{tickets.id}:{held}"


def test_a_row_that_left_the_list_is_removed(client) -> None:
    held = stamp_of(client.get("/").text)
    response = act(client, drop_seven, held)
    assert list_ops(response.text) == [f"#{i}" for i in range(1, 21) if i != 7]
    assert row_ids(response.text) == []


def test_a_new_row_ships_alone_in_the_list(client) -> None:
    held = stamp_of(client.get("/").text)
    response = act(client, add_one, held)
    assert row_ids(response.text) == ["99"]
    assert list_ops(response.text) == [*(f"#{i}" for i in range(1, 21)), "n"]
    assert DATA_ZONE_HASH not in response.text


def test_an_unknown_client_copy_ships_the_zone_whole(client) -> None:
    """The side that matters most."""
    client.get("/")
    response = act(client, close_seven, "0123456789abcdef")
    assert len(row_ids(response.text)) == 20


def test_a_refetch_patches_the_row(client) -> None:
    """The other tabs: a ``state-dirty`` signal, then a refetch that
    presents what the tab holds."""
    held = stamp_of(client.get("/").text)
    TICKETS[7] = "closed"
    response = client.get(
        refetch_url(_app, client, tickets.zone_qualname),
        headers={HEADER_ZONES: f"{tickets.id}:{held}"},
    )
    assert response.status_code == 200
    assert "closed" in response.text and response.text.count("open") == 0
    assert response.headers[HEADER_ZONE_BASES] == f"{tickets.id}:{held}"


def test_a_shared_zone_sends_the_plain_signal(client) -> None:
    published: list[tuple[str, str]] = []

    class Broker:
        def publish(self, qualname, *, except_tab="", only_session=""):
            published.append((qualname, only_session))

        def subscribe(self, session_id, qualname):
            pass

    client.get("/")
    _app._sse_broker, real = Broker(), _app._sse_broker
    try:
        act(client, close_seven, None)
    finally:
        _app._sse_broker = real
    assert published == [(state_qualname(TABLE._revision), "")]


def test_refresh_names_no_rows() -> None:
    with pytest.raises(TypeError):
        refresh(tickets, rows=[1])  # type: ignore[call-arg]
