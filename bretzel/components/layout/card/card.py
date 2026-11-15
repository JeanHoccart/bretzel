"""``Card`` — surface wrapper with V1's signature hover lift effect.

Two variants: ``solid`` (default), the bordered surface, and ``ghost``, no
background, border or shadow — a row of a list. A ghost card that acts
(``on_click=``, ``href=``) shows it by a hover background, never a lift,
and draws its focus ring inside. ``active=True`` marks the chosen element
(``data-active``, ``aria-current``, the accent's background).

Polymorphic root tag : ``<div>`` by default, ``<a>`` when ``href=``
is passed (so the whole card becomes a single click target — common
in dashboards, list views). Setting ``href=`` auto-enables
``hoverable`` since a clickable card without a hover affordance would
read as static.

The hover lift is ``relative top-0 hover:-top-0.5 hover:shadow-md`` —
subtle enough not to bounce, present enough to read as actionable.
(A ``top`` offset, deliberately NOT a translate : a transform would
make the card the containing block of its fixed-positioned overlay
panels — cf. traps.md § « Un overlay hérite des contraintes de ses ancêtres ».)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base.field_wiring import activate_keydown
from bretzel.components.base.scope_wiring import bool_attr
from bretzel.components.layout.card.theme import CARD_THEME
from bretzel.core.tree import Element


class Card(Component):
    """Surface wrapper. Pass ``href=`` to make the whole card a link
    (auto-enables ``hoverable``), ``padding=`` for the inner spacing
    scale, ``hoverable=True`` to opt in to the lift effect manually.
    ``variant="ghost"`` for a row of a list, ``active=True`` for the
    chosen one."""

    THEME: ClassVar[dict[str, Any]] = CARD_THEME
    THEME_KEY: ClassVar[str] = "card"
    # ``active`` follows a client state (a choice made in the browser),
    # as on the navigation items — R1, one word, one effect. The rest is
    # design-time; ``visible=`` shows / hides.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("active",)
    EVENTS: ClassVar[tuple[str, ...]] = ("click", "mouseenter", "mouseleave")

    variant: str = reactive_prop(default="solid", emit_attr=False)
    color: str = reactive_prop(default="surface", emit_attr=False)
    padding: str = reactive_prop(default="md", emit_attr=False)
    hoverable: bool | None = reactive_prop(default=None, emit_attr=False)
    href: str | None = reactive_prop(default=None)
    active: Any = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        *,
        variant: str | None = None,
        color: str | None = None,
        padding: str | None = None,
        hoverable: bool | None = None,
        href: str | None = None,
        active: Any = None,
        on_click: Callable[..., Any] | str | None = None,
        on_mouseenter: Callable[..., Any] | str | None = None,
        on_mouseleave: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive ``None`` kwargs
        # (keeps the default) — no more ``if x is not None`` guard to
        # retype.
        super().__init__(
            variant=variant,
            color=color,
            padding=padding,
            hoverable=hoverable,
            href=href,
            active=active,
            on_click=on_click,
            on_mouseenter=on_mouseenter,
            on_mouseleave=on_mouseleave,
            **kwargs,
        )
        # ── The tag switch is decided HERE, not at render ─────────────
        # ``emit_attrs`` removes the attributes a tag cannot carry: decided
        # at render, it would still see a ``<div>`` and throw away the
        # ``href`` just set, leaving a link card with no destination.
        #
        # Deciding early is more correct anyway: ``self._tag`` is read by
        # introspection and by the gates, and a component whose tag only
        # knows itself at render lies to whoever asks it.
        # ``ui.button(href=…)`` does the same.
        if href is not None and "tag" not in kwargs:
            self._tag = "a"
        # Known here, from the call — not read back from the transport
        # attributes at render: a component does not speak HTMX.
        self._acts = on_click is not None

    def render(self) -> Element:
        theme = self._resolved_theme()
        values = self._reactive_values
        padding = values.get("padding") or "md"
        href = values.get("href")
        acts = self._tag == "a" or self._acts

        # ``hoverable=True`` explicit, or implicit when the card links. A
        # ``ghost`` card has no box at rest: the hover background is how a
        # row says it acts, so ``on_click=`` turns it on too.
        explicit_hover = values.get("hoverable")
        is_hoverable = (
            explicit_hover if explicit_hover is not None
            else href is not None or (values.get("variant") == "ghost" and acts)
        )

        # ``overflow-hidden`` (in the root slot) is unconditional: every
        # anchored panel (Select, Tooltip, Dropdown…) is repositioned
        # ``position: fixed`` at open time by ``floating()`` and escapes
        # the clip box natively.
        parts: list[str] = [
            self.compose_class("root"),
            theme.get("paddings", {}).get(padding, ""),
        ]
        if is_hoverable:
            parts.append(self.compose_class("hoverable"))
        # The user classes (``classes=``) are set on the real root by
        # the ``_apply_universal_modifiers`` metaclass wrap — do NOT
        # re-append them here (otherwise a "X X" duplicate). Guarded by
        # test_no_manual_user_class_append.py.

        attrs = self.emit_attrs()
        # A ``<div>`` card that acts on click is a button to the keyboard
        # and to a screen reader: role, a place in the Tab order, Enter /
        # Space — the table row's gesture (``activate_keydown``). Without
        # it, only a mouse could reach it. An ``<a>`` card is all that
        # natively.
        if self._tag != "a" and self._acts:
            attrs.setdefault("role", "button")
            attrs.setdefault("tabindex", "0")
            attrs.setdefault("bz-on:keydown", activate_keydown("$el.click()"))
        if acts:
            parts.append(self.compose_class("focusable"))
        # The active layer is written under ``data-[active=true]:``: set
        # once, it follows the attribute, so a binding only drives the
        # attribute. The literal value paints the first frame, before the
        # runtime has read the binding.
        binding = self._binding_metadata.get("active")
        lit = bool(values.get("active"))
        if lit:
            attrs["data-active"] = "true"
            attrs["aria-current"] = "true"
        if binding is not None:
            expr = binding.binding_path()
            attrs["bz-attr:data-active"] = bool_attr(expr)
            attrs["bz-attr:aria-current"] = f"({expr}) ? 'true' : null"
        if lit or binding is not None:
            parts.append(theme.get("active", ""))
        attrs["class"] = " ".join(p for p in parts if p).strip()

        return Element(
            tag=self._tag,
            attrs=attrs,
            children=self._render_children(),
        )
