"""Smoke tests for the ``ui`` namespace exposed by the components package."""

from __future__ import annotations

from bretzel.components import Button, Flex, HStack, Text, VStack, ui
from bretzel.components.base.testing import render_isolated

# ───────────────────────────────────────────────────────────────────────────
# Surface — the five-component phase-1 set
# ───────────────────────────────────────────────────────────────────────────


class TestSurface:
    def test_text_alias(self) -> None:
        assert ui.text is Text

    def test_button_alias(self) -> None:
        assert ui.button is Button

    def test_layout_aliases(self) -> None:
        assert ui.flex is Flex
        assert ui.vstack is VStack
        assert ui.hstack is HStack


# ───────────────────────────────────────────────────────────────────────────
# Round-trip via the namespace
# ───────────────────────────────────────────────────────────────────────────


def test_renders_through_ui_namespace() -> None:
    with render_isolated(), ui.vstack(gap="lg") as outer:
        ui.text("Hello", size="xl")
        ui.button("Save")
    from bretzel.core.serialize import serialize

    out = serialize(outer.render())
    assert "flex-col" in out
    assert "gap-6" in out
    assert ">Hello<" in out
    assert ">Save<" in out
