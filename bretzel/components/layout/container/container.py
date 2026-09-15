"""``Container`` — centered max-width layout primitive.

Sibling of :class:`Flex` / :class:`VStack` / :class:`Card` — pure layout,
no variants, no sizes. A single ``width=`` prop picks the max-width
clamp (``sm``, ``md``, ``lg``, ``xl``, ``2xl``, ``full``). The
horizontal + vertical padding is baked into the root slot ; apps that
need a different spacing scale compose ``Container > VStack``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.layout.container.theme import CONTAINER_THEME
from bretzel.core.tree import Element


class Container(Component):
    """Centered max-width column. Pass ``width=`` to pick the clamp."""

    THEME: ClassVar[dict[str, Any]] = CONTAINER_THEME
    THEME_KEY: ClassVar[str] = "container"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    width: str = reactive_prop(default="lg", emit_attr=False)

    def __init__(
        self,
        *,
        width: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope ``width=None`` (garde le défaut).
        super().__init__(width=width, **kwargs)

    def render(self) -> Element:
        theme = self._resolved_theme()
        width = self._reactive_values.get("width") or "lg"

        parts: list[str] = []
        root = theme.get("slots", {}).get("root")
        if root:
            parts.append(root)
        width_class = theme.get("widths", {}).get(width)
        if width_class:
            parts.append(width_class)
        # Classes user posées par le wrap ``_apply_universal_modifiers`` —
        # ne pas ré-append ici (doublon). Gardé par
        # test_no_manual_user_class_append.py.

        attrs = self.emit_attrs()
        attrs["class"] = " ".join(p for p in parts if p).strip()

        return Element(
            tag=self._tag,
            attrs=attrs,
            children=self._render_children(),
        )
