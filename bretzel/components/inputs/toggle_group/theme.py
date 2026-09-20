"""Default themes for :class:`ToggleGroup` and :class:`ToggleButton`.

One visual contract — a joined-button bar. Items share their edges
(border-radius only on the first / last), the selected state is a
background fill in ``color``. Natural shape for filters, formatting
toolbars, multi-select pills.

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
        # carry — cf. traps.md § "An inline-flex root stretched by a
        # flex/grid items-stretch parent".
        #
        # Tight border-radius family from the form input design — same
        # scale as Input / Select / Combobox so a toggle group sits
        # naturally in a form row.
        # ⚠️ No ``h-fit`` here, and the step's height lives on THIS box
        # (``sizes[…]["root"]``), not on the item. The frame's border is
        # set on the root: an ``h-10`` on the item rendered a 42 px
        # cluster against 40 px for the select placed beside it in the
        # same grid — measured at every size, +2 px everywhere.
        # Cf. traps.md § "A step's height lives on the bordered
        # element".
        "root": (
            "inline-flex items-stretch w-fit select-none "
            "transition-colors duration-150 "
            "rounded-field bg-interface border-(length:--bz-stroke) border-text/10 "
            "overflow-hidden p-0 gap-0"
        ),
        # Item shell : flex centred, border-r for the inter-item
        # separator, removed on the last child via :last-child. Three
        # states for the text colour, matching the Tabs ``line`` idiom
        # — hover gives a colour preview of what selection looks like :
        # - base   : ``text-muted``
        # - hover  : ``text-(--bz-text)`` (preview, no bg yet)
        # - active : ``bg-(--bz-bg) text-(--bz-text)`` (full)
        "item": (
            "inline-flex items-center justify-center gap-1.5 "
            "font-medium text-muted cursor-pointer "
            "border-r-(length:--bz-stroke) border-text/10 last:border-r-0 "
            "transition-colors duration-150 ease-out "
            "not-disabled:hover:text-(--bz-text) "
            "data-[selected=true]:bg-(--bz-bg) "
            "data-[selected=true]:text-(--bz-text) "
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
        # ``xl`` was missing: a ``size="xl"`` silently fell back to
        # ``md``, a step smaller than an ``xl`` select/combobox placed
        # beside it in the same form (audit F91). The step traces
        # Select's (``h-14 px-5 text-lg``) so the family stays aligned.
        "xl": {"root": "h-14", "item": "h-full px-5 text-lg"},
    },
}
