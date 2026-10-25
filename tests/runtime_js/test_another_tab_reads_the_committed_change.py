"""Another tab sees a change even when the acting tab renders slowly.

The action told the other tabs "this state changed" BEFORE rendering its
own zones and committing the state. The other tab asked again after its
40 ms window, read the store — still the old value —, got an identical
zone, and never saw the change. Hidden while an action renders in under
~40 ms; the helpdesk's take 65 to 100. Now the signals wait for the
commit (``RenderContext.deferred_broadcasts``, ``routing/actions.py``).

Heavy (uvicorn + Chromium) ::

    py -m pytest tests/runtime_js/test_another_tab_reads_the_committed_change.py -q -m browser
"""

from __future__ import annotations

import time

import pytest

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import AppState, field
from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

app = Bretzel(secret_key="dev-committed-change-secret-key", title="Bretzel · commit", mode="dev")


class Counter(AppState):
    n: int = field(default=0, merge="add")


def bump() -> None:
    Counter().n += 1


@refreshable(deps=[Counter], broadcast=[Counter])
def shown() -> None:
    n = Counter().n
    time.sleep(0.3)  # read, THEN slow: the acting tab commits 0.3 s later
    with ui.vstack():  # one child alone would fuse into the zone's root
        ui.text(f"n={n}", id="n")


@page("/")
def home() -> None:
    with ui.vstack(classes="p-6"):
        ui.button("bump", on_click=bump, id="bump")
        shown()


app.include(__name__)


@pytest.fixture(scope="module")
def base_url():
    with audit_server(app) as url:
        yield url


def test_the_other_tab_reads_the_committed_value(base_url) -> None:
    with browser_page(base_url, "/", wait_until="load") as other, \
            browser_page(base_url, "/", wait_until="load") as actor:
        for tab in (other, actor):
            tab.wait_for_selector("html.bz-ready")
        other.wait_for_timeout(500)  # the stream is open
        before = other.evaluate("document.querySelector('#n').textContent")
        actor.click("#bump")
        actor.wait_for_function(f"document.querySelector('#n').textContent !== {before!r}")
        try:
            other.wait_for_function(
                f"document.querySelector('#n').textContent !== {before!r}", timeout=5000)
        except Exception:
            pytest.fail("the other tab kept the old value: it read the store before the commit")
