"""Unit tests for ``bretzel.core.serialize``."""

from __future__ import annotations

import pytest

from bretzel.core.serialize import VOID_ELEMENTS, serialize
from bretzel.core.tree import Element, FragmentNode, HtmlNode, Node, TextNode

# ───────────────────────────────────────────────────────────────────────────
# Element rendering
# ───────────────────────────────────────────────────────────────────────────


class TestElementSerialize:
    def test_empty_div(self) -> None:
        assert serialize(Element("div")) == "<div></div>"

    def test_with_attrs(self) -> None:
        out = serialize(Element("a", {"href": "/x", "class": "btn"}))
        assert out == '<a href="/x" class="btn"></a>'

    def test_with_children(self) -> None:
        node = Element("p", {}, (TextNode("hi"),))
        assert serialize(node) == "<p>hi</p>"

    def test_nested(self) -> None:
        node = Element(
            "div",
            {"id": "root"},
            (Element("span", {}, (TextNode("inside"),)),),
        )
        assert serialize(node) == '<div id="root"><span>inside</span></div>'


class TestVoidElements:
    def test_void_self_closing(self) -> None:
        assert serialize(Element("img", {"src": "x.png"})) == '<img src="x.png"/>'

    def test_void_no_attrs(self) -> None:
        assert serialize(Element("br")) == "<br/>"

    @pytest.mark.parametrize("tag", sorted(VOID_ELEMENTS))
    def test_each_void_renders_self_closing(self, tag: str) -> None:
        # No closing tag for any void element.
        out = serialize(Element(tag))
        assert out.endswith("/>")
        assert f"</{tag}>" not in out

    def test_void_void_set_is_html5_canonical(self) -> None:
        # Sanity check : the set matches the WHATWG HTML5 void list.
        assert "img" in VOID_ELEMENTS
        assert "br" in VOID_ELEMENTS
        assert "div" not in VOID_ELEMENTS
        assert "script" not in VOID_ELEMENTS


# ───────────────────────────────────────────────────────────────────────────
# TextNode rendering
# ───────────────────────────────────────────────────────────────────────────


class TestTextSerialize:
    def test_plain(self) -> None:
        assert serialize(TextNode("hello")) == "hello"

    def test_escapes_brackets(self) -> None:
        assert serialize(TextNode("<script>")) == "&lt;script&gt;"

    def test_escapes_ampersand(self) -> None:
        assert serialize(TextNode("a & b")) == "a &amp; b"

    def test_empty(self) -> None:
        assert serialize(TextNode("")) == ""


# ───────────────────────────────────────────────────────────────────────────
# HtmlNode (escape hatch)
# ───────────────────────────────────────────────────────────────────────────


class TestHtmlSerialize:
    def test_passthrough(self) -> None:
        # The documented escape hatch — payload emitted verbatim.
        raw = "<script>alert(1)</script>"
        assert serialize(HtmlNode(raw)) == raw

    def test_inside_element(self) -> None:
        node = Element("div", {}, (HtmlNode("<i>raw</i>"),))
        assert serialize(node) == "<div><i>raw</i></div>"


# ───────────────────────────────────────────────────────────────────────────
# FragmentNode
# ───────────────────────────────────────────────────────────────────────────


class TestFragmentSerialize:
    def test_empty(self) -> None:
        assert serialize(FragmentNode()) == ""

    def test_concatenates(self) -> None:
        assert serialize(FragmentNode((TextNode("a"), TextNode("b")))) == "ab"

    def test_no_wrapper_emitted(self) -> None:
        node = Element(
            "ul",
            {},
            (FragmentNode((Element("li", {}, (TextNode("a"),)), Element("li", {}, (TextNode("b"),)))),),
        )
        assert serialize(node) == "<ul><li>a</li><li>b</li></ul>"


# ───────────────────────────────────────────────────────────────────────────
# Error handling
# ───────────────────────────────────────────────────────────────────────────


class TestUnknownNode:
    def test_raises_typeerror(self) -> None:
        class Mystery(Node):
            __slots__ = ()

        with pytest.raises(TypeError, match="Mystery"):
            serialize(Mystery())


# ───────────────────────────────────────────────────────────────────────────
# Integration : a realistic page fragment
# ───────────────────────────────────────────────────────────────────────────


def test_realistic_card() -> None:
    node = Element(
        "article",
        {"class": "card", "data-id": "42"},
        (
            Element("h2", {}, (TextNode("Title <with> ampersand &"),)),
            Element(
                "p",
                {},
                (
                    TextNode("Visit "),
                    Element("a", {"href": "/x"}, (TextNode("link"),)),
                    TextNode(" for more."),
                ),
            ),
            HtmlNode("<!-- pre-rendered comment -->"),
            Element("img", {"src": "/img.png", "alt": "x"}),
        ),
    )
    expected = (
        '<article class="card" data-id="42">'
        "<h2>Title &lt;with&gt; ampersand &amp;</h2>"
        '<p>Visit <a href="/x">link</a> for more.</p>'
        "<!-- pre-rendered comment -->"
        '<img src="/img.png" alt="x"/>'
        "</article>"
    )
    assert serialize(node) == expected
