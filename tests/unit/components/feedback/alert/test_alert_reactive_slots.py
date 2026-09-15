"""Unit tests for reactive title / message / dismissible on Alert."""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.feedback.alert import Alert
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import ClientBinding, rendering_scope


class _AlertState(ClientState, persist="memory"):
    title: str = field(default="Heads up")
    message: str = field(default="Something happened")
    dismissible: bool = field(default=True)


class TestStaticAlert:
    def test_static_title_message_render_as_text(self) -> None:
        with render_isolated():
            a = Alert("Saved!", title="Done")
            out = serialize(a.render())
        assert ">Done<" in out
        assert ">Saved!<" in out
        # ``bz-text=`` : cf. la même note dans le test du Badge — le
        # palier ``text-(--bz-text)`` n'est pas la directive.
        assert "bz-text=" not in out


class TestReactiveAlert:
    def test_binding_title_emits_bz_text_span(self) -> None:
        with render_isolated(), rendering_scope():
            state = _AlertState()
            a = Alert("static-message", title=state.title)
            out = serialize(a.render())
        assert 'bz-text="$bz.state._AlertState.default.title"' in out
        # The literal "Heads up" SSR value must NOT appear as a text
        # node — emit_text_slot returns Text OR span, never both.
        assert ">Heads up<" not in out

    def test_binding_message_emits_bz_text_span(self) -> None:
        with render_isolated(), rendering_scope():
            state = _AlertState()
            a = Alert(state.message)
            out = serialize(a.render())
        assert 'bz-text="$bz.state._AlertState.default.message"' in out
        assert ">Something happened<" not in out

    def test_binding_dismissible_is_refused(self) -> None:
        # ``dismissible`` n'est plus bindable (règle « driver client, sinon
        # serveur » figée 2026-07-16 : la dismissabilité ne se toggle
        # quasi jamais en live → ∅). Un binding y lève ComponentUsageError.
        # La valeur littérale ``dismissible=True`` reste supportée.
        from bretzel.components.base.attrs import ComponentUsageError

        with render_isolated(), rendering_scope():
            with pytest.raises(ComponentUsageError):
                Alert("hi", dismissible=_AlertState().dismissible)
