"""Unit tests for :class:`bretzel.components.primitives.spinner.Spinner`."""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.spinner import Spinner
from bretzel.core.serialize import serialize


class TestStructure:
    def test_a11y_role_status_default_label(self) -> None:
        with render_isolated():
            s = Spinner()
            out = serialize(s.render())
        assert 'role="status"' in out
        assert 'aria-label="Loading"' in out

    def test_is_a_single_spinning_ring(self) -> None:
        with render_isolated():
            s = Spinner()
            out = serialize(s.render())
        # The one built-in look : a spinning ring, single element.
        assert "animate-spin" in out
        assert "rounded-full" in out
        assert out.count("<span") == 1


class TestTheme:
    @pytest.mark.parametrize(
        ("size", "expected"),
        [
            ("xs", "h-3 w-3"),
            ("sm", "h-4 w-4"),
            ("md", "h-5 w-5"),
            ("lg", "h-6 w-6"),
            ("xl", "h-8 w-8"),
        ],
    )
    def test_circular_size_classes(self, size: str, expected: str) -> None:
        with render_isolated():
            s = Spinner(size=size)
            out = serialize(s.render())
        assert expected in out

    def test_color_substitutes(self) -> None:
        with render_isolated():
            s = Spinner(color="success")
            out = serialize(s.render())
        assert "text-(--bz-text)" in out
        assert "bz-c-success" in out

    def test_default_color_is_current_for_inheritance(self) -> None:
        # Default ``color="current"`` lets the spinner inherit its
        # parent's text colour — the documented embedding convention
        # for visually subordinate components (mirrors Icon).
        with render_isolated():
            s = Spinner()
            out = serialize(s.render())
        # Le pont ``bz-c-current`` pose ``--bz-text: currentColor`` :
        # l'héritage passe par lui, plus par ``text-current``.
        assert "bz-c-current" in out
        # And no branded fallback like text-primary leaked in.
        assert "text-primary" not in out
