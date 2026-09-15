"""Unit tests for ``Component.emit_text_slot``."""

from __future__ import annotations

from bretzel.components.actions.button import Button
from bretzel.components.base.testing import render_isolated
from bretzel.core.tree import Element, TextNode
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class _LabelState(ClientState, persist="memory"):
    label: str = field(default="Save")


def _emit(value):
    # Reuses Button as a concrete Component instance ; we only need a
    # bound subclass so emit_text_slot exists with a proper context.
    with render_isolated():
        btn = Button("placeholder")
        return btn.emit_text_slot(value)


class TestEmitTextSlot:
    def test_literal_string_returns_text_node(self) -> None:
        node = _emit("Hello")
        assert isinstance(node, TextNode)
        assert node.content == "Hello"

    def test_none_returns_none(self) -> None:
        assert _emit(None) is None

    def test_empty_string_returns_none(self) -> None:
        # Empty content is treated as absent — saves emitting empty spans.
        assert _emit("") is None

    def test_binding_returns_span_with_bz_text(self) -> None:
        with rendering_scope():
            state = _LabelState()
            node = _emit(state.label)
        assert isinstance(node, Element)
        assert node.tag == "span"
        assert node.attrs.get("bz-text") == "$bz.state._LabelState.default.label"
        assert node.children == ()


class TestEmitTextSlotExpression:
    def test_client_expression_uses_binding_path(self) -> None:
        # ``ClientExpression`` is a subclass of ``ClientBinding`` and
        # MUST take the ``binding_path()`` route — otherwise the
        # full ``$bz.state.…`` path gets re-prefixed into
        # ``$bz.state.$bz.state.…``.
        from bretzel.state.scopes.client import ClientExpression
        expr = ClientExpression("$bz.state.MyState.default.count + 1")
        with rendering_scope():
            node = _emit(expr)
        assert isinstance(node, Element)
        assert node.tag == "span"
        # No double prefix.
        assert node.attrs["bz-text"] == "$bz.state.MyState.default.count + 1"
        assert "$bz.state.$bz.state" not in node.attrs["bz-text"]

    def test_integer_literal_str_coerces(self) -> None:
        # ``str(value)`` cast preserved so non-string scalars don't
        # blow up at serialize time.
        node = _emit(42)
        assert isinstance(node, TextNode)
        assert node.content == "42"
