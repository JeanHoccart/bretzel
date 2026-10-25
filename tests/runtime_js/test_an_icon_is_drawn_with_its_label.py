"""An icon is drawn in the very first frame, and its label never moves.

Reported 2026-10-23 with two screenshots: the first frame showed the
heading's text at the left edge, the next one the icon pushing it right.
The icon's script is deferred and its glyph came in one more request; the
host stayed an empty INLINE element until then, and the ``1em`` minimum
of ``theme/css.py`` does not apply to an inline element.

Now a full page carries the glyph in a declarative shadow root, and its
data for the component (``render/icons.py``). The test slows the
component's script down, records every frame from the first one, and
holds three things: the glyph is there in each frame, the label never
moves, and no glyph request leaves.

Heavy (uvicorn + Chromium) ::

    py -m pytest tests/runtime_js/test_an_icon_is_drawn_with_its_label.py -q -m browser
"""

from __future__ import annotations

import time

import pytest

from bretzel import Bretzel, page, ui
from bretzel.runtime.protocol import ROUTE_ICONS
from tests.audit.harness import audit_server, browser_context

pytestmark = pytest.mark.browser

app = Bretzel(secret_key="dev-icon-first-frame-secret-key", title="Bretzel · icon", mode="dev")


@page("/")
def home() -> None:
    with ui.hstack(gap="sm", align="center", classes="p-6", id="line"):
        ui.icon("sofa", size="lg")
        ui.heading("Dans la classe", level=2, id="label")


app.include(__name__)


@pytest.fixture(scope="module")
def base_url():
    with audit_server(app) as url:
        yield url


#: One sample per frame, from the first one: the label's left edge, and
#: whether the icon shows a glyph — the server's (before the upgrade) or
#: the component's (after).
_RECORD = """
window._frames = [];
(function sample() {
  const label = document.getElementById('label');
  const icon = document.querySelector('#line iconify-icon');
  if (label && icon) {
    const root = icon.shadowRoot;
    window._frames.push([label.getBoundingClientRect().left,
                         !!(root && root.querySelector('svg')),
                         customElements.get('iconify-icon') !== undefined]);
  }
  if (performance.now() < 2500) requestAnimationFrame(sample);
})();
"""


def _slow(route) -> None:
    time.sleep(0.6)
    route.continue_()


def test_the_icon_is_there_from_the_first_frame(base_url) -> None:
    # The harness's shared browser: a second Playwright in the same
    # worker would clash with it.
    with browser_context() as ctx:
        page_ = ctx.new_page()
        page_.add_init_script(_RECORD)
        page_.route("**/iconify-icon*.js", _slow)
        glyph_requests: list[str] = []
        page_.on("request", lambda r: glyph_requests.append(r.url) if ROUTE_ICONS in r.url else None)
        page_.goto(base_url + "/")
        page_.wait_for_timeout(2600)
        frames = page_.evaluate("window._frames")
    assert frames, "no frame was recorded"
    assert any(not defined for *_, defined in frames), (
        "the floor: some frames must come before the component's script")
    assert any(defined for *_, defined in frames), "the component never registered"
    assert all(drawn for _, drawn, _ in frames), (
        "a frame showed the icon empty: "
        f"{[(round(x), drawn, defined) for x, drawn, defined in frames][:12]}")
    assert len({round(x, 1) for x, _, _ in frames}) == 1, (
        f"the label moved: {sorted({round(x, 1) for x, _, _ in frames})}")
    assert not glyph_requests, f"the glyph was fetched again: {glyph_requests}"
