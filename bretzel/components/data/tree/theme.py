"""Default :class:`Tree` / :class:`TreeNode` theme.

A tree is a recursive disclosure list : each *branch* (a node that owns
children) collapses independently, each *leaf* is terminal. The visual
grammar is deliberately close to a file explorer :

- **chevron** — a right-pointing triangle when closed, down when open.
  Rendered as **two glyphs toggled by ``bz-show``** (per-node inline
  ``display``), NOT a CSS class swap : ``group-data-[open]:hidden`` both
  loses to the ``<iconify-icon>`` baked-in ``inline-flex`` AND matches
  *any* ancestor ``.group`` in a recursive tree (a node's chevron would
  react to its parents). ``bz-show`` sets inline ``display`` keyed to
  *this* node's ``isOpen(id)``. Cf. ``.claude/bretzel/traps.md``.
- **indicator cell** — the chevron (branch) and the leaf placeholder
  share ONE fixed-width cell so branch labels and leaf labels line up.
  The ``<iconify-icon>`` glyph is font-size-sized (~1em), so a bare
  chevron and a ``w-4`` spacer would never match — both live in the
  same ``w-*`` cell instead.
- **indent** — an inline ``padding-left`` computed from the node depth
  (``base + depth * step``), so arbitrary depth never needs N
  pre-compiled indent classes. The row's own class carries only the
  *right* padding.
- **selected** — ``data-[selected=true]`` on the row (the row's OWN
  attribute, not a group selector), rendered statically server-side for
  the initially-selected node and kept reactive via
  ``bz-attr:data-selected`` (SSR-first, no flash).

Disabled nodes dim to ``opacity-50`` and show ``cursor-not-allowed``. A
``<div>`` row has no ``disabled`` HTML attribute, so the disabled visuals
key off ``aria-disabled=true`` instead — we keep pointer events (else the
cursor never shows, cf. the Link theme) and neutralise the hover tint by
selector specificity. Interaction is already suppressed server-side (no
click / keydown handler on disabled rows).
"""

from __future__ import annotations

from typing import Any

TREE_THEME: dict[str, Any] = {
    "slots": {
        # Root <ul role="tree"> — flex column, no bullets, non-selectable
        # text (dragging a selection across a tree is never intended).
        "root": "flex flex-col w-full text-text select-none",
        # Nested <ul role="group"> — same column, no extra chrome (the
        # indent lives on each row, not on the group).
        "group": "flex flex-col",
        # The clickable row. Left padding is set inline (depth indent) ;
        # the class carries only the right + vertical padding. The
        # ``data-[selected=true]`` selectors read the row's OWN attribute.
        "row": (
            "flex items-center gap-1.5 w-full rounded-selector cursor-pointer "
            "outline-none transition-colors duration-150 "
            "focus-visible:ring-2 focus-visible:ring-inset "
            "focus-visible:ring-(--bz-focus) "
            "hover:bg-text/5 "
            "data-[selected=true]:bg-(--bz-bg) "
            "data-[selected=true]:text-(--bz-text) "
            "data-[selected=true]:font-medium"
        ),
        # Disabled row — dimmed, not-allowed cursor, no hover tint. A
        # ``role=treeitem`` div has no native ``disabled`` attribute, so we
        # key the disabled visuals off ``aria-disabled=true`` (set in
        # tree.py). We deliberately do NOT use ``pointer-events-none`` : it
        # blocks the cursor too, so ``cursor-not-allowed`` would never
        # render (same trap the Link theme documents). Instead we keep
        # pointer events and NEUTRALISE the hover by specificity — stacked
        # ``aria-disabled:hover:*`` (0,3,0) beats the row's plain ``hover:*``
        # (0,2,0), and ``aria-disabled:cursor-not-allowed`` (0,2,0) beats the
        # base ``cursor-pointer`` (0,1,0) — deterministic, no ``!important``.
        # The click / keydown handlers are already omitted server-side for
        # disabled rows (tree.py), so keeping pointer events fires no JS.
        "row_disabled": (
            "opacity-50 aria-disabled:cursor-not-allowed "
            "aria-disabled:hover:bg-transparent"
        ),
        # Fixed-width cell holding the chevron (branch) — the glyph is
        # centered so it aligns with the leaf spacer of the same width.
        # Width is set per size (``indicator`` below).
        "indicator": "shrink-0 flex items-center justify-center text-muted",
        # The chevron glyph itself — plain ; ``bz-show`` toggles its
        # inline ``display`` per node.
        "chevron": "shrink-0",
        # Leaf placeholder — occupies the SAME width as the indicator
        # cell so leaf labels line up under branch labels.
        "spacer": "shrink-0",
        # Optional per-node leading icon.
        "icon": "shrink-0 text-muted",
        # Label — truncates rather than wrapping (rows stay one line).
        "label": "truncate",
    },
    # Per-size : row padding + font, icon / chevron glyph size, the shared
    # indicator/spacer cell width, and the indent ``step`` (rem per depth
    # level) + ``base`` left pad.
    "sizes": {
        "sm": {
            "row": "pr-2 py-1 text-xs",
            "icon_size": "sm",
            "chevron_size": "xs",
            "indicator": "w-3.5",
            "base": 0.375,
            "step": 0.875,
        },
        "md": {
            "row": "pr-2 py-1.5 text-sm",
            "icon_size": "md",
            "chevron_size": "sm",
            "indicator": "w-4",
            "base": 0.5,
            "step": 1.0,
        },
        "lg": {
            "row": "pr-2.5 py-2 text-base",
            "icon_size": "md",
            "chevron_size": "md",
            "indicator": "w-5",
            "base": 0.625,
            "step": 1.25,
        },
    },
}
