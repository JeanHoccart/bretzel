"""A multi-select with many picks keeps its height: "Alice Martin +3".

The closed trigger has a fixed height (``h-8`` at ``sm``) and its pills
wrapped: four assignees in a toolbar filter stacked four pills above and
below the box (python-ui-shootout helpdesk, 2026-10-23). The trigger
now shows the first pick as text, then "+N"; a w-44 filter must read
the whole name.

Heavy (uvicorn + Chromium) ::

    py -m pytest tests/runtime_js/test_a_multi_select_stays_on_one_line.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, ui
from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

app = Bretzel(secret_key="dev-multi-one-line-secret-key", title="Bretzel · one-line multi", mode="dev")

PEOPLE = [("a", "Alice Martin"), ("b", "Bob Nguyen"), ("c", "Carol Diaz"), ("d", "Dave Okafor")]


@page("/")
def home() -> None:
    with ui.hstack(gap="sm", classes="p-6"):
        ui.select(PEOPLE, multiple=True, value=["a", "b", "c", "d"], name="who",
                  placeholder="Assignee", size="sm", classes="w-44", id="full")
        ui.select(PEOPLE, multiple=True, value=["a"], name="one",
                  placeholder="Assignee", size="sm", classes="w-40", id="one")
        ui.select(PEOPLE, multiple=True, value=[], name="none",
                  placeholder="Assignee", size="sm", classes="w-40", id="none")


app.include(__name__)


@pytest.fixture(scope="module")
def base_url():
    with audit_server(app) as url:
        yield url


_GEOMETRY = """id => {
  const t = document.querySelector('#' + id + ' [role=combobox]'), r = t.getBoundingClientRect();
  const inside = e => { const b = e.getBoundingClientRect();
    return b.width === 0 || (b.top >= r.top - 0.5 && b.bottom <= r.bottom + 0.5 && b.right <= r.right + 0.5); };
  const pills = [...t.querySelectorAll('[data-bz-row]')].filter(e => e.getBoundingClientRect().width > 0);
  return {h: r.height, pills: pills.map(e => e.textContent.replace('×', '').trim()),
          allInside: [...t.querySelectorAll('*')].every(inside), text: t.innerText.replace(/\\s+/g, ' ').trim()};
}"""


def test_four_picks_stay_inside_a_one_line_trigger(base_url) -> None:
    with browser_page(base_url, "/") as page_:
        page_.wait_for_selector("html.bz-ready")
        full, none = page_.evaluate(_GEOMETRY, "full"), page_.evaluate(_GEOMETRY, "none")
        assert full["h"] == none["h"], f"the trigger grew: {full['h']} px vs {none['h']} px empty"
        assert full["allInside"], f"something spills out of the trigger: {full}"
        assert full["pills"] == ["Alice Martin"], full
        assert "+3" in full["text"], full
        assert page_.evaluate(
            "() => { const e = document.querySelector('#full [data-bz-row]');"
            " return e.scrollWidth <= e.clientWidth; }"), "the name is cut in a w-44 filter"


def test_one_pick_has_no_counter_and_none_shows_the_placeholder(base_url) -> None:
    """The side it must spare."""
    with browser_page(base_url, "/") as page_:
        page_.wait_for_selector("html.bz-ready")
        one, none = page_.evaluate(_GEOMETRY, "one"), page_.evaluate(_GEOMETRY, "none")
        assert one["pills"] == ["Alice Martin"] and "+" not in one["text"], one
        assert none["pills"] == [] and none["text"].startswith("Assignee"), none
