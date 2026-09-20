"""Default :class:`Popover` theme.

Card-style floating panel anchored to a trigger element. Same soft
identity as :class:`Card` (rounded-box + border + shadow) so popovers
feel like a piece of the design language rather than an OS chrome
ghost panel.

Slots :
- ``root``    : ``relative inline-flex`` wrapper holding trigger + panel
- ``panel``   : the floating card itself

Positioning is owned by ``$bz.helpers.floating`` (the panel's
``bz-effect``).
"""

from __future__ import annotations

from typing import Any

POPOVER_THEME: dict[str, Any] = {
    "slots": {
        "root": "relative inline-flex w-fit h-fit",
        "panel": (
            "absolute z-40 min-w-[12rem] "
            "rounded-box border-(length:--bz-stroke) border-text/10 bg-interface "
            "p-3 shadow-lg "
            # The enter fade. The three classes go together and none
            # serves alone — the why is in a single copy in
            # ``overlay/dropdown/theme.py``.
            "transition-[opacity,display] transition-discrete duration-150 "
            "starting:opacity-0"
        ),
    },
}
