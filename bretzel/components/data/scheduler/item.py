"""``SchedulerItem`` — one event of a :class:`Scheduler`, and its content.

    with ui.scheduler(date=monday, on_move=moved):
        for lesson in week:
            with ui.scheduler_item(key=lesson.id, start=lesson.start,
                                   end=lesson.end, color=lesson.color,
                                   title=lesson.name):
                ui.text(lesson.name, weight="bold")
                ui.badge(lesson.room)

The item says WHEN and WHO it is; the ``with`` block says what the card
shows. The scheduler places it — the minute, the lane beside an
overlapping one, the bar across several days — and carries the gesture.
With no children, the card shows ``title`` and ``subtitle``.

**Required, and checked here rather than drawn wrong:**

- ``key=`` — the id the handlers receive (``on_item_click(event_id)``,
  ``Reschedule.event_id``). Two items of one scheduler cannot share it.
- ``start=`` — a ``datetime``, a ``date`` or an ISO string, local and
  NAIVE: an aware ``datetime`` is refused, since dropping its offset
  would shift the card without a word.
- ``end=`` — after ``start``. Optional only with ``all_day=True``, where
  it is an exclusive date (holidays from Thursday to Friday end on
  Saturday) and defaults to the next day.

``title`` is what a screen reader announces with the day and the hours;
give it even when the children draw the card.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Any, ClassVar

from bretzel.components.base import Component, ComponentUsageError, reject_component
from bretzel.core.tree import Element


def read_moment(value: Any, *, field: str, owner: str) -> datetime:
    """A naive ``datetime`` from a ``datetime``, a ``date`` or an ISO string."""
    moment: datetime | None = None
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, date_type):
        moment = datetime(value.year, value.month, value.day)
    elif isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            moment = None
    if moment is None:
        raise ComponentUsageError(
            f"{owner}: {field}={value!r} is neither a datetime, a date, nor an "
            "ISO string."
        )
    if moment.tzinfo is not None:
        raise ComponentUsageError(
            f"{owner}: {field}={value!r} carries a time zone. Pass a naive local "
            "datetime: dropping the offset would move the card without a word."
        )
    return moment


class SchedulerItem(Component):
    """One event placed by its parent :class:`Scheduler`."""

    THEME_KEY: ClassVar[str] = "scheduler_item"
    #: Placed by the scheduler, refreshed with it: nothing to bind per item.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    def __init__(
        self,
        title: str = "",
        *,
        start: datetime | date_type | str | None = None,
        end: datetime | date_type | str | None = None,
        subtitle: str = "",
        color: str = "primary",
        all_day: bool = False,
        editable: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        reject_component(
            title,
            owner="SchedulerItem",
            prop="title",
            because=(
                "the title is the card's accessible name: the scheduler "
                "writes it into the card's ``aria-label`` with the day and "
                "the hours, even when the ``with`` block draws the card."
            ),
            instead=(
                "For a rich card, keep ``title=\"…\"`` and draw the content "
                "in the block: ``with ui.scheduler_item(title=\"Maths\", …): "
                "ui.badge(\"B12\")``."
            ),
        )
        self._title = title
        self._subtitle = str(subtitle)
        self._color = str(color)
        self._all_day = bool(all_day)
        self._editable = bool(editable)
        self._raw = (start, end)
        self._start = self._end = datetime.min

    def _read(self) -> None:
        """Check and read ``start`` / ``end``, called by the scheduler that
        places the item: a bare ``ui.scheduler_item()`` still constructs
        (every component does), it only refuses to be PLACED wrong."""
        owner = f"ui.scheduler_item(key={self._key!r})"
        start, end = self._raw
        if start is None:
            raise ComponentUsageError(f"{owner} needs start=.")
        begin = read_moment(start, field="start", owner=owner)
        if self._all_day:
            begin = datetime(begin.year, begin.month, begin.day)
            finish = (read_moment(end, field="end", owner=owner) if end is not None
                      else begin + timedelta(days=1))
            finish = datetime(finish.year, finish.month, finish.day)
        elif end is None:
            raise ComponentUsageError(f"{owner} needs end= (or all_day=True).")
        else:
            finish = read_moment(end, field="end", owner=owner)
        if finish <= begin:
            raise ComponentUsageError(
                f"{owner} ends ({finish}) at or before it starts ({begin})."
            )
        self._start = begin
        self._end = finish

    def render(self) -> Element:
        """Outside a scheduler, only the content: an item has no place of
        its own, and a stray one must not break the page."""
        attrs = self.emit_attrs()
        return Element(tag=self._tag, attrs=attrs, children=tuple(self._render_children()))
