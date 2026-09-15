"""Unit tests for reactive ``loading`` structural mutex on Button."""

from __future__ import annotations

from bretzel.components.actions.button import Button
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class _LoadingState(ClientState, persist="memory"):
    loading: bool = field(default=False)


class TestStaticLoading:
    def test_loading_false_no_spinner(self) -> None:
        with render_isolated():
            b = Button("Save", icon_left="save", loading=False)
        out = serialize(b.render())
        # The icon renders (iconify-icon present).
        assert "iconify-icon" in out
        # No spinner.
        assert "animate-spin" not in out
        # No bz-show wiring on the icon — static path.
        assert "bz-show" not in out

    def test_loading_true_spinner_only(self) -> None:
        with render_isolated():
            b = Button("Save", icon_left="save", loading=True)
        out = serialize(b.render())
        # Spinner present.
        assert "animate-spin" in out
        # icon_left replaced by spinner at SSR-time → no iconify-icon
        # for the icon slot in this branch.
        assert out.count("iconify-icon") == 0


class TestReactiveLoading:
    def test_binding_loading_emits_both_with_mutex(self) -> None:
        with render_isolated(), rendering_scope():
            state = _LoadingState()
            b = Button("Save",
                       icon_left="save",
                       icon_right="arrow-right",
                       loading=state.loading)
        out = serialize(b.render())
        # Spinner present.
        assert "animate-spin" in out
        # Both icons rendered too (mutex toggles them). ``iconify-icon``
        # is a custom element ; the substring appears once per opening
        # tag — count opening tags to assert "2 icons present".
        assert out.count("<iconify-icon") == 2
        # Spinner shows when loading is true (V3 bz-show directive).
        assert 'bz-show="$bz.state._LoadingState.default.loading"' in out
        # icon_left + icon_right show when loading is FALSE.
        assert 'bz-show="!$bz.state._LoadingState.default.loading"' in out
        # FOUC pre-stamp (V3 replacement for x-cloak) : the spinner's
        # initial evaluation is falsy (loading starts False) so the
        # server pre-stamps ``display:none`` before the runtime's
        # first effect takes over.
        assert 'style="display:none"' in out

    def test_binding_loading_no_icons_still_emits_spinner(self) -> None:
        # When loading binds but no icons are passed, the spinner still
        # rides with bz-show (so the binding can flip it on).
        with render_isolated(), rendering_scope():
            state = _LoadingState()
            b = Button("Save", loading=state.loading)
        out = serialize(b.render())
        assert "animate-spin" in out
        assert 'bz-show="$bz.state._LoadingState.default.loading"' in out
