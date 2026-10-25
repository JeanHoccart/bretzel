"""Gate: every stateful control follows the server, and keeps the user.

Two failures of the same rule on one day (2026-10-23, comparison
helpdesk): "Clear selection" left boxes ticked, "Clear filters" left
toggles pressed. A control keeps its value in a local scope that survives
a morph; only a value stamped as a state field used to be handed back to
the server, and a value the app COMPUTED never was.

The rule (``runtime/_src/03_scope.js``, ``resyncScopes``): the server
wins when the value it renders has changed since its last render. Held
here on a page of controls fed with COMPUTED values, both ways:

1. a local choice survives a refresh that does not change the server's
   value — the side that justifies local state at all;
2. a value the server changes reaches the control.

The cases are the stateful controls an app most often resets; the rule
is one code path for every scope key, so a new control inherits it.

Heavy (uvicorn + Chromium) ::

    py -m pytest tests/runtime_js/test_controls_follow_the_server_and_keep_the_user.py -q -m browser
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import PageState, field
from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

app = Bretzel(secret_key="dev-controls-follow-secret-key", title="Bretzel · controls", mode="dev")

OPTIONS = [("a", "A"), ("b", "B"), ("c", "C")]


def noop(*_args: Any, **_kwargs: Any) -> None:
    """A server handler that changes nothing: the control is wired as an
    app wires it, with ``on_change``."""


def toggles(v: Any, cid: str) -> None:
    with ui.toggle_group(value=v, multiple=True, name=cid, on_change=noop, id=cid):
        for key, label in OPTIONS:
            ui.toggle_button(key, label)


def tabs(v: Any, cid: str) -> None:
    with ui.tabs(value=v, name=cid, on_change=noop, id=cid):
        for key, label in OPTIONS:
            ui.tab(key, label=label)


def accordion(v: Any, cid: str) -> None:
    with ui.accordion(value=v, on_change=noop, id=cid):
        for key, label in OPTIONS:
            with ui.accordion_item(key, label=label):
                ui.text(label)


#: name → (builder, scope key, server A, server B, local C ≠ A, local D ≠ B)
CASES: dict[str, tuple[Callable[[Any, str], Any], str, Any, Any, Any, Any]] = {
    "toggle_group": (toggles, "value", ["a"], ["b"], ["a", "c"], ["c"]),
    "select": (lambda v, cid: ui.select(OPTIONS, value=v, name=cid, on_change=noop, id=cid),
               "value", "a", "b", "c", "c"),
    "select_multiple": (lambda v, cid: ui.select(OPTIONS, value=v, multiple=True, name=cid,
                                                 on_change=noop, id=cid),
                        "value", ["a"], ["b"], ["a", "c"], ["c"]),
    "combobox": (lambda v, cid: ui.combobox(OPTIONS, value=v, name=cid, on_change=noop, id=cid),
                 "value", "a", "b", "c", "c"),
    "number_input": (lambda v, cid: ui.number_input(value=v, name=cid, on_change=noop, id=cid),
                     "value", 1, 2, 3, 3),
    "slider": (lambda v, cid: ui.slider(value=v, min=0, max=100, name=cid, on_change=noop, id=cid),
               "value", 10, 20, 30, 30),
    "pagination": (lambda v, cid: ui.pagination(value=v, total_pages=5, name=cid, on_change=noop,
                                                id=cid),
                   "value", 1, 2, 3, 3),
    "tabs": (tabs, "value", "a", "b", "c", "c"),
    "accordion": (accordion, "value", "a", "b", "c", "c"),
    "checkbox": (lambda v, cid: ui.checkbox(checked=v, name="checked", on_change=noop, id=cid),
                 "checked", False, True, True, False),
    "switch": (lambda v, cid: ui.switch(checked=v, name="checked", on_change=noop, id=cid),
               "checked", False, True, True, False),
}


class Step(PageState):
    step: int = field(default=0)
    ticks: int = field(default=0)


def to_b() -> None:
    Step().step = 1


def unrelated() -> None:
    Step().ticks += 1


@refreshable(deps=[Step])
def controls() -> None:
    step = Step().step
    with ui.vstack(gap="sm"):
        for name, (build, _key, a, b, _c, _d) in CASES.items():
            # COMPUTED from the state, never the field itself: the case
            # that used to stay client-owned.
            build(json.loads(json.dumps(b if step else a)), f"c-{name}")
        ui.text(f"step={step}|{Step().ticks}", id="state")


@page("/")
def home() -> None:
    with ui.vstack(gap="md", classes="p-6"):
        ui.button("to b", on_click=to_b, id="to-b")
        ui.button("unrelated", on_click=unrelated, id="unrelated")
        controls()


app.include(__name__)


@pytest.fixture(scope="module")
def base_url():
    with audit_server(app) as url:
        yield url


#: The scope of ``cid`` holding ``key``: the control's own, or the first
#: one under it (a checkbox keeps its value on its ``<input>``).
_SCOPE = """([cid, key]) => {
  for (const [id, scope] of $bz._scopes) {
    if ((id === cid || id.startsWith(cid + '_')) && scope.signals.has(key)) return id;
  }
  const inner = [...document.querySelectorAll('#' + cid + ' [bz-data], [bz-id="' + cid + '"][bz-data]')]
    .map(el => el.getAttribute('bz-id')).find(id => $bz._scopes.get(id)?.signals.has(key));
  return inner || null;
}"""
_GET = "([id, key]) => JSON.stringify($bz._scopes.get(id).signals.get(key).get())"
_SET = "([id, key, value]) => $bz._scopes.get(id).signals.get(key).set(JSON.parse(value))"


def wait_state(page_: Any, text: str) -> None:
    page_.wait_for_function(f"document.querySelector('#state')?.textContent === '{text}'")
    page_.wait_for_timeout(150)


def test_every_control_keeps_the_user_and_follows_the_server(base_url) -> None:
    with browser_page(base_url, "/") as page_:
        page_.wait_for_selector("html.bz-ready")
        scopes = {name: page_.evaluate(_SCOPE, [f"c-{name}", key])
                  for name, (_b, key, *_rest) in CASES.items()}
        missing = sorted(name for name, sid in scopes.items() if sid is None)
        assert not missing, f"the floor: no local scope found for {missing}"

        def each(js: str, pick: int) -> None:
            for name, case in CASES.items():
                page_.evaluate(js, [scopes[name], case[1], json.dumps(case[pick])])

        def read() -> dict[str, Any]:
            return {name: json.loads(page_.evaluate(_GET, [scopes[name], case[1]]))
                    for name, case in CASES.items()}

        each(_SET, 4)  # the user's choice, C
        page_.click("#unrelated")
        wait_state(page_, "step=0|1")
        kept = read()
        lost = {n: v for n, v in kept.items() if v != CASES[n][4]}
        assert not lost, f"an unrelated refresh overwrote the user's choice: {lost}"

        each(_SET, 5)  # D, so that adopting B is visible
        page_.click("#to-b")
        wait_state(page_, "step=1|1")
        followed = read()
        stale = {n: v for n, v in followed.items() if v != CASES[n][3]}
        assert not stale, f"the server changed these values and the controls kept theirs: {stale}"
