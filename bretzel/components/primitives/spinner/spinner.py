"""``Spinner`` — pure-CSS loading indicator.

One opinionated form : a rotating ring via Tailwind's ``animate-spin`` — no
JS, no SVG. Size scales via ``h × w`` ; color drives the border via
``text-{color}`` so the spinner inherits colour context when nested. Callers
who need another look override the theme's ``root`` slot.

A11y : the root carries ``role="status"`` + ``aria-label`` (default
"Loading", override via ``aria_label``) so screen readers announce it.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import theme_context
from bretzel.components.primitives.spinner.theme import SPINNER_THEME
from bretzel.core.tree import Element


class Spinner(Component):
    """Loading indicator. Pass ``size=`` for the scale, ``color=`` for
    the tint — a rotating ring is the one built-in look."""

    THEME: ClassVar[dict[str, Any]] = SPINNER_THEME
    THEME_KEY: ClassVar[str] = "spinner"
    DEFAULT_TAG: ClassVar[str] = "span"
    IS_CONTAINER: ClassVar[bool] = False
    # Pure visual indicator — visible/hidden is driven by ``visible=``
    # universal modifier on the parent, not by Spinner's own props.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    size: str = reactive_prop(default="md", emit_attr=False)
    # ``current`` mirrors Icon's default — the spinner inherits its parent's
    # text colour so embedding it inside a Button just works. Pass
    # ``color="primary"`` for a branded tint.
    color: str = reactive_prop(default="current", emit_attr=False)

    def __init__(
        self,
        *,
        size: str | None = None,
        color: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(size=size, color=color, **kwargs)

    def render(self) -> Element:
        theme, _slots, _sizes, size, _color = theme_context(self, color_default="current")

        size_cls = theme.get("sizes", {}).get(size, "")

        attrs = self.emit_attrs()
        attrs.setdefault("role", "status")
        attrs.setdefault("aria-label", "Loading")

        # Single element : root (layout + colour + ring recipe) + size
        # (box + border width). The ring's border width lives in the
        # size token so the two never collide on a single ``border-*``.
        attrs["class"] = " ".join(
            p
            for p in (
                self.compose_class(
                    "root",
                    apply_variant_size_modifiers=False,
                ),
                size_cls,
            )
            if p
        )
        return Element(tag=self._tag, attrs=attrs, children=())
