"""The contract of a navigation row, shared by the sidebar, navbar and bottom bar.

Same props, same event, same wiring (``navigation/_wiring.wire_nav_item``).
Only the theme and the drawing differ, and those stay with each item.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.navigation._wiring import capture_layout


class NavItem(Component):
    """A navigation row: icon, label, optional badge, link or action."""

    IS_CONTAINER: ClassVar[bool] = False
    EVENTS: ClassVar[tuple[str, ...]] = ("click",)
    NAMED_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    ICON_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    # ``active`` is derived from ``current_path`` when nothing is passed;
    # ``disabled`` and ``active`` follow a client state. ``label`` and
    # ``href`` are design-time: routes do not change live.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("active", "disabled")

    label: str | Component = reactive_prop(default="", emit_attr=False)
    href: str | None = reactive_prop(default=None, emit_attr=False)
    active: Any = reactive_prop(default=None, emit_attr=False)
    badge: str | int | Component | None = reactive_prop(default=None, emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)

    def __init__(
        self,
        label: str | Component = "",
        *,
        icon: str | Component | None = None,
        href: str | None = None,
        active: Any = None,
        badge: str | int | Component | None = None,
        disabled: bool | None = None,
        color: str | None = None,
        on_click: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            label=label,
            href=href,
            active=active,
            badge=badge,
            disabled=disabled,
            color=color,
            icon=icon,
            on_click=on_click,
            **kwargs,
        )
        # The enclosing layout, for the partial navigation: the
        # ``with @layout(): ...`` block is open here, and ``layout_stack``
        # is empty by the time ``render()`` runs.
        self._captured_layout: str | None = capture_layout()
