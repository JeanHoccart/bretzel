"""``Card`` polymorphic root : ``<div>`` by default, ``<a>`` when ``href=``
is passed. Setting ``href=`` also auto-enables the hover lift affordance.
"""

from __future__ import annotations

from bretzel.components.base.testing import render_isolated
from bretzel.components.layout.card.card import Card
from bretzel.core.serialize import serialize


class TestCardHref:
    def test_default_renders_as_div(self) -> None:
        with render_isolated():
            rendered = Card().render()
        assert rendered.tag == "div"

    def test_href_swaps_root_to_anchor(self) -> None:
        with render_isolated():
            rendered = Card(href="/foo").render()
        assert rendered.tag == "a"
        assert rendered.attrs.get("href") == "/foo"

    def test_href_auto_enables_hoverable(self) -> None:
        """An anchor card without a hover affordance reads as static —
        ``href=`` flips ``hoverable`` on implicitly. Detected via the
        ``hover:`` Tailwind classes the theme injects."""
        with render_isolated():
            out = serialize(Card(href="/foo").render())
        assert "hover:" in out

    def test_explicit_hoverable_false_still_wins_over_href(self) -> None:
        """``hoverable=False`` explicit overrides the implicit
        ``href`` enable — the caller knows best."""
        with render_isolated():
            out = serialize(Card(href="/foo", hoverable=False).render())
        # The implicit auto-enable only fires when ``hoverable`` is None ;
        # an explicit False keeps the card flat.
        assert "hover:-translate-y" not in out

    def test_explicit_tag_kwarg_overrides_polymorphism(self) -> None:
        """If the caller passes ``tag="section"`` explicitly, the
        polymorphic <a>-swap doesn't fire (only fires when tag is the
        default ``div``)."""
        with render_isolated():
            rendered = Card(href="/foo", tag="section").render()
        assert rendered.tag == "section"
