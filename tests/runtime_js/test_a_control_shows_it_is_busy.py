"""A control whose action is slow shows it is busy, on its own.

Before, between a click and the answer — 300 ms and more on a slow
network — nothing moved unless the app wrote ``loading=ui.pending()``.
Now the runtime marks the trigger after 200 ms (``05_bridge.js``,
the ``bz-busy`` class + ``aria-busy``) and the theme draws it per shape
(``theme/css.py``, ``_BUSY``): a spinner in a button, at the end of a
field, a pulse on a box, a dimmed zone.

What only a browser shows: the delay (a fast answer never flashes), that
a button keeps its width, that each shape is really drawn, that a zone
the runtime asks again is marked too, and that ``loading=False`` — on the
control or on a container — turns it off.

Heavy (uvicorn + Chromium) ::

    py -m pytest tests/runtime_js/test_a_control_shows_it_is_busy.py -q -m browser
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import AppState, field
from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

app = Bretzel(secret_key="dev-busy-state-secret-key", title="Bretzel · busy", mode="dev")

SLOW = 0.8


class Live(AppState):
    n: int = field(default=0, merge="add")


def slow() -> None:
    time.sleep(SLOW)


def fast() -> None:
    pass


def bump() -> None:
    Live().n += 1


@refreshable(deps=[Live], broadcast=[Live])
def live() -> None:
    # Slow only once something changed: the page itself loads at once,
    # the refetch the other tab triggers takes its time.
    if Live().n:
        time.sleep(SLOW)
    with ui.vstack():  # the zone's root holds #live-n (one child would fuse into it)
        ui.text(f"n={Live().n}", id="live-n")


@page("/")
def home() -> None:
    with ui.vstack(gap="md", align="start", classes="p-6"):
        ui.button("Save the ticket", on_click=slow, id="slow")
        ui.button("Quick", on_click=fast, id="fast")
        ui.button("Quiet", on_click=slow, loading=False, id="quiet")
        with ui.hstack(loading=False, id="quiet-box"):
            ui.button("Inside", on_click=slow, id="inside")
        ui.checkbox(label="Watch", on_change=slow, id="box")
        ui.input(placeholder="Search", on_input=slow, id="field")
        ui.button("bump", on_click=bump, id="bump")
        live()


app.include(__name__)


@pytest.fixture(scope="module")
def base_url():
    with audit_server(app) as url:
        yield url


#: Every change of the busy state on an element (``"on"`` / ``None``),
#: with its time — recorded from the page, so a flash between two samples
#: is seen.
_WATCH = """(sel) => {
  const el = document.querySelector(sel);
  window._seen = [];
  const t0 = performance.now();
  let was = el.classList.contains('bz-busy');
  new MutationObserver(() => {
    const now = el.classList.contains('bz-busy');
    if (now !== was) window._seen.push([now ? 'on' : null, Math.round(performance.now() - t0)]);
    was = now;
  }).observe(el, {attributes: true, attributeFilter: ['class']});
}"""


def _trigger(page_: Any, sel: str) -> str:
    """The element carrying the request: the control itself, or the
    input inside it (a checkbox's real input, a field's)."""
    return page_.evaluate(
        "(sel) => { const el = document.querySelector(sel);"
        " const t = el.matches('[hx-post]') ? el : el.querySelector('[hx-post]');"
        " t.setAttribute('data-test-trigger', sel); return '[data-test-trigger=\"' + sel + '\"]'; }",
        sel)


def test_a_slow_button_shows_a_spinner_and_keeps_its_width(base_url) -> None:
    with browser_page(base_url, "/") as page_:
        page_.wait_for_selector("html.bz-ready")
        width = page_.evaluate("document.querySelector('#slow').getBoundingClientRect().width")
        page_.evaluate(_WATCH, "#slow")
        page_.click("#slow")
        page_.wait_for_selector("#slow.bz-busy", timeout=2000)
        page_.wait_for_timeout(300)  # the button's own 200 ms transition
        busy = page_.evaluate("""() => { const b = document.querySelector('#slow');
          return {width: b.getBoundingClientRect().width, aria: b.getAttribute('aria-busy'),
                  spin: getComputedStyle(b, '::after').animationName,
                  label: getComputedStyle(b).webkitTextFillColor}; }""")
        page_.wait_for_function("!document.querySelector('#slow').classList.contains('bz-busy')",
                                timeout=5000)
        seen = page_.evaluate("window._seen")
    assert seen[0][0] == "on" and seen[0][1] >= 180, f"shown too early: {seen}"
    assert busy["aria"] == "true"
    assert busy["spin"] == "bz-busy-spin", "no spinner drawn"
    assert busy["label"] == "rgba(0, 0, 0, 0)", f"the label still shows: {busy['label']}"
    assert abs(busy["width"] - width) < 0.5, f"the button changed width: {width} → {busy['width']}"


def test_a_fast_answer_never_flashes(base_url) -> None:
    with browser_page(base_url, "/") as page_:
        page_.wait_for_selector("html.bz-ready")
        page_.evaluate(_WATCH, "#fast")
        page_.click("#fast")
        page_.wait_for_timeout(700)
        seen = page_.evaluate("window._seen")
    assert seen == [], f"a fast action showed a busy state: {seen}"


def test_loading_false_turns_it_off_on_the_control_and_inside_a_container(base_url) -> None:
    with browser_page(base_url, "/") as page_:
        page_.wait_for_selector("html.bz-ready")
        for sel in ("#quiet", "#inside"):
            page_.evaluate(_WATCH, sel)
            page_.click(sel)
            page_.wait_for_timeout(int(SLOW * 1000) + 300)
            assert page_.evaluate("window._seen") == [], f"{sel} showed a busy state"


def test_a_box_pulses_and_a_field_shows_a_spinner(base_url) -> None:
    with browser_page(base_url, "/") as page_:
        page_.wait_for_selector("html.bz-ready")
        box = _trigger(page_, "#box")
        page_.click("label:has(#box)")  # the real input is visually hidden
        page_.wait_for_selector(f"{box}.bz-busy", timeout=2000)
        pulse = page_.evaluate(
            f"getComputedStyle(document.querySelector('{box}').nextElementSibling).animationName")
        page_.wait_for_function(f"!document.querySelector('{box}').classList.contains('bz-busy')",
                                timeout=5000)
        field_ = _trigger(page_, "#field")
        page_.fill(field_, "printer")
        page_.wait_for_selector(f"{field_}.bz-busy", timeout=3000)
        image = page_.evaluate(f"getComputedStyle(document.querySelector('{field_}')).backgroundImage")
    assert pulse == "bz-busy-pulse", f"the box does not pulse: {pulse!r}"
    assert "data:image/svg+xml" in image, f"no spinner in the field: {image[:60]!r}"


def test_a_zone_asked_again_dims_while_it_comes(base_url) -> None:
    with browser_page(base_url, "/", wait_until="load") as other, \
            browser_page(base_url, "/", wait_until="load") as actor:
        for tab in (other, actor):
            tab.wait_for_selector("html.bz-ready")
        other.wait_for_timeout(500)  # the stream is open
        zone = "[data-bz-zone]:has(#live-n)"
        other.evaluate(_WATCH, zone)
        before = other.evaluate("document.querySelector('#live-n').textContent")
        actor.click("#bump")
        other.wait_for_function(
            f"document.querySelector('#live-n').textContent !== {before!r}", timeout=8000)
        seen = other.evaluate("window._seen")
        opacity_after = other.evaluate(f"getComputedStyle(document.querySelector('{zone}')).opacity")
    assert [v for v, _ in seen[:1]] == ["on"], f"the zone was not marked while it came: {seen}"
    assert seen[-1][0] is None, f"the zone stayed busy: {seen}"
    assert opacity_after == "1"
