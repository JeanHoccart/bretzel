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
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("title", "description")

    NAMED_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    ICON_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)

    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="muted", emit_attr=False)

    def __init__(
        self,
        title: Any = None,
        *,
        icon: str | Component | None = None,
        description: Any = None,
        size: str | None = None,
        color: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            size=size, color=color, icon=icon,
            **kwargs,
        )
        # ``adopt_slot`` laisse passer string / ClientBinding intacts (donc
        # ``emit_text_slot`` voit toujours le binding) et détache un
        # Component, qui sinon rend deux fois. Cf. traps.md § « Slot
        # Component stocké sans adopt_slot ».
        self._title = Component.adopt_slot(title)
        self._description = Component.adopt_slot(description)

        # ``size=`` doit atteindre le GLYPHE, pas seulement sa boîte. La
        # table portait déjà un token ``icon_size`` par palier, jamais
        # branché : la boîte passait de ``h-8`` à ``h-20`` (2,5 fois) pendant
        # que le glyphe restait figé au défaut d'``Icon``. Même remède que
        # Badge (``_adopt_icon``) — on ne re-taille QUE le raccourci
        # string ; un ``ui.icon(size=…)`` construit par l'appelant porte
        # une intention explicite qu'on n'écrase pas.
        if isinstance(icon, str):
            from bretzel.components.primitives.icon.icon import Icon

            size_map = self._resolved_theme().get("sizes", {}).get(
                self._reactive_values.get("size") or "md", {}
            )
            self._slot_components["icon"] = Component.adopt_slot(
                Icon(icon, size=size_map.get("icon_size", "lg")),
                icon_shortcut=True,
            )

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        sizes = theme.get("sizes", {})

        size_key = self._reactive_values.get("size") or "md"
        size_map = sizes.get(size_key, sizes.get("md", {}))

        children: list[Node] = []

        # ── Icon box (rounded background + icon inside) ─────────────
        icon_component = self._slot_components.get("icon")
        if isinstance(icon_component, Component):
            Component._detach_from_parent(icon_component)
            # Icon tint follows ``color=`` (icon inherits the box's
            # currentColor) ; ``muted`` keeps the original soft look.
            color_key = self._reactive_values.get("color") or "muted"
            # Les PALIERS : la boîte d'icône descend de la racine, donc
            # elle hérite du pont que le socle y a posé — rien à redire.
            # ``muted`` garde sa teinte douce écrite en dur, qui n'est pas
            # une couleur de composant mais un gris de repos.
            icon_tint = (
                "bg-text/5 text-muted/70" if color_key == "muted"
                else "bg-(--bz-bg) text-(--bz-text)"
            )
            icon_box_class = " ".join(p for p in (
                slots.get("icon", ""),
                icon_tint,
                size_map.get("icon_box", ""),
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
            title_class = " ".join(p for p in (
                slots.get("title", ""),
                size_map.get("title", ""),
            ) if p)
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
            desc_class = " ".join(p for p in (
                slots.get("description", ""),
                size_map.get("description", ""),
            ) if p)
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
