"""``Move`` — what a drop reports to its ``on_move`` handler.

The typed parameter is the same idiom as a typed form handler
(``def save(form: MyForm)``) and as ``Query`` for a datatable's rows
callable — one shape to learn for the whole framework ::

    def reorder(m: Move) -> None:
        if m.to_zone == "archive" and not user.can_archive:
            return                 # no mutation = refusal = snap-back
        board.apply(m.item_key, m.to_index)

**Refusing is doing nothing.** There is no ``reject()`` to call and no
exception to raise : a handler that mutates nothing leaves the card where
the finger dropped it *for one frame*, and the runtime undoes the gesture.

⚠️ This paragraph said for months that the morph was enough — "a handler
that does not mutate leaves the server's next render disagreeing with the
DOM, and the morph puts the card back". That was false: a handler that
mutates nothing makes NO zone re-render, so there is no next render and
nothing contradicts the DOM. The server answers zero bytes and the card
stays in the column that refused it (measured on 2026-09-09 on
``examples/kanban``). The snap-back is since a **witness** set by
``19_dnd.js`` on the dropped item: the server never renders that
attribute, so the morph erases it if it re-pairs the node, and its
survival says nobody answered. Gated by
``tests/runtime_js/test_a_refusal_that_mutates_nothing_snaps_back.py``,
in both directions — its legitimate side refuses that an ACCEPTED drop be
undone.

**``item_key`` is a string, never the object.** The browser can only send
back the key the item was rendered with, so the handler does its own
lookup. Typing it as anything richer would be a lie about the wire.

**No coordinate field, deliberately.** A grid's move is expressed in cells,
not in ``from_index``/``to_index`` — the roadmap's own analysis puts lists
and grids at *opposite* corners, not in a parent/child relation. And
``to_index`` is already opaque : a fixed grid addresses its cell as
``y * columns + x``, the same integer. It is the component that decides
what the integer means, which is exactly the freedom the framing asked
for. An optional coordinate would have been a field that is always
``None``.
"""

from __future__ import annotations

import dataclasses
from typing import ClassVar

from bretzel.core import EventPayload

#: The hidden form field ``19_dnd.js`` writes the JSON blob into. Shared
#: with the runtime by convention rather than by import — the JS cannot
#: read Python. ``test_dnd_wire_field_matches_runtime`` holds the two ends
#: together.
MOVE_WIRE_FIELD = "bz_move"


@dataclasses.dataclass(frozen=True)
class Move(EventPayload):
    """One completed drag, as the server sees it."""

    WIRE_FIELD: ClassVar[str] = MOVE_WIRE_FIELD

    #: ``key=`` of the dragged item — its ``each`` iteration key when the
    #: caller did not pass one explicitly.
    item_key: str = ""
    #: ``name=`` of the zone it left, and of the zone it landed in. Equal
    #: for a plain reorder inside one list.
    from_zone: str = ""
    to_zone: str = ""
    #: Positions among the *draggable items* of each zone, 0-based. Read
    #: from the DOM at drop time, so they cannot disagree with what the
    #: user is looking at.
    from_index: int = -1
    to_index: int = -1

    @property
    def same_zone(self) -> bool:
        """True for a reorder, False for a transfer between two zones."""
        return self.from_zone == self.to_zone
