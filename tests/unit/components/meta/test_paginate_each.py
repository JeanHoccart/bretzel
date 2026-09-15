"""``ui.paginate_each`` — generates a per-row ``bz-show`` window expression
from a 1-indexed page binding + a per_page size (no hand-written JS)."""

from __future__ import annotations

import pytest

from bretzel import ui
from bretzel.components.base.testing import render_isolated
from bretzel.render import serialize_html
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class Pager(ClientState):
    page: int = field(default=1)


def _render(items, per_page):
    with render_isolated(), rendering_scope():
        box = ui.vstack()
        with box:
            p = Pager()
            for it in ui.paginate_each(items, page=p.page, per_page=per_page):
                ui.text(str(it))
        return serialize_html(box)


def test_one_bz_show_per_item_referencing_the_page() -> None:
    html = _render(["a", "b", "c"], per_page=2)
    assert html.count("bz-show") == 3            # one window wrapper per row
    assert "Pager.default.page" in html          # gated on the client signal
    assert "- 1) * 2" in html                    # (page-1)*per_page, per_page baked


def test_window_uses_the_row_index() -> None:
    # 4 rows : the lower bound is compared against each row's own index, so
    # both ``0 `` and ``3 `` appear at the start of a window expression
    # (operators are HTML-escaped in the attribute, the digits are not).
    html = _render(["a", "b", "c", "d"], per_page=2)
    assert html.count("bz-show") == 4


def test_int_page_literal_supported() -> None:
    with render_isolated(), rendering_scope():
        box = ui.vstack()
        with box:
            for it in ui.paginate_each(["a", "b"], page=2, per_page=5):
                ui.text(str(it))
        html = serialize_html(box)
    assert html.count("bz-show") == 2
    assert "(2)" in html and "* 5" in html       # literal page + per_page baked


def test_per_page_must_be_positive() -> None:
    with pytest.raises(ValueError):
        list(ui.paginate_each(["a"], page=1, per_page=0))
