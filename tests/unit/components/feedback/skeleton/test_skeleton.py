"""Smoke tests for :class:`Skeleton` — loading placeholder block."""

from __future__ import annotations

from bretzel.components.base.testing import render_isolated
from bretzel.components.feedback.skeleton.skeleton import Skeleton
from bretzel.core.serialize import serialize


class TestSkeleton:
    def test_default_emits_rectangle_variant(self) -> None:
        with render_isolated():
            out = serialize(Skeleton().render())
        assert "<span" in out
        assert 'aria-hidden="true"' in out
        assert "animate-pulse" in out

    def test_circle_variant_renders_round(self) -> None:
        with render_isolated():
            out = serialize(Skeleton(variant="circle").render())
        # Theme injects ``rounded-full`` on circle variant.
        assert "rounded-full" in out

    def test_text_variant_renders_thin_bar(self) -> None:
        with render_isolated():
            out = serialize(Skeleton(variant="text").render())
        # Text variant carries a typical line-height class.
        assert "h-4" in out or "h-3" in out

    def test_animated_false_drops_pulse(self) -> None:
        with render_isolated():
            out = serialize(Skeleton(animated=False).render())
        assert "animate-pulse" not in out

    def test_width_height_inline_style(self) -> None:
        with render_isolated():
            out = serialize(
                Skeleton(width="80px", height="2rem").render()
            )
        assert "width: 80px" in out
        assert "height: 2rem" in out

    def test_no_bindable_props(self) -> None:
        assert Skeleton.BINDABLE_PROPS == ()
