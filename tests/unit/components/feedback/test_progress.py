"""Unit tests for :class:`bretzel.components.feedback.progress.Progress`."""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.feedback.progress import Progress
from bretzel.core.serialize import serialize


class TestStructure:
    def test_role_progressbar(self) -> None:
        with render_isolated():
            p = Progress(value=50)
            out = serialize(p.render())
        assert 'role="progressbar"' in out

    def test_aria_value_attrs(self) -> None:
        with render_isolated():
            p = Progress(value=42)
            out = serialize(p.render())
        assert 'aria-valuemin="0"' in out
        assert 'aria-valuemax="100"' in out
        assert 'aria-valuenow="42"' in out


class TestDeterminate:
    @pytest.mark.parametrize(
        ("value", "max_v", "expected_pct"),
        [
            (0, 100, "0.0%"),
            (50, 100, "50.0%"),
            (100, 100, "100.0%"),
            (80, 200, "40.0%"),
        ],
    )
    def test_fill_width(self, value: float, max_v: float, expected_pct: str) -> None:
        with render_isolated():
            p = Progress(value=value, max=max_v)
            out = serialize(p.render())
        assert f"width: {expected_pct}" in out

    def test_overshoot_clamps_to_100(self) -> None:
        with render_isolated():
            p = Progress(value=999, max=100)
            out = serialize(p.render())
        assert "width: 100.0%" in out

    def test_negative_clamps_to_zero(self) -> None:
        with render_isolated():
            p = Progress(value=-10, max=100)
            out = serialize(p.render())
        assert "width: 0.0%" in out


class TestIndeterminate:
    def test_indeterminate_drops_aria_valuenow(self) -> None:
        with render_isolated():
            p = Progress(indeterminate=True)
            out = serialize(p.render())
        assert "aria-valuenow" not in out

    def test_indeterminate_uses_pulse_animation(self) -> None:
        with render_isolated():
            p = Progress(indeterminate=True)
            out = serialize(p.render())
        # The fill_indeterminate slot uses ``animate-pulse``.
        assert "animate-pulse" in out
        # No fixed width is written for the indeterminate fill.
        assert "width: " not in out


class TestLabel:
    def test_no_label_by_default(self) -> None:
        with render_isolated():
            p = Progress(value=50)
            out = serialize(p.render())
        assert ">50%<" not in out

    def test_show_label_emits_percentage(self) -> None:
        with render_isolated():
            p = Progress(value=42, show_label=True)
            out = serialize(p.render())
        assert ">42%<" in out

    def test_custom_label_overrides_percentage(self) -> None:
        with render_isolated():
            p = Progress(value=42, show_label=True, label="Loading…")
            out = serialize(p.render())
        assert ">Loading…<" in out
        assert ">42%<" not in out


class TestTheme:
    @pytest.mark.parametrize(
        ("size", "expected"),
        [("xs", "h-1"), ("sm", "h-1.5"), ("md", "h-2"), ("lg", "h-3")],
    )
    def test_size_classes(self, size: str, expected: str) -> None:
        with render_isolated():
            p = Progress(value=10, size=size)
            out = serialize(p.render())
        assert expected in out

    def test_color_substitutes(self) -> None:
        with render_isolated():
            p = Progress(value=50, color="success")
            out = serialize(p.render())
        assert "bg-(--bz-solid)" in out
        assert "bz-c-success" in out
