"""In a real browser, a patched zone ends up exactly as a fresh render.

The server sends only the changed elements of a zone, each as an
out-of-band morph of its namesake (``render/zone_diff.py``). What only a
browser shows: that a lone ``<tr>`` lands in its table, that the zone's
fingerprint moves on the element so the next action patches again, and
that the page then reads like a reload.

Heavy (uvicorn + Chromium) ::

    py -m pytest tests/runtime_js/test_a_zone_ships_only_what_changed.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import AppState, field
from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

app = Bretzel(secret_key="dev-zone-patch-secret-key", title="Bretzel · zone patch", mode="dev")


class Tickets(AppState):
    status: dict = field(default_factory=lambda: {str(i): "open" for i in range(50)})
    counter: int = field(default=0, merge="add")


def close_next() -> None:
    status = dict(Tickets().status)
    tid = next(k for k, v in status.items() if v == "open")
    status[tid] = "closed"
    Tickets().status = status
    Tickets().counter += 1


@refreshable(deps=[Tickets])
def tickets() -> None:
    rows = [{"id": int(k), "status": v} for k, v in Tickets().status.items()]
    ui.text(f"closed={Tickets().counter}", id="closed")
    ui.table(columns=[ui.column("id", label="ID"), ui.column("status", label="Status")],
             rows=rows, row_key="id", id="table")
    ui.button("close next", on_click=close_next, id="close")


@page("/")
def home() -> None:
    with ui.vstack(classes="p-6"):
        tickets()


app.include(__name__)


@pytest.fixture(scope="module")
def base_url():
    with audit_server(app) as url:
        yield url


_ROWS = "() => [...document.querySelectorAll('#table tbody tr')].map(r => r.innerText.replace(/\\s+/g, ' ').trim())"


def test_patches_land_and_the_page_reads_like_a_reload(base_url) -> None:
    with browser_page(base_url, "/") as page_:
        page_.wait_for_selector("html.bz-ready")
        sizes: list[int] = []
        page_.on("response", lambda r: sizes.append(len(r.body())) if r.request.method == "POST" else None)
        for n in (1, 2, 3):
            page_.click("#close")
            page_.wait_for_function(f"document.querySelector('#closed').textContent === 'closed={n}'")
        page_.wait_for_timeout(300)
        rows_after = page_.evaluate(_ROWS)
        stamp = page_.evaluate("document.querySelector('[data-bz-zone]').getAttribute('data-bz-h')")
        with browser_page(base_url, "/") as fresh:
            fresh.wait_for_selector("html.bz-ready")
            rows_fresh = fresh.evaluate(_ROWS)
            fresh_stamp = fresh.evaluate("document.querySelector('[data-bz-zone]').getAttribute('data-bz-h')")

    assert rows_after == rows_fresh, "the patched table does not read like a fresh render"
    assert stamp == fresh_stamp, (
        "the zone's fingerprint did not follow the patches: the next action "
        "would ship it whole, or patch against the wrong base"
    )
    # Floor: three actions, each answered. Each sends one row and the
    # counter, not the 50-row table.
    assert len(sizes) == 3
    assert max(sizes[1:]) < 6000, f"the zone came back whole: {sizes} bytes"


def test_crossed_responses_forget_the_fingerprint(base_url) -> None:
    """A patch computed against another base than the one held makes the
    runtime forget the zone's fingerprint; the matching base adopts it."""
    with browser_page(base_url, "/") as page_:
        page_.wait_for_selector("html.bz-ready")
        result = page_.evaluate("""() => {
            const zone = document.querySelector('[data-bz-zone]');
            const zid = zone.getAttribute('bz-id');
            const xhr = (h, b) => ({getResponseHeader: (n) =>
                n === 'X-Bretzel-Zone-Hashes' ? zid + ':' + h : n === 'X-Bretzel-Zone-Bases' ? zid + ':' + b : null});
            zone.setAttribute('data-bz-h', 'held');
            $bz._adoptZoneHashes(xhr('next', 'held'));
            const adopted = zone.getAttribute('data-bz-h');
            $bz._adoptZoneHashes(xhr('other', 'not-held'));
            return [adopted, zone.getAttribute('data-bz-h')];
        }""")
    assert result == ["next", None]
