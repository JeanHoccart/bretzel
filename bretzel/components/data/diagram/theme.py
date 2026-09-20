"""Default theme for :class:`Diagram`.

A directed graph rendered in layers: the nodes are positioned HTML, the
edges an ``<svg>`` layer behind them. It is that split that decides the
theme — the node slots are ordinary Tailwind classes (so a node has a
focus ring, truncation, a hover tint like any control), and the edge
slots are SVG presentation attributes.

Slots :

- ``root``      : the scrolling container, IN X only. It is the REAL
  root — ``id`` / ``classes=`` / ``attrs=`` / ``visible`` / ``tooltip``
  land there. A graph wider than the page is scrolled, it does not
  shrink; its HEIGHT, for its part, is its content's, and it is up to
  the parent to decide whether to bound it. Two bars in two rectangles
  is what you get otherwise.
- ``canvas``    : the positioned box inside, at the dimensions the
  layout engine computed. ``relative``, because each node is
  ``absolute`` relative to it.
- ``edges``     : the edge layer's ``<svg>`` — ``absolute inset-0`` and
  above all ``pointer-events-none``, without which it would swallow the
  clicks meant for the nodes it covers.
- ``node``      : a node's positioned wrapper — ``absolute``, the radius
  (which the focused node's ring hugs) and the click affordance. No
  decoration: border and background live on ``node_body``, otherwise a
  home-made ``render=`` would get them ON TOP of its own. Its position
  and size arrive as an inline style (cf. the warning below).
- ``node_body`` : a node's default card, when no ``render=`` is
  supplied. Border, background, rounded corner, and the focus ring.
- ``node_focus``: the node the view is centred on. ONE marker only, set
  on the body — on the wrapper it produced a second line one pixel from
  the body's.
- ``node_dim``  : a node no edge links to the one just designated. An
  opacity only: it stays readable and clickable.
- ``label``     : a default node's text.
- ``empty``     : the word shown when the graph is empty.

``edge`` / ``edge_flipped`` / ``edge_dim`` are **classes carried by the
``<path>``**. They use Tailwind's ``stroke-*`` utilities, so an edge's
colour follows the theme like the rest and not a hard-coded value.

``sizes`` carries the geometry, in NUMBERS, because the layout needs it
before rendering anything — it is the same convention as the charts
(``bar_chart`` files ``h``, ``axis``, ``pad`` there).

Sizes :

- ``w`` / ``h``   : a node's size. **Fixed per step**: the server does
  not measure text, so the width is decided in advance or one would have
  to re-lay out on the client. A node that needs room goes through
  ``ui.node(width=…)``.
- ``layer``       : the gap between two layers — it is the visible
  length of the edges.
- ``lane``        : the gap between two nodes of the same layer.
- ``text``        : the label's typographic class.
- ``icon`` / ``badge`` : the steps the default render passes to
  ``ui.icon`` and ``ui.badge``. They live here and not hard-coded in the
  render, otherwise a ``ui.diagram(size="xl")`` would keep icons the
  size of an ``sm`` — the defect of the chips frozen in a combobox.

⚠️ **A node's position and size will NEVER go through a class.**
``left-[240px]`` is an ASSEMBLED class: the production Tailwind compiler
only sweeps literals, so it exists in dev only, the HTML is identical on
both sides and the page falls apart in production only. The coordinates
go in an inline ``style=``, and that is also what guarantees the drawn
box is exactly the one the engine placed.
"""

from __future__ import annotations

from typing import Any

