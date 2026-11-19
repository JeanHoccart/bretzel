"""A ``ui.table`` row is rebuilt only when something it depends on moved.

When an action redraws a list, the rows that did not move are taken back as
their last render in this session gave them (``render/row_memo.py``) —
measured on the comparison's Helpdesk, « change a status » went from 366 to
280 ms of server time. Taken back, a row must still be right: its reads keep
its zone subscribed, its buttons are signed for this render, and a row whose
build left a trace in the request is never kept.

Builds are counted by a column's ``render=``: one call per row built.
"""

from __future__ import annotations

import re
import time
from collections import Counter
from functools import partial

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, refresh, refreshable, ui
from bretzel.render.row_memo import RowMemo, columns_print, print_of
from bretzel.server.handlers import encode_action_id, encode_args, sign_action
from bretzel.state import AppState, SessionState, field
from tests._carriers import carriers_of
from tests._carriers import post as carrier_post
from tests._session import session_of

app = Bretzel(secret_key="memo-test-secret-key-0123456789ab", mode="prod")

#: Calls of the counting column, per row id — one per row built.
builds: Counter = Counter()
ROWS = [{"id": i, "name": f"row {i}"} for i in range(5)]


class View(SessionState):
    starred: int = field(default=-1)
    other: int = field(default=0)


class Picked(AppState):
    ids: list = field(default_factory=list)


class OnlyInCells(SessionState):
    flag: bool = field(default=False)


def counted(value, row):
    builds[row["id"]] += 1
    return ui.text(value)


def star(value, row):
    return ui.text("★" if View().starred == row["id"] else "·")


def pick(row_id: int) -> None:
    Picked().ids = [*Picked().ids, row_id]


def picker(value, row):
    return ui.button("pick", on_click=partial(pick, row["id"]), id=f"pick-{row['id']}")


def first_obtains(value, row):
    # Obtained here for the first time: the first row's build leaves a trace.
    return ui.text("x" if OnlyInCells().flag else "-")


COLUMNS = [
    ui.column("name", label="Name", render=counted),
    ui.column("id", label="Star", render=star),
    ui.column("id", label="Pick", render=picker),
]


@refreshable
def listing() -> None:
    View().other  # the zone reads it; no row does
    ui.table(columns=COLUMNS, rows=[dict(r) for r in ROWS], row_key="id")


@refreshable
def traced() -> None:
    ui.table(columns=[ui.column("name", render=counted), ui.column("id", render=first_obtains)],
             rows=[dict(r) for r in ROWS], row_key="id")


def touch_other() -> None:
    View().other += 1


def rename(row_id: int) -> None:
    ROWS[row_id]["name"] = f"renamed {row_id}"
    refresh(listing)


def star_row(row_id: int) -> None:
    View().starred = row_id


@page("/")
def home() -> None:
    listing()


@page("/traced")
def traced_page() -> None:
    traced()


app.include(__name__)


def post(client: TestClient, handler, *args) -> None:
    fn = partial(handler, *args) if args else handler
    action_id, blob = encode_action_id(handler), encode_args(fn)
    ts = str(int(time.time()))
    response = client.post(f"/_bretzel/action/{action_id}", headers={
        "X-Bz-Sig": sign_action(app.config._action_key, action_id, blob, ts=ts,
                                session_id=session_of(client)),
        "X-Bz-Ts": ts}, data={"_args": blob})
    assert response.status_code == 200, response.text[:300]


@pytest.fixture
def client():
    for i, row in enumerate(ROWS):
        row["name"] = f"row {i}"
    with TestClient(app) as c:
        c.get("/")
        builds.clear()
        yield c


def test_a_redraw_that_moves_no_row_rebuilds_none(client) -> None:
    post(client, touch_other)
    assert sum(builds.values()) == 0, builds


def test_a_changed_row_alone_is_rebuilt(client) -> None:
    post(client, rename, 2)
    assert builds == Counter({2: 1})


def test_a_state_every_row_reads_rebuilds_every_row(client) -> None:
    post(client, star_row, 3)
    assert builds == Counter(dict.fromkeys(range(5), 1))


def test_a_taken_back_row_is_signed_for_this_render(client) -> None:
    html = client.get("/").text  # every row taken back
    assert sum(builds.values()) == 0
    button = next(c for c in carriers_of(html, pick) if c.get("id") == "pick-4")
    assert button["data-bz-ts"] == re.search(r'data-bz-ts="(\d+)"', html).group(1)
    # Signed for this render: the server takes it (204, nothing to swap).
    assert carrier_post(client, button).status_code in (200, 204)


def test_a_row_that_leaves_a_trace_is_never_kept(client) -> None:
    client.get("/traced")
    builds.clear()
    client.get("/traced")
    # The first row obtains a state for the first time: rebuilt each time.
    assert builds == Counter({0: 1}), builds


def test_without_the_memo_every_row_is_rebuilt(client, monkeypatch) -> None:
    """The licit side: the counts above come from the memo, not the bench."""
    monkeypatch.setattr(type(app), "row_memo", property(lambda self: None))
    post(client, touch_other)
    assert builds == Counter(dict.fromkeys(range(5), 1))


def test_the_row_print_still_bites() -> None:
    assert print_of({"a": 1}) == print_of({"a": 1})
    assert print_of({"a": 1}) != print_of({"a": 2})
    assert print_of(object()) is None


def test_the_columns_print_still_bites() -> None:
    assert columns_print(COLUMNS) == columns_print(list(COLUMNS))
    unprintable = object()
    assert columns_print([ui.column("name", render=lambda v, r, k=unprintable: v)]) is None


def test_the_memo_drops_the_oldest_row() -> None:
    memo = RowMemo(max_rows=2)
    for key in "abc":
        memo.put(key, key)
    assert memo.get("a") is None
    assert memo.get("c") == "c"
