"""Unit tests for ``bretzel.core.tree``."""

from __future__ import annotations

import dataclasses

import pytest

from bretzel.core.tree import Element, FragmentNode, HtmlNode, Node, TextNode

# ───────────────────────────────────────────────────────────────────────────
# Element
# ───────────────────────────────────────────────────────────────────────────


class TestElement:
    def test_construct_minimal(self) -> None:
        el = Element("div")
        assert el.tag == "div"
        assert dict(el.attrs) == {}
        assert el.children == ()

    def test_default_normalisation(self) -> None:
        # Spec invariant : Element("div") == Element("div", attrs={}, children=()).
        assert Element("div") == Element("div", attrs={}, children=())

    def test_equality_recursive(self) -> None:
        a = Element("div", {"class": "x"}, (TextNode("hi"),))
        b = Element("div", {"class": "x"}, (TextNode("hi"),))
        assert a == b

    def test_inequality_on_attr_value(self) -> None:
        assert Element("div", {"class": "a"}) != Element("div", {"class": "b"})

    def test_inequality_on_tag(self) -> None:
        assert Element("div") != Element("span")

    def test_hashable(self) -> None:
        # The spec requires Element instances to be usable as dict keys / set members.
        s = {Element("div", {"class": "x"}, (TextNode("hi"),))}
        assert Element("div", {"class": "x"}, (TextNode("hi"),)) in s

    def test_hash_matches_equality(self) -> None:
        a = Element("p", {"id": "x"}, ())
        b = Element("p", {"id": "x"}, ())
        assert hash(a) == hash(b)

    def test_hash_differs_on_change(self) -> None:
        # Not strictly required, but a sane invariant.
        a = Element("p", {"id": "x"}, ())
        b = Element("p", {"id": "y"}, ())
        assert hash(a) != hash(b)

    def test_frozen_rejects_mutation(self) -> None:
        el = Element("div")
        with pytest.raises(dataclasses.FrozenInstanceError):
            el.tag = "span"  # type: ignore[misc]

    def test_attrs_order_preserved(self) -> None:
        el = Element("input", {"type": "text", "name": "q", "value": ""})
        assert list(el.attrs.keys()) == ["type", "name", "value"]


# ───────────────────────────────────────────────────────────────────────────
# TextNode / HtmlNode / FragmentNode
# ───────────────────────────────────────────────────────────────────────────


class TestText:
    def test_construct(self) -> None:
        t = TextNode("hello")
        assert t.content == "hello"

    def test_empty(self) -> None:
        assert TextNode("").content == ""

    def test_equality(self) -> None:
        assert TextNode("a") == TextNode("a")
        assert TextNode("a") != TextNode("b")

    def test_frozen(self) -> None:
        t = TextNode("hello")
        with pytest.raises(dataclasses.FrozenInstanceError):
            t.content = "bye"  # type: ignore[misc]

    def test_hashable(self) -> None:
        assert {TextNode("a"), TextNode("a")} == {TextNode("a")}


class TestHtml:
    def test_construct(self) -> None:
        h = HtmlNode("<b>raw</b>")
        assert h.html == "<b>raw</b>"

    def test_distinct_from_text(self) -> None:
        # Different node types even with structurally identical payloads.
        assert HtmlNode("hi") != TextNode("hi")

    def test_frozen(self) -> None:
        h = HtmlNode("x")
        with pytest.raises(dataclasses.FrozenInstanceError):
            h.html = "y"  # type: ignore[misc]


class TestFragment:
    def test_default_empty(self) -> None:
        f = FragmentNode()
        assert f.children == ()

    def test_construct_with_children(self) -> None:
        f = FragmentNode((TextNode("a"), TextNode("b")))
        assert f.children == (TextNode("a"), TextNode("b"))

    def test_equality(self) -> None:
        assert FragmentNode((TextNode("a"),)) == FragmentNode((TextNode("a"),))

    def test_frozen(self) -> None:
        f = FragmentNode((TextNode("a"),))
        with pytest.raises(dataclasses.FrozenInstanceError):
            f.children = ()  # type: ignore[misc]

    def test_hashable(self) -> None:
        s = {FragmentNode((TextNode("a"),))}
        assert FragmentNode((TextNode("a"),)) in s


# ───────────────────────────────────────────────────────────────────────────
# Cross-type behaviour
# ───────────────────────────────────────────────────────────────────────────


class TestNodeHierarchy:
    @pytest.mark.parametrize(
        "node",
        [
            Element("div"),
            TextNode("hi"),
            HtmlNode("<b>x</b>"),
            FragmentNode(),
        ],
    )
    def test_subclass_of_node(self, node: Node) -> None:
        assert isinstance(node, Node)

    def test_nested_tree_equality(self) -> None:
        a = Element(
            "div",
            {"class": "card"},
            (
                Element("h1", {}, (TextNode("Hello"),)),
                FragmentNode((TextNode("a"), TextNode("b"))),
                HtmlNode("<hr/>"),
            ),
        )
        b = Element(
            "div",
            {"class": "card"},
            (
                Element("h1", {}, (TextNode("Hello"),)),
                FragmentNode((TextNode("a"), TextNode("b"))),
                HtmlNode("<hr/>"),
            ),
        )
        assert a == b
        assert hash(a) == hash(b)
