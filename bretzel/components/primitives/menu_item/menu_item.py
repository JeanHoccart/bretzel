"""``MenuItem`` — shared base for clickable menu rows.

One clickable row : ``icon_left`` + ``label`` + ``icon_right`` + optional
right-aligned ``shortcut``, colour-tinted via ``color``, rendered as
``<button>`` (default) or ``<a>`` (when ``href`` given). On click it
dispatches a bubbling ``bz-dropdown-pick`` CustomEvent so the enclosing
menu closes itself.

Concrete subclasses set ``THEME`` + ``THEME_KEY`` and nothing else —
:class:`~bretzel.components.overlay.dropdown.DropdownItem` and
:class:`~bretzel.components.navigation.sidebar.SidebarFooterItem` are thin
shells so the row logic lives in ONE place (primitives/, importable by any
group — no cross-group cycle, anti-rule 5).

Theme contract — the subclass theme must expose slots ``root`` /
``icon_left`` / ``label`` / ``icon_right`` / ``shortcut`` and a ``colors``
map (semantic → tint classes).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import bool_attr
from bretzel.core.tree import Element, Node

# The bubbling event every menu row fires on click ; the enclosing menu panel
# listens (``bz-on:bz-dropdown-pick``) and flips its open flag. Generic despite
# the Dropdown-flavoured name.
MENU_PICK_EVENT = "bz-dropdown-pick"


class MenuItem(Component):
    """Base clickable menu row. Subclasses provide ``THEME``/``THEME_KEY``."""

    DEFAULT_TAG: ClassVar[str] = "button"
    IS_CONTAINER: ClassVar[bool] = False
    EVENTS: ClassVar[tuple[str, ...]] = ("click",)
    # Curated reactive surface — disabled (item locked). color is design-time.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("disabled",)

    color: str | None = reactive_prop(default=None, emit_attr=False)
    disabled: bool = reactive_prop(default=False)

    def __init__(
        self,
        *,
        label: str | Component | None = None,
        icon_left: str | Component | None = None,
        icon_right: str | Component | None = None,
        shortcut: str | None = None,
        href: str | None = None,
        color: str | None = None,
        disabled: bool | None = None,
        on_click: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            color=color, disabled=disabled, on_click=on_click, **kwargs
        )
        # ``label=`` and ``shortcut=`` are textual slots: they accept
        # ``str | ClientBinding | Component``. ``adopt_slot`` detaches a
        # Component so it does not ALSO render on its own in the
        # surrounding scope.
        self._label = Component.adopt_slot(label)
        self._href = href
        self._shortcut = Component.adopt_slot(shortcut)
        # String icon shortcuts (``icon_left="pencil"`` → ``Icon("pencil")``)
        # ; adopt_slot wraps + detaches from the active parent.
        self._icon_left: Component | None = Component.adopt_slot(
            icon_left, icon_shortcut=True
        )
        self._icon_right: Component | None = Component.adopt_slot(
            icon_right, icon_shortcut=True
        )

    @staticmethod
    def _slotted_icon(icon: Component, slot_class: str) -> Element:
        """Render an icon component and prepend the slot class to it."""
        ic = icon.render()
        return Element(
            tag=ic.tag,
            attrs={
                **ic.attrs,
                "class": f"{slot_class} {ic.attrs.get('class', '')}".strip(),
            },
            children=ic.children,
        )

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        colors = theme.get("colors", {})

        # Always tint — a plain row uses the ``neutral`` entry, a coloured one
        # its semantic tint. Keeping bg states in ``colors`` (not ``root``)
        # means a coloured item's hover wins cleanly, no same-layer clash.
        color = self._reactive_values.get("color")
        color_cls = colors.get(color or "neutral", "")

        children: list[Node] = []
        if self._icon_left is not None:
            children.append(
                self._slotted_icon(self._icon_left, slots.get("icon_left", ""))
            )
        if isinstance(self._label, Component):
            # A Component keeps its own root — wrapping it in the
            # ``label`` slot's span would impose the row's typography on
            # it, which is precisely what rich content comes to replace.
            children.append(self._label.render())
        else:
            # ``emit_text_slot`` returns ``None`` for ``None`` AND for
            # the empty string — a single guard covers both, hence the
            # absence of an ``if self._label is not None`` around this
            # block.
            label_node = self.emit_text_slot(self._label)
            if label_node is not None:
                children.append(
                    Element(
                        tag="span",
                        attrs={"class": slots.get("label", "")},
                        children=(label_node,),
                    )
                )
        if self._icon_right is not None:
            children.append(
                self._slotted_icon(self._icon_right, slots.get("icon_right", ""))
            )
        shortcut_node = self.emit_text_slot(self._shortcut)
        if shortcut_node is not None:
            children.append(
                Element(
                    tag="span",
                    attrs={"class": slots.get("shortcut", "")},
                    children=(shortcut_node,),
                )
            )

        # base row + optional colour tint ; ``classes=`` set by the
        # metaclass wrap — not here (duplicate).
        root_class = " ".join(
            p for p in (slots.get("root", ""), color_cls) if p
        )

        attrs = self.emit_attrs()
        attrs["class"] = root_class
        attrs.setdefault("role", "menuitem")

        disabled = bool(self._reactive_values.get("disabled"))
        disabled_binding = self._binding_metadata.get("disabled")
        if disabled_binding is not None:
            # ⚠️ The REACTIVE path. Everything the static branch below
            # does is decided AT CONSTRUCTION, so never when ``disabled``
            # is driven by a binding: the value at render is ``False``,
            # the branch is not taken, and the automatic emission set
            # ``bz-attr:disabled`` on an ``<a>`` — an attribute that does
            # not exist on an anchor, so nothing at all. Measured on
            # 2026-08-13: ``ui.dropdown_item(disabled=binding)`` kept its
            # ``href``, its ``bz-on:click`` and the look of an active
            # entry.
            #
            # Rewriting it as ``aria-disabled`` is what fixes all THREE
            # halves at once: the theme already dresses the state through
            # its ``aria-disabled:`` variants, a screen reader announces
            # it, and the runtime base layer derives the inertness from it
            # (``$bz._inert``) — click, navigation and server action.
            path = self.path_of(disabled_binding)
            attrs.pop("bz-attr:disabled", None)
            attrs["bz-attr:aria-disabled"] = bool_attr(path)
            attrs["bz-attr:tabindex"] = f"({path}) ? '-1' : null"
        if disabled:
            # A disabled row must announce itself to AT AND show
            # ``cursor-not-allowed`` on hover. Both rule out native
            # ``disabled`` <button> and ``pointer-events-none`` — each drops
            # every pointer event, so the not-allowed cursor never paints. Go
            # aria-only, keep the hit-test LIVE, and strip the interaction
            # wiring here instead. ``tabindex=-1`` pulls it from the tab order.
            attrs["aria-disabled"] = "true"
            attrs["tabindex"] = "-1"
            attrs.pop("disabled", None)  # native disabled would kill the cursor
            # Drop every wired handler (server ``hx-post`` + HMAC stamp AND
            # client ``bz-on:`` expressions) — ``_event_attrs`` is exactly
            # that set — so a live-hit-test row still does nothing on click.
            for key in self._event_attrs:
                attrs.pop(key, None)
        else:
            # Close the enclosing menu on click — append to any client click
            # handler, coexist with a server ``hx-post``.
            existing_click = attrs.get("bz-on:click")
            close_dispatch = f"$dispatch('{MENU_PICK_EVENT}')"
            attrs["bz-on:click"] = (
                f"{existing_click}; {close_dispatch}"
                if existing_click else close_dispatch
            )

        if self._href:
            # ``disabled`` links carry no ``href`` (inert), enabled ones do.
            if not disabled:
                attrs["href"] = self._href
            return Element(tag="a", attrs=attrs, children=tuple(children))
        # Only if the tag is still a button. ``type`` set here and not
        # by ``emit_attrs`` — so out of reach of the central guard —
        # landed as is on a custom ``tag=``, where it names a MIME type.
        # Gated by ``test_a_changed_tag_drops_what_it_cannot_carry``.
        if self._tag == "button":
            attrs.setdefault("type", "button")
        return Element(tag=self._tag, attrs=attrs, children=tuple(children))
