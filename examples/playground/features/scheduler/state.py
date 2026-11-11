"""Page-scoped + client-side state for the Scheduler playground, and the
teacher's week every card draws.

- :class:`SchedulerPlayground` (PageState) — the Server playground card:
  one field per prop, per universal escape hatch, per event shape.
- :class:`SchedulerWeek` (PageState) — the live week of the Server events
  card: the events that moved, by id.
- :class:`SchedulerQuestion` (PageState) — the move waiting for "this one
  only?".
- :class:`SchedulerAgenda` (PageState) — the assembled agenda of the
  Composability card: the date shown, the view, the calendars ticked.
- :class:`SchedulerEvents` (PageState) / :class:`SchedulerClientEvents`
  (ClientState) — the server and client logs.

The data is laid on the CURRENT week, so today's column and the line of
the current time show whenever today is a weekday.
"""

import datetime as dt

from bretzel.state import ClientState, PageState, field

TODAY = dt.date.today()
MONDAY = TODAY - dt.timedelta(days=TODAY.weekday())
TUESDAY = MONDAY + dt.timedelta(days=1)

VIEWS = ["day", "3days", "week", "month"]
#: The palette names a card can take — a sample of the bridges.
COLORS = ["primary", "secondary", "success", "warning", "error", "info", "muted",
          "violet", "amber", "teal", "pink", "indigo", "sky", "slate"]
FRENCH_DAYS = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"]

#: (day from Monday, "HH:MM", minutes, title, subtitle, colour, calendar)
LESSONS = [
    (0, "08:05", 55, "4e2", "C209", "violet", "lessons"),
    (0, "09:00", 55, "3e1", "C209", "amber", "lessons"),
    (0, "10:15", 55, "2de3", "C209", "green", "lessons"),
    (0, "13:45", 55, "5e1", "C209", "teal", "lessons"),
    (1, "08:05", 55, "3e4", "C209", "pink", "lessons"),
    (1, "09:00", 55, "2de3", "Labo", "green", "lessons"),
    (1, "10:15", 55, "4e2", "C209", "violet", "lessons"),
    (1, "14:45", 55, "1re2", "Labo", "indigo", "lessons"),
    (1, "17:00", 180, "Parents' meeting", "Hall", "slate", "school"),
    (2, "08:05", 55, "1re2", "C209", "indigo", "lessons"),
    (2, "09:00", 55, "5e3", "C209", "sky", "lessons"),
    (2, "09:30", 55, "Tutoring", "Library", "cyan", "school"),
    (2, "10:15", 55, "3e1", "C209", "amber", "lessons"),
]
#: The two that are not lessons: moving them asks nothing.
ONE_OFFS = {"Parents' meeting", "Tutoring"}
CALENDARS = [("lessons", "Lessons"), ("school", "School life")]


def lesson(day: int, at: str, minutes: int, title: str, subtitle: str, color: str) -> dict:
    start = dt.datetime.combine(MONDAY + dt.timedelta(days=day), dt.time.fromisoformat(at))
    return {
        "id": f"{title}-{start:%Y-%m-%dT%H%M}",
        "title": title,
        "subtitle": subtitle,
        "color": color,
        "start": start,
        "end": start + dt.timedelta(minutes=minutes),
    }


def week_events() -> list[dict]:
    return [lesson(*row[:6]) for row in LESSONS] + [
        {"id": "mock-exam", "title": "Mock exam", "color": "pink", "all_day": True,
         "start": MONDAY + dt.timedelta(days=2)},
        {"id": "autumn-holidays", "title": "Autumn holidays", "color": "slate",
         "all_day": True,
         "start": MONDAY + dt.timedelta(days=3), "end": MONDAY + dt.timedelta(days=5)},
    ]


def month_events() -> list[dict]:
    """Four weeks of the same timetable, for the month view: the lessons
    repeat, the holidays stay once."""
    events = []
    for week in range(-1, 3):
        for row in LESSONS:
            event = lesson(*row[:6])
            shift = dt.timedelta(weeks=week)
            events.append({**event, "id": f"{event['id']}+{week}",
                           "start": event["start"] + shift, "end": event["end"] + shift})
    return events + week_events()[-2:]


TITLES = {e["id"]: e["title"] for e in week_events()}
CALENDAR_OF = {lesson(*row[:6])["id"]: row[6] for row in LESSONS}


class SchedulerPlayground(PageState):
    view:          str = field(default="week")
    date:          str = field(default=MONDAY.isoformat())
    weekend:       str = field(default="auto")
    first_hour:    str = field(default="")
    last_hour:     str = field(default="")
    weekday_names: str = field(default="")
    snap:          str = field(default="5")
    on_item_click_mode: str = field(default="server")
    on_move_mode:  str = field(default="server")
    classes:       str = field(default="")
    custom_id:     str = field(default="")
    style:         str = field(default="")
    extra_attrs:   str = field(default="")
    visible:       str = field(default="on")


class SchedulerWeek(PageState):
    """The live week: event id -> [start, end] (ISO), once it has moved."""

    moved: dict = field(default_factory=dict)
    #: The events traced on the empty grid: [start, end] (ISO) each.
    created: list = field(default_factory=list)


class SchedulerQuestion(PageState):
    """The move waiting for "this one only?": [event id, start, end]."""

    pending: list = field(default_factory=list)


class SchedulerAgenda(PageState):
    """The assembled agenda: the date shown, the view, the calendars."""

    date: str = field(default=MONDAY.isoformat())
    view: str = field(default="week")
    calendars: list = field(default_factory=lambda: [key for key, _ in CALENDARS])


class SchedulerEvents(PageState):
    log: list = field(default_factory=list)


class SchedulerClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)
