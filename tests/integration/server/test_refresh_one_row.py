"""``refresh(zone, rows=[…])``: the table renders and ships those rows only.

Measured on 2026-10-23 on the comparison helpdesk: a status change spent
64 of its 110 ms re-rendering a 50-row table for one changed row
(``.claude/work/cadrage-rafraichir-une-ligne-2026-10-23.md``).

Both sides, as the zone diff's tests: a changed row comes back alone and
a row that left the list is removed; a new row, a new order or a client
copy the server does not know ship the zone whole — never a silence.
The data lives outside any state, as in a database: only ``refresh``
redraws it.
"""

from __future__ import annotations

import re
import time

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, refresh, refreshable, ui
from bretzel.render.decorators.refreshable import state_qualname
from bretzel.runtime.protocol import (
    DATA_ZONE_HASH,
    HEADER_ZONE_BASES,
    HEADER_ZONES,
    REFETCH_ROWS_PARAM,
)
from bretzel.server.handlers import encode_action_id, sign_action
from bretzel.state import AppState, field

_SECRET = "x" * 32
_app = Bretzel(secret_key=_SECRET, mode="dev")

#: The "database".
TICKETS: dict[int, str] = {}


class TableChanged(AppState):
    """The channel the other tabs listen on; nothing in the rows path
    changes it."""

    n: int = field(default=0, merge="add")


def reset() -> None:
    TICKETS.clear()
    TICKETS.update({i: "open" for i in range(1, 21)})


def close_seven() -> None:
    TICKETS[7] = "closed"
    refresh(tickets, rows=[7])


def drop_seven() -> None:
    TICKETS.pop(7, None)
    refresh(tickets, rows=[7])


def add_one() -> None:
    TICKETS[99] = "open"
    refresh(tickets, rows=[99])


@refreshable(broadcast=[TableChanged])
def tickets() -> None:
    rows = [{"id": k, "status": v} for k, v in sorted(TICKETS.items())]
    ui.table(columns=[ui.column("id", label="ID"), ui.column("status", label="Status")],
             rows=rows, row_key="id")


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
    sig = sign_action(_app.config._action_key, action_id, "", ts=ts)
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


def test_a_changed_row_comes_back_alone(client) -> None:
    held = stamp_of(client.get("/").text)
    response = act(client, close_seven, held)
    assert row_ids(response.text) == ["7"], response.text[:400]
    assert "closed" in response.text
    assert response.headers[HEADER_ZONE_BASES] == f"{tickets.id}:{held}"


def test_a_row_that_left_the_list_is_removed(client) -> None:
    held = stamp_of(client.get("/").text)
    response = act(client, drop_seven, held)
    assert re.search(r'id="[^"]*_7" hx-swap-oob="delete"|hx-swap-oob="delete"[^>]*id="[^"]*_7"',
                     response.text), response.text[:400]
    assert row_ids(response.text) == ["7"]


def test_a_new_row_ships_the_list(client) -> None:
    """Not row by row (a new row has no place yet): the diff takes over
    and ships the list, by position, not the whole zone."""
    held = stamp_of(client.get("/").text)
    response = act(client, add_one, held)
    assert len(row_ids(response.text)) == 21
    assert "<bz-at" in response.text and DATA_ZONE_HASH not in response.text


def test_an_unknown_client_copy_ships_the_zone_whole(client) -> None:
    """The side that matters most."""
    client.get("/")
    response = act(client, close_seven, "0123456789abcdef")
    assert len(row_ids(response.text)) == 20


def test_a_refetch_for_rows_patches_those_rows(client) -> None:
    """The other tabs: the ``zone-rows`` signal refetches with ``?rows=``."""
    held = stamp_of(client.get("/").text)
    TICKETS[7] = "closed"
    response = client.get(
        f"/_bretzel/refetch/{state_qualname(TableChanged)}/{tickets.zone_qualname}",
        params={REFETCH_ROWS_PARAM: "[7]"},
        headers={HEADER_ZONES: f"{tickets.id}:{held}"},
    )
    assert response.status_code == 200
    assert row_ids(response.text) == ["7"]
    assert response.headers[HEADER_ZONE_BASES] == f"{tickets.id}:{held}"


def test_rows_are_broadcast_as_a_zone_rows_signal(client) -> None:
    published: list[dict] = []

    class Broker:
        def publish(self, qualname, *, except_tab="", only_session="",
                    event="state-dirty", data=""):
            published.append({"state": qualname, "event": event, "data": data})

    client.get("/")
    _app._sse_broker, real = Broker(), _app._sse_broker
    try:
        act(client, close_seven, None)
    finally:
        _app._sse_broker = real
    channel = state_qualname(TableChanged)
    assert published == [{"state": channel, "event": "zone-rows", "data":
                          f'{{"state": "{channel}", "zone": "{tickets.id}", "rows": ["7"]}}'}]
