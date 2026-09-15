"""Default :class:`Spinner` theme.

Pure-CSS rotating ring : a circular border with a transparent top quadrant,
spun via ``animate-spin``. Sizes scale via fixed ``h × w`` (plus matching
border width) so the spinner sits predictably inside other components. One
opinionated look ; override this ``root`` slot for another.
"""

from __future__ import annotations

from typing import Any

SPINNER_THEME: dict[str, Any] = {
    "slots": {
        # Single element : layout + colour + ring recipe. ``inline-block`` +
        # ``align-middle`` keep it on the text baseline next to "Loading…".
        # ``border-current`` inherits ``text-{color}`` ;
        # ``border-t-transparent`` leaves the spin gap. Border WIDTH lives in
        # the size token so the two never collide on one ``border-*`` class.
        "root": (
            "inline-block align-middle text-(--bz-text) "
            "rounded-full border-current border-t-transparent animate-spin"
        ),
    },
    "sizes": {
        "xs": "h-3 w-3 border-(length:--bz-stroke)",
        "sm": "h-4 w-4 border-(length:--bz-stroke-strong)",
        "md": "h-5 w-5 border-(length:--bz-stroke-strong)",
        "lg": "h-6 w-6 border-(length:--bz-stroke-strong)",
        "xl": "h-8 w-8 border-[3px]",
    },
}
