"""A zone inside a parent that composes its children is refused.

Since 2026-08-23 a child wrapped in a ``@refreshable`` zone survived the
PAGE render of a parent that sorts its children (``unwrap_transparent``).
Measured on 2026-10-27: it did not survive the zone's FIRST refresh. The
fragment is rendered without the parent, so the child came out bare —
and the parent had composed it its own way. In Chromium, a click that
refreshed the zone:

==================  =================================================
``ui.tabs``         the tab left the bar (an empty ``<span>``)
``ui.stepper``      the step disappeared
``ui.accordion``    the item lost its header, only its body was left
``ui.tree``         the node disappeared
``ui.scheduler``    the card disappeared
``ui.toggle_group`` an error box replaced the button (it raises alone)
``ui.breadcrumb``   the segment lost its style
``ui.resizable``    the panel lost its size and its constraint
==================  =================================================

Composition, not attributes: nothing on the server can redo it, since
the parent is built in the middle of a page function. ``ui.form_field``
is the ninth case — it wires its label onto its control, and did not
even see the control through a zone at page render. All nine now
refuse the form, and their message says where the zone goes.

``ui.sidebar`` only PLACES its children: a zone there (the footer that
shows the signed-in account) still refreshes alone to the byte.

The proof that the right form works compares, for each parent, the zone
in the page with the same zone refreshed alone (a fingerprint the
browser cannot hold, so the server renders it whole). Each zone reads a
state but renders the same whatever its value: any difference would be
something the lone refresh lost.
"""

from __future__ import annotations

import datetime as dt
import re
import time
from collections.abc import Callable

import pytest
from bs4 import BeautifulSoup
from starlette.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.runtime.protocol import HEADER_ZONES
from bretzel.server.handlers import encode_action_id, sign_action
from bretzel.state import AppState, field
from tests._session import session_of

app = Bretzel(secret_key="x" * 32, mode="dev")


class S(AppState):
    n: int = field(default=0, merge="add")


def bump() -> None:
    S().n += 1


def reads() -> None:
    S().n  # read, never shown: the render does not depend on the value


MONDAY = dt.datetime(2026, 10, 26)


# ── What each parent holds ─────────────────────────────────────────────────
# One child per parent, written once, used by both forms.

def _tabs() -> None:
    with ui.tabs():
        ui.tab("messages", label="Messages")
        ui.tab("settings", label="Settings")


def _stepper() -> None:
    with ui.stepper():
        ui.step(label="Step one")
        ui.step(label="Step two")


def _accordion() -> None:
    with ui.accordion(), ui.accordion_item(label="Item one", value="one"):
        ui.text("body")


def _tree() -> None:
    with ui.tree():
        ui.tree_node(label="Root", value="root")


def _breadcrumb() -> None:
    with ui.breadcrumb():
        ui.breadcrumb_item(label="Home", href="/")
        ui.breadcrumb_item(label="Here")


def _toggle_group() -> None:
    with ui.toggle_group():
        ui.toggle_button("a", label="A")
        ui.toggle_button("b", label="B")


def _resizable() -> None:
    with ui.resizable(sizes=[30, 70]):
        with ui.resizable_panel(min_size=25):
            ui.text("left")
        with ui.resizable_panel():
            ui.text("right")


def _scheduler() -> None:
    with ui.scheduler(date=MONDAY, hours=(8, 11)):
        ui.scheduler_item(key="lesson", title="Lesson", color="violet",
                          start=MONDAY.replace(hour=8), end=MONDAY.replace(hour=9))


def _form_field() -> None:
    with ui.form_field(label="Room", required=True):
        ui.select(options=["a", "b"], value="b")


# ── The refused form: a zone directly inside the parent ────────────────────

def _zone_inside(parent: Callable[[], None], child: Callable[[], None]):
    """``parent`` holding ``child`` wrapped in a zone of its own."""
    zone = refreshable()(child)

    def build() -> None:
        parent_node = parent()
        with parent_node:
            zone()
        parent_node.render()

    return build


REFUSED: dict[str, tuple[Callable[[], None], str]] = {
    "tabs": (_zone_inside(ui.tabs, lambda: ui.tab("messages", label="Messages")),
             "AROUND ui.tabs"),
    "stepper": (_zone_inside(ui.stepper, lambda: ui.step(label="Step one")),
                "AROUND ui.stepper"),
    "accordion": (_zone_inside(ui.accordion,
                               lambda: ui.accordion_item(label="Item", value="one")),
                  "AROUND ui.accordion"),
    "tree": (_zone_inside(ui.tree, lambda: ui.tree_node(label="Root", value="root")),
             "AROUND ui.tree"),
    "breadcrumb": (_zone_inside(ui.breadcrumb, lambda: ui.breadcrumb_item(label="Home", href="/")),
                   "AROUND ui.breadcrumb"),
    "toggle_group": (_zone_inside(ui.toggle_group, lambda: ui.toggle_button("a", label="A")),
                     "AROUND ui.toggle_group"),
    "resizable": (_zone_inside(lambda: ui.resizable(sizes=[30, 70]),
                               lambda: ui.resizable_panel(min_size=25)),
                  "AROUND ui.resizable"),
    "scheduler": (_zone_inside(
        lambda: ui.scheduler(date=MONDAY, hours=(8, 11)),
        lambda: ui.scheduler_item(key="lesson", title="Lesson", start=MONDAY.replace(hour=8),
                                  end=MONDAY.replace(hour=9))),
        "AROUND ui.scheduler"),
    "form_field": (_zone_inside(lambda: ui.form_field(label="Room"),
                                lambda: ui.select(options=["a", "b"], value="b")),
                   "INSIDE the zone"),
}


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_a_zone_directly_inside_is_refused(name: str) -> None:
    build, where = REFUSED[name]
    with render_isolated(), pytest.raises(ComponentUsageError) as raised:
        build()
    assert where in str(raised.value), (
        f"ui.{name}: the refusal does not say where the zone goes:\n{raised.value}"
    )


