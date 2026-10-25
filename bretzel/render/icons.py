"""Icons drawn at the first paint, with the text beside them.

``<iconify-icon>`` draws its glyph once its script has run — the script
is deferred — and once it has the glyph's data — one more request. Until
then the host was EMPTY: the label beside it sat one icon to the left and
jumped when the icon appeared (reported 2026-10-23, with a screenshot).

A full page now carries, for each icon of a set shipped in the wheel:

- its glyph, in a declarative shadow root (``<template
  shadowrootmode>``): the browser draws it while parsing, no script;
- its data, in a JSON block (``#bz-icons``) the shell's icons script
  hands to the component as it registers: when the component upgrades
  the host it empties that root, and draws again from this data in the
  same task (the same script makes its first check synchronous) — no
  request, no empty frame. A data block, not a script: the CSP only lets
  the shell's fixed inline scripts run (``server/security.py``).

Only on a full page: a fragment that htmx swaps in is parsed without its
shadow roots. Its icons rely on the preloaded data, else on the request,
in a box the CSS keeps at ``1em`` (``theme/css.py``, ``_ICON_BOX``).

Added after the zones are stamped, so the fingerprints of the zone diff
(``zone_diff.py``) never see it: a partial render has no glyphs either.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from bretzel.core.tree import Element, FragmentNode, HtmlNode, Node
from bretzel.render.vendor import packaged_glyph
from bretzel.runtime.protocol import ICONS_DATA_ID

ICON_TAG = "iconify-icon"

#: What the component writes in its own shadow root (``:host`` without
#: the ``inline`` attribute): the glyph must look the same before and
#: after the upgrade.
_HOST_STYLE = ":host{display:inline-block;vertical-align:0}span,svg{display:block}"

#: Attributes that change how the component draws the glyph: an icon
#: carrying one is left to the component.
_CUSTOMISED = frozenset({"width", "height", "rotate", "flip", "mode", "inline"})


def with_glyphs(nodes: Sequence[Node]) -> tuple[list[Node], str]:
    """``nodes`` with each static icon's glyph inside it, and the JSON
    block of their data (``""`` when there is none)."""
    glyphs: dict[str, tuple[str, int, int]] = {}
    roots: dict[str, Element] = {}
    out = [_fill(node, glyphs, roots) for node in nodes]
    if not glyphs:
        return out, ""
    sets: dict[str, dict] = {}
    for icon, (body, width, height) in glyphs.items():
        prefix, _, name = icon.partition(":")
        entry = sets.setdefault(prefix, {"prefix": prefix, "icons": {}})
        entry["icons"][name] = {"body": body, "width": width, "height": height}
    payload = json.dumps(list(sets.values()), separators=(",", ":")).replace("</", "<\\/")
    return out, f'<script type="application/json" id="{ICONS_DATA_ID}">{payload}</script>'


def _fill(node: Node, glyphs: dict[str, tuple[str, int, int]],
          roots: dict[str, Element]) -> Node:
    """``node`` with its icons' glyphs, rebuilt only along the paths that
    change: this walks every element of a full page."""
    if isinstance(node, Element):
        if node.tag == ICON_TAG:
            return _with_glyph(node, glyphs, roots)
        if node.tag == "template":
            return node
    elif not isinstance(node, FragmentNode):
        return node
    kids = node.children
    out: list[Node] | None = None
    for i, kid in enumerate(kids):
        if not isinstance(kid, (Element, FragmentNode)):
            continue
        new = _fill(kid, glyphs, roots)
        if new is not kid:
            if out is None:
                out = list(kids)
            out[i] = new
    if out is None:
        return node
    if isinstance(node, Element):
        return Element(node.tag, node.attrs, tuple(out))
    return FragmentNode(tuple(out))


def _with_glyph(node: Element, glyphs: dict[str, tuple[str, int, int]],
                roots: dict[str, Element]) -> Element:
    icon = node.attrs.get("icon")
    if (node.children or not isinstance(icon, str)
            or any(name in node.attrs for name in _CUSTOMISED)):
        return node
    root = roots.get(icon)
    if root is None:
        glyph = packaged_glyph(icon)
        if glyph is None:
            return node
        glyphs[icon] = glyph
        body, width, height = glyph
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width / height:g}em" '
               f'height="1em" viewBox="0 0 {width} {height}">{body}</svg>')
        root = roots[icon] = Element("template", {"shadowrootmode": "open"},
                                     (HtmlNode(f"<style>{_HOST_STYLE}</style>{svg}"),))
    return Element(node.tag, node.attrs, (root,))
