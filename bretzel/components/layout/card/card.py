"""``Card`` — surface wrapper with V1's signature hover lift effect.

Polymorphic root tag : ``<div>`` by default, ``<a>`` when ``href=``
is passed (so the whole card becomes a single click target — common
in dashboards, list views). Setting ``href=`` auto-enables
``hoverable`` since a clickable card without a hover affordance would
read as static.

The hover lift is ``relative top-0 hover:-top-0.5 hover:shadow-md`` —
subtle enough not to bounce, present enough to read as actionable.
(A ``top`` offset, deliberately NOT a translate : a transform would
make the card the containing block of its fixed-positioned overlay
panels — cf. traps.md § « Hover lift en translate ».)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.layout.card.theme import CARD_THEME
from bretzel.core.tree import Element


class Card(Component):
    """Surface wrapper. Pass ``href=`` to make the whole card a link
    (auto-enables ``hoverable``), ``padding=`` for the inner spacing
    scale, ``hoverable=True`` to opt in to the lift effect manually."""

    THEME: ClassVar[dict[str, Any]] = CARD_THEME
    THEME_KEY: ClassVar[str] = "card"
    # design-time. Use ``visible=`` universal modifier to show/hide.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    EVENTS: ClassVar[tuple[str, ...]] = ("click", "mouseenter", "mouseleave")

    color: str = reactive_prop(default="surface", emit_attr=False)
    padding: str = reactive_prop(default="md", emit_attr=False)
    hoverable: bool | None = reactive_prop(default=None, emit_attr=False)
    href: str | None = reactive_prop(default=None, never_code=True)

    def __init__(
        self,
        *,
        color: str | None = None,
        padding: str | None = None,
        hoverable: bool | None = None,
        href: str | None = None,
        on_click: Callable[..., Any] | str | None = None,
        on_mouseenter: Callable[..., Any] | str | None = None,
        on_mouseleave: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive ``None`` kwargs
        # (keeps the default) — no more ``if x is not None`` guard to
        # retype.
        super().__init__(
            color=color,
            padding=padding,
            hoverable=hoverable,
            href=href,
            on_click=on_click,
            on_mouseenter=on_mouseenter,
            on_mouseleave=on_mouseleave,
            **kwargs,
        )
        # ── The tag switch is decided HERE, not at render ─────────────
        # It lived in ``render`` until 2026-08-23, and a new guard
        # revealed it: ``emit_attrs`` now removes the attributes a tag
        # cannot carry, and it still saw a ``<div>`` — so it threw away
        # the ``href`` we had just set. The symptom (a link card with no
        # destination) was worse than the original defect.
        #
        # Deciding early is more correct anyway: ``self._tag`` is read by
        # introspection and by the gates, and a component whose tag only
        # knows itself at render lies to whoever asks it.
        # ``ui.button(href=…)`` does the same.
        if href is not None and "tag" not in kwargs:
            self._tag = "a"

    def render(self) -> Element:
        theme = self._resolved_theme()
        padding = self._reactive_values.get("padding") or "md"
        href = self._reactive_values.get("href")

        # ``hoverable=True`` explicit, or implicit when href is set.
        explicit_hover = self._reactive_values.get("hoverable")
        is_hoverable = (
            explicit_hover if explicit_hover is not None else href is not None
        )

        parts: list[str] = []
        root = theme.get("slots", {}).get("root")
        if root:
            root_class = root
            # ``overflow-hidden`` is unconditional : every anchored
            # panel (Select, Tooltip, Dropdown…) is repositioned
            # ``position: fixed`` at open time by ``floating()`` and
            # escapes the clip box natively — so no auto-swap to
            # ``overflow-visible`` is needed. Cf. traps.md § "Card
            # auto-swap (REMOVED)".
            parts.append(root_class)
        padding_class = theme.get("paddings", {}).get(padding)
        if padding_class:
            parts.append(padding_class)
        if is_hoverable:
            hoverable_class = theme.get("hoverable", "")
            if hoverable_class:
                parts.append(hoverable_class)
        # The user classes (``classes=``) are set on the real root by
        # the ``_apply_universal_modifiers`` metaclass wrap — do NOT
        # re-append them here (otherwise a "X X" duplicate). Guarded by
        # test_no_manual_user_class_append.py.

        attrs = self.emit_attrs()
        attrs["class"] = " ".join(p for p in parts if p).strip()

        return Element(
            tag=self._tag,
            attrs=attrs,
            children=self._render_children(),
        )
