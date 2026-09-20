"""``Divider`` — horizontal or vertical separator with optional label.

Renders ``[line, label?, line]`` — a present label is flanked by two lines.
The line uses ``bg-current`` so it follows whatever ``text-{color}`` the
root carries.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.primitives.divider.theme import DIVIDER_THEME
from bretzel.core.tree import Element
from bretzel.state.scopes.client import ClientBinding


class Divider(Component):
    """Horizontal or vertical separator. ``orientation="vertical"``
    flips the axis ; pass ``label="…"`` for the boxed-section look."""

    THEME: ClassVar[dict[str, Any]] = DIVIDER_THEME
    THEME_KEY: ClassVar[str] = "divider"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("label",)

    orientation: str = reactive_prop(default="horizontal", emit_attr=False)
    color: str = reactive_prop(default="muted", emit_attr=False)

    def __init__(
        self,
        *,
        orientation: str | None = None,
        label: str | ClientBinding | None = None,
        color: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(orientation=orientation, color=color, **kwargs)
        # ``adopt_slot`` + ``emit_text_slot`` go together : the 1st detaches a
        # Component (else rendered 2×), the 2nd RENDERS it (else it hits
        # ``TextNode()`` which expects a string → crash at serialize).
        self._label = Component.adopt_slot(label)

    def render(self) -> Element:
        theme = self._resolved_theme()
        orientation = self._reactive_values.get("orientation") or "horizontal"
        color = self._reactive_values.get("color") or "muted"
        ovr = theme.get("orientations", {}).get(orientation, {})

        # Root : base slot + orientation override + ``text-{color}`` so
        # the inner line inherits via ``bg-current``.
        # ``classes=`` set by the metaclass wrap — not here (duplicate).
        root_class = " ".join(
            p
            for p in (
                theme.get("slots", {}).get("root", ""),
                ovr.get("root", ""),
            # The STEP: the root's bridge carries the colour.
                "text-(--bz-text)" if color else "",
            )
            if p
        )
        line_class = " ".join(
            p
            for p in (
                theme.get("slots", {}).get("line", ""),
                ovr.get("line", ""),
            )
            if p
        )

        line = Element(tag="div", attrs={"class": line_class}, children=())
        children: list[Any] = []
        has_label = self._label is not None and (
            not isinstance(self._label, str) or self._label != ""
        )
        if has_label:
            children.append(line)
            children.append(
                Element(
                    tag="span",
                    attrs={"class": theme.get("slots", {}).get("label", "")},
                    children=(self.emit_text_slot(self._label),),
                )
            )
            # Re-emit a fresh second line — Element is immutable so
            # we can't reuse the same instance as a sibling twice.
            children.append(
                Element(tag="div", attrs={"class": line_class}, children=())
            )
        else:
            children.append(line)

        attrs = self.emit_attrs()
        attrs["class"] = root_class
        # Accessibility : ``role="separator"`` so screen readers
        # announce the visual cue.
        attrs.setdefault("role", "separator")
        attrs.setdefault(
            "aria-orientation",
            "vertical" if orientation == "vertical" else "horizontal",
        )
        return Element(tag=self._tag, attrs=attrs, children=tuple(children))
