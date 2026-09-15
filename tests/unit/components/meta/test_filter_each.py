"""``ui.filter_each`` — generates a per-row ``bz-show`` match expression
from a query binding + a text extractor (no hand-written JS)."""

from __future__ import annotations

from bretzel import ui
from bretzel.components.base.testing import render_isolated
from bretzel.render import serialize_html
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class Filter(ClientState):
    q: str = field(default="")


def _render(items, text):
    with render_isolated(), rendering_scope():
        box = ui.vstack()
        with box:
            f = Filter()
            for it in ui.filter_each(items, query=f.q, text=text):
                ui.text(str(it))
        return serialize_html(box)


def test_one_bz_show_per_item_referencing_the_query() -> None:
    html = _render(["Button", "Select", "Switch"], text=lambda s: s)
    assert html.count("bz-show") == 3
    assert "Filter.default.q" in html           # gated on the client signal


def test_text_extractor_is_baked_lowercased() -> None:
    html = _render([{"name": "Combobox"}], text=lambda i: i["name"])
    # the row's searchable string is fixed into the expression, lowercased
    assert "combobox" in html.lower()
    assert "indexof" in html.lower()            # contains-match


def test_empty_callable_renders_a_no_match_wrapper() -> None:
    with render_isolated(), rendering_scope():
        box = ui.vstack()
        with box:
            f = Filter()
            for it in ui.filter_each(["Button", "Input"], query=f.q,
                                     text=lambda s: s,
                                     empty=lambda: ui.text("nothing here")):
                ui.text(str(it))
        html = serialize_html(box)
    assert ".every(" in html                    # all-texts-exclude check
    assert "Filter.default.q" in html
    assert "nothing here" in html               # the empty content rendered


def test_no_empty_callable_means_no_extra_wrapper() -> None:
    # Two items, no empty= → exactly two row wrappers, no .every() guard.
    html = _render(["Button", "Input"], text=lambda s: s)
    assert html.count("bz-show") == 2
    assert ".every(" not in html
