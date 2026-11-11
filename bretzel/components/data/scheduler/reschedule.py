"""``Reschedule`` — what a drop or a pulled edge reports to its handler.

The same idiom as ``Move`` for a dropzone: a typed parameter, filled by
the runtime ::

    def moved(r: Reschedule) -> None:
        lesson = lessons.get(r.event_id)
        lesson.start, lesson.end = r.start, r.end

``on_move`` and ``on_resize`` receive the same shape: a move changes both
ends, a resize only ``end``; the handler reads the two either way.

**Refusing is doing nothing**, or raising: the card goes back to where it
was. **Asking first** is opening a dialog: while a modal dialog is open
the card stays where it was dropped, and it goes back when the dialog
closes without the scheduler having been redrawn — the user cancelled.

**``event_id`` is the string the event was rendered with**, never the
object: the browser can only send back what it was given.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import ClassVar

from bretzel.core import EventPayload

#: The hidden form field ``scheduler.js`` writes the JSON blob into.
#: Shared with the runtime by convention — the JS cannot read Python.
RESCHEDULE_WIRE_FIELD = "bz_reschedule"


@dataclasses.dataclass(frozen=True)
class Reschedule(EventPayload):
    """One completed gesture on a scheduler card, as the server sees it."""

    WIRE_FIELD: ClassVar[str] = RESCHEDULE_WIRE_FIELD

    #: The ``id`` of the event, as it was passed in ``events=``.
    event_id: str = ""
    #: The new start and end, to the minute, aligned on ``snap=``. The
    #: runtime sends ISO strings in the page's local time; the payload
    #: base reads them, so the handler receives ``datetime`` objects.
    start: datetime | None = None
    end: datetime | None = None
