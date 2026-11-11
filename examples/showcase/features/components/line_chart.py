"""``/line-chart`` — a value over time, and several of them side by side."""

import math
from datetime import date, timedelta

from bretzel import refreshable, ui
from bretzel.components import Reference, Series
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Trends over time with dates on the axis, several series, "
           "targets and thresholds — and a hover crosshair on every point.")


def dollars(value: float) -> str:
    return f"${value / 1000:.0f}k"


def mrr() -> list[tuple[date, float]]:
    months = [date(2025, m, 1) for m in range(9, 13)] + \
             [date(2026, m, 1) for m in range(1, 9)]
    values = [61200, 63900, 66100, 70400, 72800, 75100, 79600, 83300,
              86900, 91800, 95200, 99700]
    return list(zip(months, values, strict=True))


def mrr_card() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        with ui.hstack(justify="between", align="start", wrap=True):
            with ui.vstack(gap="none"):
                ui.text("Monthly recurring revenue", size="sm", color="muted")
                ui.heading("$99.7k", level=3, size="2xl")
            ui.badge("+62.9% in 12 months", color="success", variant="soft",
                     size="sm", icon_left="trending-up")
        ui.line_chart(data=mrr(), y_format=dollars, area_fill=True, size="sm")


def signups_by_channel() -> list[Series]:
    weeks = [date(2026, 6, 1) + timedelta(weeks=i) for i in range(10)]
    return [
        Series("Organic", list(zip(weeks, [320, 341, 338, 362, 390, 402,
                                           398, 431, 455, 470], strict=True))),
        Series("Paid", list(zip(weeks, [210, 236, 228, 251, 244, 270,
                                        302, 288, 296, 315], strict=True))),
        Series("Referral", list(zip(weeks, [88, 92, 101, 97, 112, 126,
                                            131, 140, 138, 152], strict=True))),
    ]


def multi_series() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        with ui.vstack(gap="none"):
            ui.text("Weekly sign-ups by channel", size="sm", color="muted")
            ui.heading("937", level=3, size="2xl")
        ui.line_chart(data=signups_by_channel())


def latency() -> list[tuple[date, float]]:
    days = [date(2026, 9, 1) + timedelta(days=i) for i in range(14)]
    values = [212, 198, 225, 240, 231, 318, 342, 267, 229, 214, 205, 221,
              236, 219]
    return list(zip(days, values, strict=True))


def threshold() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        with ui.hstack(justify="between", align="start", wrap=True):
            with ui.vstack(gap="none"):
                ui.text("API latency · p95", size="sm", color="muted")
                ui.heading("219 ms", level=3, size="2xl")
            ui.badge("2 breaches this month", color="warning", variant="soft",
                     size="sm", icon_left="triangle-alert")
        ui.line_chart(data=latency(), color="warning", smooth=False,
                      show_dots=True, y_unit="ms", size="sm",
                      y_reference_lines=[Reference(300, "SLO", "error")])


def active_users() -> list[Series]:
    months = [date(2026, m, 1) for m in range(1, 10)]
    return [
        Series("This year", list(zip(months, [4.1, 4.4, 4.9, 5.2, 5.8, 6.1,
                                              6.0, 6.7, 7.2], strict=True))),
        Series("Last year", list(zip(months, [3.2, 3.3, 3.6, 3.5, 3.9, 4.0,
                                              3.8, 4.2, 4.4], strict=True)), color="muted"),
    ]


def comparison() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        ui.text("Monthly active users, in thousands", size="sm", color="muted")
        ui.line_chart(data=active_users(), show_gridlines=False, y_unit="k",
                      size="sm")


def releases() -> list[tuple[date, float]]:
    weeks = [date(2026, 7, 6) + timedelta(weeks=i) for i in range(8)]
    return list(zip(weeks, [12, 9, 15, 7, 18, 11, 14, 20], strict=True))


class Release(PageState):
    week: str = field(default="")


def pick_week(week: str, issues: float) -> None:
    Release().week = week


@refreshable
def release_detail() -> None:
    week = Release().week
    ui.text(f"Week of {week}: the changelog opens here." if week
            else "Click a week to open its changelog.", size="sm", color="muted")


def clickable() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        ui.text("Issues closed per week · click a point", size="sm", color="muted")
        ui.line_chart(data=releases(), show_dots=True, y_min=0,
                      y_label="Issues closed", on_item_click=pick_week, size="sm")
        release_detail()


class Traffic(PageState):
    period: str = field(default="30")


def change_period(state: Traffic) -> None:
    """The typed parameter receives the toggle's value; nothing else to do."""


def visits(days: int) -> list[tuple[date, float]]:
    start = date(2026, 9, 28) - timedelta(days=days - 1)
    points = []
    for i in range(days):
        day = start + timedelta(days=i)
        weekend = 320 if day.weekday() >= 5 else 0
        points.append((day, 2100 + 160 * math.sin(i / 5) + 4 * i - weekend))
    return points


@refreshable
def traffic_chart() -> None:
    days = int(Traffic().period)
    ui.line_chart(data=visits(days), color="info", area_fill=True,
                  y_format="abbreviated", size="sm")


def live_range() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        with ui.hstack(justify="between", align="center", wrap=True):
            ui.text("Daily visits", size="sm", color="muted")
            ui.toggle_group(value=Traffic().period, on_change=change_period,
                            size="sm", options=[("7", "7 days"),
                                                ("30", "30 days"),
                                                ("90", "90 days")])
        traffic_chart()


def page() -> None:
    page_header("line_chart", "Line chart", SUMMARY)
    example("A revenue card", mrr_card, uses=[dollars, mrr], full=True,
            note="Pass dates as x values: the axis formats itself for the "
                 "span it covers.")
    example("Several series", multi_series, uses=[signups_by_channel],
            full=True,
            note="One Series per line, sharing the same x values. The legend "
                 "and the colours follow the order you give.")
    example("Against a threshold", threshold, uses=[latency], full=True,
            note="Straight segments and dots for discrete measures, and a "
                 "reference line for the objective.")
    example("This year against last year", comparison, uses=[active_users],
            full=True,
            note="Pin the comparison series to muted so the current one "
                 "carries the colour.")
    example("A point that runs Python", clickable,
            uses=[releases, Release, pick_week, release_detail], full=True,
            note="on_item_click receives the point's x and y — a date as its "
                 "ISO text. One series: a column of several would not say "
                 "which point.")
    example("A range that reloads the chart", live_range,
            uses=[Traffic, change_period, visits, traffic_chart], full=True,
            note="The toggle writes the period to a server state; only the "
                 "chart that reads it is rendered again.")
