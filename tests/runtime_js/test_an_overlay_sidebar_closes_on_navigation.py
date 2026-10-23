"""An ``overlay`` sidebar closes when one of its links is followed.

The sidebar lives in the layout: a partial navigation swaps the page and
keeps the aside, ``open`` included. On a phone the menu stayed over the
page the user had just asked for (python-ui-shootout helpdesk,
2026-10-23). Only a real browser shows it: the swap, the kept scope and
the click all have to happen.

Heavy (uvicorn + Chromium) ::

    py -m pytest tests/runtime_js/test_an_overlay_sidebar_closes_on_navigation.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, layout, page, ui
from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

app = Bretzel(secret_key="dev-overlay-closes-secret-key", title="Bretzel · overlay nav", mode="dev")


@layout
def shell() -> None:
    # The recommended app shell: the sidebar and the outlet's pane in a
    # viewport — a link swaps the outlet only, the aside stays.
    with ui.viewport():
        with ui.sidebar(collapsible="overlay", open=False):
            ui.sidebar_title("Menu")
            with ui.sidebar_section(label="Pages"):
                ui.sidebar_item("Page A", icon="dot", href="/a", id="to-a")
                ui.sidebar_item("Page B", icon="dot", href="/b", id="to-b")
        with ui.pane(gap="none", padding="none", classes="min-w-0"):
            ui.outlet(classes="flex flex-col flex-1 min-h-0 min-w-0")


def page_body(title: str) -> None:
    ui.sidebar_trigger(id="menu")
    ui.heading(title, level=1, id="title")


@page("/a", layout=shell)
def page_a() -> None:
    page_body("A")


@page("/b", layout=shell)
def page_b() -> None:
    page_body("B")


app.include(shell, page_a, page_b)


@pytest.fixture(scope="module")
def base_url():
    with audit_server(app) as url:
        yield url


_OPEN = "() => !document.querySelector('aside').hasAttribute('inert')"


def test_following_a_link_closes_the_menu(base_url) -> None:
    with browser_page(base_url, "/a", viewport=(390, 844)) as page_:
        page_.wait_for_selector("html.bz-ready")
        page_.click("#menu")
        page_.wait_for_function(_OPEN)
        page_.evaluate("window.__same = 1")
        page_.click("#to-b")
        page_.wait_for_function("document.querySelector('#title')?.textContent === 'B'")
        page_.wait_for_timeout(300)
        assert page_.evaluate("window.__same === 1"), (
            "the floor: the link must swap the page in place, not reload it")
        assert not page_.evaluate(_OPEN), (
            "page B is shown but the overlay menu is still open over it")


def test_a_click_beside_the_links_keeps_it_open(base_url) -> None:
    """The side it must spare: a click in the panel that follows nothing."""
    with browser_page(base_url, "/a", viewport=(390, 844)) as page_:
        page_.wait_for_selector("html.bz-ready")
        page_.click("#menu")
        page_.wait_for_function(_OPEN)
        page_.get_by_text("Pages", exact=True).click()
        page_.wait_for_timeout(300)
        assert page_.evaluate(_OPEN)
