"""Switching light / dark repaints the page at once, not in a wave.

Many components carry ``transition-colors`` for their hover; those
transitions also ran on the scheme change, and ``:root`` had its own
150 ms colour transition. Each element faded on its own clock and the
page repainted in a staggered wave, where seven other frameworks switch
in one frame (found 2026-10-23, side by side on the python-ui-shootout
comparison page). The runtime now suspends transitions for the frame of
the switch.

Heavy (uvicorn + Chromium) ::

    py -m pytest tests/runtime_js/test_a_scheme_switch_is_instant.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, ui
from bretzel.theme import ColorScheme
from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

app = Bretzel(secret_key="dev-scheme-instant-secret-key", title="Bretzel · instant scheme", mode="dev")


@page("/")
def home() -> None:
    with ui.vstack(gap="md", classes="p-6"):
        ui.button("dark", on_click=ColorScheme.set("dark"), id="to-dark")
        ui.button("light", on_click=ColorScheme.set("light"), id="to-light")
        # A slow colour transition: the wave would be impossible to miss.
        ui.card(id="probe", classes="transition-colors duration-1000 bg-background")


app.include(__name__)


@pytest.fixture(scope="module")
def base_url():
    with audit_server(app) as url:
        yield url


_BG = "() => getComputedStyle(document.getElementById('probe')).backgroundColor"


def test_the_switch_lands_in_one_frame(base_url) -> None:
    with browser_page(base_url, "/") as page_:
        page_.wait_for_selector("html.bz-ready")
        page_.click("#to-light")
        page_.wait_for_timeout(1200)
        light = page_.evaluate(_BG)
        page_.click("#to-dark")
        # Two frames after the click: a 1 s transition would still be at
        # its very start, so the colour would barely have moved.
        early = page_.evaluate(
            "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => "
            "r(getComputedStyle(document.getElementById('probe')).backgroundColor))))")
        page_.wait_for_timeout(1200)
        final = page_.evaluate(_BG)
        assert final != light, "the floor: the probe must change colour between schemes"
        assert early == final, (
            f"two frames after switching to dark the card reads {early}, not its "
            f"final {final}: the scheme change is running the components' "
            "colour transitions."
        )
