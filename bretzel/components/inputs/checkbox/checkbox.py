"""``Checkbox`` — boolean input with a styled "soft-tick" box.

The real ``<input type="checkbox">`` is hidden via ``sr-only`` so the
keyboard / screen-reader path stays native. A styled ``<div>`` next to
it impersonates the visual checkbox, filling on ``peer-checked``. An
absolute-positioned SVG check rides over the box, fading in via
``opacity-0 → peer-checked:opacity-100 transition-opacity``.

The SVG overlay lets the tick animate — native ``accent-color`` looks
like the platform default and can't.

"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base.focus import FocusCommands
from bretzel.components.inputs._checkable import render_checkable
from bretzel.components.inputs._wiring import CheckedCommands
from bretzel.components.inputs.checkbox.theme import CHECKBOX_THEME
from bretzel.core.tree import Element

# Single-stroke checkmark, lucide-style. ``stroke="currentColor"`` so
# the SVG inherits the text colour the ``icon`` slot sets.
_CHECK_PATH = "M20 6 9 17l-5-5"


class Checkbox(CheckedCommands, FocusCommands, Component):
    """Boolean toggle input with optional inline label."""

    THEME: ClassVar[dict[str, Any]] = CHECKBOX_THEME
    THEME_KEY: ClassVar[str] = "checkbox"
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
    required: bool = reactive_prop(default=False)
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
        required: bool | None = None,
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
            disabled=disabled, required=required,
            color=color, size=size,
            on_change=on_change,
            on_focus=on_focus,
            on_blur=on_blur,
            **kwargs,
        )
        self._label = label

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        # The tick SVG — a single stroke, lucide style. Width/height
        # inherit the icon classes; the stroke comes from
        # ``currentColor``, set by the slot's ``--bz-on-solid`` step.
        svg = Element(
            tag="svg",
            attrs={
                "class": self.compose_class("icon"),
                "viewBox": "0 0 24 24",
                "fill": "none",
                "stroke": "currentColor",
                "stroke-width": "3",
                "stroke-linecap": "round",
                "stroke-linejoin": "round",
                "aria-hidden": "true",
            },
            children=(Element(tag="path", attrs={"d": _CHECK_PATH}, children=()),),
        )

        return render_checkable(
            self,
            visuals=(
                Element(
                    tag="div",
                    attrs={"class": self.compose_class("box")},
                    children=(),
                ),
                svg,
            ),
        )
