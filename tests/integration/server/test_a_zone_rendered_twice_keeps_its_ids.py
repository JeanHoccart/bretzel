"""A zone rendered twice in one request keeps its ids.

Found in a layout editor: posing one table sent
537 KB. The layer of cells and the screen around it both followed the
layout, and the queue renders in decoration order: the cells came first,
alone, then again inside the screen. The id counters lived for the whole
request, so the second render counted on from the first —
``…_flex_0_…`` in the page, ``…_flex_1_…`` in the fragment — and the
zone diff found no id it knew: every cell went out as new.

The same shape here: ``cells`` (unkeyed buttons, so positional ids) is
decorated before ``screen``, which calls it; all three zones read the
state an action changes. Only the count of tables moves.
"""

from __future__ import annotations

import re
import time

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.runtime.protocol import DATA_ZONE_HASH, HEADER_ZONES
from bretzel.server.handlers import encode_action_id, sign_action
from bretzel.state import AppState, field
from tests._session import session_of

_SECRET = "x" * 32
_app = Bretzel(secret_key=_SECRET, mode="dev")


class Room(AppState):
    tables: int = field(default=0, merge="add")


def table_posed() -> None:
    Room().tables += 1


#: How many times ``cells`` ran: the second test counts its renders.
RENDERS = {"cells": 0}


@refreshable
def cells() -> None:
    RENDERS["cells"] += 1
    Room().tables  # read, as the editor's cells read the whole layout
    with ui.flex():
        for i in range(30):
            ui.button(f"case {i}", on_click=table_posed)


@refreshable
def furniture() -> None:
    ui.text(f"{Room().tables + 1} tables")


@refreshable
def screen() -> None:
    Room().tables
    cells()
    furniture()


@page("/")
def home() -> None:
    screen()


_app.include(home)


@pytest.fixture
def client():
    with TestClient(_app) as c:
        yield c


def held_zones(html: str) -> str:
    """What the browser presents: each zone of the page and its stamp."""
    found = []
    for tag in re.findall(r"<[^>]+\bbz-id=\"refresh_[^>]+>", html):
        zone = re.search(r'bz-id="(refresh_[^"]+)"', tag)
        stamp = re.search(rf'{DATA_ZONE_HASH}="([0-9a-f]+)"', tag)
        if zone and stamp:
            found.append(f"{zone.group(1)}:{stamp.group(1)}")
    assert found, "the page stamps no zone"
    return ",".join(found)


def pose(client: TestClient, html: str):
    action_id = encode_action_id(table_posed)
    ts = str(int(time.time()))
    response = client.post(
        f"/_bretzel/action/{action_id}",
        headers={"X-Bz-Sig": sign_action(_app.config._action_key, action_id, "", ts=ts, session_id=session_of(client)),
                 "X-Bz-Ts": ts, HEADER_ZONES: held_zones(html)},
        data={"_args": ""},
    )
    assert response.status_code == 200, response.text[:200]
    return response


def test_a_zone_inside_a_queued_parent_is_rendered_once(client) -> None:
    """The browser lists its zones in document order: the parent renders
    first, and the child it covers is not rendered on its own."""
    html = client.get("/").text
    RENDERS["cells"] = 0
    pose(client, html)
    assert RENDERS["cells"] == 1, f"cells rendered {RENDERS['cells']} times for one action"


def test_a_zone_rendered_again_inside_its_parent_ships_nothing_new(client) -> None:
    html = client.get("/").text
    response = pose(client, html)
    assert "2 tables" in response.text
    page_ids = set(re.findall(r'id="([^"]*_button_\d+)"', html))
    sent_ids = set(re.findall(r'id="([^"]*_button_\d+)"', response.text))
    assert sent_ids <= page_ids, (
        f"the fragment renamed the cells: {sorted(sent_ids - page_ids)[:2]} "
        f"where the page had {sorted(page_ids)[:2]}"
    )
    assert "case 5" not in response.text, (
        f"unchanged cells went out again ({len(response.text)} bytes)"
    )
