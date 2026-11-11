"""``Dropdown`` + ``DropdownItem`` — anchored menu of clickable rows.

Composition pattern : pass the trigger as ``trigger=`` on the
Dropdown, put :class:`DropdownItem` instances as children inside
the ``with`` block ::

    class UI(ClientState, persist="memory"):
        menu_open: bool = field(default=False)

    ui_state = UI()

    with ui.dropdown(
        trigger=ui.icon_button("more-horizontal"),
        open=ui_state.menu_open,
    ):
        ui.dropdown_item(label="Edit",      icon_left="pencil",
                         on_click=edit_handler)
        ui.dropdown_item(label="Duplicate", icon_left="copy",
                         on_click=duplicate_handler)
        ui.dropdown_item(label="Delete",    icon_left="trash-2",
                         color="error",
                         on_click=delete_handler)

The Dropdown itself is a thin shell : it owns the open flag (via
the universal ``open=binding`` contract), positioning (via
``$bz.helpers.floating``), click-outside + escape dismiss. Each
DropdownItem is responsible for its own click behaviour (server
handler, link, or pure-client action) and for closing the parent
dropdown after the click — that close is wired automatically via the
runtime ``$dispatch('bz-dropdown-pick')`` when an item is picked.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.overlay._anchored import render_anchored_overlay
from bretzel.components.overlay._base import AnchoredOverlay
from bretzel.components.overlay.dropdown.theme import (
    DROPDOWN_ITEM_THEME,
    DROPDOWN_THEME,
)
from bretzel.components.primitives.menu_item import MenuItem
from bretzel.core.tree import Element


class Dropdown(AnchoredOverlay):
    """Anchored menu of clickable rows."""

    THEME: ClassVar[dict[str, Any]] = DROPDOWN_THEME
    THEME_KEY: ClassVar[str] = "dropdown"
    def render(self) -> Element:
        return render_anchored_overlay(
            self,
            slots=self._resolved_theme().get("slots", {}),
            role="menu",
            haspopup="menu",
            default_align="start",
            # The items dispatch ``bz-dropdown-pick`` when they are
            # picked: that is what closes the menu.
            close_on_event="bz-dropdown-pick",
        )


class DropdownItem(MenuItem):
    """One clickable row inside a :class:`Dropdown`.

    All the row logic — icons + label + shortcut, colour tint, link/button,
    and the ``$dispatch('bz-dropdown-pick')`` close-on-click — lives in
    :class:`~bretzel.components.primitives.menu_item.MenuItem`. This shell
    only binds the dropdown theme.
    """

    THEME: ClassVar[dict[str, Any]] = DROPDOWN_ITEM_THEME
    THEME_KEY: ClassVar[str] = "dropdown_item"

