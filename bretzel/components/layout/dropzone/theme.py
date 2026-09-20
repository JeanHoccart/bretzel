"""Theme slots for ``ui.dropzone``.

Slots :

- ``root``      : the zone itself. Deliberately layout-free — a dropzone
                  arranges nothing, it *receives*. Callers stack their
                  items with the container they already use
                  (``ui.vstack`` / ``ui.grid``), so the zone never fights
                  a layout the app already chose.
- ``valid``     : composed over ``root`` while a drag is in flight and
                  this zone would accept it. Requirement 1 of the framing
                  — "highlight the valid zones".
- ``carrier``   : the hidden input. Never visible ; the class exists only
                  so the element cannot inherit a stray flex/grid slot.

⚠️ **No ``hover:`` variant anywhere in this file, on purpose.** The drop
affordance must be visible to a touch user : the target browser of record
reports ``any-hover: none`` with 10 touch points, so a hover-gated
highlight would simply never appear (memory
``project_user_browser_has_no_fine_pointer``). The highlight is therefore
gated on ``data-bz-drop-ok=true``, which the runtime sets from the *gesture*,
not from the pointer's resting position.
"""

from __future__ import annotations

from typing import Any

DROPZONE_THEME: dict[str, Any] = {
    "slots": {
        # ``min-h-*`` so an EMPTY zone is still a target — a kanban column
        # with no cards left would otherwise collapse to zero height and
        # become impossible to drop into.
        "root": (
            "relative min-h-12 rounded-box "
            "border-(length:--bz-stroke) border-dashed border-transparent "
            "transition-colors duration-150"
        ),
        # ``data-[bz-drop-ok]`` : set on every zone that would accept the
        # item currently in flight, cleared when the gesture ends.
        "valid": (
            "data-[bz-drop-ok=true]:border-(--bz-solid) "
            "data-[bz-drop-ok=true]:bg-(--bz-bg)"
        ),
        # ``data-[bz-drop-replace]``: set by the gesture on a
        # ``holds="one"`` zone that ALREADY carries an occupant. It does
        # not receive the node — sliding it in would give it two — so the
        # eye must understand that it will be OVERWRITTEN, not completed.
        #
        # A solid line and a tint, where ordinary acceptance is dashed:
        # two neighbouring states must be told apart without comparing
        # them side by side.
        "replace": (
            "data-[bz-drop-replace=true]:border-solid "
            "data-[bz-drop-replace=true]:border-(--bz-solid) "
            "data-[bz-drop-replace=true]:bg-(--bz-bg) "
            "data-[bz-drop-replace=true]:ring-2 "
            "data-[bz-drop-replace=true]:ring-(--bz-solid)"
        ),
        "carrier": "hidden",
    },
}
