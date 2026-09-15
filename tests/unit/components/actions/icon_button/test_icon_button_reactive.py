"""Unit tests for IconButton reactive props (loading mutex + icon name)."""

from __future__ import annotations

from bretzel.components.actions.icon_button import IconButton
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class _IconButtonState(ClientState, persist="memory"):
    icon: str = field(default="save")
    loading: bool = field(default=False)


class TestReactiveIconName:
    def test_binding_icon_emits_bz_attr_directive(self) -> None:
        with render_isolated(), rendering_scope():
            state = _IconButtonState()
            ib = IconButton(state.icon, aria_label="Save")
        out = serialize(ib.render())
        assert "bz-attr:icon=\"$bz._resolveIcon($bz.state._IconButtonState.default.icon" in out


class TestStaticLoading:
    def test_loading_false_emits_icon_only(self) -> None:
        with render_isolated():
            ib = IconButton("save", aria_label="Save", loading=False)
        out = serialize(ib.render())
        # The icon renders.
        assert "iconify-icon" in out
        # No spinner.
        assert "animate-spin" not in out
        # No bz-show wiring on the icon — static path.
        assert "bz-show" not in out

    def test_loading_true_emits_spinner_only(self) -> None:
        with render_isolated():
            ib = IconButton("save", aria_label="Save", loading=True)
        out = serialize(ib.render())
        # Spinner present.
        assert "animate-spin" in out
        # No iconify-icon for the icon slot in this branch.
        assert "iconify-icon" not in out
        # No bz-show wiring — static path.
        assert "bz-show" not in out


class TestReactiveLoading:
    def test_binding_loading_emits_spinner_icon_mutex(self) -> None:
        with render_isolated(), rendering_scope():
            state = _IconButtonState()
            ib = IconButton("save", aria_label="Save", loading=state.loading)
        out = serialize(ib.render())
        # Both spinner AND icon are in the DOM.
        assert "animate-spin" in out
        assert out.count("<iconify-icon") == 1
        # Spinner shows when loading is true (V3 bz-show directive).
        assert 'bz-show="$bz.state._IconButtonState.default.loading"' in out
        # Icon shows when loading is FALSE.
        assert 'bz-show="!$bz.state._IconButtonState.default.loading"' in out
        # FOUC pre-stamp (V3 replacement for x-cloak) : the spinner's
        # initial evaluation is falsy (loading starts False) so the
        # server pre-stamps ``display:none``.
        assert 'style="display:none"' in out
