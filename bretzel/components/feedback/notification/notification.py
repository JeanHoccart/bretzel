"""``ui.notification`` — toast helper, V1 idiom.

Server-side, ``ui.notification("Saved!", color="success")`` is fire-
and-forget : it appends a payload to the request's notification
queue. The partial-renderer drains the queue at end-of-action into
a single ``<bz-patch>{"patches": {"_notifications": […]}}`` tag ;
the bridge (``bridge.js``) recognises that reserved key and
forwards each entry to ``$bz.notify`` (a ``bz:notify`` DOM event),
which the toaster's ``bz-init`` subscription pushes through
``show``. The toaster DOM auto-mounts in ``<body>`` on the first toast.

There is no ``NotificationContainer`` to mount. The runtime owns the
visible DOM and lazily inserts the six corner stacks the very first
time a toast is shown — same UX as V1.

``color=`` takes the four semantic colours (``info`` / ``success`` /
``warning`` / ``error``), pre-compiled in the theme
(``notification/theme.py``) and in sync with the runtime's class map. Any
other colour is refused: the toaster DOM is built in JS, where the Tailwind
compiler cannot see assembled class strings.
"""

from __future__ import annotations

import json
from typing import Any

from bretzel.components.base import ComponentUsageError, reject_component
from bretzel.components.feedback.notification.theme import (
    NOTIFICATION_THEME,
    POSITIONS,
    VARIANTS,
)
from bretzel.core.serialize import serialize
from bretzel.core.tree import Element
from bretzel.render import text

# ───────────────────────────────────────────────────────────────────────────
# Public helper — ``ui.notification(...)``
# ───────────────────────────────────────────────────────────────────────────


def notification(
    message: str,
    *,
    color: str = "info",
    title: str | None = None,
    duration_ms: int = 4000,
    position: str = "top-right",
    dismissible: bool = True,
    icon: str | bool | None = None,
    **retired: Any,
) -> None:
    """Queue a toast to fire at end-of-request.

    Safe to call from action handlers, refreshable bodies, anywhere a
    render context is active. Out-of-context calls are a no-op
    (mirrors how the free :func:`refresh` degrades).

    ``color`` must be one of ``"info"`` / ``"success"`` / ``"warning"``
    / ``"error"`` — these are the four semantic states the framework
    ships with pre-compiled Tailwind classes. Anything else raises
:class:`ComponentUsageError`, as does a ``position`` the theme's
    ``positions`` table does not list. App theme overrides can add new variants ;
    add their names to ``notification/theme.py`` and they'll be
    accepted automatically.

    ``icon`` :
    - ``None`` (default) → use the colour's default icon.
    - ``"rocket"`` (string) → override with a specific Iconify glyph
      from the lucide set.
    - ``False`` → render the toast without any icon at all.
    """

    if retired:
        name = next(iter(retired))
        raise ComponentUsageError(
            f"ui.notification({name}=…): "
            + ("write ``color=``." if name == "variant" else "no such argument.")
        )

    for prop, value, known in (("color", color, VARIANTS),
                               ("position", position, POSITIONS)):
        if value not in known:
            raise ComponentUsageError(
                f"ui.notification: {prop}={value!r} — expected one of "
                f"{sorted(known)}."
            )

    for prop, value in (("message", message), ("title", title)):
        reject_component(
            value,
            owner="ui.notification",
            prop=prop,
            because=(
                "the toast is built in the browser from a JSON payload and "
                "its texts are written with ``bz-text``, which only sets "
                "characters."
            ),
            instead=(
                "For rich content that stays on screen, that is "
                "``ui.alert`` or a ``ui.dialog``."
            ),
        )

    from bretzel.render.context import maybe_current_context

    ctx = maybe_current_context()
    if ctx is None:
        return
    payload: dict[str, Any] = {
        "message": message,
        "variant": color,
        "duration_ms": int(duration_ms),
        "position": position,
        "dismissible": bool(dismissible),
    }
    if title is not None:
        payload["title"] = title
    if icon is False:
        # The runtime treats empty string / false as "no icon at all" —
        # serialise as empty string so JSON.parse on the client gets a
        # value that ``normalise`` recognises as opt-out.
        payload["icon"] = ""
    elif icon is not None:
        payload["icon"] = icon
    ctx.notifications.append(payload)


def _js_object_literal(obj: dict[str, str]) -> str:
    """Build a JS object literal with single-quoted keys/values.

    Single quotes so the result is safe inside double-quoted HTML
    attribute values (``bz-attr:class``, etc.) — double quotes would
    terminate the attribute mid-stream.
    """

    parts = [f"'{k}':'{v}'" for k, v in obj.items()]
    return "{" + ",".join(parts) + "}"


