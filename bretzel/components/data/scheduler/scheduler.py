"""``Scheduler`` — events posed on a grid of time, to the minute.

Usage ::

    with ui.scheduler(date=date(2026, 11, 10), on_move=moved):
        for lesson in week:
            with ui.scheduler_item(key=lesson.id, title=lesson.name,
                                   start=lesson.start, end=lesson.end,
                                   color=lesson.color):
                ui.text(lesson.name, weight="bold")
                ui.badge(lesson.room)

The app writes the loop and the content of each card
(:class:`~bretzel.components.data.scheduler.item.SchedulerItem`); the
scheduler does what no app should rewrite — the minute, the lanes, the
bar across days, the gesture. Its rules on the data:

- an item needs ``key=``, ``start=`` and ``end=`` (``end`` is optional for
  an all-day item); a missing one, an ``end`` at or before ``start``, an
  aware ``datetime`` or two items sharing a key raise — an event drawn in
  the wrong place is worse than an error;
- two events at the same time sit side by side, in lanes, inside their
  column — a cluster is a run of events overlapping one another, directly
  or through a third;
- an event running past midnight is cut into one card per day; its cards
  are shown, not dragged (which half would the hand hold?);
- with a fixed ``hours=``, an event partly outside the grid is clipped to
  it, and one wholly outside is not drawn; a clipped card is not dragged
  either — its visible length is not its length;
- a very short event keeps a card tall enough to be seen and clicked.

**The shortcut.** ``events=[{...}]`` materialises the same items, for the
case where a card shows a title and a subtitle ::

    ui.scheduler(events=[
        {"id": "12-2026-11-10", "title": "4e2", "subtitle": "C209",
         "start": "2026-11-10T08:05", "end": "2026-11-10T09:00",
         "color": "violet"},
        {"id": "toussaint", "title": "Vacances", "all_day": True,
         "start": date(2026, 11, 12), "end": date(2026, 11, 14)},
    ], date=date(2026, 11, 10))

Each dict takes the item's keywords, with ``id`` for ``key``.

The component knows no business rule: repetition, A/B weeks, holidays
stay with the app, which passes occurrences already computed.

**Views.** Four, the usual ones of a scheduler:

- ``view="day"`` — the one day of ``date``: the view for a phone;
- ``view="3days"`` — ``date`` and the two days after it;
- ``view="week"`` — the working days; Saturday and Sunday appear when an
  event falls on them (an all-day event merely running through the
  weekend does not count), or always with ``weekend=True``, never with
  ``weekend=False``;
- ``view="month"`` — the weeks of ``date``'s month, a cell per day, with
  the same weekend rule. No hours: a timed event is a small chip in its
  day, an all-day one a bar across the week. A chip is dragged to another
  day (its hours kept); nothing is pulled, there is no length to see.
  A day shows ``MONTH_CHIPS`` chips and says how many more it holds.

**Hours.** ``hours=(8, 19)`` fixes the grid; by default it shows 8h to
18h and grows to fit the events.

**Day names** come from the browser (``Intl``, from ``<html lang>``),
like ``ui.calendar``'s; ``weekday_names=`` (seven names, Sunday first)
renders them server-side instead.

**Gestures.** With ``on_move=``, a card is dragged to another day or
hour; with ``on_resize=``, its bottom edge is pulled to change its end.
Both snap to ``snap=`` minutes (5 by default) and call their handler with
a :class:`~bretzel.components.data.scheduler.reschedule.Reschedule`. A
ghost follows the pointer with the new time; at the drop the card goes to
its new place at once, and the server decides:

- it **accepts** by changing the events, so the scheduler is redrawn
  where the card already is;
- it **refuses** by changing nothing, or by raising: the card goes back;
- it **asks** by opening a dialog ("this one or all of them?"): the card
  stays at its new place while a modal dialog is open, and goes back if
  the dialog closes without the scheduler being redrawn.

**Creating.** With ``on_create=``, a press on the EMPTY grid traced
downwards (or upwards) draws a draft of the new event, snapped to
``snap=`` minutes; at the release the handler receives a ``Reschedule``
whose ``event_id`` is empty, with the slot's ``start`` and ``end``. The
draft stays until the answer: the app shows its own provisional item,
or answers nothing and the draft goes. A press that does not move creates nothing:
a click on the grid is often meant to close a panel. Not in the month
view, which has no hours.

A press that moves less than a few pixels is a click: ``on_item_click=``
receives the item's ``key`` — also on Enter, a card being focusable. The
click a browser fires at the end of a drag is swallowed for a moment,
not until the next click. ``editable=False`` on an item keeps it
clickable and still.

The gesture lives in the runtime (``scheduler.js``), delegated from
the document, so it survives every redraw; the app writes no JavaScript.

The navigation (previous / next week, today), the detail of an event and
the week's labels are the app's, built from ``ui.button``,
``ui.popover``, ``ui.badge`` around the scheduler.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Any, ClassVar

from bretzel.components.base import Component, ComponentUsageError, el
from bretzel.components.base.composition import unwrap_transparent
from bretzel.components.base.events import item_action_attrs
from bretzel.components.base.field_wiring import activate_keydown
from bretzel.components.base.theme_values import refuse_unknown_color
from bretzel.components.base.universals import finish_render
from bretzel.components.data.scheduler.item import SchedulerItem
from bretzel.components.data.scheduler.reschedule import RESCHEDULE_WIRE_FIELD
from bretzel.components.data.scheduler.theme import SCHEDULER_THEME
from bretzel.core import key_segment
from bretzel.core.tree import Element, Node
from bretzel.render.context import current_context
from bretzel.theme.bridges import bridge_class


def clock(minutes: int, lang: str) -> str:
    """An hour as the page's language writes it: « 8h », « 10h10 » in
    French, « 8:00 », « 10:10 » otherwise.

    Not ``Intl``, which the day names use: for French it says « 08 h » or
    « 8:00 », never « 8h » — the form a French reader writes and expects.
    Another language joins this function
    the day its own form is asked for.
    """
    hours, rest = divmod(minutes, 60)
    if lang.split("-")[0].lower() == "fr":
        return f"{hours}h{rest:02d}" if rest else f"{hours}h"
    return f"{hours}:{rest:02d}"


def hhmm(minutes: int) -> str:
    """``485`` → ``"08:05"``: the value the browser's clock reads."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def shown_clock(minutes: int, lang: str, *, compact: bool = False
                ) -> tuple[dict[str, str], list[Node]]:
    """An hour on the page: the server writes it with :func:`clock`, the
    browser rewrites it with THE clock, ``$bz.times.shown`` — the one the
    time picker uses, and the one that knows « 2:30 PM ».
    French reads the same on both sides; elsewhere the server's form is
    only what shows before the runtime starts."""
    flag = ", true" if compact else ""
    return {"bz-text": f"$bz.times.shown('{hhmm(minutes)}'{flag})"}, [clock(minutes, lang)]


