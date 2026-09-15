"""Unit tests for :class:`MetaTag` — ``<meta>`` head injector."""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.meta.meta_tag.meta_tag import MetaTag
from bretzel.core.serialize import serialize
from bretzel.core.tree import Element, FragmentNode as FragmentNode


class TestMetaTagWritesContext:
    def test_name_meta_appends_to_head_extras(self) -> None:
        with render_isolated() as ctx:
            MetaTag(name="description", content="Hello").render()
        assert len(ctx.head_extras) == 1
        elem = ctx.head_extras[0]
        assert isinstance(elem, Element)
        assert elem.tag == "meta"
        assert elem.attrs == {"name": "description", "content": "Hello"}

    def test_property_meta_for_open_graph(self) -> None:
        with render_isolated() as ctx:
            MetaTag(property="og:title", content="Dashboard").render()
        elem = ctx.head_extras[0]
        assert elem.attrs == {"property": "og:title", "content": "Dashboard"}

    def test_http_equiv_kebab_cased_in_attr(self) -> None:
        """Python ``http_equiv`` → HTML ``http-equiv`` (Bretzel norm
        for snake_case → kebab-case attribute mapping)."""
        with render_isolated() as ctx:
            MetaTag(
                http_equiv="refresh", content="30; url=/logout",
            ).render()
        elem = ctx.head_extras[0]
        assert "http-equiv" in elem.attrs
        assert elem.attrs["http-equiv"] == "refresh"

    def test_multiple_calls_all_appended(self) -> None:
        """No auto-dedup — every call adds a tag in source order."""
        with render_isolated() as ctx:
            MetaTag(name="description", content="A").render()
            MetaTag(property="og:title", content="B").render()
            MetaTag(name="twitter:card", content="summary").render()
        assert len(ctx.head_extras) == 3
        assert ctx.head_extras[0].attrs["name"] == "description"
        assert ctx.head_extras[1].attrs["property"] == "og:title"
        assert ctx.head_extras[2].attrs["name"] == "twitter:card"


class TestMetaTagSerialization:
    def test_renders_empty_in_body(self) -> None:
        """The body sees nothing — the tag is appended to head_extras
        only, and the render itself returns an empty FragmentNode."""
        with render_isolated():
            rendered = MetaTag(name="x", content="y").render()
        assert isinstance(rendered, FragmentNode)
        assert serialize(rendered) == ""

    def test_appended_element_serializes_to_meta_tag(self) -> None:
        """The Element pushed to head_extras serializes as a valid
        void ``<meta/>`` HTML tag."""
        with render_isolated() as ctx:
            MetaTag(name="description", content="Hi").render()
        out = serialize(ctx.head_extras[0])
        # ``meta`` is in VOID_ELEMENTS — self-closing form.
        assert out.startswith("<meta ")
        assert out.endswith("/>")
        assert 'name="description"' in out
        assert 'content="Hi"' in out


class TestMetaTagArgsValidation:
    def test_no_identifier_raises(self) -> None:
        with render_isolated():
            with pytest.raises(TypeError, match="exactly one of name="):
                MetaTag(content="Just content")

    def test_two_identifiers_raises(self) -> None:
        with render_isolated():
            with pytest.raises(TypeError, match="only ONE identifier"):
                MetaTag(name="a", property="og:b", content="X")

    def test_three_identifiers_raises(self) -> None:
        with render_isolated():
            with pytest.raises(TypeError, match="only ONE identifier"):
                MetaTag(
                    name="a",
                    property="og:b",
                    http_equiv="refresh",
                    content="X",
                )

    def test_non_string_content_raises(self) -> None:
        with render_isolated():
            with pytest.raises(TypeError, match="content must be a str"):
                MetaTag(name="x", content=123)  # type: ignore[arg-type]

    def test_unknown_kwarg_rejected(self) -> None:
        with render_isolated():
            with pytest.raises(TypeError, match="got extras"):
                MetaTag(
                    name="x",
                    content="y",
                    classes="hidden",  # type: ignore[call-arg]
                )


class TestMetaTagOutsideRenderScope:
    def test_render_outside_scope_raises(self) -> None:
        with render_isolated():
            t = MetaTag(name="x", content="y")
        with pytest.raises(RuntimeError, match="render scope"):
            t.render()


class TestMetaTagSurface:
    def test_not_container(self) -> None:
        assert MetaTag.IS_CONTAINER is False

    def test_no_bindable_props(self) -> None:
        assert MetaTag.BINDABLE_PROPS == ()

    def test_no_events(self) -> None:
        assert MetaTag.EVENTS == ()
