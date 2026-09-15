"""``ui.limit_each`` (first-N client iteration) + ``ui.show_more``
(limit_each + a reveal button)."""

from __future__ import annotations

import pytest

from bretzel import ui
from bretzel.components.base.testing import render_isolated
from bretzel.render import serialize_html
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class Reveal(ClientState):
    count: int = field(default=2)


def test_limit_each_one_bz_show_per_item_referencing_the_limit() -> None:
    with render_isolated(), rendering_scope():
        box = ui.vstack()
        with box:
            r = Reveal()
            for it in ui.limit_each(["a", "b", "c"], limit=r.count):
                ui.text(str(it))
        html = serialize_html(box)
    assert html.count("bz-show") == 3
    assert "Reveal.default.count" in html        # gated on the client signal


def test_limit_each_int_literal() -> None:
    with render_isolated(), rendering_scope():
        box = ui.vstack()
        with box:
            for it in ui.limit_each(["a", "b"], limit=1):
                ui.text(str(it))
        html = serialize_html(box)
    assert html.count("bz-show") == 2
    assert "(1)" in html                          # the literal cap baked


def test_show_more_drops_a_reveal_button_after_the_rows() -> None:
    with render_isolated(), rendering_scope():
        box = ui.vstack()
        with box:
            r = Reveal()
            for it in ui.show_more(["a", "b", "c"], count=r.count, step=2):
                ui.text(str(it))
        html = serialize_html(box)
    # 3 row wrappers + 1 button wrapper, all carrying a bz-show
    assert html.count("bz-show") == 4
    assert "Show more" in html
    assert "bz-on:click" in html                  # the increment is wired
    # rows reference the count, and so does the button (visible + increment)
    assert html.count("Reveal.default.count") >= 4


def test_show_more_requires_a_binding_count() -> None:
    with pytest.raises(TypeError):
        list(ui.show_more(["a"], count=5))
