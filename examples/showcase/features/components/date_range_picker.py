"""``/date-range-picker`` — a start and an end, picked on one calendar."""

from datetime import date, timedelta

from bretzel import refreshable, ui
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Two dates in one field — a report period, a trip, a leave "
           "request — picked with two clicks on a shared calendar.")


def report_period() -> None:
    today = date.today()
    with ui.form_field(label="Period", classes="w-full max-w-sm"):
        ui.date_range_picker(value=(today - timedelta(days=30), today))


def book_a_trip() -> None:
    today = date.today()
    sold_out = [today + timedelta(days=offset) for offset in (6, 7, 13)]
    with ui.card(padding="md", classes="w-full max-w-md"), ui.vstack(gap="md"):
        with ui.hstack(gap="sm"):
            ui.icon("hotel", color="primary", size="lg")
            with ui.vstack(gap="none"):
                ui.text("Seaside Suites, Lisbon", weight="medium")
                ui.text("From €128 a night", color="muted", size="sm")
        ui.date_range_picker(placeholder_start="Check-in",
                             placeholder_end="Check-out", min=today,
                             disabled_dates=sold_out, color="secondary")
        ui.button("Check availability", icon_left="search")


def leave_request() -> None:
    today = date.today()
    with ui.vstack(gap="md", classes="w-full max-w-sm"):
        with ui.form_field(label="Annual leave", hint="12 days left this year."):
            ui.date_range_picker(value=(today + timedelta(days=20),
                                        today + timedelta(days=27)),
                                 separator="to", size="lg", name="leave")
        with ui.form_field(label="Last approved leave"):
            ui.date_range_picker(value=(today - timedelta(days=90),
                                        today - timedelta(days=83)),
                                 disabled=True, size="sm", name="approved")


def last_two_weeks() -> list[str]:
    today = date.today()
    return [(today - timedelta(days=13)).isoformat(), today.isoformat()]


class Report(PageState):
    period: list = field(default_factory=last_two_weeks)


def change_period(report: Report) -> None:
    """The new period is already in ``report``; the figures re-render."""


@refreshable
def revenue_figures() -> None:
    start, end = (date.fromisoformat(day) for day in Report().period)
    days = (end - start).days + 1
    with ui.grid(cols=3, gap="md", classes="w-full"):
        for label, value in (("Days", str(days)),
                             ("Orders", str(days * 37)),
                             ("Revenue", f"€{days * 1_284:,}")):
            with ui.vstack(gap="none"):
                ui.text(label, color="muted", size="sm")
                ui.heading(value, level=3, size="xl")


def revenue_report() -> None:
    with ui.card(padding="md", classes="w-full max-w-lg"), ui.vstack(gap="md"):
        ui.date_range_picker(value=Report().period, max=date.today(),
                             clearable=False, on_change=change_period)
        revenue_figures()


def page() -> None:
    page_header("date_range_picker", "Date range picker", SUMMARY)
    example("A report period", report_period,
            note="The value is a pair of dates: start, then end.")
    example("Book a trip", book_a_trip,
            note="Your own placeholders, no date in the past, and sold-out "
                 "nights disabled.")
    example("A leave request", leave_request,
            note="A custom separator and size, and a disabled range for one "
                 "that is already approved.")
    example("A revenue report", revenue_report,
            uses=[last_two_weeks, Report, change_period, revenue_figures],
            note="on_change sends the two dates to Python once the range is "
                 "closed; the figures re-render.")
