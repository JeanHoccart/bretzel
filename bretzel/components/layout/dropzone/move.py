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

⚠️ Ce paragraphe a dit pendant des mois que le morph suffisait — « a
handler that does not mutate leaves the server's next render disagreeing
with the DOM, and the morph puts the card back ». C'était faux : un
handler qui ne mute rien ne fait re-rendre AUCUNE zone, donc il n'y a
pas de rendu suivant et rien ne contredit le DOM. Le serveur répond zéro
octet et la carte reste dans la colonne qui l'a refusée (mesuré le
2026-09-09 sur ``examples/kanban``). Le snap-back est depuis un
**témoin** posé par ``19_dnd.js`` sur l'item déposé : le serveur ne rend
jamais cet attribut, donc le morph l'efface s'il ré-apparie le nœud, et
son survivant dit que personne n'a répondu. Gaté par
``tests/runtime_js/test_a_refusal_that_mutates_nothing_snaps_back.py``,
dans les deux sens — le versant licite y refuse qu'un dépôt ACCEPTÉ soit
défait.

**``item_key`` is a string, never the object.** The browser can only send
back the key the item was rendered with, so the handler does its own
lookup. Typing it as anything richer would be a lie about the wire.

**No coordinate field, deliberately.** A grid's move is expressed in cells,
not in ``from_index``/``to_index`` — the roadmap's own analysis puts lists
and grids at *opposite* corners, not in a parent/child relation. And
``to_index`` is already opaque : a fixed grid addresses its cell as
``y * columns + x``, the same integer. It is the component that decides
what the integer means, which is exactly the freedom the cadrage asked for.
An optional coordinate would have been a field that is always ``None``.
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
