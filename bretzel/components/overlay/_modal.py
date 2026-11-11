"""The shared render of the two modal overlays — ``Dialog`` and ``Drawer``.

One component rendered twice
----------------------------
``Dialog`` and ``Drawer`` are not two components that resemble each
other, it is one component rendered twice, whose whole difference fits
in three style values: the width class (the drawer picks it on TWO axes
depending on the side), what the side adds to the panel, what it adds to
the container.

What stays with the caller
---------------------------
The style strings. They stay per-component and arrive here **already
composed**: this module never reads a theme, it assembles nodes.

⚠️ The drawer's closed translation class
(``data-[open=false]:translate-x-full``) is already COMPLETE in its theme
and cannot be assembled here — a Tailwind class assembled at runtime is
invisible to the compiler and only exists in dev.
"""

from __future__ import annotations

from typing import Any

from bretzel.components.actions.icon_button import IconButton
from bretzel.components.base import Component
from bretzel.components.base.arguments import has_content, shown
from bretzel.components.base.overlay_wiring import (
    escape_init,
    focus_trap_effect,
    imperative_listeners,
    modal_root_effect,
    show_attrs,
)
from bretzel.components.base.scope_wiring import server_sync_marker
from bretzel.core.tree import Element, Node
from bretzel.render import text


