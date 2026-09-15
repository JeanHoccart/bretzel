"""Default :class:`Divider` theme.

``bg-current opacity-20`` line so the divider inherits the root's
``text-{color}``. Optional centred label : uppercase + tracking-widest +
``text-xs``.

Three slots :
- ``root``  : the flex container, orientation-aware
- ``line``  : the rule ; takes the bulk of the space via ``grow``
- ``label`` : optional, sandwiched between two ``line`` instances
"""

from __future__ import annotations

from typing import Any

DIVIDER_THEME: dict[str, Any] = {
    "slots": {
        "root": "flex items-center justify-center",
        "line": "bg-current opacity-20 grow",
        "label": (
            "text-xs font-semibold px-4 whitespace-nowrap "
            "tracking-widest uppercase"
        ),
    },
    # Per-orientation overlays applied on top of the root + line slots.
    "orientations": {
        "horizontal": {
            "root": "flex-row w-full my-2",
            "line": "h-px w-full",
        },
        "vertical": {
            "root": "flex-col h-full min-h-[1rem] mx-2",
            "line": "w-px h-full",
        },
    },
}