def test_a_fragment_is_still_traversed() -> None:
    """``ui.fragment`` never refreshes: it stays transparent to the parent."""
    with render_isolated():
        tabs = ui.tabs()
        with tabs, ui.fragment():
            ui.tab("messages", label="FRAGMENT_TAB")
        assert "FRAGMENT_TAB" in str(tabs.render())


# ── The right form: the zone around the parent ─────────────────────────────
# Module level: the server finds a zone again by its function.

@refreshable
def z_tabs() -> None:
    reads()
    _tabs()


@refreshable
def z_stepper() -> None:
    reads()
    _stepper()


@refreshable
def z_accordion() -> None:
    reads()
    _accordion()


@refreshable
def z_tree() -> None:
    reads()
    _tree()


@refreshable
def z_breadcrumb() -> None:
    reads()
    _breadcrumb()


@refreshable
def z_toggle_group() -> None:
    reads()
    _toggle_group()


@refreshable
def z_resizable() -> None:
    reads()
    _resizable()


@refreshable
def z_scheduler() -> None:
    reads()
    _scheduler()


@refreshable
def z_form_field() -> None:
    reads()
    _form_field()


@refreshable
def z_sidebar_footer() -> None:
    """The one parent that only places: a zone stays inside it."""
    reads()
    with ui.sidebar_footer(name="Aïcha Benali", subtitle="Sales"):
        ui.sidebar_footer_item(label="Settings", icon_left="settings", href="/p")


def _sidebar() -> None:
    with ui.sidebar(collapsible="rail", open=True):
        ui.sidebar_title("MyCRM", icon="zap")
        with ui.sidebar_section(label="MENU"):
            ui.sidebar_item("Entry", icon="circle", href="/x")
        z_sidebar_footer()


RIGHT_FORM: dict[str, Callable[[], None]] = {
    "tabs": z_tabs, "stepper": z_stepper, "accordion": z_accordion, "tree": z_tree,
    "breadcrumb": z_breadcrumb, "toggle_group": z_toggle_group, "resizable": z_resizable,
    "scheduler": z_scheduler, "form_field": z_form_field, "sidebar": _sidebar,
}

for _name, _build in RIGHT_FORM.items():
    def _page(build=_build) -> None:
        build()
        ui.button("bump", on_click=bump, id="bump")
    _page.__name__ = _page.__qualname__ = f"page_{_name}"
    app.include(page(f"/{_name}")(_page))


_TRANSPORT = re.compile(r"^(hx-swap-oob|data-bz-h|data-bz-r)$")


def _normalized(el) -> str:
    """The node, attributes sorted, without what belongs to the transport
    alone — and without the icons' SVG, which the page inlines and a
    fragment does not."""
    for tpl in el.find_all("template", attrs={"shadowrootmode": True}):
        tpl.decompose()
    for node in [el, *el.find_all(True)]:
        node.attrs = {k: v for k, v in sorted(node.attrs.items()) if not _TRANSPORT.match(k)}
    return el.prettify()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _refreshed_alone(client: TestClient, zone_id: str):
    action_id = encode_action_id(bump)
    ts = str(int(time.time()))
    response = client.post(f"/_bretzel/action/{action_id}", headers={
        "X-Bz-Sig": sign_action(app.config._action_key, action_id, "", ts=ts, session_id=session_of(client)),
        "X-Bz-Ts": ts,
        # A fingerprint the browser cannot hold: the server cannot answer
        # with a diff, it renders the zone whole.
        HEADER_ZONES: f"{zone_id}:0000000000000000"}, data={"_args": ""})
    assert response.status_code == 200, response.text[:200]
    soup = BeautifulSoup(response.text, "lxml")
    # The out-of-band wrappers go; a ``bz-teleport`` template is content.
    for tpl in soup.find_all("template"):
        if not tpl.has_attr("bz-teleport"):
            tpl.unwrap()
    return soup.find(attrs={"bz-id": zone_id})


@pytest.mark.parametrize("name", sorted(RIGHT_FORM))
def test_the_zone_around_the_parent_refreshes_alone_to_the_byte(client, name: str) -> None:
    page_soup = BeautifulSoup(client.get(f"/{name}").text, "lxml")
    zone = page_soup.find(attrs={"bz-id": re.compile(r"^refresh_")})
    assert zone is not None, f"/{name} holds no zone: the probe is broken"
    fragment = _refreshed_alone(client, zone["bz-id"])
    assert fragment is not None, f"ui.{name}: the zone is missing from its own refresh"
    assert _normalized(fragment) == _normalized(zone), (
        f"ui.{name}: refreshed alone, the zone does not render what the page rendered"
    )


def test_the_comparison_bites() -> None:
    """Two different renders do not normalize to the same text — otherwise
    the byte comparison above would pass on anything."""
    a = BeautifulSoup('<div bz-id="z" class="x"><span>one</span></div>', "lxml").div
    b = BeautifulSoup('<div bz-id="z" class="x"><span>two</span></div>', "lxml").div
    assert _normalized(a) != _normalized(b)
