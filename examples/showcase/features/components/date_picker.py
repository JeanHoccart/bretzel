"""``/date-picker`` — a date field with a calendar one click away."""

from datetime import date, timedelta

from bretzel import refreshable, ui
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A date you can type or pick: the calendar opens in a popover, "
           "with bounds, closed days and marks.")


def due_date() -> None:
    with ui.form_field(label="Due date", classes="w-full max-w-xs"):
        ui.date_picker(value=date.today() + timedelta(days=14))


def date_of_birth() -> None:
    with ui.form_field(label="Date of birth",
                       hint="You must be 18 or over to open an account.",
                       classes="w-full max-w-xs"):
        ui.date_picker(max=date.today() - timedelta(days=18 * 365),
                       placeholder="YYYY-MM-DD")


def delivery_day() -> None:
    today = date.today()
    window = [today + timedelta(days=offset) for offset in range(1, 31)]
    weekdays = [day for day in window if day.weekday() < 5]
    weekends = [day for day in window if day.weekday() >= 5]
    few_slots_left = {weekdays[0]: 1, weekdays[1]: 2}
    with ui.form_field(label="Delivery day",
                       hint="Weekdays within the next 30 days. A dot means "
                            "few slots left.",
                       classes="w-full max-w-xs"):
        ui.date_picker(value=weekdays[2], min=window[0], max=window[-1],
                       disabled_dates=weekends,
                       marks=few_slots_left, clearable=False, color="success")


def sizes() -> None:
    today = date.today()
    with ui.vstack(gap="md", classes="w-full max-w-xs"):
        for offset, size in enumerate(("xs", "sm", "md", "lg", "xl")):
            ui.date_picker(value=today + timedelta(days=offset), size=size,
                           name=f"when-{size}")
        ui.date_picker(value=today, disabled=True, name="when-locked")


def next_monday() -> str:
    today = date.today()
    return (today + timedelta(days=7 - today.weekday())).isoformat()


class Post(PageState):
    publish_on: str = field(default_factory=next_monday)


def schedule_post(post: Post) -> None:
    """The new date is already in ``post``; the summary re-renders."""


@refreshable
def schedule_summary() -> None:
    publish_on = Post().publish_on
    if not publish_on:
        ui.text("Not scheduled — the post stays a draft.", color="muted")
        return
    day = date.fromisoformat(publish_on)
    days_left = (day - date.today()).days
    with ui.hstack(gap="sm"):
        ui.icon("send", color="primary")
        ui.text(f"Goes live on {day:%A, %B} {day.day}", weight="medium")
        ui.badge(f"in {days_left} days" if days_left > 0 else "today",
                 variant="soft", size="sm")


def schedule_a_post() -> None:
    with ui.card(padding="md", classes="w-full max-w-md"), ui.vstack(gap="md"):
        with ui.form_field(label="Publish “Our Q3 product update” on"):
            ui.date_picker(value=Post().publish_on, min=date.today(),
                           on_change=schedule_post)
        schedule_summary()


def page() -> None:
    page_header("date_picker", "Date picker", SUMMARY)
    example("A due date", due_date,
            note="Type the date or pick it; the value is an ISO date.")
    example("Date of birth", date_of_birth,
            note="max= keeps every later day out of reach, in the grid and "
                 "when typed.")
    example("A delivery day", delivery_day,
            note="A window with min and max, weekends disabled, marks on "
                 "busy days, and no clear button.")
    example("Sizes", sizes)
    example("Schedule a post", schedule_a_post,
            uses=[next_monday, Post, schedule_post, schedule_summary],
            note="on_change sends the date to Python; the summary below "
                 "re-renders.")
