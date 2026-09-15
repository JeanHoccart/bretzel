"""Unit tests for :class:`bretzel.components.primitives.text.Text`."""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.text import Text
from bretzel.core.serialize import serialize

# ───────────────────────────────────────────────────────────────────────────
# Construction + content
# ───────────────────────────────────────────────────────────────────────────


class TestContent:
    def test_positional_content(self) -> None:
        with render_isolated():
            t = Text("Hello")
        out = serialize(t.render())
        assert ">Hello<" in out

    def test_default_tag_span(self) -> None:
        with render_isolated():
            t = Text("Hi")
        out = serialize(t.render())
        assert "<span" in out

    def test_custom_tag(self) -> None:
        with render_isolated():
            t = Text("Hi", tag="p")
        out = serialize(t.render())
        assert "<p" in out

    def test_html_content_escaped(self) -> None:
        with render_isolated():
            t = Text("<script>")
        out = serialize(t.render())
        assert "<script>" not in out
        assert "&lt;script&gt;" in out


# ───────────────────────────────────────────────────────────────────────────
# IS_CONTAINER=False — leaf semantics
# ───────────────────────────────────────────────────────────────────────────


class TestLeaf:
    def test_with_block_raises(self) -> None:
        with render_isolated():
            t = Text("Hi")
            with pytest.raises(TypeError, match="leaf"), t:
                pass


class TestComponentContent:
    """Text.content accepts a Component (universal contract). The
    inner component must render properly inside the <span> AND must
    NOT remain in the parent's _children (double-render risk)."""

    def test_component_content_renders_inner(self) -> None:
        from bretzel.components.primitives.icon import Icon

        with render_isolated():
            t = Text(Icon("save"))
        out = serialize(t.render())
        # The inner Icon renders as an <iconify-icon>.
        assert "iconify-icon" in out
        # No leaked Python repr.
        assert "object at 0x" not in out

    def test_component_content_detached_from_parent(self) -> None:
        from bretzel.components.layout.stack import VStack
        from bretzel.components.primitives.icon import Icon

        with render_isolated():
            with VStack() as stack:
                Text(Icon("save"))
            # Only the Text remains in the stack — the Icon was
            # adopted into the Text and detached.
            assert len(stack._children) == 1
            assert isinstance(stack._children[0], Text)


# ───────────────────────────────────────────────────────────────────────────
# Theme classes — modifiers compose
# ───────────────────────────────────────────────────────────────────────────


class TestModifiers:
    def test_root_class_emitted(self) -> None:
        with render_isolated():
            t = Text("Hi")
        out = serialize(t.render())
        assert 'class="leading-normal"' in out

    @pytest.mark.parametrize(
        ("size", "expected"),
        [
            ("xs", "text-xs"),
            ("sm", "text-sm"),
            ("md", "text-base"),
            ("lg", "text-lg"),
            ("xl", "text-xl"),
        ],
    )
    def test_size(self, size: str, expected: str) -> None:
        with render_isolated():
            t = Text("Hi", size=size)
        assert expected in serialize(t.render())

    @pytest.mark.parametrize(
        ("weight", "expected"),
        [
            ("normal", "font-normal"),
            ("medium", "font-medium"),
            ("semibold", "font-semibold"),
            ("bold", "font-bold"),
        ],
    )
    def test_weight(self, weight: str, expected: str) -> None:
        with render_isolated():
            t = Text("Hi", weight=weight)
        assert expected in serialize(t.render())

    def test_align_left(self) -> None:
        with render_isolated():
            t = Text("Hi", align="left")
        assert "text-left" in serialize(t.render())

    def test_italic(self) -> None:
        with render_isolated():
            t = Text("Hi", italic=True)
        assert "italic" in serialize(t.render())

    def test_truncate(self) -> None:
        with render_isolated():
            t = Text("Hi", truncate=True)
        assert "truncate" in serialize(t.render())

    def test_decoration_underline(self) -> None:
        with render_isolated():
            t = Text("Hi", decoration="underline")
        out = serialize(t.render())
        assert "underline" in out

    def test_color_falls_back_to_template(self) -> None:
        # No theme palette wired → template falls back to verbatim
        # color name (semantic colors render fine that way).
        with render_isolated():
            t = Text("Hi", color="primary")
        assert "text-(--bz-text)" in serialize(t.render())
        assert "bz-c-primary" in serialize(t.render())

    def test_user_classes_appended(self) -> None:
        with render_isolated():
            t = Text("Hi", classes="custom-class")
        assert "custom-class" in serialize(t.render())


# ───────────────────────────────────────────────────────────────────────────
# Composition with siblings
# ───────────────────────────────────────────────────────────────────────────


class TestComposition:
    def test_two_texts_distinct_ids(self) -> None:
        with render_isolated() as ctx:
            a = Text("A")
            b = Text("B")
        assert a.id != b.id
        assert a in ctx.root_children
        assert b in ctx.root_children
