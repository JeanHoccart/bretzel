"""Unit tests for reactive ``name=`` on the Icon component."""

from __future__ import annotations

from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.icon import Icon
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class _IconState(ClientState, persist="memory"):
    glyph: str = field(default="save")


class TestStaticName:
    def test_literal_name_emits_static_icon_attr(self) -> None:
        with render_isolated():
            icon = Icon("trash-2")
        out = serialize(icon.render())
        assert 'icon="lucide:trash-2"' in out
        # No reactive directive on the static path.
        assert "bz-attr:icon=" not in out
        # ``name`` reactive_prop must not leak as an HTML attr.
        assert 'name="trash-2"' not in out

    def test_literal_full_form_passes_through(self) -> None:
        with render_isolated():
            icon = Icon("lucide:save")
        out = serialize(icon.render())
        assert 'icon="lucide:save"' in out


class TestReactiveName:
    def test_binding_emits_bz_attr_icon_directive(self) -> None:
        with render_isolated(), rendering_scope():
            state = _IconState()
            icon = Icon(state.glyph)
        out = serialize(icon.render())
        # V3 directive : drives live updates.
        assert "bz-attr:icon=\"$bz._resolveIcon($bz.state._IconState.default.glyph" in out
        # Static ``icon=`` SSR fallback : present so iconify-icon
        # renders a glyph between SSR and runtime boot. The binding's
        # underlying SSR value (``glyph: str = "save"``) resolves to
        # the full ``lucide:save`` form via the same ``_resolve_name``
        # lookup the static-name path uses.
        opening = out.split(">", 1)[0]
        assert ' icon="lucide:save"' in opening
        # ``name`` reactive_prop must not leak as an HTML attr nor as
        # its own bz-attr directive (we own the icon attribute on this
        # element via the bz-attr:icon directive ; the static ``icon=``
        # above is the SSR fallback, not ``name=``).
        assert 'name="' not in opening
        assert 'bz-attr:name' not in opening
        # Exactly one directive owns the icon attribute.
        assert opening.count('bz-attr:icon') == 1

    def test_binding_uses_default_set_in_resolve_call(self) -> None:
        with render_isolated(), rendering_scope():
            state = _IconState()
            icon = Icon(state.glyph)
        out = serialize(icon.render())
        # The second arg to $bz._resolveIcon is the default set —
        # ``lucide`` from the theme.
        assert "'lucide'" in out
        # Third arg is the default style — ``null`` for lucide (no
        # style suffix configured).
        assert "null)" in out