def spoken_event_js(title: str, subtitle: str | None, day: date_type,
                    start: int, end: int) -> str:
    """An event's accessible name, written by the browser: its title, its
    day in words (« mardi 3 novembre 2026 ») and its hours. Written by the
    server, it would say the day in ISO to a screen reader."""
    head = [json.dumps(t) for t in (title, subtitle) if t]
    return " + ', ' + ".join([
        *head,
        f"$bz.dates.shownLong('{day.isoformat()}')",
        f"$bz.times.shown('{hhmm(start)}') + ' – ' + $bz.times.shown('{hhmm(end)}')",
    ])


def minute_of(moment: datetime) -> int:
    return moment.hour * 60 + moment.minute


#: A minute's height: a 55-minute lesson is 77 px, room for its line.
PX_PER_MINUTE = 1.4
#: Between two cards, and from a card to its column's edges.
GAP = 3
#: The smallest card, in pixels: a five-minute event stays visible and
#: clickable (it would otherwise be 4 px).
MIN_CARD_PX = 18
#: Below this height a card is COMPACT: one line, smaller, the title then
#: the hour, cut with an ellipsis — never a line sliced through its letters
#: (a 30-minute event, a card clipped by ``hours=``).
COMPACT_PX = 40
#: The height of one row of all-day bars.
ALL_DAY_ROW = 30
#: The span the grid always shows, in hours; it grows to fit the events.
DEFAULT_HOURS = (8, 18)
VIEWS = ("day", "3days", "week", "month")
DAY = 24 * 60
#: How many chips a month cell shows before "+N".
MONTH_CHIPS = 3
#: The height of one row of all-day bars in a month week, and the room
#: left above them for the day's number.
MONTH_BAR_ROW = 24
MONTH_NUMBER_ROW = 30
#: A click on the pulled edge must not open the event: the trigger's
#: filter, with neither a comma nor a ``]`` (htmx's parser splits on the
#: first and closes on the second — cf. ``ui.table``'s row guard).
_NOT_THE_EDGE = "!event.target.hasAttribute('data-bz-resize')"


@dataclass(frozen=True, slots=True)
class _Placed:
    """An item, its key, and what gives it back its wrapper (a zone)."""

    key: str
    item: SchedulerItem
    rewrap: Any


@dataclass(frozen=True, slots=True)
class _Segment:
    """The part of a timed event drawn in one day's column."""

    placed: _Placed
    day: date_type
    #: Minutes from that day's midnight; ``end`` may be 1440.
    start: int
    end: int
    #: The whole event, unclipped: only such a card can be dragged.
    whole: bool


