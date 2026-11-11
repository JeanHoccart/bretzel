"""The client-side dismiss shared by the alert family."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bretzel.components.base.field_wiring import trigger_event
from bretzel.components.base.scope_wiring import _server_sync_entry
from bretzel.core.tree import Element
from bretzel.runtime import (
    BZ_ON_PREFIX,
)

#: The × button's handler: hides the component client-side AND
#: re-dispatches ``close`` so the server/client ``on_close=`` fires.
DISMISS_TOGGLE_CLICK = "open = false; $dispatch('close')"


def split_icon_flag(icon: Any) -> tuple[Any, bool]:
    """``icon=`` of a feedback component: ``(the icon, suppress the automatic one)``.

    ``False`` removes the icon the colour would pick. A FLAG is judged by
    its value, not its identity: a boolean read from a state arrives stamped
    (``_BoundBool``), not as the ``False`` object.
    """
    if isinstance(icon, bool) or getattr(icon, "_is_bound_bool", False):
        return None, not bool(icon)
    return icon, False


def close_handler_wired(attrs: dict[str, Any]) -> bool:
    """True if a ``close`` handler is wired on ``attrs`` — server
    (``hx-trigger="close"``) or client (``bz-on:close``).

    Encodes the rule "declaring an ``on_close=`` MUST bring out the ×
    affordance that fires it": without it, the handler was a silent
    dead letter (no × ever dispatched ``close``). The peek was copied
    identically into Alert / Badge / Banner.
    """
    return trigger_event(attrs) == "close" or "bz-on:close" in attrs


def dismiss_local_scope(root_attrs: Mapping[str, Any]) -> dict[str, str]:
    """The dismiss's client-local scope: ``bz-data="{open: true}"`` +
    ``bz-show="open"`` to set on the root. Keyed by ``bz-id``; no FOUC
    pre-stamp (the initial ``open: true`` eval is truthy). Shared by
    Alert / Badge / Banner.

    **Who owns ``open``** is read from ``root_attrs``, the root's wiring:

    - a SERVER ``on_close`` receives the close, so it decides whether the
      element still exists — the render it triggers is the truth, and
      ``open`` is re-seeded (``_serverSync``). Without that, the ``false``
      outlived the morph: in a loop without ``key=``, the next chip
      inherited the closed one's positional ``bz-id``, hence its scope,
      and vanished with it
      (``tests/runtime_js/test_a_reported_dismiss_follows_the_server.py``);
    - otherwise the close is the browser's alone, and a neighbouring
      refresh must not reopen it: nothing re-seeds ``open``.
    """
    reported = trigger_event(root_attrs) == "close"
    synced = f", {_server_sync_entry(('open',))}" if reported else ""
    return {"bz-data": f"{{open: true{synced}}}", "bz-show": "open"}


def dismiss_button(
    *,
    button_class: str,
    aria_label: str,
    icon_size: str = "sm",
    on_click: str = DISMISS_TOGGLE_CLICK,
    extra_attrs: dict[str, Any] | None = None,
) -> Element:
    """The × button — ONE emission for the whole framework.

    ``on_click`` defaults to the dismiss's local toggle (feedback family:
    Alert / Badge / Banner). FileUpload overrides it: its × removes ONE
    entry from a list, not the whole component. The gesture differs, the
    CONSTRUCTION is the same, and that is what this helper single-sources,
    as this module does the *wiring* (``DISMISS_TOGGLE_CLICK`` /
    ``dismiss_local_scope`` / ``close_handler_wired``).

    The detach is baked in: the Icon is built then
    :meth:`Component.render_detached`, so a × cannot leak to the root
    through ``serialize_html``.

    The **style strings stay per-theme**: ``button_class`` is composed by
    the caller from ITS theme (we factor out the logic, not the visual
    tokens).

    ⚠️ The × has no ``bz-show`` gating: the three constructors REFUSE a
    ``dismissible=<ClientBinding>`` (``dismissible`` is in no
    ``BINDABLE_PROPS``), and the × lives in any case in a root already
    hidden by ``bz-show="open"``.
    """
    # Deferred: base.component depends on base._wiring, top-level = cycle.
    from bretzel.components.base.component import Component
    from bretzel.components.primitives.icon import Icon

    attrs: dict[str, Any] = {
        "type": "button",
        "class": button_class,
        "aria-label": aria_label,
        f"{BZ_ON_PREFIX}click": on_click,
    }
    if extra_attrs:
        attrs.update(extra_attrs)
    return Element(
        tag="button",
        attrs=attrs,
        children=(Component.render_detached(Icon("x", size=icon_size)),),
    )
