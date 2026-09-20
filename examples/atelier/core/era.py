"""core/era — logic: since when a task counts.

A ``kind="logic"`` feature: no state, no resource, one question.

Why a cut-off
--------------
Decided by the user on 2026-09-12, faced with eleven tasks from an
``examples/ecole`` that no longer exists: "since the finished version of
describe, check, probe is recent, the old subjects are a bit obsolete".

They are right, and it is a question of the measurement's honesty, not of
tidying up. The workshop judges a task on the FOUR-TIMES RULE — did we
ask for the surface before writing, have the contract judged, verify in
one pass. A task from July could not make those gestures: the
instruments did not exist. Counting it is blaming somebody for not using
a tool that had not shipped.

The milestone
--------------
10 September 2026, the day ``bretzel probe`` shipped. It is the LAST of
the three instruments: ``describe`` and ``check`` are from 16 August, so
it is only at that date that the rule becomes judgeable in full.

⚠️ Nothing is deleted. The ingest still reads every transcript, and
deleting rows would not hold: the next ingest would recreate them from
their source. It is the READING that stops at the milestone, and it does
so through SQL views (``core/db.VIEWS``) rather than a clause copied into
every query — there are twenty-six, hence twenty-six chances to forget.
"""

from __future__ import annotations

from bretzel import Feature

#: The date from which a task is judgeable, in ISO — compared as is to
#: ``tasks.started``, which is an ISO timestamp. String comparison is
#: enough and it is intended: same format, same order.
MILESTONE = "2026-09-10"

#: The milestone spelled out, for the screen. It MUST be shown: an app
#: that shows 67 tasks out of 1 525 without saying why lies by omission.
MILESTONE_LABEL = "since 10 September 2026"

#: What the milestone marks. On the screen too — a marker without its
#: reason reads as a whim.
MILESTONE_WHY = (
    "the day `bretzel probe` shipped, the last of the three instruments "
    "the rule assumes"
)


def is_judgeable(started: str | None) -> bool:
    """Was this task done with the complete tooling?

    The Python door onto the same rule as the SQL views. It serves the
    tests, and any caller already holding the row rather than a query.
    """
    return bool(started) and str(started) >= MILESTONE


feature = Feature(
    name="era",
    kind="logic",
    provides=[is_judgeable],
)