def _items_of(events: Iterable[Mapping[str, Any]]) -> None:
    """The ``events=`` shortcut: the same items, built inside the scheduler."""
    for raw in events:
        if not raw.get("id"):
            raise ComponentUsageError(
                f"ui.scheduler: every event needs an 'id' — got {dict(raw)!r}."
            )
        fields = {k: v for k, v in raw.items() if k != "id"}
        SchedulerItem(key=str(raw["id"]), **fields)


def lanes(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Spans at the same time share the column side by side: for each span
    (start, end), its (lane, number of lanes of its cluster). A cluster is
    a run of spans that overlap one another, directly or through a third."""
    placed: list[tuple[int, int]] = [(0, 1)] * len(spans)
    cluster: list[tuple[int, int]] = []          # (span index, lane)
    cluster_end = -1

    def close() -> None:
        width = max(lane for _, lane in cluster) + 1
        for index, lane in cluster:
            placed[index] = (lane, width)

    for index in sorted(range(len(spans)), key=lambda i: (spans[i][0], -spans[i][1])):
        start, end = spans[index]
        if cluster and start >= cluster_end:
            close()
            cluster = []
        taken = {lane for other, lane in cluster if spans[other][1] > start}
        lane = next(n for n in range(len(cluster) + 1) if n not in taken)
        cluster.append((index, lane))
        cluster_end = max(cluster_end, end) if len(cluster) > 1 else end
    if cluster:
        close()
    return placed


def all_day_bars(
    items: list[_Placed], days: list[date_type]
) -> list[tuple[_Placed, int, int, int]]:
    """Each all-day item as one bar: (item, first column, columns spanned,
    row). Bars that overlap stack on separate rows; a bar is clipped to the
    days shown (holidays running through a hidden weekend)."""
    bars: list[tuple[_Placed, int, int, int]] = []
    rows_end: list[int] = []
    for placed in sorted(items, key=lambda p: (p.item._start, -(p.item._end - p.item._start).days)):
        shown = [i for i, day in enumerate(days)
                 if placed.item._start.date() <= day < placed.item._end.date()]
        if not shown:
            continue
        first, last = shown[0], shown[-1]
        row = next((r for r, taken in enumerate(rows_end) if taken < first), len(rows_end))
        if row == len(rows_end):
            rows_end.append(last)
        else:
            rows_end[row] = last
        bars.append((placed, first, last - first + 1, row))
    return bars


def _midnight(day: date_type) -> datetime:
    return datetime(day.year, day.month, day.day)


def segments(placed: list[_Placed], days: list[date_type]) -> list[_Segment]:
    """Every timed item cut at midnight into the days shown."""
    cut: list[_Segment] = []
    for p in placed:
        for day in days:
            midnight = _midnight(day)
            low = max(p.item._start, midnight)
            high = min(p.item._end, midnight + timedelta(days=1))
            if low >= high:
                continue
            cut.append(_Segment(
                placed=p, day=day,
                start=int((low - midnight).total_seconds() // 60),
                end=int((high - midnight).total_seconds() // 60),
                whole=low == p.item._start and high == p.item._end,
            ))
    return cut


def _saturday_of(day: date_type) -> date_type:
    """The Saturday of the weekend ``day`` belongs to."""
    return day - timedelta(days=day.weekday() - 5)


class Scheduler(Component):
    """Events on a grid of time — week or day view."""

    THEME: ClassVar[dict[str, Any]] = SCHEDULER_THEME
    THEME_KEY: ClassVar[str] = "scheduler"
    #: Draws its children itself: a zone among them is refused
    #: (``base/composition.unwrap_transparent``).
    _COMPOSES_CHILDREN: ClassVar[bool] = True
    #: The app writes the loop and the content of each card: it gets
    #: ``ui.scheduler_item`` children, and ``events=`` stays the shortcut of
    #: the title-and-subtitle case. Cf. ``Component.COLLECTION_OWNER``.
    COLLECTION_OWNER: ClassVar[str | None] = "author"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    #: Routed by hand, like ``ui.table``'s ``item_click``: ``item_click`` on
    #: each CARD (bound to its key), ``move`` / ``resize`` on two hidden
    #: carriers the runtime writes the payload into. The base layer would
    #: set all three on the root, and an element carries one ``hx-post``.
    EVENTS: ClassVar[tuple[str, ...]] = ("item_click", "move", "resize", "create")
    #: Retired names, refused with the new one (``attrs.split_kwargs``).
    RENAMED_PROPS: ClassVar[dict[str, str]] = {
        "on_select": "write ``on_item_click=``, as on ``ui.table`` and the "
                     "charts — clicking an element of a collection.",
    }

    def __init__(
        self,
        *,
        events: Iterable[Mapping[str, Any]] = (),
        date: date_type | str | None = None,
        view: str = "week",
        hours: tuple[int, int] | None = None,
        weekend: bool | None = None,
        week_start: int = 1,
        weekday_names: list[str] | None = None,
        snap: int = 5,
        on_item_click: Callable[..., Any] | str | None = None,
        on_move: Callable[..., Any] | str | None = None,
        on_resize: Callable[..., Any] | str | None = None,
        on_create: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if view not in VIEWS:
            raise ComponentUsageError(
                f"ui.scheduler: view={view!r} is not one of {VIEWS}."
            )
        if hours is not None and not (0 <= hours[0] < hours[1] <= 24):
            raise ComponentUsageError(
                f"ui.scheduler: hours={hours!r} must be (first, last) with "
                "0 <= first < last <= 24."
            )
        if not 1 <= snap <= 60:
            raise ComponentUsageError(
                f"ui.scheduler: snap={snap!r} must be between 1 and 60 minutes."
            )
        if week_start not in range(7):
            raise ComponentUsageError(
                f"ui.scheduler: week_start={week_start!r} must be 0 (Sunday) to 6 (Saturday)."
            )
        if weekday_names is not None and len(weekday_names) != 7:
            raise ComponentUsageError(
                f"ui.scheduler: weekday_names must have 7 entries (Sunday "
                f"first), got {len(weekday_names)}."
            )
        if isinstance(date, str):
            date = date_type.fromisoformat(date)
        self._date = date or date_type.today()
        self._view = view
        self._hours = hours
        self._weekend = weekend
        self._week_start = week_start
        self._weekday_names = list(weekday_names) if weekday_names else None
        self._snap = snap
        self._on_item_click = on_item_click
        self._on_move = on_move
        self._on_resize = on_resize
        self._on_create = on_create
        # The shortcut materialises the SAME children as the container form
        # — one render path afterwards (Breadcrumb's rule).
        events = list(events)
        if events:
            with self:
                _items_of(events)

    def _needs_identity(self) -> bool:
        """With a handler, the cards and the carriers need ids: htmx and
        idiomorph find them again by it, and the actions register under
        the scheduler's."""
        return bool(self._on_item_click or self._gestures()) or super()._needs_identity()

    def _gestures(self) -> bool:
        """A gesture is wired: the root carries the grid for the runtime."""
        return bool(self._on_move or self._on_resize or self._on_create)

    def _carrier(self, cls: dict[str, str], event: str, handler: Any) -> Element:
        """The hidden input the runtime writes a :class:`Reschedule` into,
        then fires ``event`` from. ``name`` only for a server handler: an
        unconditional one would inject the field into an enclosing form."""
        attrs: dict[str, Any] = {
            "type": "hidden",
            "class": cls["carrier"],
            "data-bz-scheduler-carrier": event,
            **item_action_attrs(handler, event=event, bind=lambda fn: fn,
                                owner_id=self.id, ctx=current_context(),
                                modifier=self._trigger_modifier),
        }
        handlers = handler if isinstance(handler, (list, tuple)) else [handler]
        if any(callable(one) for one in handlers):
            attrs["name"] = RESCHEDULE_WIRE_FIELD
        return el("input", attrs)

    # ── What is shown ──────────────────────────────────────────────────

    def _placed(self) -> list[_Placed]:
        """The items, unwrapped from any zone, with their checked keys.

        ``unwrap_transparent``: an item inside a ``@refreshable`` zone is
        not an instance of ``SchedulerItem`` — sorting by type alone would
        drop it in silence."""
        placed: list[_Placed] = []
        seen: set[str] = set()
        for raw in self._children:
            child, rewrap = unwrap_transparent(raw, self)
            if not isinstance(child, SchedulerItem):
                raise ComponentUsageError(
                    f"ui.scheduler holds ui.scheduler_item children only — got "
                    f"{type(child).__name__}. Put what surrounds the week "
                    "(navigation, legend) beside the scheduler, and what a card "
                    "shows inside its ui.scheduler_item."
                )
            if child._key in (None, ""):
                raise ComponentUsageError(
                    "ui.scheduler_item needs key= — the id on_item_click and "
                    f"Reschedule.event_id give back (item {child._title!r})."
                )
            key = str(child._key)
            if key in seen:
                raise ComponentUsageError(
                    f"ui.scheduler: two items share key={key!r}. A gesture on one "
                    "would be reported for the other."
                )
            seen.add(key)
            child._read()
            placed.append(_Placed(key=key, item=child, rewrap=rewrap))
        return placed

    def _days(self, placed: list[_Placed]) -> list[date_type]:
        if self._view == "day":
            return [self._date]
        if self._view == "3days":
            return [self._date + timedelta(days=d) for d in range(3)]
        start = self._week_of(self._date)
        return [
            day for day in (start + timedelta(days=d) for d in range(7))
            if day.weekday() < 5 or self._weekend
            or (self._weekend is None and self._used(day, _saturday_of(day), placed))
        ]

    def _week_of(self, day: date_type) -> date_type:
        """The first day of ``day``'s week."""
        return day - timedelta(days=((day.weekday() + 1) % 7 - self._week_start) % 7)

    def _weeks(self, placed: list[_Placed]) -> list[list[date_type]]:
        """The month's weeks, each cut to the days shown: the weekend columns
        appear if one of the month's weekends is used."""
        first = self._date.replace(day=1)
        last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        start = self._week_of(first)
        starts = []
        while start <= last:
            starts.append(start)
            start += timedelta(days=7)
        weeks = [[s + timedelta(days=d) for d in range(7)] for s in starts]
        weekend = self._weekend
        if weekend is None:
            weekend = any(
                self._used(day, _saturday_of(day), placed)
                for week in weeks for day in week if day.weekday() >= 5
            )
        return [[day for day in week if weekend or day.weekday() < 5] for week in weeks]

    @staticmethod
    def _used(day: date_type, saturday: date_type, placed: list[_Placed]) -> bool:
        """A timed event touches that day, or an all-day one starts within
        the weekend — holidays running through it do not count."""
        midnight = _midnight(day)
        return any(
            p.item._start < midnight + timedelta(days=1) and p.item._end > midnight
            if not p.item._all_day
            else saturday <= p.item._start.date() <= day < p.item._end.date()
            for p in placed
        )

    def _span(self, cut: list[_Segment]) -> tuple[int, int]:
        """The grid's first and last minute."""
        if self._hours is not None:
            return self._hours[0] * 60, self._hours[1] * 60
        first = min([s.start // 60 * 60 for s in cut], default=DAY)
        last = max([-(-s.end // 60) * 60 for s in cut], default=0)
        # Grown to fit, the grid keeps an hour of room when the cards can
        # move: a meeting ending at 20:00 on a grid ending at 20:00 could
        # not be lengthened, nor moved later.
        room = 60 if self._gestures() else 0
        start, end = DEFAULT_HOURS[0] * 60, DEFAULT_HOURS[1] * 60
        if first < start:
            start = max(0, first - room)
        # ``>=`` at the end: the bottom edge is the gesture people use, and
        # a lesson ending at 18:00 must still be pulled to 18:30.
        if last >= end:
            end = min(DAY, last + room)
        return start, end

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        # The page's language, for the hours (``clock``) — read at render,
        # where the request has resolved it.
        self._lang = current_context().lang
        theme_slots = self._resolved_theme().get("slots", {})
        # Composed once per render through ``slot_class``, which honours the
        # instance's ``slots={...}`` override; the root's override is set by
        # the base layer after render, so the root reads the theme as is.
        cls = {name: self.slot_class(name) for name in theme_slots if name != "root"}
        placed = self._placed()
        for color in {p.item._color for p in placed}:
            refuse_unknown_color(self, color)
        rows: list[Node]
        if self._view == "month":
            start, end = 0, DAY
            rows = self._month(cls, placed)
        else:
            days = self._days(placed)
            cut = segments([p for p in placed if not p.item._all_day], days)
            start, end = self._span(cut)
            rows = [self._head(cls, days)]
            bars = all_day_bars([p for p in placed if p.item._all_day], days)
            if bars:
                rows.append(self._all_day_row(cls, days, bars))
            rows.append(self._body(cls, days, cut, start, end))
        if self._gestures():
            # The label of the new time during a gesture: rendered here so
            # the THEME paints it, moved by the runtime.
            rows.append(el("div", {"class": cls["tag"], "data-bz-scheduler-tag": "",
                                   "hidden": ""}))
        if self._on_move:
            rows.append(self._carrier(cls, "move", self._on_move))
        if self._on_resize:
            rows.append(self._carrier(cls, "resize", self._on_resize))
        if self._on_create and self._view != "month":
            rows.append(self._carrier(cls, "create", self._on_create))
            # The draft the runtime copies under a trace: painted by the
            # theme, never shown in place.
            rows.append(el("div", {"class": cls["draft"], "data-bz-scheduler-draft": "",
                                   "hidden": "", "aria-hidden": "true"}))

        attrs = self.emit_attrs()
        attrs["class"] = theme_slots.get("root", "")
        attrs["data-bz-view"] = self._view
        if self._gestures():
            # What the runtime reads to turn a pointer into a minute.
            attrs["data-bz-scheduler"] = ""
            attrs["data-bz-grid-start"] = str(start)
            attrs["data-bz-grid-end"] = str(end)
            attrs["data-bz-px"] = str(PX_PER_MINUTE)
            attrs["data-bz-snap"] = str(self._snap)
            attrs["data-bz-gap"] = str(GAP)
        return Element(tag=self._tag, attrs=attrs, children=tuple(rows))

    def _day_mark(self, cls: dict[str, str], day: date_type, today: date_type) -> str:
        """Today, and today only. The day of ``date=`` wears no mark: next
        to today's it would read as a second today."""
        return cls["today"] if day == today else ""

    def _head(self, cls: dict[str, str], days: list[date_type]) -> Element:
        today = date_type.today()
        heads: list[Node] = [el("div", {"class": cls["gutter"]})]
        for day in days:
            name = self._day_name(cls, day)
            number_class = f"{cls['day_number']} {self._day_mark(cls, day, today)}"
            heads.append(el("div", {"class": cls["day_head"]},
                            [name, el("div", {"class": number_class}, [str(day.day)])]))
        return el("div", {"class": cls["head"]}, heads)

    def _all_day_row(
        self,
        cls: dict[str, str],
        days: list[date_type],
        bars: list[tuple[_Placed, int, int, int]],
    ) -> Element:
        count = len(days)
        placed: list[Node] = []
        for p, first, span, row in bars:
            content = (list(p.item._render_children())
                       or [el("span", {"class": cls["all_day_title"]},
                              [p.item.emit_text_slot(p.item._title)])])
            placed.append(p.rewrap(finish_render(p.item, el("div", {
                "class": f"{bridge_class(p.item._color)} {cls['all_day_bar']}",
                "data-bz-event": p.key,
                "style": (
                    f"inset-inline-start:calc({first} * 100% / {count} + {GAP}px);"
                    f"width:calc({span} * 100% / {count} - {2 * GAP}px);"
                    f"top:{row * ALL_DAY_ROW}px;height:{ALL_DAY_ROW - GAP}px"
                ),
            }, content))))
        rows = max(row for *_, row in bars) + 1
        area = el("div", {"class": cls["all_day"], "style": f"height:{rows * ALL_DAY_ROW}px"},
                  placed)
        return el("div", {"class": cls["all_day_row"]},
                  [el("div", {"class": cls["gutter"]}), area])

    def _body(
        self,
        cls: dict[str, str],
        days: list[date_type],
        cut: list[_Segment],
        start: int,
        end: int,
    ) -> Element:
        height = f"height:{round((end - start) * PX_PER_MINUTE)}px"

        def top(minute: int) -> str:
            return f"top:{(minute - start) * PX_PER_MINUTE:.0f}px"

        hours = el("div", {"class": f"{cls['gutter']} {cls['hours']}", "style": height}, [
            # ``compact``: the axis is narrow, « 9 AM » and not « 9:00 AM ».
            el("div", {"class": cls["hour"], "style": top(minute),
                       **shown_clock(minute, self._lang, compact=True)[0]},
               shown_clock(minute, self._lang)[1])
            for minute in range(start, end + 1, 60)
        ])
        now = datetime.now()
        now_minute = now.hour * 60 + now.minute
        pieces = {s.placed.key for s in cut if not s.whole}
        columns: list[Node] = [hours]
        for day in days:
            # Clipped to the grid; wholly outside a fixed ``hours=``, not drawn.
            visible = [
                (s, max(s.start, start), min(s.end, end))
                for s in cut if s.day == day and min(s.end, end) > max(s.start, start)
            ]
            placed = lanes([(low, high) for _, low, high in visible])
            children: list[Node] = [
                el("div", {"class": cls["line_hour" if minute % 60 == 0 else "line_half"],
                           "style": top(minute)})
                for minute in range(start, end + 1, 30)
            ]
            for (segment, low, high), (lane, width) in zip(visible, placed, strict=True):
                draggable = segment.whole and (low, high) == (segment.start, segment.end)
                card = self._card(cls, segment, low - start, high - low, lane, width, draggable)
                # A zone gives back its wrapper once: a cut event's pieces
                # stay bare rather than repeat the zone's id.
                children.append(card if segment.placed.key in pieces
                                else segment.placed.rewrap(card))
            if day == now.date() and start <= now_minute <= end:
                children.append(el("div", {"class": cls["now"], "data-bz-now": "",
                                           "style": top(now_minute)}))
            columns.append(el("div", {"class": cls["column"], "data-bz-day": day.isoformat(),
                                      "style": height}, children))
        return el("div", {"class": cls["body"]}, columns)

    def _card(
        self,
        cls: dict[str, str],
        segment: _Segment,
        offset: int,
        minutes: int,
        lane: int,
        width: int,
        draggable: bool,
    ) -> Element:
        item = segment.placed.item
        key = segment.placed.key
        height = max(minutes * PX_PER_MINUTE - GAP, MIN_CARD_PX)
        compact = height < COMPACT_PX
        content = list(item._render_children())
        if not content and compact:
            start = segment.start
            content = [el("div", {"class": cls["event_line"]}, [
                el("span", {"class": cls["event_line_title"]}, [item.emit_text_slot(item._title)]),
                el("span", {"class": cls["event_line_time"], **shown_clock(start, self._lang)[0]},
                   shown_clock(start, self._lang)[1]),
            ])]
        elif not content:
            texts = [el("span", {"class": cls["event_title"]},
                        [item.emit_text_slot(item._title)])]
            if item._subtitle:
                texts.append(el("span", {"class": cls["event_subtitle"]}, [item._subtitle]))
            content = [el("div", {"class": cls["event_row"]}, texts)]
        attrs: dict[str, Any] = {
            "class": f"{bridge_class(item._color)} {cls['event']}",
            "data-bz-event": key,
            "data-bz-start": str(segment.start),
            "data-bz-duration": str(segment.end - segment.start),
            "tabindex": "0",
            # The WIDTH is written, not the end inset: a ``w-full`` child
            # would win over it and the card would spill into the next
            # column.
            "style": (
                f"inset-inline-start:calc({lane} * (100% - {GAP}px) / {width} + {GAP}px);"
                f"width:calc((100% - {GAP}px) / {width} - {GAP}px);"
                f"top:{offset * PX_PER_MINUTE + GAP / 2:.0f}px;height:{height:.0f}px"
            ),
        }
        if isinstance(item._title, str) and item._title:
            attrs["aria-label"] = ", ".join(filter(None, [
                item._title, item._subtitle, item._start.date().isoformat(),
                f"{clock(minute_of(item._start), self._lang)} – "
                f"{clock(minute_of(item._end), self._lang)}",
            ]))
            attrs["bz-attr:aria-label"] = spoken_event_js(
                item._title, item._subtitle, item._start.date(),
                minute_of(item._start), minute_of(item._end))
            if compact:
                # What the single line cannot hold, a pointer can read —
                # in the page's shared tooltip, not the browser's ``title``
                # bubble.
                attrs["data-bz-tip-root"] = ""
                attrs["data-bz-tip"] = attrs["aria-label"]
                attrs["bz-attr:data-bz-tip"] = attrs["bz-attr:aria-label"]
        if compact:
            attrs["data-compact"] = ""
        if self.id:
            suffix = "" if segment.day == item._start.date() else f"-{segment.day:%Y%m%d}"
            attrs["id"] = f"{self.id}__ev_{key_segment(key)}{suffix}"
        editable = draggable and item._editable
        if editable and self._on_move:
            attrs["data-bz-movable"] = ""
        if editable and self._on_resize:
            content.append(el("div", {"class": cls["resize"], "data-bz-resize": "",
                                      "aria-hidden": "true"}))
        if self._on_item_click is not None:
            attrs.update(item_action_attrs(
                self._on_item_click, event="item_click",
                payload={"key": key},
                owner_id=self.id, ctx=current_context(),
                dom_event="click", guard=_NOT_THE_EDGE,
                modifier=self._trigger_modifier,
            ))
            attrs["role"] = "button"
            attrs["bz-on:keydown"] = activate_keydown("$el.click();")
        # ``finish_render``: the scheduler draws the item (a card, a chip,
        # an all-day bar — one per day it crosses) instead of calling its
        # ``render()``, so the two passes of the metaclass wrap
        # (``classes=``, ``style=``, ``slots={"root"}``…) happen on each.
        return finish_render(item, el("div", attrs, content))

    # ── The month ──────────────────────────────────────────────────────

    def _day_name(self, cls: dict[str, str], day: date_type) -> Element:
        sunday_first = (day.weekday() + 1) % 7
        if self._weekday_names is not None:
            return el("div", {"class": cls["day_name"]}, [self._weekday_names[sunday_first]])
        return el("div", {
            "class": cls["day_name"],
            "bz-text": f"$bz.locale.weekdayLongNames()[{sunday_first}].slice(0, 3)",
        })

    def _month(self, cls: dict[str, str], placed: list[_Placed]) -> list[Node]:
        weeks = self._weeks(placed)
        head = el("div", {"class": cls["month_head"]},
                  [el("div", {"class": cls["month_head_cell"]}, [self._day_name(cls, d)])
                   for d in weeks[0]])
        timed = [p for p in placed if not p.item._all_day]
        whole_days = [p for p in placed if p.item._all_day]
        return [head, el("div", {"class": cls["month"]},
                         [self._month_week(cls, week, timed, whole_days) for week in weeks])]

    def _month_week(
        self,
        cls: dict[str, str],
        week: list[date_type],
        timed: list[_Placed],
        whole_days: list[_Placed],
    ) -> Element:
        today = date_type.today()
        count = len(week)
        bars = all_day_bars(whole_days, week)
        rows = max((row for *_, row in bars), default=-1) + 1
        reserved = MONTH_NUMBER_ROW + rows * MONTH_BAR_ROW
        cut = segments(timed, week)
        cells: list[Node] = []
        for day in week:
            outside = day.month != self._date.month
            number_class = cls["month_number"]
            if mark := self._day_mark(cls, day, today):
                number_class = f"{number_class} {mark}"
            elif outside:
                number_class = f"{number_class} {cls['month_outside']}"
            pieces = sorted((s for s in cut if s.day == day), key=lambda s: (s.start, -s.end))
            chips: list[Node] = [self._chip(cls, s) for s in pieces[:MONTH_CHIPS]]
            if len(pieces) > MONTH_CHIPS:
                chips.append(el("div", {"class": cls["month_more"]},
                                [f"+{len(pieces) - MONTH_CHIPS}"]))
            cells.append(el("div", {"class": cls["month_cell"], "data-bz-day": day.isoformat()}, [
                el("div", {"class": number_class}, [str(day.day)]),
                el("div", {"class": cls["month_list"], "data-bz-month-list": "",
                           "style": f"padding-top:{reserved - MONTH_NUMBER_ROW}px"}, chips),
            ]))
        placed_bars: list[Node] = []
        for p, first, span, row in bars:
            content = (list(p.item._render_children())
                       or [el("span", {"class": cls["all_day_title"]},
                              [p.item.emit_text_slot(p.item._title)])])
            placed_bars.append(p.rewrap(finish_render(p.item, el("div", {
                "class": f"{bridge_class(p.item._color)} {cls['all_day_bar']}",
                "data-bz-event": p.key,
                "style": (
                    f"inset-inline-start:calc({first} * 100% / {count} + {GAP}px);"
                    f"width:calc({span} * 100% / {count} - {2 * GAP}px);"
                    f"top:{MONTH_NUMBER_ROW + row * MONTH_BAR_ROW}px;"
                    f"height:{MONTH_BAR_ROW - GAP}px"
                ),
            }, content))))
        return el("div", {"class": cls["month_week"]}, cells + placed_bars)

    def _chip(self, cls: dict[str, str], segment: _Segment) -> Element:
        item = segment.placed.item
        key = segment.placed.key
        content = list(item._render_children())
        if not content:
            content = [
                el("span", {"class": cls["chip_time"], **shown_clock(segment.start, self._lang)[0]},
                   shown_clock(segment.start, self._lang)[1]),
                el("span", {"class": cls["chip_title"]}, [item.emit_text_slot(item._title)]),
            ]
        attrs: dict[str, Any] = {
            "class": f"{bridge_class(item._color)} {cls['chip']}",
            "data-bz-event": key,
            "data-bz-start": str(segment.start),
            "data-bz-duration": str(int((item._end - item._start).total_seconds() // 60)),
            "tabindex": "0",
        }
        if isinstance(item._title, str) and item._title:
            attrs["aria-label"] = ", ".join(filter(None, [
                item._title, item._subtitle, item._start.date().isoformat(),
                f"{clock(minute_of(item._start), self._lang)} – "
                f"{clock(minute_of(item._end), self._lang)}",
            ]))
            attrs["bz-attr:aria-label"] = spoken_event_js(
                item._title, item._subtitle, item._start.date(),
                minute_of(item._start), minute_of(item._end))
        if self.id:
            suffix = "" if segment.day == item._start.date() else f"-{segment.day:%Y%m%d}"
            attrs["id"] = f"{self.id}__ev_{key_segment(key)}{suffix}"
        if segment.whole and item._editable and self._on_move:
            attrs["data-bz-movable"] = ""
        if self._on_item_click is not None:
            attrs.update(item_action_attrs(
                self._on_item_click, event="item_click",
                payload={"key": key},
                owner_id=self.id, ctx=current_context(),
                dom_event="click", guard=_NOT_THE_EDGE,
                modifier=self._trigger_modifier,
            ))
            attrs["role"] = "button"
            attrs["bz-on:keydown"] = activate_keydown("$el.click();")
        # ``finish_render``: the scheduler draws the item (a card, a chip,
        # an all-day bar — one per day it crosses) instead of calling its
        # ``render()``, so the two passes of the metaclass wrap
        # (``classes=``, ``style=``, ``slots={"root"}``…) happen on each.
        return finish_render(item, el("div", attrs, content))
