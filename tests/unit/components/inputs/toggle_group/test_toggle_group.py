"""Unit tests for :class:`ToggleGroup` + :class:`ToggleButton`."""

from __future__ import annotations

import re

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.toggle_group.toggle_group import (
    ToggleButton,
    ToggleGroup,
)
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class _Picks(ClientState, persist="memory"):
    filter: str = field(default="active")
    formatting: list = field(default_factory=lambda: ["b", "i"])


# ── Shortcut API (options=) ───────────────────────────────────────────────


class TestOptionsShortcut:
    def test_single_renders_one_button_per_option(self) -> None:
        with render_isolated():
            out = serialize(
                ToggleGroup(
                    value="active",
                    options=[("all", "All"), ("active", "Active"),
                             ("done", "Done")],
                ).render()
            )
        assert out.count("<button") == 3
        for label in ("All", "Active", "Done"):
            assert f">{label}<" in out

    def test_rejects_three_tuple(self) -> None:
        with render_isolated():
            with pytest.raises(TypeError, match="2-tuple"):
                ToggleGroup(
                    options=[("b", "Bold", "bold")],
                )

    def test_rejects_non_tuple(self) -> None:
        with render_isolated():
            with pytest.raises(TypeError, match="2-tuple"):
                ToggleGroup(options=["bold"])


# ── Container API ────────────────────────────────────────────────────────


class TestContainerAPI:
    def test_with_block_picks_up_children(self) -> None:
        with render_isolated():
            g = ToggleGroup(value="b")
            with g:
                ToggleButton("a", "A")
                ToggleButton("b", "B")
                ToggleButton("c", "C")
            out = serialize(g.render())
        assert out.count("<button") == 3
        for label in ("A", "B", "C"):
            assert f">{label}<" in out

    def test_icons_emit_iconify(self) -> None:
        with render_isolated():
            g = ToggleGroup()
            with g:
                ToggleButton("b", "Bold",      icon="bold")
                ToggleButton("i", "Italic",    icon="italic")
                ToggleButton("u", "Underline", icon="underline")
            out = serialize(g.render())
        assert out.count("<iconify-icon") == 3

    def test_icon_only_button_omits_label(self) -> None:
        with render_isolated():
            g = ToggleGroup()
            with g:
                ToggleButton("a", None, icon="check")
            out = serialize(g.render())
        # The iconify-icon is there, but no text node for the label.
        assert "<iconify-icon" in out
        button_block = out[out.index("<button"):out.index("</button>")]
        text_after_icon = button_block.split("</iconify-icon>", 1)[1]
        assert ">" not in text_after_icon.replace("</button", "")

    def test_toggle_button_render_raises_outside_group(self) -> None:
        with render_isolated():
            t = ToggleButton("a", "A")
        with pytest.raises(RuntimeError, match="ToggleGroup"):
            t.render()


# ── Single visual identity : joined-button bar (no thumb) ────────────────


class TestVisual:
    def test_no_thumb_indicator_ever(self) -> None:
        """ToggleGroup has one visual contract — a joined-button bar.
        There is no sliding-thumb variant, so the ``data-toggle-indicator``
        element must never be emitted (single or multi)."""
        with render_isolated():
            single = serialize(
                ToggleGroup(
                    value="b",
                    options=[("a", "A"), ("b", "B"), ("c", "C")],
                ).render()
            )
            multi = serialize(
                ToggleGroup(
                    multiple=True,
                    value=["a"],
                    options=[("a", "A"), ("b", "B")],
                ).render()
            )
        assert "data-toggle-indicator" not in single
        assert "data-toggle-indicator" not in multi
        # No imperative-positioning machinery left over either.
        assert "updateIndicator" not in single
        assert "data-toggle-id" not in single


# ── Single vs multi click expressions ────────────────────────────────────


class TestClickExpressions:
    def test_single_click_assigns_picked(self) -> None:
        with render_isolated():
            out = serialize(
                ToggleGroup(
                    options=[("a", "A"), ("b", "B")],
                ).render()
            )
        # Single-mode click : ``picked = "a"``. In an HTML attribute
        # the ``=`` becomes ``=`` and ``"`` becomes ``&quot;``.
        assert "value = &quot;a&quot;" in out

    def test_multi_click_toggles_membership(self) -> None:
        with render_isolated():
            out = serialize(
                ToggleGroup(
                    multiple=True,
                    options=[("b", "Bold"), ("i", "Italic")],
                ).render()
            )
        assert ".includes(" in out
        assert ".filter(" in out

    def test_data_selected_uses_equality_in_single(self) -> None:
        with render_isolated():
            out = serialize(
                ToggleGroup(options=[("a", "A")]).render()
            )
        assert "value === &quot;a&quot;" in out

    def test_data_selected_uses_includes_in_multi(self) -> None:
        with render_isolated():
            out = serialize(
                ToggleGroup(
                    multiple=True,
                    options=[("a", "A")],
                ).render()
            )
        assert "value.includes(&quot;a&quot;)" in out


