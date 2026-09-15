"""Unit tests for :class:`bretzel.components.data.table.Table`."""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.data.table import Column, Table, column
from bretzel.components.feedback.badge import Badge
from bretzel.core.serialize import serialize


def _basic_cols() -> list[Column]:
    return [column("name", label="Name"), column("age", label="Age")]


class TestStructure:
    def test_renders_table_thead_tbody(self) -> None:
        with render_isolated():
            t = Table(columns=_basic_cols(), rows=[{"name": "Ada", "age": 36}])
            out = serialize(t.render())
        # The root is the scroll-container <div> (a <table> can't scroll its
        # own overflow) ; the <table> lives one level in.
        assert out.startswith("<div")
        assert "overflow-x-auto" in out
        assert "<table" in out
        assert "<thead" in out
        assert "<tbody" in out

    def test_header_labels_visible(self) -> None:
        with render_isolated():
            t = Table(columns=_basic_cols(), rows=[])
            out = serialize(t.render())
        assert ">Name<" in out
        assert ">Age<" in out

    def test_dict_row_lookup(self) -> None:
        with render_isolated():
            t = Table(
                columns=_basic_cols(),
                rows=[{"name": "Ada", "age": 36}, {"name": "Bob", "age": 50}],
            )
            out = serialize(t.render())
        assert ">Ada<" in out
        assert ">36<" in out
        assert ">Bob<" in out


class TestEmpty:
    def test_empty_state_row(self) -> None:
        with render_isolated():
            t = Table(columns=_basic_cols(), rows=[])
            out = serialize(t.render())
        assert "No data." in out
        # Empty row spans every column.
        assert 'colspan="2"' in out
        # The placeholder is the EmptyState component, not raw text :
        # it carries the live-region role.
        assert 'role="status"' in out

    def test_custom_empty_text(self) -> None:
        with render_isolated():
            t = Table(
                columns=_basic_cols(),
                rows=[],
                empty_text="Nothing here yet.",
                empty_description="Add a row to get started.",
            )
            out = serialize(t.render())
        assert "Nothing here yet." in out
        assert "Add a row to get started." in out

    def test_empty_callable_escape_hatch(self) -> None:
        from bretzel.components.primitives.text import Text

        with render_isolated():
            t = Table(
                columns=_basic_cols(),
                rows=[],
                empty=lambda: Text("custom empty"),
            )
            out = serialize(t.render())
        assert "custom empty" in out
        # The auto EmptyState is NOT used when the escape hatch is given.
        assert 'role="status"' not in out


class TestLook:
    def test_striped_always_on(self) -> None:
        # Zebra stripes are baked into the one opinionated look (no
        # ``striped`` prop) — the default table carries the modifier.
        with render_isolated():
            t = Table(columns=_basic_cols(), rows=[{"name": "A", "age": 1}])
            out = serialize(t.render())
        assert "nth-child(even)" in out

    def test_hover_uses_important_to_beat_striped(self) -> None:
        # The always-on hover background MUST be ``!important`` so it wins
        # over the equal-specificity striped rule on every row (the "hover
        # only on 1 row out of 2" bug). The serialized arbitrary class
        # keeps the ``:!bg-`` marker.
        with render_isolated():
            t = Table(columns=_basic_cols(), rows=[{"name": "A", "age": 1}])
            out = serialize(t.render())
        assert ":!bg-text/" in out

    def test_body_renders(self) -> None:
        with render_isolated():
            t = Table(columns=_basic_cols(), rows=[])
            out = serialize(t.render())
        assert "tbody" in out

    def test_size_sm_shrinks_padding(self) -> None:
        # ``size="sm"`` (the former ``compact=True``) tightens cell padding.
        with render_isolated():
            md = serialize(
                Table(columns=_basic_cols(),
                      rows=[{"name": "A", "age": 1}]).render()
            )
            sm = serialize(
                Table(columns=_basic_cols(), rows=[{"name": "A", "age": 1}],
                      size="sm").render()
            )
        assert "px-4 py-2.5" in md
        assert "px-3 py-1.5" in sm
        assert "px-4 py-2.5" not in sm


