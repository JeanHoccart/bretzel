"""Theme slots for ``ui.draggable``.

Slots :

- ``root``     : the grabbable wrapper. ``touch-action`` leaves the PAN
                 there (``touch-pan-x touch-pan-y``): the card takes up
                 the whole surface of a kanban column, so forbidding it
                 the scroll gesture amounts to forbidding scrolling at
                 all. It is the CAUGHT gesture that takes over, not the
                 CSS — cf. the non-passive ``touchmove`` of
                 ``19_dnd.js``, and the § below.
- ``dragging`` : composed over ``root`` while this item is in flight.
- ``handle``   : the opt-in grip. Sized ≥ 24×24 px (WCAG 2.2 target
                 size) because a 16 px grip is unusable with a finger, and
                 the browser of record is touch-first.
- ``disabled`` : an item that cannot be picked up.
"""

from __future__ import annotations

from typing import Any

DRAGGABLE_THEME: dict[str, Any] = {
    "slots": {
        # No ``cursor-grab``: it is a no-op on a touch device and would be
        # the only affordance if it were the only one. The visible signal
        # is the handle (when asked for) and the drag state itself.
        "root": "relative transition-shadow duration-150",
        # ``select-none`` matters during the gesture specifically: without
        # it a long-press on touch starts a text selection that fights the
        # drag and leaves the page with a blue smear.
        #
        # ⚠️ ``touch-pan-x touch-pan-y`` and most certainly NOT
        # ``touch-none``, which lived here until 2026-08-21.
        # ``touch-action: none`` takes the scroll gesture away from the
        # browser over the card's whole surface: in a column full of
        # cards, the finger could no longer scroll anything as soon as it
        # landed — "touch does not work, I cannot scroll while selecting
        # the cards". The irony: ``19_dnd.js`` carries a threshold
        # commented "this is what PRESERVES THE SCROLL", which worked
        # very well — above a CSS that made scrolling impossible.
        #
        # The pan alone is NOT ENOUGH, and it is measured: it gives back
        # the scroll and **loses the grab**, the browser taking the
        # gesture away. The second half is the non-passive ``touchmove``
        # of ``19_dnd.js``, which takes over when the long press
        # succeeds — at that instant the finger has not moved, so nothing
        # is in progress. Both halves are gated separately by
        # ``tests/runtime_js/test_a_draggable_card_still_lets_the_finger_scroll.py``.
        "grab_all": "touch-pan-x touch-pan-y select-none",
        # With a handle, the root becomes a ROW: otherwise the grip is
        # a block child and takes its own line above the content.
        # Invisible to every test — the DOM and the attributes are
        # identical in both cases; it only shows on a screenshot.
        "with_handle": "flex items-center gap-2",
        # ``min-w-0``: without it, a flex child refuses to shrink below
        # its content width and overflows the column.
        "handle_body": "min-w-0 grow",
        # During the gesture, the original becomes a PLACEHOLDER, not a
        # duplicate card: it is the clone (`.bz-drag-preview`, a hook in
        # theme/css.py) that carries the lift and follows the pointer.
        # Leaving it a shadow would make two lifted cards at once.
        # ⚠️ **The card KEEPS its size, and it is a choice** — settled on
        # 2026-09-13 after trying it both ways.
        #
        # During the gesture, the original fades and stays in place: the
        # landing zone opens by the height of a card, and the neighbours
        # go at once to their new position. It reads because what you see
        # is what you will get, at the scale you will get it.
        #
        # The other route — shrinking the card to a dashed placeholder,
        # like react-beautiful-dnd — was written, measured (50 px at rest
        # against 9 in flight) then REMOVED from the default: it asks the
        # eye to link a thin line to a card floating elsewhere, and on a
        # short list it costs more than it gives.
        #
        # ⚠️ **It stays reachable, and that is this comment's subject.**
        # The runtime publishes ``data-bz-drag-axis`` on the element in
        # flight (``y`` for a vertical list, ``x`` for a row) — for a
        # zone that only INSERTS; a ``holds="one"`` zone inserts nothing
        # and does not get one. An app that wants the placeholder
        # overrides this slot, once, for the whole app ::
        #
        #     Theme(components={"draggable": {"slots": {"dragging": (
        #         "data-[bz-dragging=true]:opacity-30 "
        #         "data-[bz-drag-axis]:opacity-100 "
        #         "data-[bz-drag-axis]:overflow-hidden "
        #         "data-[bz-drag-axis]:rounded-box "
        #         "data-[bz-drag-axis]:border-(length:--bz-stroke) "
        #         "data-[bz-drag-axis]:border-dashed "
        #         "data-[bz-drag-axis=y]:h-3 "
        #         "data-[bz-drag-axis=x]:w-3 "
        #         "transition-[height,width] duration-150 ease-out"
        #     )}}})
        #
        # No prop for that, and it is deliberate: ``holds=`` describes a
        # FACT about the zone — how many items it holds, which the server
        # uses — whereas "should the card shrink" is a taste. Facts live
        # on the component, tastes in the theme. One more prop would make
        # every author decide, on every zone, a question they have no
        # opinion about — and ``check`` could say nothing about it, for
        # want of a wrong answer.
        "dragging": (
            "data-[bz-dragging=true]:opacity-30 "
            "data-[bz-dragging=true]:grayscale"
        ),
        # ⚠️ **NO ``pointer-events-none``.** Putting it on the same
        # element as ``cursor-not-allowed`` CANCELS the cursor: an
        # element that receives no pointer event never paints one. It is
        # the exact trap ``test_disabled_affordance`` documents (the Tree
        # had shipped it), and the inertness is obtained anyway on the
        # runtime side, which ignores a ``data-bz-disabled`` at
        # ``pointerdown``.
        "disabled": "opacity-50 cursor-not-allowed",
        # 24px floor = WCAG 2.2 § 2.5.8. iOS HIG asks 44, Material 48 —
        # this is the accessible minimum, not a comfortable target, and a
        # touch-first app should pass a bigger one via ``classes=``.
        # ⚠️ ``touch-none`` is still RIGHT here, and for the opposite
        # reason: the handle is a 24 px target dedicated to the gesture,
        # not a reading surface. Nobody puts a finger on it to scroll,
        # and allowing it there would make the gesture hesitant.
        "handle": (
            "inline-flex items-center justify-center "
            "min-w-6 min-h-6 shrink-0 touch-none select-none "
            "text-muted hover:text-(--bz-text) "
            "focus-visible:outline-none focus-visible:ring-2 "
            "focus-visible:ring-(--bz-focus) rounded"
        ),
    },
}
