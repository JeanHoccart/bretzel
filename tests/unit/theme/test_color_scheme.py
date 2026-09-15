"""Unit tests for :class:`bretzel.theme.ColorScheme`.

The ClientState mechanics are covered upstream in
``tests/unit/state/scopes/test_client.py`` — this file locks in the
``ColorScheme``-specific surface : the persist mode, the default
``mode``, and the JS emitted by ``toggle()`` / ``set()``.
"""

from __future__ import annotations

from bretzel.state.persistence.memory import MemoryBackend
from bretzel.state.registry import StateRegistry, use_registry
from bretzel.state.scopes.client import rendering_scope
from bretzel.theme import ColorScheme


def _with_registry():
    return use_registry(StateRegistry(MemoryBackend()))


class TestDeclaration:
    def test_persist_is_local(self) -> None:
        # The framework FOUC script + the runtime effect both rely on
        # localStorage as the source of truth. Drift would silently
        # break cold-load theme application.
        assert ColorScheme.__persist__ == "local"

    def test_default_mode_is_system(self) -> None:
        # First visit (no localStorage) follows the OS — the FOUC script
        # and the runtime effect both resolve ``"system"`` against
        # ``prefers-color-scheme``.
        with _with_registry():
            scheme = ColorScheme()
            assert scheme.mode == "system"


class TestToggleJs:
    def test_toggle_emits_flip_expression(self) -> None:
        with _with_registry(), rendering_scope():
            scheme = ColorScheme()
            js = scheme.toggle()
        # The toggle must ASSIGN the canonical binding path so the
        # runtime effect (00_index.js boot) picks up the mutation.
        assert js.startswith("$bz.state.ColorScheme.default.mode = ")
        # Both ends of the conditional must be present — a stray
        # truthy/falsy flip would leave us in non-canonical modes.
        assert "'dark'" in js
        assert "'light'" in js

    def test_toggle_decides_from_the_resolved_state(self) -> None:
        """It must NOT re-read the token it writes.

        ``mode`` has three values, the screen has two. Comparing the
        token made the first click a no-op for anyone starting in
        ``"system"`` on a dark OS — it wrote ``"dark"``, already the
        painted value. Fixed 2026-09-04 ; gated in
        ``tests/consistency/
        test_the_theme_flip_and_the_paint_share_one_resolution.py``.
        """
        with _with_registry(), rendering_scope():
            js = ColorScheme.toggle()
        target, _, decision = js.partition(" = ")
        assert target not in decision
        assert "$bz._isDark()" in decision

    def test_set_emits_assignment(self) -> None:
        with _with_registry(), rendering_scope():
            scheme = ColorScheme()
            js = scheme.set("dark")
        # Uses ClientBinding.set under the hood — path = value form.
        assert js == '$bz.state.ColorScheme.default.mode = "dark"'

    def test_set_quotes_arbitrary_values(self) -> None:
        with _with_registry(), rendering_scope():
            scheme = ColorScheme()
            js = scheme.set("high-contrast")
        # Apps can extend the mode beyond light/dark — the value must
        # round-trip through JSON quoting cleanly.
        assert '= "high-contrast"' in js


class TestClassLevelApi:
    """``ColorScheme`` is framework-owned : the coder drives it WITHOUT
    ever writing ``scheme = ColorScheme()``. ``set`` / ``toggle`` are
    class-level and resolve the ``default`` singleton internally."""

    def test_set_is_callable_on_the_class(self) -> None:
        with _with_registry(), rendering_scope():
            js = ColorScheme.set("dark")
        assert js == '$bz.state.ColorScheme.default.mode = "dark"'

    def test_set_system_is_the_third_state(self) -> None:
        with _with_registry(), rendering_scope():
            js = ColorScheme.set("system")
        assert js == '$bz.state.ColorScheme.default.mode = "system"'

    def test_toggle_is_callable_on_the_class(self) -> None:
        with _with_registry(), rendering_scope():
            js = ColorScheme.toggle()
        # 2-state (dark ⇄ light) even though "system" exists — a 3-state
        # cycle is the app's job via set(). The decision comes from what
        # is PAINTED (``$bz._isDark()``), not from the stored token.
        assert js == (
            "$bz.state.ColorScheme.default.mode = "
            "$bz._isDark() ? 'light' : 'dark'"
        )
