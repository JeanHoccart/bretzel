"""``Skeleton`` — loading placeholder block.

Three variants :

- ``text`` — a thin rounded rectangle the height of a typical text
  line. Stack several with different widths to mock paragraphs.
- ``circle`` — perfectly round, useful as an avatar placeholder.
- ``rectangle`` (default) — arbitrary box, drives ``width=`` and
  ``height=`` for cards / images / charts.

``animated=True`` (default) uses Tailwind's ``animate-pulse`` so the
placeholder breathes ; pass ``animated=False`` for fully static
print / screenshot use.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.feedback.skeleton.theme import SKELETON_THEME
from bretzel.core.tree import Element


class Skeleton(Component):
    """Loading-placeholder block."""

    THEME: ClassVar[dict[str, Any]] = SKELETON_THEME
    THEME_KEY: ClassVar[str] = "skeleton"
    DEFAULT_TAG: ClassVar[str] = "span"
    IS_CONTAINER: ClassVar[bool] = False
    # Pure placeholder while loading — show/hide via the parent's
    # ``visible=`` universal modifier, not via Skeleton's own props.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    variant: str = reactive_prop(default="rectangle", emit_attr=False)
    width: str | None = reactive_prop(default=None, emit_attr=False)
    height: str | None = reactive_prop(default=None, emit_attr=False)
    animated: bool = reactive_prop(default=True, emit_attr=False)

    def __init__(
        self,
        *,
        variant: str | None = None,
        width: str | None = None,
        height: str | None = None,
        animated: bool | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            variant=variant, width=width,
            height=height, animated=animated,
            **kwargs,
        )

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        variants = theme.get("variants", {})
        variant = self._reactive_values.get("variant") or "rectangle"
        width = self._reactive_values.get("width")
        height = self._reactive_values.get("height")
        animated = bool(self._reactive_values.get("animated"))

        attrs = self.emit_attrs()
        attrs["class"] = " ".join(
            p
            for p in (
                slots.get("root", ""),
                variants.get(variant, variants.get("rectangle", "")),
                "animate-pulse" if animated else "",
            )
            if p
        )
        attrs.setdefault("aria-hidden", "true")
        # Inline ``width`` / ``height`` keep the placeholder agnostic
        # of any Tailwind setup — caller passes any CSS unit.
        style_parts: list[str] = []
        if width is not None:
            style_parts.append(f"width: {width}")
        if height is not None:
            style_parts.append(f"height: {height}")
        if style_parts:
            existing = attrs.get("style", "")
            attrs["style"] = (
                f"{existing}; " if existing else ""
            ) + "; ".join(style_parts)
        return Element(tag=self._tag, attrs=attrs, children=())
