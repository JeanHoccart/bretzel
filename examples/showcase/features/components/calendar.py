"""``/calendar`` — a month grid to pick a day or a stay, always open."""

from datetime import date, timedelta

from bretzel import refreshable, ui
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("An always-open month grid: one day or a range, busy days marked, "
           "closed days greyed out.")


def pick_a_day() -> None:
    ui.calendar(value=date.today() + timedelta(days=3))


def book_a_stay() -> None:
    today = date.today()
    ui.calendar(value=(today + timedelta(days=5), today + timedelta(days=9)),
                mode="range", min=today, color="success")


def room_bookings() -> None:
    first = date.today().replace(day=1)
    bookings = {first + timedelta(days=day): count
                for day, count in ((1, 2), (3, 5), (8, 1), (10, 7),
                                   (14, 3), (17, 4), (21, 6), (24, 2))}
    with ui.vstack(gap="xs", align="center"):
        ui.calendar(marks=bookings, week_start=0, color="secondary")
        ui.text("Meeting room A · a dot on every booked day", color="muted",
                size="sm")


def closed_days() -> None:
    today = date.today()
    next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    sundays = [today + timedelta(days=offset) for offset in range(61)
               if (today + timedelta(days=offset)).weekday() == 6]
    ui.calendar(month=next_month, min=today, max=today + timedelta(days=60),
                disabled_dates=sundays, size="lg")


def tomorrow() -> str:
    return (date.today() + timedelta(days=1)).isoformat()


class Agenda(PageState):
    day: str = field(default_factory=tomorrow)


def open_day(agenda: Agenda) -> None:
    """The clicked day is already in ``agenda``; the list re-renders."""


APPOINTMENTS = [
    ("09:00", "Dental check-up", "Dr. Moreau"),
    ("10:30", "Physiotherapy", "Dr. Hart"),
    ("13:15", "Blood test", "Lab 2"),
    ("15:00", "Follow-up call", "Dr. Moreau"),
    ("16:45", "Eye exam", "Dr. Okafor"),
]


@refreshable
def day_schedule() -> None:
    day = date.fromisoformat(Agenda().day)
    with ui.vstack(gap="sm", classes="min-w-64"):
        ui.heading(f"{day:%A, %B} {day.day}", level=3, size="md")
        if day.weekday() >= 5:
            ui.text("The clinic is closed at weekends.", color="muted")
            return
        for hour, what, who in APPOINTMENTS[day.day % 3:day.day % 3 + 3]:
            with ui.hstack(gap="sm"):
                ui.badge(hour, variant="soft", size="sm", classes="font-mono")
                ui.text(what, weight="medium")
                ui.text(who, color="muted", size="sm")


def clinic_agenda() -> None:
    with ui.hstack(gap="xl", align="start", wrap=True):
        ui.calendar(value=Agenda().day, on_change=open_day)
        day_schedule()


def page() -> None:
    page_header("calendar", "Calendar", SUMMARY)
    example("Pick a day", pick_a_day,
            note="The value is a date; today is outlined.")
    example("Book a stay", book_a_stay,
            note="mode=\"range\": the first click sets the check-in, the "
                 "second the check-out. min= forbids the past.")
    example("Busy days", room_bookings,
            note="marks= takes a mapping of date to count (or a list of "
                 "dates). week_start=0 starts the week on Sunday.")
    example("Closed days", closed_days,
            note="A two-month booking window opened on next month, with every "
                 "Sunday disabled.")
    example("A day's appointments", clinic_agenda,
            uses=[tomorrow, Agenda, open_day, day_schedule],
            note="on_change sends the clicked day to Python; the schedule "
                 "beside it re-renders.")
