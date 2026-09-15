"""Unit tests for ``bretzel.render.fusion``."""

from __future__ import annotations

from bretzel.core.tree import Element, FragmentNode, HtmlNode, TextNode
from bretzel.render.fusion import fuse_or_wrap
from bretzel.runtime.protocol import BZ_ID_ATTR

# ───────────────────────────────────────────────────────────────────────────
# Single root — splice attrs onto the existing element
# ───────────────────────────────────────────────────────────────────────────


class TestSingleRoot:
    def test_element_root_no_extra_div(self) -> None:
        # The hallmark v1 win we keep : single child = no wrapper.
        node = Element("section", {"class": "card"}, (TextNode("hi"),))
        out = fuse_or_wrap([node], bz_id="cs")
        assert out.tag == "section"
        assert out.attrs[BZ_ID_ATTR] == "cs"
        assert out.attrs["id"] == "cs"
        # Original cosmetic attrs survive.
        assert out.attrs["class"] == "card"
        # Children preserved.
        assert out.children == (TextNode("hi"),)

    def test_existing_bz_id_wraps_instead_of_splicing(self) -> None:
        # Components stamp their own bz-id during render — that's a
        # per-component morph identity, distinct from the refreshable
        # section id we're attaching here. Wrap so the inner id stays
        # intact below the section root.
        node = Element("div", {BZ_ID_ATTR: "inner"}, ())
        out = fuse_or_wrap([node], bz_id="section")
        assert out.tag == "div"
        assert out.attrs[BZ_ID_ATTR] == "section"
        assert out.children == (node,)
        # Inner identity preserved on the child element.
        assert out.children[0].attrs[BZ_ID_ATTR] == "inner"

    def test_extra_attrs_spliced_after_framework(self) -> None:
        node = Element("a", {"href": "/x"}, ())
        out = fuse_or_wrap(
            [node],
            bz_id="link",
            extra_attrs={"data-marker": "X"},
        )
        assert out.attrs["data-marker"] == "X"
        assert out.attrs["href"] == "/x"
        assert out.attrs[BZ_ID_ATTR] == "link"

    def test_extra_attrs_cannot_stomp_bz_id(self) -> None:
        node = Element("div")
        out = fuse_or_wrap(
            [node],
            bz_id="real",
            extra_attrs={BZ_ID_ATTR: "fake", "id": "fake-id"},
        )
        assert out.attrs[BZ_ID_ATTR] == "real"
        assert out.attrs["id"] == "real"


# ───────────────────────────────────────────────────────────────────────────
# Multi-root and non-Element — wrap in <div>
# ───────────────────────────────────────────────────────────────────────────


class TestWrap:
    def test_two_elements_wrapped(self) -> None:
        out = fuse_or_wrap(
            [Element("a"), Element("b")],
            bz_id="cs",
        )
        assert out.tag == "div"
        assert out.attrs[BZ_ID_ATTR] == "cs"
        assert out.attrs["id"] == "cs"
        assert out.children == (Element("a"), Element("b"))

    def test_text_only_wrapped(self) -> None:
        out = fuse_or_wrap([TextNode("hello")], bz_id="cs")
        assert out.tag == "div"
        assert out.children == (TextNode("hello"),)

    def test_html_only_wrapped(self) -> None:
        out = fuse_or_wrap([HtmlNode("<i>raw</i>")], bz_id="cs")
        assert out.tag == "div"
        assert out.children == (HtmlNode("<i>raw</i>"),)

    def test_empty_list_wrapped(self) -> None:
        out = fuse_or_wrap([], bz_id="cs")
        assert out.tag == "div"
        assert out.children == ()

    def test_custom_wrapper_tag(self) -> None:
        out = fuse_or_wrap(
            [TextNode("a"), TextNode("b")],
            bz_id="cs",
            wrapper_tag="section",
        )
        assert out.tag == "section"


# ───────────────────────────────────────────────────────────────────────────
# FragmentNode handling — flatten then apply rule
# ───────────────────────────────────────────────────────────────────────────


class TestFragments:
    def test_fragment_with_single_element_fuses(self) -> None:
        # FragmentNode dissolves : the contained Element is treated as the root.
        frag = FragmentNode((Element("p", {"class": "x"}, (TextNode("hi"),)),))
        out = fuse_or_wrap([frag], bz_id="cs")
        assert out.tag == "p"
        assert out.attrs["class"] == "x"
        assert out.attrs[BZ_ID_ATTR] == "cs"
        assert out.children == (TextNode("hi"),)

    def test_fragment_with_multi_root_wraps(self) -> None:
        frag = FragmentNode((Element("a"), Element("b")))
        out = fuse_or_wrap([frag], bz_id="cs")
        assert out.tag == "div"
        assert out.children == (Element("a"), Element("b"))

    def test_nested_fragments_flattened(self) -> None:
        inner = FragmentNode((Element("a"),))
        outer = FragmentNode((inner, Element("b")))
        out = fuse_or_wrap([outer], bz_id="cs")
        assert out.tag == "div"
        assert out.children == (Element("a"), Element("b"))

    def test_fragment_alongside_element_wraps(self) -> None:
        # Top-level [FragmentNode(...), Element(...)] → 2+ effective roots.
        out = fuse_or_wrap(
            [FragmentNode((Element("a"),)), Element("b")],
            bz_id="cs",
        )
        assert out.tag == "div"
        assert out.children == (Element("a"), Element("b"))


# ───────────────────────────────────────────────────────────────────────────
# Purity / immutability
# ───────────────────────────────────────────────────────────────────────────


class TestPurity:
    def test_does_not_mutate_input_element(self) -> None:
        node = Element("p", {"class": "x"})
        before_attrs = dict(node.attrs)
        fuse_or_wrap([node], bz_id="cs")
        # Frozen Element guarantees this, but spell it out anyway.
        assert dict(node.attrs) == before_attrs

    def test_returns_fresh_element(self) -> None:
        node = Element("div")
        out = fuse_or_wrap([node], bz_id="cs")
        assert out is not node

    def test_iterable_input(self) -> None:
        # Generator argument works (single iteration is enough).
        def gen() -> object:
            yield Element("a")
            yield Element("b")

        out = fuse_or_wrap(gen(), bz_id="cs")
        assert out.children == (Element("a"), Element("b"))
