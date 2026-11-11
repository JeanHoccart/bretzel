"""``EmptyState`` — "nothing here yet" placeholder.

Centred column of icon + title + description + optional action(s).
Used wherever a list, table, filtered search, or any data view
returns nothing — gives the user a deliberate signal instead of
an awkward blank area::

    # Standalone, no action.
    ui.empty_state("No tasks yet", icon="inbox")

    # With description.
    ui.empty_state(
        "No matching countries",
        icon="search",
        description="Try a different spelling or clear your filter.",
    )

    # With actions — IS_CONTAINER so the user opens a ``with`` block
    # for any layout / number of buttons they want.
    with ui.empty_state(
        "No issues",
        icon="ticket",
        description="Create your first issue to track work here.",
    ):
        ui.button("New issue", icon_left="plus")

The component is a container (:attr:`IS_CONTAINER`) so the action row content
is the user's own composition ; the theme just provides the
flex-wrap row layout via the ``actions`` slot.

Retro-fit candidates : Combobox's ``empty_text`` filter-empty
state, Table's ``empty_text`` row-empty state, and any list zone
that wants a consistent "no items" presentation.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.feedback.empty_state.theme import EMPTY_STATE_THEME
from bretzel.core.tree import Element, Node


class EmptyState(Component):
    """Centred placeholder for "nothing here yet" surfaces."""

    THEME: ClassVar[dict[str, Any]] = EMPTY_STATE_THEME
    THEME_KEY: ClassVar[str] = "empty_state"
    # message follow filter state without a server round-trip.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    NAMED_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    ICON_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)

    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="muted", emit_attr=False)

    def __init__(
        self,
        title: str | Component | None = None,
        *,
        icon: str | Component | None = None,
        description: str | Component | None = None,
        size: str | None = None,
        color: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            size=size, color=color, icon=icon,
            **kwargs,
        )
        self._title = title
        self._description = description

        # ``size=`` must reach the GLYPH, not only its box. The table
        # already carried an ``icon_size`` token per step, never wired
        # up: the box went from ``h-8`` to ``h-20`` (2.5 times) while the
        # glyph stayed frozen at ``Icon``'s default. Same remedy as
        # Badge's (``adopt_slot(icon_size=…)``) — we only re-size the STRING
        # shortcut; a ``ui.icon(size=…)`` built by the caller carries an
        # explicit intent we do not overwrite.
        if isinstance(icon, str):
            size_map = self._size_row() or {}
            self._slot_components["icon"] = Component.adopt_slot(
                icon, icon_shortcut=True,
                icon_size=size_map.get("icon_size", "lg"),
            )

    def render(self) -> Element:
        slots = self._resolved_theme().get("slots", {})
        children: list[Node] = []

        # ── Icon box (rounded background + icon inside) ─────────────
        icon_component = self._slot_components.get("icon")
        if isinstance(icon_component, Component):
            Component._detach_from_parent(icon_component)
            # Icon tint follows ``color=`` (icon inherits the box's
            # currentColor) ; ``muted`` keeps the original soft look.
            color_key = self._reactive_values.get("color") or "muted"
            # The STEPS: the icon's box descends from the root, so it
            # inherits the bridge the base layer set there — nothing to
            # say. ``muted`` keeps its soft tint written out, which is
            # not a component colour but a resting grey.
            icon_tint = (
                "bg-text/5 text-muted/70" if color_key == "muted"
                else "bg-(--bz-bg) text-(--bz-text)"
            )
            icon_box_class = " ".join(p for p in (
                self.compose_class("icon"),
                icon_tint,
            ) if p)
            # We don't mutate the icon's classes — the rendered span
            # keeps the user's (or auto-built shortcut's) size ; the box
            # provides the tint + dimensions around it.
            icon_render = icon_component.render()
            children.append(
                Element(
                    tag="div",
                    attrs={"class": icon_box_class},
                    children=(icon_render,),
                )
            )

        # ── Title ───────────────────────────────────────────────────
        title_node = self.emit_text_slot(self._title)
        if title_node is not None:
            title_class = self.compose_class("title")
            children.append(
                Element(
                    tag="h3",
                    attrs={"class": title_class},
                    children=(title_node,),
                )
            )

        # ── Description ─────────────────────────────────────────────
        desc_node = self.emit_text_slot(self._description)
        if desc_node is not None:
            desc_class = self.compose_class("description")
            children.append(
                Element(
                    tag="p",
                    attrs={"class": desc_class},
                    children=(desc_node,),
                )
            )

        # ── Actions slot (IS_CONTAINER children) ────────────────────
        body_nodes = list(self._render_children())
        if body_nodes:
            children.append(
                Element(
                    tag="div",
                    attrs={"class": slots.get("actions", "")},
                    children=tuple(body_nodes),
                )
            )

        attrs = self.emit_attrs()
        attrs["class"] = slots.get("root", "")
        attrs.setdefault("role", "status")
        attrs.setdefault("aria-live", "polite")
        return Element(
            tag=self._tag, attrs=attrs, children=tuple(children),
        )


__all__ = ["EmptyState"]
