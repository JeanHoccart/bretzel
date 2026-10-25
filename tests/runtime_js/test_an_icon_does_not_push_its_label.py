"""An icon below the fold does not push its label when it scrolls in.

The behaviour end of ``tests/consistency/test_every_icon_renders_at_once.py``.

Heavy (uvicorn + Chromium) ::

    py -m pytest tests/runtime_js/test_an_icon_does_not_push_its_label.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, ui
from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

app = Bretzel(secret_key="dev-icon-label-secret-key", title="Bretzel · icon label", mode="dev")


@page("/")
def home() -> None:
    with ui.vstack(gap="sm", classes="p-6"):
        ui.text("tall spacer", classes="block h-[3000px]", id="top")
        with ui.hstack(gap="sm", align="center", id="line"):
            ui.icon("inbox", size="md")
            ui.text("Label", id="label")


app.include(__name__)


@pytest.fixture(scope="module")
def base_url():
    with audit_server(app) as url:
        yield url


_X = "() => document.getElementById('label').getBoundingClientRect().left"


_DRAWN = "() => !!document.querySelector('#line iconify-icon').shadowRoot?.querySelector('svg, span')"
_TWO_FRAMES = "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"


def test_the_label_stays_put_when_the_icon_comes_and_goes(base_url) -> None:
    """In view, scrolled away (the lazy component emptied it), and on a
    second visit (its glyph cached, so emptied before it was ever seen)."""
    with browser_page(base_url, "/", viewport=(800, 600)) as page_:
        page_.wait_for_selector("html.bz-ready")
        page_.evaluate("document.getElementById('line').scrollIntoView()")
        page_.wait_for_function(_DRAWN)
        shown = page_.evaluate(_X)
        page_.evaluate("document.getElementById('top').scrollIntoView()")
        page_.evaluate(_TWO_FRAMES)
        away = page_.evaluate(_X)
        page_.reload()
        page_.wait_for_selector("html.bz-ready")
        page_.evaluate(_TWO_FRAMES)
        revisit = page_.evaluate(_X)
        drawn = page_.evaluate(_DRAWN)
    assert drawn, "the floor: the icon must be drawn off screen"
    assert shown == away == revisit, (
        f"the label sits at x={shown} with its icon in view, x={away} once the "
        f"icon left the screen, x={revisit} on a second visit"
    )
