"""A refreshed zone sends only the elements that changed.

Measured on 2026-10-23 on the comparison helpdesk: one status change
sent four whole zones, 18.6 KB gzipped; between two consecutive changes
only three elements differ, 6.3 KB (``render/zone_diff.py``).

What these tests hold, both ways:

- the patch: one renamed row comes back alone, with the base it was
  computed against;
- the safety: a fingerprint the server does not know, or a zone whose
  skeleton changed, ships whole — never a silence;
- the zone-level silence now survives the render second: a zone with a
  button looked changed one second later.
"""

from __future__ import annotations

import re
import time

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.render.decorators.refreshable import state_qualname
from bretzel.runtime.protocol import (
    DATA_ZONE_HASH,
    HEADER_ZONE_BASES,
    HEADER_ZONE_HASHES,
    HEADER_ZONES,
)
from bretzel.server.handlers import encode_action_id, sign_action
from bretzel.state import AppState, field

_SECRET = "x" * 32
_app = Bretzel(secret_key=_SECRET, mode="dev")


class Board(AppState):
    labels: list = field(default_factory=lambda: [f"label {i}" for i in range(20)])
    touched: int = field(default=0, merge="add")


def rename_third() -> None:
    labels = list(Board().labels)
    labels[3] = labels[3] + "!"
    Board().labels = labels


def add_row() -> None:
    Board().labels = [*Board().labels, "new"]


def touch() -> None:
    """Dirties the zone's state WITHOUT changing what it shows."""
    Board().touched += 1


@refreshable(deps=[Board], broadcast=[Board])
def board() -> None:
    with ui.vstack(id="rows"):
        for i, label in enumerate(Board().labels):
            ui.text(label, id=f"row-{i}")
    ui.button("touch", on_click=touch, id="touch")


@page("/")
def home() -> None:
    board()


_app.include(home)


@pytest.fixture
def client():
    # ``Board`` is an AppState shared by the tests: they only rename,
    # add and touch, and none relies on the labels of another.
    with TestClient(_app) as c:
        yield c


def stamp_of(html: str) -> str:
    found = re.search(rf'bz-id="{board.id}"[^>]*?{DATA_ZONE_HASH}="([0-9a-f]+)"', html) or \
        re.search(rf'{DATA_ZONE_HASH}="([0-9a-f]+)"[^>]*?bz-id="{board.id}"', html)
    assert found, "the page does not stamp its zone with a fingerprint"
    return found.group(1)


def act(client: TestClient, fn, held: str | None):
    action_id = encode_action_id(fn)
    ts = str(int(time.time()))
    sig = sign_action(_app.config._action_key, action_id, "", ts=ts)
    response = client.post(
        f"/_bretzel/action/{action_id}",
        headers={"X-Bz-Sig": sig, "X-Bz-Ts": ts,
                 HEADER_ZONES: f"{board.id}:{held}" if held else board.id},
        data={"_args": ""},
    )
    assert response.status_code in (200, 204), response.text[:200]
    return response


def test_one_renamed_row_comes_back_alone(client) -> None:
    held = stamp_of(client.get("/").text)
    response = act(client, rename_third, held)
    assert 'id="row-3"' in response.text and "hx-swap-oob" in response.text
    assert 'id="row-4"' not in response.text, (
        f"the whole zone came back ({len(response.text)} bytes) for one renamed row"
    )
    assert response.headers[HEADER_ZONE_BASES] == f"{board.id}:{held}"
    fresh = response.headers[HEADER_ZONE_HASHES].split(":", 1)[1]
    assert fresh != held


def test_an_unknown_fingerprint_ships_the_zone_whole(client) -> None:
    """The side that matters most: not knowing what the client holds
    must cost a re-ship, never a silence."""
    client.get("/")
    response = act(client, rename_third, "0123456789abcdef")
    assert 'id="row-4"' in response.text
    assert HEADER_ZONE_BASES not in response.headers
    assert DATA_ZONE_HASH in response.text, "a zone shipped whole must carry its fingerprint"


def test_a_new_row_ships_its_list(client) -> None:
    held = stamp_of(client.get("/").text)
    response = act(client, add_row, held)
    assert 'id="rows"' in response.text and 'id="row-0"' in response.text


def test_an_unchanged_zone_stays_silent_a_second_later(client) -> None:
    """The zone carries a signed button whose render second changes: it
    used to make the zone look changed, and it shipped whole."""
    held = stamp_of(client.get("/").text)
    time.sleep(1.1)
    response = act(client, touch, held)
    assert "row-" not in response.text, (
        f"an unchanged zone was shipped again ({len(response.text)} bytes)"
    )


def test_a_refetch_patches_and_announces_its_fingerprint(client) -> None:
    """The SSE path: another user changed a row; this client refetches
    with what it holds and gets the row alone."""
    held = stamp_of(client.get("/").text)
    act(client, rename_third, None)
    response = client.get(
        f"/_bretzel/refetch/{state_qualname(Board)}/{board.zone_qualname}",
        headers={HEADER_ZONES: f"{board.id}:{held}"},
    )
    assert response.status_code == 200
    assert 'id="row-3"' in response.text and 'id="row-4"' not in response.text
    assert response.headers[HEADER_ZONE_BASES] == f"{board.id}:{held}"
    assert HEADER_ZONE_HASHES in response.headers


def test_debug_reports_each_zone_render_time(client) -> None:
    """``Server-Timing`` names the zone and its cost, so DevTools show
    where an action's time goes (the app here runs in dev, so debug)."""
    held = stamp_of(client.get("/").text)
    timing = act(client, rename_third, held).headers.get("Server-Timing", "")
    assert re.search(r"zone_board;dur=[\d.]+;desc=\"[^\"]*board\"", timing), timing
