"""An element with no ``id`` is patched in place, found by its position.

The ticket panel of the comparison helpdesk shipped whole (~38 KB raw)
for one changed field: the diff could only target elements carrying an
``id``, and almost nothing inside the panel had one
(``render/zone_diff.py``, ``at_position``). Now such an element ships
alone, with its path from the nearest identified ancestor.

What only a browser shows: that the runtime finds the element — skipping
the ``bz-for`` rows a multi-select inserted before it —, that the page
then reads like a fresh render, and that a DOM moved under the server's
feet is not patched blindly: the zone forgets its fingerprint and the
next exchange ships it whole.

Heavy (uvicorn + Chromium) ::

    py -m pytest tests/runtime_js/test_an_unnamed_element_is_patched_by_position.py -q -m browser
"""

from __future__ import annotations

from typing import Any

import pytest

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import AppState, field
from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

app = Bretzel(secret_key="dev-position-patch-secret-key", title="Bretzel · by position", mode="dev")


class Ticket(AppState):
    status: str = field(default="open")
    n: int = field(default=0, merge="add")


def bump() -> None:
    Ticket().status = "closed" if Ticket().status == "open" else "open"
    Ticket().n += 1


@refreshable(deps=[Ticket])
def panel() -> None:
    with ui.card(padding="md"):
        # A multi-select first: its picked values are bz-for rows the
        # runtime inserts, so the browser's children are not the server's.
        ui.select([("a", "A"), ("b", "B")], multiple=True, value=["a", "b"], name="tags",
                  placeholder="Tags")
        with ui.vstack(gap="xs"):
            ui.text("Ticket #42", weight="semibold")
            ui.text(f"Status: {Ticket().status}", classes="status-line")
            ui.text(f"Changes: {Ticket().n}", classes="count-line")
        for i in range(30):
            ui.text(f"history line {i}")


@page("/")
def home() -> None:
    with ui.vstack(gap="md", classes="p-6"):
        ui.button("bump", on_click=bump, id="bump")
        panel()


app.include(__name__)


@pytest.fixture(scope="module")
def base_url():
    with audit_server(app) as url:
        yield url


_TEXT = "() => document.querySelector('[data-bz-zone]').innerText.replace(/\\s+/g, ' ').trim()"


def bump_and_wait(page_: Any, count: int, sizes: list[int]) -> None:
    page_.click("#bump")
    page_.wait_for_function(
        f"document.querySelector('.count-line')?.textContent === 'Changes: {count}'")
    page_.wait_for_timeout(200)


def test_an_unnamed_element_ships_alone_and_lands(base_url) -> None:
    with browser_page(base_url, "/") as page_:
        page_.wait_for_selector("html.bz-ready")
        start = int(page_.evaluate("document.querySelector('.count-line').textContent.split(': ')[1]"))
        sizes: list[int] = []
        bodies: list[str] = []
        page_.on("response", lambda r: (sizes.append(len(r.body())), bodies.append(r.text()))
                 if r.request.method == "POST" else None)
        bump_and_wait(page_, start + 1, sizes)
        bump_and_wait(page_, start + 2, sizes)
        shown = page_.evaluate(_TEXT)
        pills = page_.evaluate(
            "() => [...document.querySelectorAll('[data-bz-row]')].filter(e => e.offsetParent).length")
        with browser_page(base_url, "/") as fresh:
            fresh.wait_for_selector("html.bz-ready")
            expected = fresh.evaluate(_TEXT)
    assert shown == expected, "the patched zone does not read like a fresh render"
    assert pills == 1, "the multi-select lost its pill: the patch landed on the wrong element"
    assert "<bz-at" in bodies[-1], "the change did not ship by position"
    assert max(sizes) < 3000, f"the zone came back whole: {sizes} bytes"


def test_a_moved_dom_is_not_patched_blindly(base_url) -> None:
    """The side that matters: the walk no longer lands where the server
    thinks, so the zone forgets its fingerprint and ships whole next."""
    with browser_page(base_url, "/") as page_:
        page_.wait_for_selector("html.bz-ready")
        start = int(page_.evaluate("document.querySelector('.count-line').textContent.split(': ')[1]"))
        # On the path (the zone root), not inside the element that ships:
        # that one is replaced whole, an <hr> in it is simply morphed away.
        page_.evaluate("""() => {
            const root = document.querySelector('[data-bz-zone]');
            root.insertBefore(document.createElement('hr'), root.firstChild);
        }""")
        sizes: list[int] = []
        page_.on("response", lambda r: sizes.append(len(r.body())) if r.request.method == "POST" else None)
        page_.click("#bump")
        page_.wait_for_timeout(800)
        stale = page_.evaluate("document.querySelector('[data-bz-zone]').getAttribute('data-bz-h')")
        bump_and_wait(page_, start + 2, sizes)
        shown = page_.evaluate(_TEXT)
        with browser_page(base_url, "/") as fresh:
            fresh.wait_for_selector("html.bz-ready")
            expected = fresh.evaluate(_TEXT)
    assert stale is None, "a patch that missed its element kept the zone's fingerprint"
    assert shown == expected, "after a missed patch, the next exchange did not restore the zone"
    assert sizes[-1] > 3000, "the exchange after a missed patch should ship the zone whole"
