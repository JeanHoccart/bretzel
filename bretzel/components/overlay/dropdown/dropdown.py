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

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import install_open_close_toggle
from bretzel.components.overlay._anchored import render_anchored_overlay
from bretzel.components.overlay.dropdown.theme import (
    DROPDOWN_ITEM_THEME,
    DROPDOWN_THEME,
)
from bretzel.components.primitives.menu_item import MenuItem
from bretzel.core.tree import Element


class Dropdown(Component):
    """Anchored menu of clickable rows."""

    THEME: ClassVar[dict[str, Any]] = DROPDOWN_THEME
    THEME_KEY: ClassVar[str] = "dropdown"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("open",)
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("open", "close", "toggle")
    EVENTS: ClassVar[tuple[str, ...]] = ("open", "close")
    # ``open`` AND ``close`` both fire on the root, so a single dropdown can
    # wire on_open + on_close to the server (the second rides a hidden
    # carrier — cf. ``Component.ALLOW_MULTI_SERVER_EVENTS``).
    ALLOW_MULTI_SERVER_EVENTS: ClassVar[bool] = True

    open: Any = reactive_prop(default=False, emit_attr=False, writes=True)
    # ``auto`` = best-fit (``$bz.helpers.floating`` picks the roomiest
    # side that fits, aligned per ``align``) ; pin a side to override.
    position: str = reactive_prop(default="auto", emit_attr=False)
    align: str = reactive_prop(default="start", emit_attr=False)
    dismissible: bool = reactive_prop(default=True, emit_attr=False)

    def __init__(
        self,
        *,
        trigger: Component | None = None,
        open: Any = None,
        position: str | None = None,
        align: str | None = None,
        dismissible: bool | None = None,
        on_open: Callable[..., Any] | str | None = None,
        on_close: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            open=open,
            position=position,
            align=align,
            dismissible=dismissible,
            on_open=on_open,
            on_close=on_close,
            **kwargs,
        )
        self._trigger: Component | None = Component.adopt_slot(trigger)
        # Write-only imperative API ``.open()`` / ``.close()`` /
        # ``.toggle()`` — installed as instance attributes (shadowing the
        # ``open`` descriptor) by the base helper, identical on the 4
        # open-driven overlays. Cf. `imperative-api.md`.
        install_open_close_toggle(self)


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

