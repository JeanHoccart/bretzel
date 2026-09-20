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
from bretzel.components.inputs._checkable import render_checkable, sized_slot
from bretzel.components.inputs.checkbox.theme import CHECKBOX_THEME
from bretzel.core.tree import Element

# Single-stroke checkmark, lucide-style. ``stroke="currentColor"`` so
# the SVG inherits the text colour the ``icon`` slot sets.
_CHECK_PATH = "M20 6 9 17l-5-5"


class Checkbox(Component):
    """Boolean toggle input with optional inline label."""

    THEME: ClassVar[dict[str, Any]] = CHECKBOX_THEME
    THEME_KEY: ClassVar[str] = "checkbox"
    DEFAULT_TAG: ClassVar[str] = "label"
    IS_CONTAINER: ClassVar[bool] = False
    # Curated reactive surface — the boolean toggle + lock flag.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("checked", "disabled")
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "toggle")
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
        *,
        checked: Any = None,
        name: str | None = None,
        value: str | None = None,
        label: str | None = None,
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
        # ``adopt_slot`` + ``emit_text_slot`` are a COUPLE (cf.
        # emit_text_slot's docstring): the 1st detaches the Component
        # (otherwise rendered twice), the 2nd RENDERS it (otherwise it
        # goes into TextNode() which expects a string → `'Text' object
        # has no attribute 'replace'` at serialize). Doing one without
        # the other swaps one bug for another.
        self._label = Component.adopt_slot(label)

    # ── Imperative write-only API ─────────────────────────────────────
    #
    # Methods returning client JS for ``on_click=``. Write-through when
    # ``checked=`` carries a binding ; else DOM dispatch on the input
    # listener. ``.set(bool)`` sets, ``.toggle()`` flips. Cf. `imperative-api.md`.

    def set(self, value: bool) -> str:
        return self._value_command(bool(value), prop="checked")

    def toggle(self) -> str:
        return self._toggle_command()


    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        size_key = self._reactive_values.get("size") or "md"
        size_map: dict[str, str] = (
            self._resolved_theme().get("sizes", {}).get(size_key) or {}
        )

        # The tick SVG — a single stroke, lucide style. Width/height
        # inherit the icon classes; the stroke comes from
        # ``currentColor``, set by the slot's ``--bz-on-solid`` step.
        svg = Element(
            tag="svg",
            attrs={
                "class": sized_slot(self, "icon", size_map),
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
            size_map=size_map,
            visuals=(
                Element(
                    tag="div",
                    attrs={"class": sized_slot(self, "box", size_map)},
                    children=(),
                ),
                svg,
            ),
        )
