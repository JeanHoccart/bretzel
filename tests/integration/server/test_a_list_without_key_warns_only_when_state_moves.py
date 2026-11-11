"""In debug, a list with no key warns only when a client state moves.

A child with no ``key`` is named by its rank. When a neighbour comes or
goes, its ids slide; the zone diff follows (``zone_diff.Patch.slid``),
but the runtime keys a component's client state — an open menu, a
ticked box — by ``bz-id``: it stays with the rank and lands on the
neighbour. ``ui.each(items, key=...)`` names each child by its item.

Jean, 2026-10-26: « il faut pas avertir à chaque fois que l'on a un
for, il faut faire ça intelligemment ». Four zones, one action that
drops the first name, and one warning only — the four arms:

- a ``for`` over the names, a popover in each: warns;
- the same through ``ui.each``: silent;
- a ``for`` over the names with no client state: silent (nothing lost);
- a ``for`` over a fixed list, popovers inside: silent (never moves).
"""

from __future__ import annotations

import time
import warnings

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.runtime.protocol import DATA_ZONE_HASH, HEADER_ZONES
from bretzel.server.handlers import encode_action_id, sign_action
from tests._carriers import zone_stamp
from bretzel.state import AppState, field
from tests._session import session_of

_SECRET = "w" * 32
_app = Bretzel(secret_key=_SECRET, mode="dev")


class Names(AppState):
    names: list = field(default_factory=lambda: ["ada", "bob", "cyd"])


def drop_first() -> None:
    Names().names = Names().names[1:]


def menu(label: str) -> None:
    with ui.popover(trigger=ui.button(label)):
        ui.text(label)


@refreshable
def bare_menus() -> None:
    with ui.vstack():
        for name in Names().names:
            with ui.hstack():
                menu(name)


@refreshable
def keyed_menus() -> None:
    with ui.vstack():
        for name in ui.each(Names().names, key=lambda n: n):
            with ui.hstack():
                menu(name)


@refreshable
def bare_buttons() -> None:
    with ui.vstack():
        for name in Names().names:
            with ui.hstack():
                ui.button(name)


@refreshable
def fixed_menus() -> None:
    with ui.vstack():
        ui.text(f"{len(Names().names)} names")
        for size in ("sm", "md"):
            with ui.hstack():
                menu(size)


ZONES = (bare_menus, keyed_menus, bare_buttons, fixed_menus)


@page("/")
def home() -> None:
    for zone in ZONES:
        zone()


_app.include(home)


@pytest.fixture
def client():
    with TestClient(_app) as c:
        yield c


def stamp_of(html: str, zone) -> str:
    return zone_stamp(html, zone.id)


def test_only_a_moving_client_state_with_no_key_warns(client) -> None:
    html = client.get("/").text
    held = ",".join(f"{zone.id}:{stamp_of(html, zone)}" for zone in ZONES)
    action_id = encode_action_id(drop_first)
    ts = str(int(time.time()))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        response = client.post(
            f"/_bretzel/action/{action_id}",
            headers={"X-Bz-Sig": sign_action(_app.config._action_key, action_id, "", ts=ts, session_id=session_of(client)),
                     "X-Bz-Ts": ts, HEADER_ZONES: held},
            data={"_args": ""},
        )
    assert response.status_code == 200, response.text[:200]
    # Not vacuous: every zone was patched against what the client held.
    assert DATA_ZONE_HASH + '="' not in response.text, "a zone shipped whole"
    said = [str(w.message) for w in caught if "have no key" in str(w.message)]
    assert len(said) == 1, said
    assert "bare_menus" in said[0] and "ui.each(items, key=...)" in said[0]
