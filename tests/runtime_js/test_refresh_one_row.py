"""In real browsers, ``refresh(zone, rows=[…])`` moves only that row.

Two tabs on the same table. The first acts: its response carries the row
alone. The second hears the ``zone-rows`` signal and refetches that row
alone. Only a browser shows that the lone ``<tr>`` lands, that a removed
row really leaves, and that both tables then read like a reload.

Heavy (uvicorn + Chromium) ::

    py -m pytest tests/runtime_js/test_refresh_one_row.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, refresh, refreshable, ui
from bretzel.state import AppState, field
from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

app = Bretzel(secret_key="dev-one-row-secret-key", title="Bretzel · one row", mode="dev")

TICKETS: dict[int, str] = {i: "open" for i in range(1, 31)}


class TableChanged(AppState):
    n: int = field(default=0, merge="add")


def close_next() -> None:
    tid = next(k for k, v in sorted(TICKETS.items()) if v == "open")
    TICKETS[tid] = "closed"
    refresh(tickets, rows=[tid])


def drop_last() -> None:
    tid = max(TICKETS)
    TICKETS.pop(tid)
    refresh(tickets, rows=[tid])


@refreshable(broadcast=[TableChanged])
def tickets() -> None:
    rows = [{"id": k, "status": v} for k, v in sorted(TICKETS.items())]
    ui.table(columns=[ui.column("id", label="ID"), ui.column("status", label="Status")],
             rows=rows, row_key="id")


@page("/")
def home() -> None:
    with ui.vstack(classes="p-6"):
        ui.button("close next", on_click=close_next, id="close")
        ui.button("drop last", on_click=drop_last, id="drop")
        tickets()


app.include(__name__)


@pytest.fixture(scope="module")
def base_url():
    with audit_server(app) as url:
        yield url


_ROWS = "() => [...document.querySelectorAll('[data-bz-zone] tbody tr')].map(r => r.innerText.replace(/\\s+/g, ' ').trim())"


def test_both_tabs_move_one_row(base_url) -> None:
    with browser_page(base_url, "/", wait_until="load") as other, \
            browser_page(base_url, "/", wait_until="load") as actor:
        for tab in (other, actor):
            tab.wait_for_selector("html.bz-ready")
        other.wait_for_timeout(500)  # the stream is open
        refetched: list[int] = []
        other.on("response", lambda r: refetched.append(len(r.body()))
                 if "/_bretzel/refetch/" in r.url else None)
        acted: list[int] = []
        actor.on("response", lambda r: acted.append(len(r.body()))
                 if r.request.method == "POST" else None)

        actor.click("#close")
        actor.wait_for_function("document.querySelector('[data-bz-zone] tbody tr').innerText.includes('closed')")
        other.wait_for_function("document.querySelector('[data-bz-zone] tbody tr').innerText.includes('closed')")
        actor.click("#drop")
        actor.wait_for_function("document.querySelectorAll('[data-bz-zone] tbody tr').length === 29")
        other.wait_for_function("document.querySelectorAll('[data-bz-zone] tbody tr').length === 29")
        other.wait_for_timeout(300)
        rows_actor, rows_other = actor.evaluate(_ROWS), other.evaluate(_ROWS)
        with browser_page(base_url, "/", wait_until="load") as fresh:
            fresh.wait_for_selector("html.bz-ready")
            rows_fresh = fresh.evaluate(_ROWS)

    assert rows_actor == rows_fresh and rows_other == rows_fresh, "a table does not read like a reload"
    assert acted and max(acted) < 2500, f"the acting tab got more than a row: {acted} bytes"
    assert refetched and max(refetched) < 2500, f"the other tab refetched more than a row: {refetched}"
