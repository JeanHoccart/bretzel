"""Card keeps ``overflow-hidden`` UNCONDITIONALLY — the auto-swap to
``overflow-visible`` (marker ``OVERFLOWS_CONTAINER``) was retired on
2026-07-15.

Rationale (probe ``tests/probes/probe_overflow_card.py``) : every
anchored panel (Select, Combobox, Dropdown, Popover, Tooltip, date
pickers) is repositioned ``position: fixed`` at open time by the
runtime's ``floating()`` helper, so it escapes the card's clip box
natively — the swap protected nothing and cost the card its
rounded-corner clipping whenever ANY descendant carried a ``tooltip=``.
The one case where clipping could still bite (the hover lift's
``translate`` turning the card into a containing block) was root-fixed
by moving the lift to a ``top`` offset — cf. traps.md § « Hover lift en
translate » and § « Card auto-swap (RETIRÉ) ».
"""

from __future__ import annotations

import pytest

from bretzel.components.actions.button import Button
from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.select.select import Select
from bretzel.components.layout.card.card import Card
from bretzel.components.overlay.dialog import Dialog
from bretzel.components.overlay.dropdown.dropdown import Dropdown
from bretzel.components.overlay.popover.popover import Popover
from bretzel.components.overlay.tooltip.tooltip import Tooltip
from bretzel.components.primitives.text import Text


def _card_class(build) -> str:
    with render_isolated():
        c = Card()
        with c:
            build()
        return c.render().attrs.get("class", "")


class TestOverflowAlwaysHidden:
    @pytest.mark.parametrize(
        "label, build",
        [
            ("plain", lambda: Text("plain content")),
            ("popover", lambda: Popover(trigger=Button("Open"))),
            ("dropdown", lambda: Dropdown(trigger=Button("Menu"))),
            ("select", lambda: Select(options=[("a", "A"), ("b", "B")])),
            ("dialog", lambda: Dialog(title="X")),
        ],
        ids=["plain", "popover", "dropdown", "select", "dialog"],
    )
    def test_card_always_keeps_overflow_hidden(self, label, build) -> None:
        cls = _card_class(build)
        assert "overflow-hidden" in cls, f"{label}: {cls!r}"
        assert "overflow-visible" not in cls, f"{label}: {cls!r}"

    def test_card_with_wrapped_tooltip_keeps_overflow_hidden(self) -> None:
        def build() -> None:
            with Tooltip("hint"):
                Button("Hover me")

        cls = _card_class(build)
        assert "overflow-hidden" in cls
        assert "overflow-visible" not in cls

    def test_marker_is_gone_from_the_component_contract(self) -> None:
        # Nobody re-introduces the marker quietly : neither the base
        # class nor a component may still declare it.
        from tests.consistency._discovery import public_component_classes

        offenders = [
            cls.__name__
            for cls in public_component_classes()
            if hasattr(cls, "OVERFLOWS_CONTAINER")
            or hasattr(cls, "_has_overflowing_descendant")
        ]
        assert not offenders, (
            f"OVERFLOWS_CONTAINER / _has_overflowing_descendant réintroduit "
            f"sur : {offenders} — le swap a été retiré le 2026-07-15, cf. "
            f"traps.md § « Card auto-swap (RETIRÉ) »."
        )


class TestHoverLiftIsTopBased:
    def test_hoverable_card_lift_uses_top_not_translate(self) -> None:
        # Un transform/translate ferait de la card le containing block
        # des panels fixed de ses descendants (panel détaché de 477px,
        # mesuré au probe). Le lift DOIT rester un offset de position.
        #
        # ``-top-px`` et non ``-top-0.5`` depuis le 2026-09-13 : un demi-cran
        # vaut 1,5 px à 3 px le pas, donc un demi-pixel que les navigateurs
        # arrondissent chacun à leur façon. Le lift d'une carte se mesure en
        # PIXELS, pas en crans d'échelle.
        with render_isolated():
            cls = Card(hoverable=True).render().attrs.get("class", "")
        assert "hover:-top-px" in cls
        assert "relative" in cls and "top-0" in cls
        assert "translate" not in cls, (
            f"le lift Card repasse en translate → containing block pour "
            f"les overlays ancrés (cf. traps.md § « Hover lift en "
            f"translate ») : {cls!r}"
        )
