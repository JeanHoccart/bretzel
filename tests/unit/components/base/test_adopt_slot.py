"""Unit tests for ``Component.adopt_slot`` covering string + binding + Component."""

from __future__ import annotations

from bretzel.components.base import Component
from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.icon import Icon
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class _IconSlotState(ClientState, persist="memory"):
    glyph: str = field(default="save")


class TestAdoptSlotIconShortcut:
    def test_string_wraps_into_icon(self) -> None:
        with render_isolated():
            wrapped = Component.adopt_slot("save", icon_shortcut=True)
            assert isinstance(wrapped, Icon)

    def test_client_binding_wraps_into_icon(self) -> None:
        with render_isolated(), rendering_scope():
            state = _IconSlotState()
            wrapped = Component.adopt_slot(state.glyph, icon_shortcut=True)
            assert isinstance(wrapped, Icon)

    def test_already_an_icon_flows_through(self) -> None:
        with render_isolated():
            original = Icon("trash-2")
            wrapped = Component.adopt_slot(original, icon_shortcut=True)
            # adopt_slot may return the SAME instance or a transparent
            # detached copy — either way it must still be an Icon.
            assert isinstance(wrapped, Icon)

    def test_none_flows_through(self) -> None:
        wrapped = Component.adopt_slot(None, icon_shortcut=True)
        assert wrapped is None
