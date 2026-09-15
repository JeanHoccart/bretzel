"""Unit tests for reactive label + href on the Link component."""

from __future__ import annotations

from bretzel.components.actions.link import Link
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class _LinkState(ClientState, persist="memory"):
    label: str = field(default="Docs")
    url: str = field(default="/docs")


class TestStaticLink:
    def test_literal_label_emits_text_node(self) -> None:
        with render_isolated():
            link = Link("Open", href="/x")
        out = serialize(link.render())
        assert ">Open<" in out
        # ``bz-text=`` : la DIRECTIVE, que le palier ``text-(--bz-text)``
        # ne fait que contenir en sous-chaîne.
        assert "bz-text=" not in out


class TestReactiveLink:
    def test_label_binding_emits_bz_text(self) -> None:
        with render_isolated(), rendering_scope():
            state = _LinkState()
            link = Link(state.label, href="/")
        out = serialize(link.render())
        assert 'bz-text="$bz.state._LinkState.default.label"' in out

    def test_href_binding_emits_bz_attr(self) -> None:
        with render_isolated(), rendering_scope():
            state = _LinkState()
            link = Link("Open", href=state.url)
        out = serialize(link.render())
        assert 'bz-attr:href="$bz.state._LinkState.default.url"' in out

    def test_disabled_link_drops_reactive_href(self) -> None:
        with render_isolated(), rendering_scope():
            state = _LinkState()
            link = Link("Open", href=state.url, disabled=True)
        out = serialize(link.render())
        assert "href=" not in out
        assert "bz-attr:href=" not in out
        assert 'aria-disabled="true"' in out
