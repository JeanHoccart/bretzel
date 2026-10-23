"""A multi-select re-rendered by its own action keeps showing its pills.

The pills of ``ui.select(multiple=True)`` are rows of a ``<template
bz-for>``, cloned in the browser; the server's HTML never carries them.
When the select's ``on_change`` writes the state its own ``@refreshable``
depends on, the zone comes back and idiomorph matches the siblings of the
template by POSITION: it recycled the first pill's node into the
"Priority" placeholder that follows the template. ``bz-for`` kept that
node in its row map — still connected, so "present" — and never cloned the
pill again. The filter showed its clear cross and nothing else, while the
server held the value. Found on 2026-10-23 on the python-ui-shootout
helpdesk (a priority filter).

Why a real browser: it is the morph of a refreshable zone over an HTTP
round trip that recycles the node; mounting the component twice
reproduces nothing.

Heavy (uvicorn + Chromium) ::

    py -m pytest tests/runtime_js/test_a_multi_select_keeps_its_pills_after_its_own_refresh.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import PageState, field
from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

app = Bretzel(
    secret_key="dev-multi-select-pills-secret-key",
    title="Bretzel · pills of a self-refreshing multi-select",
    mode="dev",
)


class Filter(PageState):
    prios: list = field(default_factory=list)


def set_prios(prios: list[str] | None = None) -> None:
    Filter().prios = list(prios or [])


@refreshable(deps=[Filter])
def zone() -> None:
    with ui.vstack(gap="sm"):
        ui.select([("urgent", "Urgent"), ("high", "High")], multiple=True,
                  value=Filter().prios, name="prios", on_change=set_prios,
                  placeholder="Priority", id="ms")
        ui.text(f"chosen={','.join(Filter().prios)}", id="state")


@page("/")
def home() -> None:
    with ui.vstack(gap="md", classes="p-6"):
        zone()


app.include(__name__)


@pytest.fixture(scope="module")
def base_url():
    with audit_server(app) as url:
        yield url


_SHOWN = """() => [...document.querySelectorAll('#ms [role=combobox] [data-bz-row]')]
    .filter(e => e.getBoundingClientRect().width > 0).map(e => e.textContent.replace('×', '').trim())"""


def pick(page_, value: str, expected_state: str) -> None:
    if not page_.locator("#ms [role=option]").first.is_visible():
        page_.click("#ms [role=combobox]")
    page_.click(f"#ms [role=option][data-value={value}]")
    page_.wait_for_function(
        f"document.querySelector('#state').textContent === 'chosen={expected_state}'")
    page_.wait_for_timeout(200)


def test_the_pills_survive_the_zone_coming_back(base_url) -> None:
    with browser_page(base_url, "/") as page_:
        page_.wait_for_selector("html.bz-ready")
        pick(page_, "high", "high")
        # The server holds the value: only the display can be at fault below.
        assert page_.evaluate(_SHOWN) == ["High"], (
            "after its own refresh the multi-select shows no pill: the morph "
            "recycled the pill's node into the placeholder and bz-for kept it "
            "as a row."
        )
        pick(page_, "urgent", "high,urgent")
        # The trigger stays on one line: the first pick, then "+1".
        assert page_.evaluate(_SHOWN) == ["High"]
        assert "+1" in page_.locator("#ms [role=combobox]").inner_text()


def test_the_placeholder_is_not_a_pill(base_url) -> None:
    """The side it must spare: with nothing picked, the placeholder shows
    and no row is drawn."""
    with browser_page(base_url, "/") as page_:
        page_.wait_for_selector("html.bz-ready")
        assert page_.evaluate(_SHOWN) == []
        assert page_.locator("#ms [role=combobox]").inner_text().strip().startswith("Priority")
