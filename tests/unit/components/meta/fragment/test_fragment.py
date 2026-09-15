"""Unit tests for :class:`Fragment` — wrap-less container."""

from __future__ import annotations

import pytest

from bretzel.components.actions.button import Button
from bretzel.components.base.testing import render_isolated
from bretzel.components.layout.stack import HStack
from bretzel.components.meta.fragment.fragment import Fragment
from bretzel.components.primitives.text import Text
from bretzel.core.serialize import serialize
from bretzel.core.tree import FragmentNode


class TestFragmentBasics:
    def test_no_wrapping_tag_in_serialized_html(self) -> None:
        """A Fragment's children inline directly — no surrounding tag
        appears in the serialized output."""
        with render_isolated():
            f = Fragment()
            with f:
                Button("A")
                Button("B")
            out = serialize(f.render())
        # Two buttons concatenated, no wrapping element.
        assert out.count("<button") == 2
        # No fragment-like wrapper tag.
        assert "<fragment" not in out
        assert "<Fragment" not in out

    def test_render_returns_fragment_node(self) -> None:
        """``render()`` returns the tree-level :class:`FragmentNode`
        the serializer knows how to inline — not an :class:`Element`."""
        with render_isolated():
            f = Fragment()
            with f:
                Text("hi")
            rendered = f.render()
        assert isinstance(rendered, FragmentNode)

    def test_empty_fragment_serializes_to_empty_string(self) -> None:
        """No children → no output. Useful for conditional emit
        (``with ui.fragment(): … if cond …`` where cond stays False)."""
        with render_isolated():
            out = serialize(Fragment().render())
        assert out == ""


class TestFragmentComposition:
    def test_children_inline_into_parent_hstack(self) -> None:
        """The classic use case : a helper that wants to add multiple
        children to an outer layout without imposing its own wrapper."""
        with render_isolated():
            outer = HStack()
            with outer:
                with Fragment():
                    Button("A")
                    Button("B")
                Button("C")
            out = serialize(outer.render())
        # The HStack carries all 3 buttons as direct children — no
        # intermediate wrapper between hstack and buttons.
        # We assert structurally : 3 buttons inside ONE flex container.
        assert out.count("<button") == 3
        assert out.count("flex") >= 1
        # The first button "A" appears AFTER the hstack root open tag
        # and BEFORE any nested div / fragment marker that would
        # demote its siblings to a different level.
        a_idx = out.index(">A<")
        b_idx = out.index(">B<")
        c_idx = out.index(">C<")
        assert a_idx < b_idx < c_idx

    def test_nested_fragments_flatten_all_the_way(self) -> None:
        """Fragments inside Fragments still produce a flat children
        list — there's no "fragment of fragments" intermediate."""
        with render_isolated():
            outer = HStack()
            with outer:
                with Fragment():
                    Button("A")
                    with Fragment():
                        Button("B")
                        Button("C")
                    Button("D")
            out = serialize(outer.render())
        assert out.count("<button") == 4
        for label in ("A", "B", "C", "D"):
            assert f">{label}<" in out


class TestFragmentRejectsAttributeKwargs:
    """Fragment has no DOM element, so kwargs that would attach to one
    (``classes=``, ``id=``, ``role=``) are user errors — surface them
    instead of silently dropping."""

    def test_classes_kwarg_raises(self) -> None:
        with render_isolated():
            with pytest.raises(TypeError, match="no keyword arguments"):
                Fragment(classes="hidden")

    def test_id_kwarg_raises(self) -> None:
        with render_isolated():
            with pytest.raises(TypeError, match="no keyword arguments"):
                Fragment(id="foo")


class TestFragmentSurface:
    def test_is_container(self) -> None:
        assert Fragment.IS_CONTAINER is True

    def test_no_bindable_props(self) -> None:
        assert Fragment.BINDABLE_PROPS == ()

    def test_no_events(self) -> None:
        assert Fragment.EVENTS == ()
