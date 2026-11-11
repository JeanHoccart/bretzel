"""``/time-picker`` — hours and minutes in two snapping columns."""

from datetime import datetime, timedelta

from bretzel import refreshable, ui
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A time field with an hours column and a minutes column — the "
           "step decides which slots exist.")


def meeting_start() -> None:
    with ui.form_field(label="Starts at", classes="w-full max-w-xs"):
        ui.time_picker(value="09:30")


def opening_hours() -> None:
    with ui.card(padding="md", classes="w-full max-w-md"), ui.vstack(gap="md"):
        ui.heading("Opening hours", level=3, size="md")
        for day, opens, closes in (("Monday", "08:00", "18:00"),
                                   ("Saturday", "10:00", "16:30")):
            with ui.form_field(label=day), ui.grid(cols=2, gap="sm"):
                ui.time_picker(value=opens, step=30, min="06:00", max="22:00",
                               clearable=False, name=f"{day}-opens")
                ui.time_picker(value=closes, step=30, min="06:00", max="22:00",
                               clearable=False, name=f"{day}-closes")


def sizes() -> None:
    with ui.vstack(gap="md", classes="w-full max-w-xs"):
        ui.time_picker(value="07:15", size="sm", name="time-sm")
        ui.time_picker(value="12:00", size="md", name="time-md")
        ui.time_picker(value="18:45", size="lg", name="time-lg")
        ui.time_picker(value="23:00", disabled=True, name="time-locked")


class Booking(PageState):
    start: str = field(default="14:30")


def book_slot(booking: Booking) -> None:
    """The picked time is already in ``booking``; the confirmation follows."""


@refreshable
def booking_summary() -> None:
    start = Booking().start
    if not start:
        ui.text("Pick a time to see your slot.", color="muted")
        return
    end = datetime.strptime(start, "%H:%M") + timedelta(minutes=45)
    with ui.hstack(gap="sm"):
        ui.icon("calendar-check", color="success")
        ui.text(f"Onboarding call, {start} – {end:%H:%M}", weight="medium")
        ui.badge("45 min", variant="soft", size="sm")


def book_a_call() -> None:
    with ui.card(padding="md", classes="w-full max-w-md"), ui.vstack(gap="md"):
        with ui.form_field(label="Onboarding call with Priya",
                           hint="Between 09:00 and 17:00, on the quarter hour."):
            ui.time_picker(value=Booking().start, min="09:00", max="17:00",
                           color="success", on_change=book_slot)
        booking_summary()


def page() -> None:
    page_header("time_picker", "Time picker", SUMMARY)
    example("A meeting start", meeting_start,
            note="The value is an “HH:MM” string. The default step is 15 "
                 "minutes.")
    example("Opening hours", opening_hours,
            note="step=30 for half hours; min and max disable the hours "
                 "outside the day.")
    example("Sizes", sizes)
    example("Book a call", book_a_call,
            uses=[Booking, book_slot, booking_summary],
            note="Picking a minute closes the panel and sends the time to "
                 "Python; the confirmation re-renders.")
