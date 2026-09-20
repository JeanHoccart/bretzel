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
from bretzel.components.inputs._checkable import render_checkable, sized_slot
from bretzel.components.inputs.switch.theme import SWITCH_THEME
from bretzel.core.tree import Element


class Switch(Component):
    """Boolean toggle rendered as a sliding rail."""

    THEME: ClassVar[dict[str, Any]] = SWITCH_THEME
    THEME_KEY: ClassVar[str] = "switch"
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
        # ``adopt_slot`` + ``emit_text_slot`` are a COUPLE (cf.
        # emit_text_slot's docstring): the 1st detaches the Component
        # (otherwise rendered twice), the 2nd RENDERS it (otherwise it
        # goes into TextNode() which expects a string → `'Text' object
        # has no attribute 'replace'` at serialize). Doing one without
        # the other swaps one bug for another.
        self._label = Component.adopt_slot(label)

    # ── Imperative write-only API ─────────────────────────────────────
    #
    # Same contract as Checkbox — see ``Checkbox._imperative_*`` and
    # `imperative-api.md`. Switch is a visual variant of the same
    # bool toggle, so the API stays uniform.

    def set(self, value: bool) -> str:
        return self._value_command(bool(value), prop="checked")

    def toggle(self) -> str:
        return self._toggle_command()


    def render(self) -> Element:
        size_key = self._reactive_values.get("size") or "md"
        size_map: dict[str, str] = (
            self._resolved_theme().get("sizes", {}).get(size_key) or {}
        )

        return render_checkable(
            self,
            size_map=size_map,
            visuals=(
                Element(
                    tag="div",
                    attrs={"class": sized_slot(self, "track", size_map)},
                    children=(),
                ),
                Element(
                    tag="span",
                    attrs={"class": sized_slot(self, "thumb", size_map)},
                    children=(),
                ),
            ),
        )
