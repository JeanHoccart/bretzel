"""Default :class:`Checkbox` theme.

The real ``<input type="checkbox">`` is hidden via ``sr-only`` and a
styled ``<div class="box">`` impersonates it ; a separate
absolute-positioned ``<svg>`` checkmark fades in on check via
``opacity-0 peer-checked:opacity-100 transition-opacity``. That combo
gives the "soft tick" feel — a flat native checkbox can't do it.

Slots :
- ``root``     : ``<label>`` wrapper, click target + focus-within plumbing
- ``container``: relative wrapper that aligns the box and the icon
- ``input``    : the visually hidden real ``<input>`` (``peer``)
- ``box``      : the visible square that fills on check
- ``icon``     : the SVG check that fades in
- ``label``    : text next to the box
"""

from __future__ import annotations

from typing import Any

CHECKBOX_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            "bz-checkbox "
            # ``items-start``: a label on several lines keeps the box on its
            # first line — the container is one line high (``_checkable``).
            "inline-flex items-start align-middle gap-2 group select-none cursor-pointer "
            # Disabled visual — same pair as the rest of the family.
            # ``has-[:disabled]:`` keys off the invisible ``peer``
            # ``<input disabled>`` descendant so the toggle is fully
            # CSS-reactive (literal AND ClientBinding) without a
            # Python-side ``modifiers`` flush that would freeze the
            # value at SSR time.
            "has-[:disabled]:opacity-50 "
            "has-[:disabled]:cursor-not-allowed"
        ),
        "container": (
            "relative inline-flex items-center justify-center shrink-0"
        ),
        # The real input, invisible but ON TOP of the drawn box (``z-10``
        # over the container): it takes the click itself, so a test's
        # ``checkbox.check()`` works — with ``sr-only`` the box intercepts
        # it. Still
        # keyboard- and screen-reader-accessible; the visual fakes ride on
        # its ``:checked``, ``:focus-visible`` and ``:disabled`` states
        # via Tailwind's ``peer-*`` modifier stack. Same for the switch
        # and the radio.
        "input": "peer absolute inset-0 m-0 opacity-0 z-10 cursor-pointer disabled:cursor-not-allowed",
        "box": (
            "block rounded-selector border-(length:--bz-stroke) border-text/25 bg-interface "
            "transition duration-200 ease-out "
            "peer-checked:bg-(--bz-solid) peer-checked:border-(--bz-solid) "
            "peer-focus-visible:ring-2 peer-focus-visible:ring-(--bz-focus) "
            "peer-focus-visible:ring-offset-2 "
            "peer-focus-visible:ring-offset-background"
        ),
        "icon": (
            "absolute pointer-events-none "
            "opacity-0 peer-checked:opacity-100 "
            "transition-opacity duration-200 ease-out "
            "text-(--bz-on-solid)"
        ),
        "label": (
            "font-medium text-text transition duration-200 "
            "group-has-[input:not(:disabled)]:group-hover:opacity-70"
        ),
    },
    # Sizes scale the box, the icon, and the label together. We use a
    # nested dict (one entry per size, each keyed by slot name) so a
    # single ``size="md"`` propagates the right value to each visual
    # element without exposing a per-slot prop.
    "sizes": {
        "xs": {"box": "h-3 w-3",   "icon": "h-2 w-2",     "label": "text-xs"},
        "sm": {"box": "h-4 w-4",   "icon": "h-3 w-3",     "label": "text-xs"},
        "md": {"box": "h-5 w-5",   "icon": "h-3.5 w-3.5", "label": "text-sm"},
        "lg": {"box": "h-6 w-6",   "icon": "h-4 w-4",     "label": "text-base"},
        "xl": {"box": "h-7 w-7",   "icon": "h-5 w-5",     "label": "text-lg"},
    },
}
