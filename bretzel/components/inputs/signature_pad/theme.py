"""Default :class:`SignaturePad` theme.

A dashed frame, a baseline, and a canvas that fills everything. Three
details are not cosmetic:

- ``touch-none`` (``touch-action: none``) on the canvas is
  **mandatory**. Without it the browser takes a finger drag for a page
  scroll and never sends the ``pointermove``: the pad is unusable on
  touch, in silence, while it works with a mouse. Same trap as the
  Resizable's handle, paid once and for all.
- ``text-text`` on the canvas is not decorative: it is the colour the
  runtime READS (``getComputedStyle(...).color``) to ink the stroke. It
  therefore follows dark mode without any prop stating it — a
  ``pen_color`` would have frozen an ink that becomes invisible on the
  other background.
- The height comes from the ``pad`` slot through the ``sizes`` table,
  and from nowhere else: a ``<canvas>`` has **no intrinsic size**, so a
  pad with no declared height is a pad of zero pixels.

The prompt (``hint``) is hidden as soon as a stroke exists, through
``data-empty`` that the runtime sets on the frame. An attribute rather
than a class: ``data-[empty=…]:`` is the variant the rest of the
repository uses for JS-driven states (cf. the selector clusters'
``data-selected``).

Slots :
- ``root``    : the column — frame then action bar
- ``pad``     : the dashed frame carrying the height and ``data-empty``
- ``canvas``  : the drawing surface
- ``hint``    : the centred prompt, erased at the first stroke
- ``baseline``: the line you sign above
- ``actions`` : the row under the frame (the Clear button)
"""

from __future__ import annotations

from typing import Any

SIGNATURE_PAD_THEME: dict[str, Any] = {
    "slots": {
        "root": "flex flex-col gap-2 w-full",
        "pad": (
            "relative w-full rounded-box overflow-hidden "
            "border-(length:--bz-stroke-strong) border-dashed border-text/15 bg-surface "
            "transition-colors duration-150 ease-out "
            "focus-within:border-(--bz-border-hover) "
            # The frame greys out AND loses its dashes when it is
            # locked: a signed pad must no longer INVITE a signature.
            "data-[locked=true]:border-solid "
            "data-[locked=true]:bg-text/5 "
            "data-[locked=true]:cursor-not-allowed"
        ),
        # ``block``: a canvas is ``inline`` by default, so it drags its
        # parent's baseline around and leaves a few pixels under it — a
        # light band at the bottom of the frame, which nobody ever links
        # back to that.
        "canvas": "block w-full h-full touch-none select-none text-text",
        # No ``text-<size>`` here: the ``sizes`` table sets one, and
        # both would coexist in the HTML — Tailwind would decide by ITS
        # sheet's order, not the string. The slot keeps only what does
        # not depend on the step.
        "hint": (
            "pointer-events-none absolute inset-x-0 bottom-3 "
            "text-center text-text/40 "
            # Erased at the first stroke — the prompt has said what it
            # had to say.
            "transition-opacity duration-150 ease-out "
            "data-[empty=false]:opacity-0"
        ),
        "baseline": (
            "pointer-events-none absolute inset-x-6 bottom-10 "
            "border-b-(length:--bz-stroke) border-text/20"
        ),
        "actions": "flex items-center justify-end",
    },
    # The frame's height, and nothing else: it is the only size axis a
    # pad has. No extra ``height=`` prop — two ways of saying the same
    # thing (principle 4); whoever wants an exact height goes through
    # ``classes="!h-64"``.
    "sizes": {
        "xs": {"pad": "h-24", "hint": "text-xs", "button": "xs"},
        "sm": {"pad": "h-32", "hint": "text-xs", "button": "xs"},
        "md": {"pad": "h-40", "hint": "text-sm", "button": "sm"},
        "lg": {"pad": "h-56", "hint": "text-sm", "button": "sm"},
        "xl": {"pad": "h-72", "hint": "text-base", "button": "md"},
    },
}
