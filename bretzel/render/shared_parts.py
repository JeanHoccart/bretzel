"""Parts a page carries ONCE, cloned where they are needed.

A component whose hidden panel is the same from one instance to the next —
a calendar picker's header (arrows, month and year menus), a colour
picker's palette — does not ship it with every
instance. It registers the part here; the page carries ONE ``<template
data-bz-part>`` per distinct part (its key is the hash of its HTML and of
the template's attributes), and the instance names it on its host
(``data-bz-part="<key>"``). The runtime clones it into the host the first
time it opens (``$bz.parts.fill``, ``helpers.js``) — and again after a
morph took it out, since the server never renders it. A part never opened
costs the DOM nothing.

Emitted by the page pipeline (end of a full page, end of a partial
navigation's outlet) and by ``render_partial`` (appended to ``<body>``
out of band — the runtime keeps one per key).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from bretzel.core.serialize import serialize
from bretzel.core.tree import Element, Node
from bretzel.render.context import maybe_current_context

__all__ = [
    "PART_ATTR",
    "graft_shared_parts",
    "share_part",
    "shared_part_templates",
]

#: On the host: the key of the part it clones in.
PART_ATTR = "data-bz-part"


def share_part(
    children: tuple[Node, ...], *, template_attrs: Mapping[str, str] | None = None,
) -> str | None:
    """Register ``children`` as a part of the page; return its key.

    ``template_attrs`` ride on the ``<template>`` (the calendar's theme,
    read by the runtime from there). ``None`` outside a render context: the
    caller then renders the children in place, as before.
    """
    ctx = maybe_current_context()
    if ctx is None:
        return None
    attrs = dict(template_attrs or {})
    html = "".join(serialize(c) for c in children)
    key = hashlib.sha1(
        (json.dumps(attrs, sort_keys=True) + html).encode()).hexdigest()[:12]
    ctx.shared_parts.setdefault(key, (attrs, children))
    return key


def shared_part_templates(ctx: Any, *, oob: bool = False) -> str:
    """The ``<template>`` of each part this render shared, once each."""
    parts = getattr(ctx, "shared_parts", None)
    if not parts:
        return ""
    html = "".join(
        serialize(Element(
            tag="template",
            attrs={PART_ATTR: key, **attrs},
            children=children,
        ))
        for key, (attrs, children) in parts.items()
    )
    return f'<div hx-swap-oob="beforeend:body">{html}</div>' if oob else html


def graft_shared_parts(node: Node, ctx: Any) -> Node:
    """``node`` with every shared part put back in its host.

    What the browser holds once the parts were cloned: the part's nodes
    after the host's leading hidden inputs, the template's attributes on
    the host. For the benches and gates that read a component's tree —
    without it, a picker's menus or swatches would be invisible to them.
    """
    parts = getattr(ctx, "shared_parts", None)
    if not parts or not isinstance(node, Element):
        return node
    children = tuple(graft_shared_parts(c, ctx) for c in node.children)
    key = node.attrs.get(PART_ATTR)
    if key in parts:
        attrs, part = parts[key]
        lead = 0
        while (lead < len(children) and isinstance(children[lead], Element)
               and children[lead].tag == "input"
               and children[lead].attrs.get("type") == "hidden"):
            lead += 1
        children = (*children[:lead], *part, *children[lead:])
        return Element(tag=node.tag, attrs={**node.attrs, **attrs}, children=children)
    return Element(tag=node.tag, attrs=node.attrs, children=children)
