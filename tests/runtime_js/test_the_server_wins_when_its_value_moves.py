"""A control re-adopts the server's value when the server changed it.

A control keeps its value in a local scope that survives a morph, so an
unrelated refresh does not wipe what the user did. Until 2026-10-23 the
server took over only for a value stamped as a state field: a value the
app COMPUTED — filters read from the URL, a selection from a list —
stayed client-owned for good. On the comparison helpdesk, "Clear filters"
left the status toggles pressed, "Clear selection" left the boxes ticked.

The rule now (``runtime/_src/03_scope.js``, ``resyncScopes``): the server
wins when the value it renders has changed since its last render. Both
sides are held here: the reset reaches the controls, and a local change
the server did not touch survives an unrelated refresh.

Heavy (uvicorn + Chromium) ::

    py -m pytest tests/runtime_js/test_the_server_wins_when_its_value_moves.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import PageState, field
from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

app = Bretzel(secret_key="dev-server-wins-secret-key", title="Bretzel · server wins", mode="dev")


class Filters(PageState):
    #: Comma-separated, as a URL would carry it: the controls get a value
    #: the app COMPUTES from it, never the field itself.
    statuses: str = field(default="")
    ticked: bool = field(default=False)
    ticks: int = field(default=0)


def set_statuses(statuses: list[str] | None = None) -> None:
    Filters().statuses = ",".join(statuses or [])


def set_ticked(checked: bool = False) -> None:
    Filters().ticked = checked


def clear() -> None:
    Filters().statuses = ""
    Filters().ticked = False


def unrelated() -> None:
    Filters().ticks += 1


@refreshable(deps=[Filters])
def controls() -> None:
    picked = [s for s in Filters().statuses.split(",") if s]
    with ui.vstack(gap="sm"):
        with ui.toggle_group(value=list(picked), multiple=True, name="statuses",
                             on_change=set_statuses, id="statuses"):
            ui.toggle_button("open", "Open")
            ui.toggle_button("closed", "Closed")
        ui.checkbox(checked=bool(Filters().ticked), name="checked", on_change=set_ticked,
                    id="tick", attrs={"aria-label": "tick"})
        with ui.toggle_group(value=[], multiple=True, name="local", id="local"):
            ui.toggle_button("x", "Local only")
        ui.text(f"state={Filters().statuses}|{Filters().ticked}|{Filters().ticks}", id="state")


@page("/")
def home() -> None:
    with ui.vstack(gap="md", classes="p-6"):
        ui.button("clear", on_click=clear, id="clear")
        ui.button("unrelated", on_click=unrelated, id="unrelated")
        controls()


app.include(__name__)


@pytest.fixture(scope="module")
def base_url():
    with audit_server(app) as url:
        yield url


#: ``group/label`` → the button's ``aria-pressed``.
_PRESSED = """key => { const [group, label] = key.split('/');
  const b = [...document.querySelectorAll('#' + group + ' button')].find(x => x.textContent.trim() === label);
  return b.getAttribute('aria-pressed'); }"""
_OPEN, _LOCAL = "#statuses button:has-text('Open')", "#local button:has-text('Local only')"
_TICK = "input#tick, #tick input"
_TICKED = f"() => document.querySelector('{_TICK}').checked"


def state(page_, text: str) -> None:
    page_.wait_for_function(f"document.querySelector('#state')?.textContent === 'state={text}'")
    page_.wait_for_timeout(150)


def test_a_server_reset_reaches_the_controls(base_url) -> None:
    with browser_page(base_url, "/") as page_:
        page_.wait_for_selector("html.bz-ready")
        page_.click(_OPEN)
        state(page_, "open|False|0")
        page_.click("label:has(#tick)")
        state(page_, "open|True|0")
        assert page_.evaluate(_PRESSED, "statuses/Open") == "true" and page_.evaluate(_TICKED)
        page_.click("#clear")
        state(page_, "|False|0")
        assert page_.evaluate(_PRESSED, "statuses/Open") == "false", (
            "the server cleared the filters, the toggle stays pressed")
        assert not page_.evaluate(_TICKED), "the server cleared the box, it stays ticked"


def test_a_local_change_survives_an_unrelated_refresh(base_url) -> None:
    """The side it must spare: the server renders the same value as
    before, so what the user did stays."""
    with browser_page(base_url, "/") as page_:
        page_.wait_for_selector("html.bz-ready")
        page_.click(_LOCAL)
        assert page_.evaluate(_PRESSED, "local/Local only") == "true"
        page_.click("#unrelated")
        state(page_, "|False|1")
        assert page_.evaluate(_PRESSED, "local/Local only") == "true", (
            "an unrelated refresh wiped a local choice the server never touched")