DIAGRAM_THEME: dict[str, Any] = {
    "slots": {
        # It scrolls in X, and IN X ONLY.
        #
        # `overflow-auto` (both axes) made this component the only one in
        # the catalogue to scroll vertically — measured: every other
        # scrolling container (`table`, `carousel`, `file_upload`) writes
        # `overflow-x-auto`. The price showed as soon as you put it in a
        # bounded column: the column scrolled AND the diagram scrolled,
        # two bars in two different rectangles, one inside the other
        # outside.
        #
        # A layered layout grows SIDEWAYS, not downwards: the height is
        # that of the fullest layer, and it is up to the parent — the
        # page, or a `ui.pane` — to decide whether it scrolls.
        "root": (
            # No `bg-`: the root inherits from the page, like
            # `ui.table`'s. A background set here is tinted by the colour
            # bridge, so the WHOLE surface takes the colour — it is a
            # wash, not an accent, and it crushes the drawing.
            "bz-diagram "  # marqueur d'audit — cf. tests/audit/checklist.py
            "relative overflow-x-auto max-w-full rounded-box "
            "border-(length:--bz-stroke) border-text/10"
        ),
        # The placed box. Its dimensions arrive as an inline style.
        "canvas": "relative",
        # The edge layer. `pointer-events-none` is structural: it
        # covers the nodes, so without it no click would reach a node —
        # and that only shows on trying it, never on re-reading.
        "edges": "absolute inset-0 pointer-events-none overflow-visible",
        # A node's wrapper: the positioning, plus the RADIUS.
        #
        # The radius is not decorative here: it is what the focused
        # node's ring follows. Without it the ring is a RECTANGLE around
        # a rounded node — two concentric shapes that do not coincide,
        # which shows immediately and is fixed in this place only.
        # `cursor-pointer` UNCONDITIONALLY, and it is not an
        # approximation: a node ALWAYS answers a click — it lights up its
        # neighbours even with no `on_item_click=`. Reserving it for
        # nodes carrying a server handler would lie the other way.
        # `select-none` with it: without that a slightly firm click
        # highlights the label instead of designating the node.
        "node": "absolute rounded-box cursor-pointer select-none",
        # The default card. `h-full w-full` so it fills exactly the box
        # the engine reserved — otherwise the drawing and the layout
        # diverge by a pixel or two per node.
        #
        # ⚠️ Where the colour goes, and where it does NOT. The BACKGROUND
        # stays neutral (`bg-surface`): a coloured step there tints the
        # whole box, and twenty tinted boxes make a wash that crushes the
        # drawing. The BORDER, for its part, reads the bridge's step
        # (`--bz-border`), so `color=` shows — an outline, not a flat
        # fill. Without that `color=` does NOTHING any more, and a kwarg
        # that does nothing is this repository's dominant failure mode.
        "node_body": (
            "h-full w-full flex items-center gap-2 px-3 rounded-box "
            "border-(length:--bz-stroke) border-(--bz-border) bg-surface "
            "transition-[opacity,background-color,border-color] "
            # The hover: it had DISAPPEARED when the palette was
            # neutralised. A clickable node that does not react to the
            # pointer no longer signals itself as clickable.
            "hover:bg-(--bz-bg) hover:border-(--bz-border-hover) "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus)"
        ),
        # The node the view is centred on. A ring on the wrapper —
        # which now carries the same radius as the body, so it hugs it
        # instead of framing it.
        "node_focus": "ring-2 ring-(--bz-focus)",
        # The dimming, when another node is designated. An opacity and
        # nothing else: the node stays readable and clickable, it just
        # moves to the background.
        "node_dim": "opacity-25",
        "label": "truncate",
        # The empty state's wrapper. The CONTENT, for its part, is a
        # real `ui.empty_state` — not a grey text dropped in the middle.
        "empty": "p-6",
    },
    # The edges. `fill-none` is mandatory: a `<path>` is filled by
    # default, so a curve without it shows as a black blob.
    # The bridge's BORDER step, not a flat fill: an edge follows the
    # component's colour without catching the eye. It is the other place
    # — along with the nodes' outline — where `color=` stays visible.
    "edge": "fill-none stroke-(--bz-border) stroke-[1.5]",
    "edge_flipped": (
        "fill-none stroke-(--bz-border) stroke-[1.5] [stroke-dasharray:4_3]"
    ),
    "edge_dim": "fill-none stroke-(--bz-border) stroke-[1.5] opacity-15",
    # The standard enum's five steps. Missing one does not raise: the
    # render falls back on `md` in silence, so a `size="xl"` would be
    # SMALLER than a neighbour at the same step.
    "sizes": {
        "xs": {"w": 100, "h": 30, "layer": 44, "lane": 10,
               "text": "text-xs", "icon": "xs", "badge": "xs"},
        "sm": {"w": 120, "h": 36, "layer": 56, "lane": 14,
               "text": "text-xs", "icon": "xs", "badge": "xs"},
        "md": {"w": 160, "h": 44, "layer": 72, "lane": 20,
               "text": "text-sm", "icon": "sm", "badge": "sm"},
        "lg": {"w": 200, "h": 52, "layer": 88, "lane": 26,
               "text": "text-base", "icon": "md", "badge": "md"},
        "xl": {"w": 240, "h": 60, "layer": 104, "lane": 32,
               "text": "text-lg", "icon": "lg", "badge": "md"},
    },
}
