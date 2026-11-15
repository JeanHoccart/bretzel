"""``ui.card(variant=…)`` and ``ui.card(active=…)`` (2026-11-14).

``solid`` is the card it always was; ``ghost`` is a row of a list — no
background, border or shadow, a hover background instead of a lift when it
acts, and a focus ring drawn inside. ``active=True`` marks the chosen row.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.layout.card.card import Card
from bretzel.state import ClientBinding


def _act() -> None:
    """A module-level handler: the framework refuses a lambda."""


def _attrs(**kwargs):
    with render_isolated():
        return Card(**kwargs).render().attrs


def _classes(**kwargs) -> list[str]:
    return _attrs(**kwargs)["class"].split()


def test_solid_is_the_default_and_unchanged() -> None:
    assert _attrs()["class"] == (
        "block w-full rounded-box overflow-hidden bg-(--bz-solid) "
        "text-(--bz-on-solid) border-(length:--bz-stroke) border-line "
        "p-(--bz-pad-4) sm:p-(--bz-pad-6) bz-c-surface"
    )
    assert _attrs(variant="solid")["class"] == _attrs()["class"]


def test_a_ghost_card_draws_no_box() -> None:
    classes = _classes(variant="ghost")
    assert "bg-transparent" in classes
    assert not [c for c in classes if c.startswith(("border", "shadow", "bg-(--bz"))]
    assert not [c for c in classes if c.startswith("hover:")]


@pytest.mark.parametrize("kwargs", [{"on_click": _act}, {"href": "/inbox"}])
def test_a_ghost_card_that_acts_lights_up_without_lifting(kwargs: dict) -> None:
    classes = _classes(variant="ghost", **kwargs)
    assert "hover:bg-hover" in classes
    assert not [c for c in classes if "top" in c or "shadow" in c]
    assert "focus-visible:ring-inset" in classes
    assert "focus-visible:ring-offset-2" not in classes


def test_a_ghost_card_honours_an_explicit_hoverable() -> None:
    assert "hover:bg-hover" not in _classes(variant="ghost", on_click=_act, hoverable=False)
    assert "hover:bg-hover" in _classes(variant="ghost", hoverable=True)


def test_active_marks_the_chosen_element() -> None:
    attrs = _attrs(variant="ghost", on_click=_act, active=True)
    assert attrs["data-active"] == "true"
    assert attrs["aria-current"] == "true"
    assert "data-[active=true]:bg-primary-wash" in attrs["class"].split()


def test_a_card_not_chosen_says_nothing() -> None:
    attrs = _attrs(variant="ghost", on_click=_act)
    assert "data-active" not in attrs and "aria-current" not in attrs
    assert "data-[active=true]" not in attrs["class"]


def test_a_variant_off_the_table_is_refused() -> None:
    with render_isolated(), pytest.raises(ComponentUsageError, match="ghost, solid"):
        Card(variant="soft").render()


def test_a_client_state_drives_active() -> None:
    """One-way, as on the navigation items: a choice made in the browser
    lights its card with no request."""
    for value in (False, True):
        binding = ClientBinding(class_name="Plan", instance_key="default",
                                field_name="team", value=value)
        attrs = _attrs(on_click=_act, active=binding)
        expr = attrs["bz-attr:data-active"]
        assert "$bz.state.Plan.default.team" in expr
        assert expr.endswith("? 'true' : 'false'")
        assert attrs["bz-attr:aria-current"].endswith("? 'true' : null")
        assert "data-[active=true]:bg-primary-wash" in attrs["class"].split()
        assert (attrs.get("data-active") == "true") is value
