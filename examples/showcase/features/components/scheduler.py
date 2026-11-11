"""``/scheduler`` — events posed on a grid of time, to the minute."""

import datetime as dt

from bretzel import ui
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Events on a grid of hours, placed to the minute: a timetable, "
           "a room's bookings, a team's week. Overlaps sit side by side.")

MONDAY = dt.date.today() - dt.timedelta(days=dt.date.today().weekday())


def at(day: int, hour: str, minutes: int) -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime.combine(MONDAY + dt.timedelta(days=day), dt.time.fromisoformat(hour))
    return start, start + dt.timedelta(minutes=minutes)


def timetable() -> list[dict]:
    rows = [
        (0, "08:05", 55, "Physics", "Room 209", "violet"),
        (0, "09:00", 55, "Chemistry", "Lab", "green"),
        (1, "08:15", 55, "Physics", "Room 209", "violet"),
        (1, "10:15", 90, "Team meeting", "Hall", "slate"),
        (2, "09:00", 55, "Chemistry", "Lab", "green"),
        (2, "09:30", 55, "Office hours", "Library", "amber"),
        (3, "13:45", 55, "Physics", "Room 209", "violet"),
    ]
    events = []
    for day, hour, minutes, title, place, color in rows:
        start, end = at(day, hour, minutes)
        events.append({"id": f"{day}-{hour}", "title": title, "subtitle": place,
                       "color": color, "start": start, "end": end})
    events.append({"id": "trip", "title": "School trip", "color": "sky", "all_day": True,
                   "start": MONDAY + dt.timedelta(days=3),
                   "end": MONDAY + dt.timedelta(days=5)})
    return events


def week() -> None:
    ui.scheduler(events=timetable(), date=MONDAY, hours=(8, 15))


def custom_cards() -> None:
    with ui.scheduler(date=MONDAY, hours=(8, 12)):
        for event in timetable():
            if event.get("all_day"):
                continue
            with ui.scheduler_item(key=event["id"], title=event["title"],
                                   start=event["start"], end=event["end"],
                                   color=event["color"]), ui.vstack(gap="xs"):
                ui.text(event["title"], weight="bold", size="sm")
                with ui.hstack(gap="xs", align="center"):
                    ui.icon("map-pin", size="xs")
                    ui.text(event["subtitle"], size="xs")


def day() -> None:
    ui.scheduler(events=timetable(), date=MONDAY + dt.timedelta(days=2),
                 view="day", hours=(8, 12))


def page() -> None:
    page_header("scheduler", "Scheduler", SUMMARY)
    example("A teacher's week", week, uses=[at, timetable], full=True,
            note="Each event is a dict: id, title, start, end, and an optional "
                 "subtitle and colour. all_day events become one bar across "
                 "their days.")
    example("Cards drawn your way", custom_cards, uses=[at, timetable], full=True,
            note="Write the loop: each ui.scheduler_item says when, its "
                 "children say what the card shows. The scheduler places them.")
    example("One day", day, uses=[at, timetable],
            note='view="day" shows a single column — the view for a phone.')
