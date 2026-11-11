"""``Switch`` — visual variant of checkbox with a sliding thumb.

Same DOM idiom as ``Checkbox`` : a real ``<input type="checkbox">``
hidden via ``sr-only``, two visual fakes (``track`` + ``thumb``)
riding on its ``:checked`` / ``:focus-visible`` states. The thumb
slides via ``transition-transform peer-checked:translate-x-N`` —
where N depends on size.

"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base.focus import FocusCommands
from bretzel.components.inputs._checkable import render_checkable
from bretzel.components.inputs._wiring import CheckedCommands
from bretzel.components.inputs.switch.theme import SWITCH_THEME
from bretzel.core.tree import Element


class Switch(CheckedCommands, FocusCommands, Component):
    """Boolean toggle rendered as a sliding rail."""

    THEME: ClassVar[dict[str, Any]] = SWITCH_THEME
    THEME_KEY: ClassVar[str] = "switch"
    DEFAULT_TAG: ClassVar[str] = "label"
    IS_CONTAINER: ClassVar[bool] = False
    # Curated reactive surface — the boolean toggle + lock flag.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("checked", "disabled")
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "toggle", "focus", "blur")
    # Where ``autofocus=`` / ``.focus()`` land: the native ``<input>`` carries the id.
    FOCUS_TARGET: ClassVar[tuple[str, ...] | None] = ()
    EVENTS: ClassVar[tuple[str, ...]] = ("change", "focus", "blur")

    checked: bool | Any = reactive_prop(default=False, writes=True, names_field=True)
    name: str | None = reactive_prop(default=None)
    value: str | None = reactive_prop(default=None)
    disabled: bool = reactive_prop(default=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)

    def __init__(
        self,
        label: str | Component | None = None,
        *,
        checked: Any = None,
        name: str | None = None,
        value: str | None = None,
        disabled: bool | None = None,
        color: str | None = None,
        size: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            checked=checked, name=name, value=value,
            disabled=disabled, color=color, size=size,
            on_change=on_change,
            on_focus=on_focus,
            on_blur=on_blur,
            **kwargs,
        )
        self._label = label

    def render(self) -> Element:
        return render_checkable(
            self,
            visuals=(
                Element(
                    tag="div",
                    attrs={"class": self.compose_class("track")},
                    children=(),
                ),
                Element(
                    tag="span",
                    attrs={"class": self.compose_class("thumb")},
                    children=(),
                ),
            ),
        )
