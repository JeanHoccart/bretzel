"""``Heading`` — semantic ``h1``–``h6`` with size decoupled from level.

The HTML tag follows ``level=`` (an int 1-6) for SEO / a11y semantics,
the visible size follows ``size=`` (or auto-derives from the level via
the theme dict's ``level_sizes`` map). That decoupling lets you write
``ui.heading("Section A", level=2, size="4xl")`` — an ``<h2>`` at the
size of an h1.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, ComponentUsageError, reactive_prop
from bretzel.components.primitives.heading.theme import HEADING_THEME
from bretzel.core.tree import Element
from bretzel.state.scopes.client import ClientBinding

#: The weight a heading takes when none is given — read by ``ui.markdown``
#: too, whose ``#`` titles are headings.
DEFAULT_WEIGHT = "bold"


def heading_classes(theme: dict[str, Any], level: int, *, size: str | None = None,
                    weight: str | None = None) -> list[str]:
    """The classes of a level-``level`` title in ``theme``: its root, its
    size (``level_sizes`` unless ``size`` is given), its weight.

    The ONE scale of the titles: ``ui.heading`` and the ``#`` titles of
    ``ui.markdown`` both read it, so a ``##`` and a level-2 heading look
    the same, and a level 3 never reads louder than the level 2 above it.
    """
    size_key = size or theme.get("level_sizes", {}).get(level, "2xl")
    parts = [
        theme.get("slots", {}).get("root"),
        theme.get("sizes", {}).get(size_key),
        theme.get("weights", {}).get(weight or DEFAULT_WEIGHT),
    ]
    return [part for part in parts if part]


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
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    level: int = reactive_prop(default=2, emit_attr=False)
    size: str | None = reactive_prop(default=None, emit_attr=False)
    weight: str = reactive_prop(default=DEFAULT_WEIGHT, emit_attr=False)
    color: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        text: str | Component | ClientBinding | None = None,
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
        # ``emit_text_slot`` picks the shape. ``ClientBinding.__bool__``
        # raises → explicit ``is None`` check, not truthiness.
        self._text = "" if text is None else text

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        level = self._reactive_values.get("level") or 2

        # The size follows the level when ``size=`` is not passed.
        color = self._reactive_values.get("color")
        parts = heading_classes(
            theme, level,
            size=self._reactive_values.get("size"),
            weight=self._reactive_values.get("weight"),
        )
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
        # ``level`` builds the tag: only 1 to 6 are headings (a string
        # such as ``"1><img …"`` would be markup).
        if level not in (1, 2, 3, 4, 5, 6) or isinstance(level, bool):
            raise ComponentUsageError(f"ui.heading(level={level!r}): a heading level is 1 to 6.")
        return Element(tag=f"h{level}", attrs=attrs, children=children)
