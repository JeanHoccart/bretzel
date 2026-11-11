"""The shared render of the ANCHORED overlays — ``Dropdown`` and ``Popover``.

``_modal``'s sibling: same family of components, different mechanics. An
anchored overlay has neither backdrop nor scroll lock; its panel is
teleported into ``<body>`` then positioned by ``$bz.helpers.floating``
against the trigger.

One render, four values
------------------------
``Dropdown`` and ``Popover`` share their render. The difference fits in
four values:

======================  ====================  ==============
                        Dropdown              Popover
======================  ====================  ==============
default alignment       ``start``             ``center``
panel ``role``          ``menu``              ``dialog``
``aria-haspopup``       ``menu``              ``dialog``
close on pick           ``bz-dropdown-pick``  —
======================  ====================  ==============

⚠️ The bound-overlay ref trap (with no scope of its own, the
teleported panel walks up to the shared ``rootScope`` where every
``bztrigger`` tramples the others, and the panel anchors to ANOTHER
overlay's trigger) is explained once, in the render below.

What stays with the caller
---------------------------
The style strings: they arrive **already composed**, this module never
reads a theme.
"""

from __future__ import annotations

from typing import Any

from bretzel.components.base.overlay_wiring import (
    anchored_dismiss_init,
    anchored_panel,
    anchored_trigger_wrapper,
    dispatch_root_effect,
    expand_fit_wrapper,
    floating_placement,
    imperative_listeners,
    teleport_to_body,
    trigger_is_full_width,
)
from bretzel.components.base.scope_wiring import server_sync_marker
from bretzel.core.tree import Element, Node


def render_anchored_overlay(
    component: Any,
    *,
    slots: dict[str, str],
    role: str,
    haspopup: str,
    default_align: str,
    close_on_event: str | None = None,
) -> Element:
    """Wrapped trigger + teleported panel + wired root.

    ``close_on_event`` serves the one thing a dropdown has in addition:
    its items dispatch ``bz-dropdown-pick`` when they are picked, and
    that is what closes the menu. The open expression is computed HERE
    (binding or local flag), so the caller cannot write the listener
    themselves — they name the event, we wire it.
    """
    position = component._reactive_values.get("position") or "auto"
    align = component._reactive_values.get("align") or default_align
    dismissible = bool(component._reactive_values.get("dismissible"))

    # ── The open state: ClientBinding or literal boolean ─────────────
    # The binding lives in ``_binding_metadata``; the raw bool stays in
    # ``_reactive_values`` for the literal case and for the SSR.
    open_binding = component._binding_metadata.get("open")
    bound_open = open_binding is not None
    open_expr = open_binding.binding_path() if bound_open else "open"
    initial_open = bool(component._reactive_values.get("open"))

    # ── Panel ────────────────────────────────────────────────────────
    # The placement belongs to ``$bz.helpers.floating``, attached by the
    # panel's ``bz-effect`` on opening — no static position class.
    panel = anchored_panel(
        css=slots.get("panel", ""),
        children=tuple(component._render_children()),
        open_expr=open_expr,
        placement=floating_placement(position, align),
        role=role,
        attrs={f"bz-on:{close_on_event}": f"{open_expr} = false"} if close_on_event else None,
        # Pre-stamped closed, so nothing paints at (0,0) before the boot.
        closed=not initial_open,
    )

    # ── Trigger ──────────────────────────────────────────────────────
    trigger_nodes: list[Node] = []
    if component._trigger is not None:
        trigger_nodes.append(
            anchored_trigger_wrapper(
                component._trigger.render(),
                open_expr=open_expr,
                haspopup=haspopup,
            )
        )

    # ── Root ─────────────────────────────────────────────────────────
    # A full-width trigger must widen the ``w-fit`` wrapper, otherwise it
    # folds back to the content's width (shared with Tooltip).
    attrs = component.emit_attrs()
    root_slot = slots.get("root", "")
    if trigger_is_full_width([component._trigger]):
        root_slot = expand_fit_wrapper(root_slot)
    # ``classes=`` is set by the metaclass wrap — not here (duplicate).
    attrs["class"] = root_slot

    if not bound_open:
        # A server-backed ``open`` must re-adopt on refresh (``absorb``
        # would otherwise keep the stale scope signal); the guard leaves
        # a client literal alone.
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
    else:
        # Bound: the flag lives in the global store, but the root
        # STILL needs its own scope (an empty literal) so that
        # ``bztrigger`` / ``bzpanel`` isolate per instance. With no scope
        # host, ``findScope`` walks up from the teleported panel to the
        # shared ``rootScope`` — where EVERY bound overlay registers the
        # same ``bztrigger``, last one wins — and the floating helper
        # anchors the panel to ANOTHER overlay's trigger, off screen.
        attrs["bz-data"] = "{}"

    # Open/close dispatch (no scroll lock for an anchored panel),
    # imperative API receivers, Escape + click-outside: the shared
    # anchored wiring (``base/``).
    attrs["bz-effect"] = dispatch_root_effect(open_expr)
    attrs.update(imperative_listeners(open_expr))
    if dismissible:
        attrs["bz-init"] = anchored_dismiss_init(open_expr)

    # The panel teleports into <body> (cf. ``teleport_to_body``).
    return Element(
        tag=component._tag,
        attrs=attrs,
        children=(
            *trigger_nodes,
            teleport_to_body(panel, component),
            *component._event_carrier_nodes(),
        ),
    )


__all__ = ["render_anchored_overlay"]
