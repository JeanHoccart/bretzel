"""A card one acts on is a button to the keyboard.

Before 2026-10-26 a ``<div>`` card with ``on_click=`` was reachable by a
mouse only: no ``role``, no place in the Tab order, Enter did nothing.
It now takes the table row's
gesture (``activate_keydown``): ``role="button"``, ``tabindex="0"``,
Enter / Space click it — and shows its focus like a button.
"""

from __future__ import annotations

from bretzel.components.base.testing import render_isolated
from bretzel.components.layout.card.card import Card


def _act() -> None:
    """A module-level handler: the framework refuses a lambda."""


def _attrs(**kwargs):
    with render_isolated():
        return Card(**kwargs).render().attrs


def test_a_card_with_a_server_action_is_a_keyboard_button() -> None:
    attrs = _attrs(on_click=_act)
    assert attrs["role"] == "button"
    assert attrs["tabindex"] == "0"
    assert "Enter" in attrs["bz-on:keydown"] and "$el.click()" in attrs["bz-on:keydown"]
    assert "focus-visible:ring-2" in attrs["class"]


def test_a_card_with_a_client_action_is_one_too() -> None:
    attrs = _attrs(on_click="console.log('x')")
    assert attrs["role"] == "button" and attrs["tabindex"] == "0"


def test_a_link_card_stays_a_link_and_shows_its_focus() -> None:
    attrs = _attrs(href="/classes/4e2")
    assert "role" not in attrs and "tabindex" not in attrs
    assert "focus-visible:ring-2" in attrs["class"]


def test_a_card_one_does_not_act_on_stays_a_plain_box() -> None:
    attrs = _attrs()
    assert "role" not in attrs and "tabindex" not in attrs
    assert "focus-visible" not in attrs["class"]


def test_a_role_given_by_the_app_is_kept() -> None:
    attrs = _attrs(on_click=_act, attrs={"role": "option"})
    assert attrs["role"] == "option"
