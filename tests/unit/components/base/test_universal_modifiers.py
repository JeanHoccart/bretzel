"""Unit tests for the universal ``visible`` / ``tooltip`` modifiers
applied by :class:`bretzel.components.base.component._ComponentMeta`.
"""

from __future__ import annotations

from bretzel.components.actions.button import Button
from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.text import Text
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class _UIState(ClientState, persist="memory"):
    show:    bool = field(default=True)
    hint:    str  = field(default="initial hint")


# ── visible ────────────────────────────────────────────────────────────


class TestVisible:
    def test_visible_true_is_default_render(self) -> None:
        with render_isolated():
            b = Button("Save", visible=True)
        out = serialize(b.render())
        assert ">Save<" in out

    def test_visible_none_is_default_render(self) -> None:
        with render_isolated():
            b = Button("Save")
        out = serialize(b.render())
        assert ">Save<" in out

    def test_visible_false_skips_render_entirely(self) -> None:
        # Literal False → empty Fragment, nothing in the output.
        with render_isolated():
            b = Button("Save", visible=False)
        out = serialize(b.render())
        assert "Save" not in out
        assert out == ""

    def test_visible_client_binding_adds_bz_show(self) -> None:
        with render_isolated(), rendering_scope():
            state = _UIState()
            b = Button("Save", visible=state.show)
        out = serialize(b.render())
        # The button itself still renders (SSR fallback honours
        # state.show = True), but it carries a bz-show on its root
        # so the runtime can hide it client-side when the binding
        # flips. Truthy SSR value → no display:none pre-stamp.
        assert ">Save<" in out
        assert 'bz-show="$bz.state._UIState.default.show"' in out
        assert "display:none" not in out

    def test_visible_on_a_text_primitive(self) -> None:
        # Works on leaf primitives too — same metaclass wrap.
        with render_isolated():
            t = Text("hello", visible=False)
        assert serialize(t.render()) == ""


# ── tooltip ────────────────────────────────────────────────────────────


class TestTooltip:
    def test_tooltip_none_is_default_render(self) -> None:
        with render_isolated():
            b = Button("Save")
        out = serialize(b.render())
        assert 'role="tooltip"' not in out

    def test_tooltip_empty_string_is_default_render(self) -> None:
        with render_isolated():
            b = Button("Save", tooltip="")
        out = serialize(b.render())
        assert 'role="tooltip"' not in out

    def test_tooltip_static_text_wraps_in_tooltip(self) -> None:
        with render_isolated():
            b = Button("Save", tooltip="Save your work")
        out = serialize(b.render())
        # A Tooltip wrapper appears around the button — role + the
        # tooltip text node.
        assert 'role="tooltip"' in out
        assert "Save your work" in out
        # The wrapped button is still in the output as the trigger.
        assert ">Save<" in out

    def test_tooltip_client_binding_emits_bz_text(self) -> None:
        with render_isolated(), rendering_scope():
            state = _UIState()
            b = Button("Save", tooltip=state.hint)
        out = serialize(b.render())
        assert 'role="tooltip"' in out
        # Panel text is rendered as a bz-text span, not a literal.
        assert 'bz-text="$bz.state._UIState.default.hint"' in out
        # The SSR fallback "initial hint" is NOT used as literal text —
        # it lives in the bz-patch envelope, the panel reads via bz-text.
        assert ">initial hint<" not in out


# ── combined : visible + tooltip ───────────────────────────────────────


class TestCombined:
    def test_visible_false_short_circuits_tooltip(self) -> None:
        # When visible=False kills the render, the tooltip wrap is
        # also skipped (Fragment has no element to wrap).
        with render_isolated():
            b = Button("Save", visible=False, tooltip="Should not appear")
        out = serialize(b.render())
        assert out == ""
        assert "Should not appear" not in out

    def test_visible_binding_plus_tooltip_both_apply(self) -> None:
        with render_isolated(), rendering_scope():
            state = _UIState()
            b = Button("Save", visible=state.show, tooltip="Save")
        out = serialize(b.render())
        # Both effects present : bz-show on the button + tooltip wrap.
        assert 'bz-show="$bz.state._UIState.default.show"' in out
        assert 'role="tooltip"' in out
