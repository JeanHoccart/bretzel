"""``Heading`` — semantic ``h1``–``h6`` with size decoupled from level.

The HTML tag follows ``level=`` (an int 1-6) for SEO / a11y semantics,
the visible size follows ``size=`` (or auto-derives from the level via
the theme dict's ``level_sizes`` map). That decoupling lets you write
``ui.heading("Section A", level=2, size="4xl")`` — an ``<h2>`` at the
size of an h1.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.primitives.heading.theme import HEADING_THEME
from bretzel.core.tree import Element
from bretzel.state.scopes.client import ClientBinding


class Heading(Component):
    """Semantic heading. Pass text positionally, set ``level=`` (int
    1–6) for the HTML tag, ``size=`` to override the auto-derived
    visual size."""

    THEME: ClassVar[dict[str, Any]] = HEADING_THEME
    THEME_KEY: ClassVar[str] = "heading"
    DEFAULT_TAG: ClassVar[str] = "h2"
    IS_CONTAINER: ClassVar[bool] = False
    # Curated reactive surface — only the text text. Visual axes
    # (size / weight / color / level) are design-time.
    # ``text`` is the first positional arg, picked up by name in the check.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("text",)

    level: int = reactive_prop(default=2, emit_attr=False)
    size: str | None = reactive_prop(default=None, emit_attr=False)
    weight: str = reactive_prop(default="bold", emit_attr=False)
    color: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        text: str | ClientBinding | None = None,
        *,
        level: int | None = None,
        size: str | None = None,
        weight: str | None = None,
        color: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            level=level, size=size, weight=weight, color=color, **kwargs
        )
        # ``text`` may be a string, ClientBinding, Component or absent ;
        # ``emit_text_slot`` picks the shape. ``adopt_slot`` detaches a
        # Component so it isn't rendered twice. ``ClientBinding.__bool__``
        # raises → explicit ``is None`` check, not truthiness.
        self._text = "" if text is None else Component.adopt_slot(text)

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        level = self._reactive_values.get("level") or 2

        # Auto-derive size from the level when ``size=`` not passed.
        size_key = self._reactive_values.get("size") or theme.get(
            "level_sizes", {}
        ).get(level, "2xl")

        weight = self._reactive_values.get("weight") or "bold"
        color = self._reactive_values.get("color")

        parts: list[str] = []
        root = theme.get("slots", {}).get("root")
        if root:
            parts.append(root)
        size_class = theme.get("sizes", {}).get(size_key)
        if size_class:
            parts.append(size_class)
        weight_class = theme.get("weights", {}).get(weight)
        if weight_class:
            parts.append(weight_class)
        if color:
            # The STEP: the root's bridge carries the colour.
            parts.append("text-(--bz-text)")
        # ``classes=`` set by the metaclass wrap — not here (duplicate).

        attrs = self.emit_attrs()
        attrs["class"] = " ".join(p for p in parts if p).strip()
        # The HTML tag is built from ``level=`` (``h{level}``), not ``self._tag``.
        text_node = self.emit_text_slot(self._text)
        children: tuple[Any, ...] = (
            (text_node,) if text_node is not None else ()
        )
        return Element(tag=f"h{level}", attrs=attrs, children=children)