def skeleton_html() -> str:
    """Build the empty toaster skeleton injected into ``<body>`` once
    per page render.

    Six position stacks, each holding an empty ``<template bz-for>``
    over its bucket in the toaster's ``bz-data`` scope
    (``$bz.notification.makeScope()``). The toaster's ``bz-init``
    subscribes to the ``bz:notify`` DOM event (fired by the bridge
    when the server sends a ``_notifications`` patch, or by a direct
    ``$bz.notify(...)`` call) and pushes the toast into the right
    bucket — the ``bz-for`` materialises it.

    All Tailwind classes from the theme appear as **literal attribute
    values** in the HTML — Tailwind scans them on the SSR pass so the
    CSS is ready before the first toast appears. Enter animation is
    pure CSS (the ``bz-toast-enter`` keyframe fires on mount, in the
    shell's ``_NOTIFICATION_ANIM_STYLE``) ; leave is immediate — what
    disappears does not linger.
    """

    theme = NOTIFICATION_THEME
    slots = theme["slots"]
    variant_map = _js_object_literal(theme["variants"])
    accent_map = _js_object_literal(theme["accents"])
    neutral = theme["neutral"]
    # Elements and not ``dismiss_button``: the shell also draws pages with
    # no render context (an error page), where no ``Icon`` can be built.
    dismiss = serialize(Element(
        tag="button",
        attrs={
            "type": "button",
            "bz-show": "t.dismissible",
            "bz-on:click": "dismiss(t.id)",
            "class": slots["dismiss"],
            "aria-label": text("notification.dismiss"),
        },
        children=(Element(
            tag="iconify-icon",
            attrs={"icon": "lucide:x", "style": "font-size: 1rem"},
            children=(),
        ),),
    ))

    stacks: list[str] = []
    for position, position_classes in theme["positions"].items():
        stack = (
            f'<div class="{slots["stack_outer"]} {position_classes}" '
            f'data-bz-notification-position="{position}">'
            f'<div class="{slots["stack_inner"]}">'
            # ``:flip`` opts the stack into FLIP reflow so a dismissed toast's
            # neighbours glide into the freed slot instead of teleporting
            # (cf. runtime bz-for).
            f"<template bz-for=\"t in stacks['{position}'] :key=t.id :flip\">"
            # Toast root + reactive chrome. ``bz-class`` MERGES the
            # variant classes onto the static ``root`` slot (a plain
            # ``bz-attr:class`` would wipe it — cf. traps.md). The static
            # ``bz-toast-enter`` fires the enter keyframe on mount (bz-for
            # is keyed on ``t.id`` so only new toasts animate). No leave
            # class: a dismissed toast goes at once.
            f'<div class="{slots["root"]} bz-toast-enter" '
            f'bz-class="(({variant_map})[t.variant] || \'{neutral}\')" '
            f'role="status" bz-attr:id="t.id">'
            # Icon (only when ``t.icon`` is set)
            f'<iconify-icon class="{slots["icon"]}" '
            f'bz-show="t.icon" '
            f'bz-class="({accent_map})[t.variant]" '
            f"bz-attr:icon=\"'lucide:' + t.icon\" "
            f'style="font-size: 1.25rem"></iconify-icon>'
            # Content : optional title + message
            f'<div class="{slots["content"]}">'
            f'<div class="{slots["title"]}" '
            f'bz-class="({accent_map})[t.variant]" '
            f'bz-show="t.title" bz-text="t.title"></div>'
            f'<div class="{slots["message"]}" bz-text="t.message"></div>'
            f'</div>'
            # Dismiss button
            f"{dismiss}"
            f'</div>'
            f'</template>'
            f'</div>'
            f'</div>'
        )
        stacks.append(stack)

    # ``class="contents"`` makes the wrapper layout-transparent so the
    # six fixed-positioned stacks anchor to the viewport, not to us.
    # NOTHING ELSE goes in this class : transform / opacity utilities
    # on a ``display: contents`` element create a containing block for
    # ``position: fixed`` descendants in some browsers, AND their
    # ``--tw-*`` custom properties inherit to children. Both produce
    # visible layout pollution (the "horizontal cascade" trap).
    #
    # ``bz-data`` builds the toaster's local scope (one bucket per
    # position) ; ``bz-init`` wires the ``bz:notify`` subscription so
    # every server / client notification lands in ``show``.
    return (
        '<div id="bz-notification-root" class="contents" '
        'bz-data="$bz.notification.makeScope()" '
        "bz-init=\"document.addEventListener('bz:notify', "
        '(e) => show(e.detail))">'
        + "".join(stacks)
        + '</div>'
    )


def serialise_pending(notifications: list[dict[str, Any]]) -> str:
    """Render the pending toast queue into a ``<bz-patch>`` block (V3).

    Returns the empty string when the queue is empty so the partial
    render can append it unconditionally without trailing whitespace.

    Output shape : one ``<bz-patch>{"patches":{"_notifications":[…]}}``
    tag. The bridge (``bridge.js``) recognises the reserved
    ``_notifications`` key and forwards each entry to ``$bz.notify`` (a
    ``bz:notify`` DOM event), which the toaster's ``bz-init``
    subscription catches and pushes through ``show``. Replaces the V2
    ``#bz-script-outbox`` inline-``<script>`` injection.
    """
    if not notifications:
        return ""
    from bretzel.core.escape import escape_inline_json
    from bretzel.runtime.protocol import PATCH_TAG_NAME

    payload = escape_inline_json(
        json.dumps(
            {"patches": {"_notifications": list(notifications)}},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return f"<{PATCH_TAG_NAME}>{payload}</{PATCH_TAG_NAME}>"