# ── SSR initial state (data-selected, aria-pressed, hidden value) ────────


class TestInitialState:
    def test_picked_initial_in_x_data(self) -> None:
        with render_isolated():
            out = serialize(
                ToggleGroup(
                    value="active",
                    options=[("all", "All"), ("active", "Active")],
                ).render()
            )
        # ``picked`` carries the SSR snapshot (escaped quotes in HTML).
        assert 'value: &quot;active&quot;' in out

    def test_multi_initial_value_in_x_data(self) -> None:
        with render_isolated():
            out = serialize(
                ToggleGroup(
                    multiple=True,
                    value=["b", "i"],
                    options=[("b", "B"), ("i", "I"), ("u", "U")],
                ).render()
            )
        assert "value: [&quot;b&quot;, &quot;i&quot;]" in out

    def test_default_multi_initial_is_empty_list(self) -> None:
        with render_isolated():
            out = serialize(
                ToggleGroup(
                    multiple=True,
                    options=[("a", "A")],
                ).render()
            )
        assert "value: []" in out

    def test_initial_selected_stamps_data_selected_true(self) -> None:
        """SSR initial state must put ``data-selected="true"`` on the
        right button so the active styling paints BEFORE Alpine boots
        (same idiom as Tabs)."""
        with render_isolated():
            out = serialize(
                ToggleGroup(
                    value="b",
                    options=[("a", "A"), ("b", "B"), ("c", "C")],
                ).render()
            )
        # The 'b' button gets ``data-selected="true"``, others false.
        buttons = re.findall(r"<button[^>]*>", out)
        a_btn = next(b for b in buttons if 'value="a"' in b)
        b_btn = next(b for b in buttons if 'value="b"' in b)
        assert 'data-selected="false"' in a_btn
        assert 'data-selected="true"' in b_btn

    def test_multi_initial_selected_stamps_each_picked(self) -> None:
        with render_isolated():
            out = serialize(
                ToggleGroup(
                    multiple=True,
                    value=["a", "c"],
                    options=[("a", "A"), ("b", "B"), ("c", "C")],
                ).render()
            )
        buttons = re.findall(r"<button[^>]*>", out)
        a_btn = next(b for b in buttons if 'value="a"' in b)
        b_btn = next(b for b in buttons if 'value="b"' in b)
        c_btn = next(b for b in buttons if 'value="c"' in b)
        assert 'data-selected="true"' in a_btn
        assert 'data-selected="false"' in b_btn
        assert 'data-selected="true"' in c_btn

    def test_aria_pressed_emitted_for_a11y(self) -> None:
        """Beyond the visual ``data-selected``, we keep the reactive
        ``aria-pressed`` binding so screen readers announce the toggle
        state correctly."""
        with render_isolated():
            out = serialize(
                ToggleGroup(options=[("a", "A")]).render()
            )
        assert ":aria-pressed=" in out


# ── Hidden input + form integration ──────────────────────────────────────


class TestHiddenInput:
    def test_name_passes_through_to_hidden_input(self) -> None:
        with render_isolated():
            out = serialize(
                ToggleGroup(
                    value="active",
                    options=[("active", "A")],
                    name="filter",
                ).render()
            )
        assert 'type="hidden"' in out
        assert 'name="filter"' in out

    def test_multi_hidden_input_uses_json_stringify(self) -> None:
        with render_isolated():
            out = serialize(
                ToggleGroup(
                    multiple=True,
                    value=["a"],
                    options=[("a", "A")],
                    name="picks",
                ).render()
            )
        assert "JSON.stringify(value)" in out

    def test_no_hidden_input_without_name_or_listener(self) -> None:
        with render_isolated():
            out = serialize(
                ToggleGroup(
                    options=[("a", "A")],
                ).render()
            )
        assert 'type="hidden"' not in out


# ── ClientBinding integration (AUTONAME_FROM=value) ──────────────────────


class TestBinding:
    def test_binding_path_used_in_expressions(self) -> None:
        with render_isolated(), rendering_scope():
            state = _Picks()
            out = serialize(
                ToggleGroup(
                    value=state.filter,
                    options=[("all", "All"), ("active", "Active")],
                ).render()
            )
        assert "$bz.state._Picks.default.filter" in out
        # No local ``picked`` in x-data — the binding owns truth.
        assert "value:" not in out

    def test_autoname_picks_field_name_for_hidden_input(self) -> None:
        with render_isolated(), rendering_scope():
            state = _Picks()
            out = serialize(
                ToggleGroup(
                    value=state.filter,
                    options=[("active", "A")],
                ).render()
            )
        assert 'name="filter"' in out


# ── Disabled ─────────────────────────────────────────────────────────────


