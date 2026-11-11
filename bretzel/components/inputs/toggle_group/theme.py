"""Default themes for :class:`ToggleGroup` and :class:`ToggleButton`.

One visual contract — a segmented bar. A framed rail holds the items
slightly apart; each selected item is a filled pill in ``color``'s
solid fill, as every selection of the framework. Natural shape for
filters, formatting toolbars, multi-select pills: several selected items
stay separate pills, never one block.

The selected state is driven by ``data-selected="true"`` (Tailwind's
``data-[selected=true]:`` variant) rather than ``aria-pressed:``.
Both attributes ARE emitted by the component (a11y stays correct),
but the visual cue rides on ``data-selected`` because that's the
proven path used by :class:`Tabs` ; we know it composes cleanly with
the Tailwind v4 browser CDN compiler. ``aria-pressed:`` Tailwind
variant works in theory, but binding the visual to ``data-*``
removes any ambiguity.

Vocabulary :
- ``root`` : the container ``<div role="group">``
- ``item`` : the per-button shell (centered button)
"""

from __future__ import annotations

from typing import Any

TOGGLE_GROUP_THEME: dict[str, Any] = {
    "slots": {
        # ``w-fit h-fit`` : forces intrinsic sizing on both axes so the
        # root doesn't get stretched by a parent flex/grid with
        # ``align-items: stretch`` (the default). Without this, the
        # cluster claims the full cross-axis width of its container ;
        # any tooltip / popover that anchors on the cluster centers on
        # the STRETCHED width, not on the actual button row, and the
        # panel floats off to the side. Same fix Popover + Dropdown
        # carry.
        #
        # Tight border-radius family from the form input design — same
        # scale as Input / Select / Combobox so a toggle group sits
        # naturally in a form row.
        # ⚠️ No ``h-fit`` here, and the step's height lives on THIS box
        # (``sizes[…]["root"]``), not on the item. The frame's border is
        # set on the root: an ``h-10`` on the item would make the cluster
        # 2 px taller than a select placed beside it in the same grid.
        #
        # The spacing between items belongs to the ROW (``gap``): an item
        # wrapped in its tooltip is the only child of that wrapper, so any
        # ``first:`` / ``last:`` on the item reads the wrapper, not the row.
        #
        # Too narrow for its column, it SCROLLS (``max-w-full
        # overflow-x-auto``) rather than overflow onto its neighbour, wrap
        # (no longer a bar) or shrink (« Trim… »). The bar is hidden, since a 40 px rail
        # has no room for it; a trackpad, a finger, or Tab reaching an
        # item scroll it. The items do not shrink (``shrink-0``).
        "root": (
            "inline-flex items-stretch w-fit max-w-full select-none "
            "transition-colors duration-150 "
            "rounded-field bg-interface border-(length:--bz-stroke) border-text/10 "
            "overflow-x-auto [scrollbar-width:none] p-0.5 gap-0.5"
        ),
        # Item shell : a pill nested in the rail (``rounded-selector``,
        # the family of a control nested inside another). Three states:
        # - base   : ``text-muted``
        # - hover  : ``text-(--bz-text)`` on an unselected item, a colour
        #   preview of the selection
        # - active : the colour's solid fill, its label in the colour
        #   written on it — as a sidebar's active row, a checked box, a
        #   picked day
        "item": (
            "inline-flex shrink-0 items-center justify-center gap-1.5 "
            "rounded-selector font-medium text-muted cursor-pointer "
            "transition-colors duration-150 ease-out "
            "not-disabled:not-data-[selected=true]:hover:text-(--bz-text) "
            # The fill is ``--bz-solid``, the colour itself — every
            # selection of the framework says "chosen" the same way. The
            # palette gives each colour a dark value that reads on the dark
            # rail (``palette.py``). A faint tint would not read there.
            # Gate: ``tests/runtime_js/test_a_selection_is_visible.py``.
            "data-[selected=true]:bg-(--bz-solid) "
            "data-[selected=true]:text-(--bz-on-solid) "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus) "
            "focus-visible:ring-inset "
            "disabled:opacity-50 disabled:cursor-not-allowed"
        ),
    },
    # Sizes scale the root height and the item padding. ``root`` and
    # ``item`` keys per size — read by hand in ``ToggleGroup.render()``
    # (a multi-slot component, it composes its own classes).
    #
    # The height is on ``root`` (the element carrying the border) and
    # the item fills it with ``h-full``: it is what aligns the cluster
    # with a select / input / button of the same size to the pixel.
    "sizes": {
        "xs": {"root": "h-7", "item": "h-full px-2 text-xs"},
        "sm": {"root": "h-8", "item": "h-full px-3 text-sm"},
        "md": {"root": "h-10", "item": "h-full px-4 text-sm"},
        "lg": {"root": "h-12", "item": "h-full px-5 text-base"},
        # ``xl`` traces Select's step (``h-14 px-5 text-lg``), so the
        # cluster stays aligned with an ``xl`` select/combobox placed
        # beside it in the same form.
        "xl": {"root": "h-14", "item": "h-full px-5 text-lg"},
    },
}
