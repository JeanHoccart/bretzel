"""Unit tests for the static class composition path.

The reactive-axes binding path ($bz.compose for variant / size / color)
was removed (mai 2026) — variant / size / color became design-time per
the BINDABLE_PROPS contract. Only static composition + the
``classes=binding`` extras path remain ; the latter is tested in
``test_classes_style_binding.py``.

This file now only verifies the static path (no binding on any axis).
"""

from __future__ import annotations

from bretzel.components.actions.button import Button
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize


class TestStatic:
    def test_no_binding_emits_static_class(self) -> None:
        with render_isolated():
            b = Button("Save", variant="ghost", color="success")
        out = serialize(b.render())
        # No reactive marker, the class= is a plain static string.
        assert ':class="$bz.compose(' not in out
        assert "text-(--bz-text)" in out  # ghost variant color subst landed
        assert "bz-c-success" in out  # ghost variant color subst landed