class TestDisabled:
    def test_group_disabled_locks_all_buttons(self) -> None:
        with render_isolated():
            g = ToggleGroup(disabled=True)
            with g:
                ToggleButton("a", "A")
                ToggleButton("b", "B")
            out = serialize(g.render())
        button_blocks = re.findall(r"<button[^>]*>", out)
        assert len(button_blocks) == 2
        # ``disabled`` standalone attr (separated by spaces / =/ >).
        # Tailwind classes contain ``disabled:...`` so we check for
        # the attribute boundary specifically.
        for block in button_blocks:
            assert re.search(r"\sdisabled(?=[\s=>])", block)

    def test_per_item_disabled(self) -> None:
        with render_isolated():
            g = ToggleGroup()
            with g:
                ToggleButton("a", "A")
                ToggleButton("b", "B", disabled=True)
            out = serialize(g.render())
        button_blocks = re.findall(r"<button[^>]*>", out)
        def _has_disabled_attr(block: str) -> bool:
            return bool(re.search(r"\sdisabled(?=[\s=>])", block))
        assert not _has_disabled_attr(button_blocks[0])
        assert _has_disabled_attr(button_blocks[1])

    def test_disabled_binding_is_reactive_per_button(self) -> None:
        """``disabled=binding`` must propagate to every button as a
        reactive ``bz-attr:disabled`` so the runtime flips the HTML attr
        live when the binding mutates (truthy → attr present, falsy →
        removed). Without this, toggling the bound state has no visual
        effect."""
        with render_isolated(), rendering_scope():
            state = _Picks()
            g = ToggleGroup(
                value="a",
                disabled=state.filter,  # any bool-ish binding for the test
                options=[("a", "A"), ("b", "B")],
            )
            out = serialize(g.render())
        # Every button stamps the reactive directive referencing the
        # bound path (one per button — flipped in lockstep).
        assert out.count("bz-attr:disabled") == 2
        assert "$bz.state._Picks.default.filter" in out


# ── Imperative API ───────────────────────────────────────────────────────


class TestImperative:
    def test_set_via_binding_writes_through(self) -> None:
        with render_isolated(), rendering_scope():
            state = _Picks()
            g = ToggleGroup(
                value=state.filter,
                options=[("done", "Done")],
            )
        js = g.set("done")
        assert "$bz.state._Picks.default.filter" in js
        assert "done" in js

    def test_set_without_binding_dispatches_bz_set(self) -> None:
        with render_isolated():
            g = ToggleGroup(options=[("a", "A")])
        js = g.set("a")
        assert "bz-set" in js
        assert "a" in js

    def test_clear_single_emits_empty_string(self) -> None:
        with render_isolated():
            g = ToggleGroup(options=[("a", "A")])
        js = g.clear()
        assert '""' in js or "'" in js

    def test_clear_multi_emits_empty_array(self) -> None:
        with render_isolated():
            g = ToggleGroup(multiple=True, options=[("a", "A")])
        js = g.clear()
        assert "[]" in js

    def test_select_all_multi_only(self) -> None:
        with render_isolated():
            g = ToggleGroup(options=[("a", "A")])
        with pytest.raises(RuntimeError, match="multi-only"):
            g.select_all()

    def test_deselect_all_multi_only(self) -> None:
        with render_isolated():
            g = ToggleGroup(options=[("a", "A")])
        with pytest.raises(RuntimeError, match="multi-only"):
            g.deselect_all()

    def test_select_all_multi_dispatches_bz_command(self) -> None:
        with render_isolated():
            g = ToggleGroup(multiple=True, options=[("a", "A")])
        js = g.select_all()
        assert "bz-select-all" in js


# ── Surface ──────────────────────────────────────────────────────────────


class TestSurface:
    def test_bindable_props(self) -> None:
        assert set(ToggleGroup.BINDABLE_PROPS) == {"value", "disabled"}

    def test_events(self) -> None:
        assert set(ToggleGroup.EVENTS) == {"change", "focus", "blur"}

    def test_autoname_from(self) -> None:
        assert ToggleGroup.AUTONAME_FROM == "value"

    def test_is_container(self) -> None:
        assert ToggleGroup.IS_CONTAINER is True

    def test_toggle_button_no_events(self) -> None:
        assert ToggleButton.EVENTS == ()

    def test_toggle_button_bindable_disabled(self) -> None:
        assert ToggleButton.BINDABLE_PROPS == ("disabled",)


# ── Role + a11y ──────────────────────────────────────────────────────────


class TestA11y:
    def test_root_has_role_group(self) -> None:
        with render_isolated():
            out = serialize(
                ToggleGroup(options=[("a", "A")]).render()
            )
        assert 'role="group"' in out

    def test_buttons_have_data_selected_and_aria_pressed(self) -> None:
        """Both attributes are emitted reactively + statically :
        ``data-selected`` drives the Tailwind visual variant ;
        ``aria-pressed`` carries the same value for screen readers."""
        with render_isolated():
            out = serialize(
                ToggleGroup(options=[("a", "A")]).render()
            )
        assert ":data-selected=" in out
        assert ":aria-pressed=" in out