def render_modal_overlay(
    component: Any,
    *,
    slots: dict[str, str],
    panel_extra: tuple[str, ...] = (),
    container_extra: tuple[str, ...] = (),
) -> Element:
    """Backdrop + container + panel (header, body) + wired root.

    ``panel_extra`` is what follows ``slots["panel"]`` on the panel — the
    width class for a dialog, plus the two side classes for a drawer.
    **The order belongs to the caller**: two utilities of the same family
    and the same specificity are decided by the SHEET's order, not by the
    ``class=``'s, but the order stays what the component wrote and a gate
    watches it (``test_no_same_specificity_conflict``).
    """
    # ``shown``: a bound title is drawn live,
    # and ``aria-labelledby`` points at it by id, so the name follows too.
    # ``has_content`` below because a binding refuses ``if title:``.
    title = shown(component, "title")
    has_title = has_content(title)
    dismissible = bool(component._reactive_values.get("dismissible"))
    persistent = bool(component._reactive_values.get("persistent"))

    # ── The open state: ClientBinding or literal boolean ─────────────
    # When the user passes a ClientBinding, the base layer filed it in
    # ``_binding_metadata`` and left the raw bool in ``_reactive_values``
    # for the SSR. We branch here.
    open_binding = component._binding_metadata.get("open")
    bound_open = open_binding is not None
    # ``$bz.state.<Class>.<key>.<field>`` — the exact path the binding's
    # ``.set()`` / ``.toggle()`` writes to. Otherwise, a flag local to
    # this overlay's scope.
    open_expr = open_binding.binding_path() if bound_open else "open"
    initial_open = bool(component._reactive_values.get("open"))

    title_id = f"{component.id}_title" if component.id and has_title else None

    # ── Backdrop ─────────────────────────────────────────────────────
    # A persistent overlay SWALLOWS the backdrop click; a dismissible one
    # closes. In both cases the click never reaches a descendant of the
    # panel: the panel lives in a SIBLING element.
    backdrop_attrs: dict[str, Any] = {
        "class": slots.get("backdrop", ""),
        **show_attrs(open_expr, initial_open),
        "aria-hidden": "true",
    }
    if dismissible and not persistent:
        backdrop_attrs["bz-on:click"] = f"{open_expr} = false"
    backdrop = Element(tag="div", attrs=backdrop_attrs, children=())

    # ── Panneau ──────────────────────────────────────────────────────
    panel_attrs: dict[str, Any] = {
        "class": " ".join(
            p for p in (slots.get("panel", ""), *panel_extra) if p
        ),
        "role": "dialog",
        "aria-modal": "true",
        **show_attrs(open_expr, initial_open),
        # Focus trap while it is open: Tab/Shift+Tab cycle inside the
        # panel, the first focusable child gets the focus, and the
        # previously focused element is restored on close
        # (``$bz.helpers.focusTrap`` returns its own dispose).
        "bz-effect": focus_trap_effect(open_expr),
    }
    if title_id:
        panel_attrs["aria-labelledby"] = title_id

    panel_children: list[Node] = []

    # Header (title + close button) — only if there is a title OR
    # something to close with, so a persistent confirmation overlay can
    # do without it entirely with ``title=None``.
    if has_title or dismissible:
        header_children: list[Node] = []
        if has_title:
            title_attrs: dict[str, Any] = {"class": slots.get("title", "")}
            if title_id:
                title_attrs["id"] = title_id
            header_children.append(
                Element(
                    tag="h2",
                    attrs=title_attrs,
                    children=(component.emit_text_slot(title),),
                )
            )
        if dismissible:
            close_btn = IconButton(
                "x",
                variant="ghost",
                size="sm",
                color="muted",
                aria_label=text("modal.close"),
                on_click=f"{open_expr} = false",
            )
            Component._detach_from_parent(close_btn)
            header_children.append(
                Element(
                    tag="div",
                    attrs={"class": slots.get("close", "")},
                    children=(close_btn.render(),),
                )
            )
        panel_children.append(
            Element(
                tag="div",
                attrs={"class": slots.get("header", "")},
                children=tuple(header_children),
            )
        )

    # Body — every child captured in the ``with``.
    body_nodes = list(component._render_children())
    if body_nodes:
        panel_children.append(
            Element(
                tag="div",
                attrs={"class": slots.get("body", "")},
                children=tuple(body_nodes),
            )
        )

    panel = Element(tag="div", attrs=panel_attrs, children=tuple(panel_children))

    # ── Container ────────────────────────────────────────────────────
    # It places the panel and provides the click-outside surface. We do
    # NOT put ``bz-on:click`` there: the panel is its child, the click
    # would bubble — it is the backdrop that carries the close.
    container = Element(
        tag="div",
        attrs={
            "class": " ".join(
                p for p in (slots.get("container", ""), *container_extra) if p
            ),
            **show_attrs(open_expr, initial_open),
        },
        children=(panel,),
    )

    # ── Racine ───────────────────────────────────────────────────────
    attrs = component.emit_attrs()
    # ``contents`` removes the wrapper from the layout flow, so the
    # ``fixed`` children anchor on the viewport and not on its box.
    attrs["class"] = "contents"
    if not bound_open:
        # ``open`` lives in the local scope, which ``absorb``
        # PRESERVES across a morph — so an ``open=state.field`` driven by
        # the SERVER would be ignored on refresh if the key does not ask
        # for ``_serverSync``. We gate on "server-backed": a literal
        # ``open=True`` must, for its part, keep its client state across
        # an unrelated refresh.
        #
        # The single dialect: ``_value_server_backed`` answers "where
        # does my value come from" (and returns False on a binding, so it
        # stays correct even outside this ``if``).
        sync = server_sync_marker(
            "open", enabled=component._value_server_backed("open")
        )
        attrs["bz-data"] = (
            "{open: " + ("true" if initial_open else "false")
            + (f",{sync}" if sync else "") + "}"
        )
    # Scroll lock + open/close dispatch (root bz-effect), imperative
    # API receivers, Escape to close: the shared overlay wiring (cf.
    # ``base/``).
    attrs["bz-effect"] = modal_root_effect(open_expr)
    attrs.update(imperative_listeners(open_expr))
    if dismissible and not persistent:
        attrs["bz-init"] = escape_init(open_expr)

    return Element(
        tag=component._tag,
        attrs=attrs,
        children=(backdrop, container, *component._event_carrier_nodes()),
    )


__all__ = ["render_modal_overlay"]