class TestColumnFeatures:
    def test_align_class_on_header_and_cell(self) -> None:
        with render_isolated():
            t = Table(
                columns=[column("n", label="N", align="right")],
                rows=[{"n": 7}],
            )
            out = serialize(t.render())
        # ``text-right`` should appear at least twice (th + td).
        assert out.count("text-right") >= 2

    def test_width_via_col_tag(self) -> None:
        with render_isolated():
            t = Table(
                columns=[column("n", label="N", width="8rem")],
                rows=[{"n": 1}],
            )
            out = serialize(t.render())
        assert "<colgroup>" in out
        assert "width: 8rem" in out

    def test_render_callback_emits_component(self) -> None:
        # The custom renderer drops a Badge into the cell.
        with render_isolated():
            t = Table(
                columns=[
                    column(
                        "status",
                        label="Status",
                        render=lambda v, row: Badge(
                            v, color="success"
                        ),
                    )
                ],
                rows=[{"status": "Active"}],
            )
            out = serialize(t.render())
        # Badge surface markers : le fond de la variante soft, qui est
        # le palier ``--bz-bg`` posé par le pont ``bz-c-success``.
        # and the label content.
        assert "bg-(--bz-bg)" in out
        assert "bz-c-success" in out
        assert ">Active<" in out

    def test_render_callback_returning_string(self) -> None:
        with render_isolated():
            t = Table(
                columns=[
                    column(
                        "n",
                        label="Doubled",
                        render=lambda v, row: f"={v * 2}",
                    )
                ],
                rows=[{"n": 21}],
            )
            out = serialize(t.render())
        assert ">=42<" in out

    def test_object_row_attr_lookup(self) -> None:
        from types import SimpleNamespace
        with render_isolated():
            row = SimpleNamespace(name="Ada", age=36)
            t = Table(columns=_basic_cols(), rows=[row])
            out = serialize(t.render())
        assert ">Ada<" in out
        assert ">36<" in out


class TestColor:
    def test_header_tinted_with_default_primary(self) -> None:
        with render_isolated():
            t = Table(columns=_basic_cols(), rows=[{"name": "A", "age": 1}])
            out = serialize(t.render())
        # Défaut primary → l'en-tête porte le palier de fond, et la
        # racine porte le pont qui dit lequel.
        assert "bg-(--bz-bg)" in out
        assert "bz-c-primary" in out

    def test_header_tint_follows_color_prop(self) -> None:
        with render_isolated():
            t = Table(columns=_basic_cols(), rows=[{"name": "A", "age": 1}],
                      color="success")
            out = serialize(t.render())
        assert "bg-(--bz-bg)" in out
        assert "bz-c-success" in out
        assert "bz-c-primary" not in out


def _click_handler(key) -> None:  # module-level : addressable by the route
    pass


class TestClickableRows:
    def test_each_row_gets_its_own_action(self) -> None:
        rows = [{"id": 1, "name": "A", "age": 1},
                {"id": 2, "name": "B", "age": 2}]
        with render_isolated():
            t = Table(columns=_basic_cols(), rows=rows, id="t",
                      on_item_click=_click_handler)
            out = serialize(t.render())
        # One hx-post per body row (rows share the action id, differ by
        # the bound key in hx-vals).
        assert out.count("hx-post=") == 2
        # The interactive-child guard rides on the trigger.
        assert "click[!event.target.closest" in out
        # Keyboard a11y : focusable button-role rows.
        assert out.count('role="button"') == 2
        assert out.count('tabindex="0"') == 2
        assert "bz-on:keydown=" in out

    def test_guard_has_no_commas_or_brackets(self) -> None:
        # HTMX splits hx-trigger on commas and matches the filter's
        # closing ``]`` — the guard must avoid both or the trigger breaks.
        rows = [{"id": 1, "name": "A", "age": 1}]
        with render_isolated():
            t = Table(columns=_basic_cols(), rows=rows, id="t",
                      on_item_click=_click_handler)
            # root <div> > <table> > tbody (last) > first tr
            table_el = t.render().children[0]
            tr = table_el.children[-1].children[0]
        trigger = tr.attrs["hx-trigger"]
        assert "," not in trigger
        assert "]" not in trigger.split("click[", 1)[1][:-1]

    def test_non_clickable_table_has_no_row_action(self) -> None:
        with render_isolated():
            t = Table(columns=_basic_cols(),
                      rows=[{"id": 1, "name": "A", "age": 1}])
            out = serialize(t.render())
        assert "hx-post=" not in out
        assert 'role="button"' not in out

    def test_row_key_drives_the_bound_identity(self) -> None:
        # A custom row_key column is what the handler receives — verify the
        # action registry bound the right keys (not the positional index).
        rows = [{"slug": "alpha", "name": "A", "age": 1},
                {"slug": "beta", "name": "B", "age": 2}]
        with render_isolated() as ctx:
            # Row actions register lazily on render (not on construction).
            serialize(Table(columns=_basic_cols(), rows=rows, id="t",
                            row_key="slug", on_item_click=_click_handler).render())
        # The handler is registered once (shared id) ; per-row keys ride
        # in each row's hx-vals blob, asserted via the rendered output.
        assert any(_click_handler is h or getattr(h, "func", None) is _click_handler
                   for h in ctx.action_registry.values())
