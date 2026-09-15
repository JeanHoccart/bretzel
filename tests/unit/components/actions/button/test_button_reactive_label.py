"""Unit tests for reactive ``label`` on the Button component."""

from __future__ import annotations

from bretzel.components.actions.button import Button
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class _ButtonLabelState(ClientState, persist="memory"):
    label: str = field(default="Save")


class TestStaticLabel:
    def test_literal_label_emits_plain_text_node(self) -> None:
        with render_isolated():
            b = Button("Save")
        out = serialize(b.render())
        assert ">Save<" in out
        assert "bz-text" not in out  # no wrapper span for static labels

    def test_no_label_emits_no_text_node(self) -> None:
        with render_isolated():
            b = Button()
        out = serialize(b.render())
        # No text node, no span wrapper
        assert "bz-text" not in out


class TestComponentLabel:
    def test_text_component_as_label_renders_inner_component(self) -> None:
        """Passing a Component as label must render that component
        inside the button, NOT emit its Python ``__repr__`` as a
        string. Universal contract : every slot accepts
        ``str | ClientBinding | Component``."""
        from bretzel.components.primitives.text import Text

        with render_isolated():
            b = Button(Text("Custom", color="success", weight="bold"))
        out = serialize(b.render())
        # The inner Text rendered as a <span> ... not stringified.
        assert "<span" in out
        assert ">Custom<" in out
        # No leaked Python repr.
        assert "object at 0x" not in out
        assert "bretzel.components" not in out

    def test_component_label_is_detached_from_parent(self) -> None:
        """When the Text label is constructed inside a ``with``
        block, Button's __init__ must detach it via adopt_slot so
        the same instance never ends up rendered twice."""
        from bretzel.components.layout.stack import VStack
        from bretzel.components.primitives.text import Text

        with render_isolated():
            with VStack() as stack:
                Button(Text("Inner"))
            # Only the Button should remain as a direct child of the
            # VStack — the Text was adopted into the Button's label
            # slot and detached from the stack.
            assert len(stack._children) == 1
            assert isinstance(stack._children[0], Button)


class TestReactiveLabel:
    def test_binding_label_emits_span_with_bz_text(self) -> None:
        with render_isolated(), rendering_scope():
            state = _ButtonLabelState()
            b = Button(state.label)
        out = serialize(b.render())
        assert '<span bz-text="$bz.state._ButtonLabelState.default.label"' in out
        # The raw SSR string MUST NOT appear as a text node — the
        # runtime would otherwise render the SSR text and the reactive
        # value would overwrite it, creating a one-frame flash on mount.
        # emit_text_slot returns either a Text OR a span (mutually
        # exclusive) so the SSR ``Save`` should be absent.
        assert ">Save<" not in out


class _IconState(ClientState, persist="memory"):
    glyph: str = field(default="save")


class TestIconSlotsNotBindable:
    """``icon_left`` / ``icon_right`` are NOT in Button's BINDABLE_PROPS.
    The framework's Icon-wrapper auto-detection (``adopt_slot(icon_shortcut=True)``)
    still exists for components that opt-in to icon binding, but Button
    treats icons as design-time configuration. Passing a binding raises
    a clear ``ComponentUsageError`` at construction.
    """

    def test_icon_left_binding_raises(self) -> None:
        from bretzel.components.base import ComponentUsageError
        import pytest

        with render_isolated(), rendering_scope():
            state = _IconState()
            with pytest.raises(ComponentUsageError, match="icon_left is not bindable"):
                Button("Save", icon_left=state.glyph)

    def test_icon_right_binding_raises(self) -> None:
        from bretzel.components.base import ComponentUsageError
        import pytest

        with render_isolated(), rendering_scope():
            state = _IconState()
            with pytest.raises(ComponentUsageError, match="icon_right is not bindable"):
                Button("Save", icon_right=state.glyph)
