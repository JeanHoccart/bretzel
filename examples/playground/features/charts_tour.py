"""``/charts-tour`` — everything the charts can do, on one page.

The component pages each show one chart at a time, with a control per
prop: the right place to try a prop, the wrong one to find out what
exists. Jean asked (2026-10-29) for one place that shows it all — the
base added that day (a fixed scale, axis titles, a click and a legend
everywhere, the keyboard, the data behind the drawing) and what was
there before and nobody looked at (stacks, references, a date axis,
the donut's centre, the sizes, the empty state).

One card per feature: what it shows, what to try, the call that draws it.
"""

from __future__ import annotations

from datetime import date, timedelta

from bretzel import refreshable, ui
from bretzel.components import Reference, Series
from bretzel.state import PageState, field

PATH = "/charts-tour"

MARKS = [12.5, 14, 8, 16.5, 11, 9.5, 15, 13, 18, 7, 12, 14.5, 10, 16, 13.5,
         11.5, 19, 6.5, 12, 15.5]
SPREAD = [(str(n), sum(1 for m in MARKS if int(m) == n)) for n in range(21)]
TESTS = [("Quiz 14/9", 13.2), ("Lab 24/9", 12.7), ("Test 15/10", 12.6)]
#: The same, for the small charts: their labels have no room.
SHORT = [("Quiz", 13.2), ("Lab", 12.7), ("Test", 12.6)]
TERMS = [
    Series("5A", [("Term 1", 12.4), ("Term 2", 13.1), ("Term 3", 13.8)]),
    Series("5B", [("Term 1", 11.2), ("Term 2", 11.9), ("Term 3", 12.5)]),
    Series("5C", [("Term 1", 13.0), ("Term 2", 12.2), ("Term 3", 12.9)]),
]
SKILLS = [
    Series("Mastered", [("Practice", 14), ("Design", 11), ("Tools", 9), ("Language", 6)],
           color="success"),
    Series("Fragile", [("Practice", 6), ("Design", 8), ("Tools", 9), ("Language", 10)],
           color="warning"),
    Series("Not yet", [("Practice", 4), ("Design", 5), ("Tools", 6), ("Language", 8)],
           color="error"),
]
WEEKS = [date(2026, 9, 7) + timedelta(weeks=i) for i in range(8)]
ABSENCES = list(zip(WEEKS, [2, 1, 3, 0, 4, 2, 1, 5], strict=True))
CLASSES = [
    Series("5A", list(zip(WEEKS, [12.1, 12.4, 12.9, 13.0, 12.6, 13.3, 13.5, 13.8], strict=True))),
    Series("5B", list(zip(WEEKS, [11.0, 11.4, 11.2, 11.9, 12.1, 11.8, 12.4, 12.5], strict=True))),
]
EFFORT = [(4, 9.5), (6, 11), (7, 12.5), (9, 13), (10, 15.5), (12, 14), (13, 17),
          (3, 7), (8, 10.5), (11, 16), (5, 12), (14, 18)]
WORK = [("Done", 18), ("Late", 4), ("Not done", 2)]


class TourClicks(PageState):
    log: list = field(default_factory=list)


def clicked_bar(label: str, value: float) -> None:
    TourClicks().log = [f"bar → {label} = {value}", *TourClicks().log][:6]


def clicked_point(x, y) -> None:
    TourClicks().log = [f"point → x={x}, y={y}", *TourClicks().log][:6]


def clicked_slice(label: str, value: float) -> None:
    TourClicks().log = [f"slice → {label} = {value}", *TourClicks().log][:6]


@refreshable
def click_log() -> None:
    log = TourClicks().log
    if not log:
        ui.text("No click yet — the server writes each one here.", color="muted", size="sm")
    for entry in log:
        ui.text(entry, size="sm", classes="font-mono")


def card(title: str, what: str, call: str, new: bool = False):
    """A feature: its title, what it shows and what to try, the call."""
    box = ui.card(padding="md")
    with box, ui.vstack(gap="xs"):
        with ui.hstack(gap="sm", align="center", wrap=True):
            ui.heading(title, level=3)
            if new:
                ui.badge("New", variant="soft", color="primary", size="sm")
        ui.text(what, color="muted", size="sm")
        ui.text(call, size="xs", classes="font-mono text-text/60")
    return box


def section(title: str, intro: str) -> None:
    with ui.vstack(gap="none", classes="pt-4"):
        ui.heading(title, level=2)
        ui.text(intro, color="muted")


def page() -> None:
    with ui.container(), ui.vstack(gap="lg"):
        ui.heading("Charts tour", level=1)
        ui.text("Everything the five charts do, one card each. Hover, click, "
                "press Tab: each card says what to try. The component pages "
                "(Bar chart, Line chart…) have a control per prop.", color="muted")

        section("Read the numbers right", "The axis says what the data is.")
        with ui.grid(cols={"base": 1, "lg": 2}, gap="md"):
            with card("A fixed scale", "Marks out of 20 on a 0–20 axis, not "
                      "0–15 because nobody passed 14. A value past the bound "
                      "still shows.", 'ui.bar_chart(means, y_max=20)', new=True):
                with ui.grid(cols=2, gap="sm"):
                    with ui.vstack(gap="none"):
                        ui.text("Without", size="xs", color="muted")
                        ui.bar_chart(TESTS, show_values=True, size="sm")
                    with ui.vstack(gap="none"):
                        ui.text("y_max=20", size="xs", color="muted")
                        ui.bar_chart(TESTS, show_values=True, size="sm", y_max=20)
            with card("Axis titles", "Level, never turned on their side: the "
                      "vertical axis's above, the horizontal's below.",
                      'ui.bar_chart(spread, x_label="Mark", y_label="Pupils")',
                      new=True):
                ui.bar_chart(SPREAD, x_label="Mark", y_label="Pupils", size="sm",
                             show_values=True)
            with card("Counts read in whole numbers", "Pupils per mark: the "
                      "axis steps by 1 at least, and an empty bar carries no « 0 ».",
                      "automatic when every value is whole", new=True):
                ui.bar_chart(SPREAD, show_values=True, size="sm")
            with card("Formats and units", "abbreviated (12.5k), percent, "
                      "currency, or your own function; a unit after each value.",
                      'y_format="abbreviated" · y_format="percent" · y_unit="ms"'):
                with ui.grid(cols=2, gap="sm"):
                    ui.bar_chart([("Web", 12500), ("iOS", 8300), ("Android", 6100)],
                                 y_format="abbreviated", size="xs", show_values=True)
                    ui.bar_chart([("Done", 0.72), ("Late", 0.18), ("Missing", 0.10)],
                                 y_format="percent", size="xs", show_values=True)

        section("Touch it", "Every chart answers the mouse, the keyboard and "
                "the server.")
        with ui.grid(cols={"base": 1, "lg": 2}, gap="md"):
            with card("A click that runs Python", "Click a bar, a point or a "
                      "slice: the function runs on the server and writes below. "
                      "The line and the scatter learnt it today.",
                      "on_item_click=f  →  f(label, value) · f(x, y)", new=True):
                with ui.grid(cols=3, gap="sm"):
                    ui.bar_chart(SHORT, on_item_click=clicked_bar, size="xs")
                    ui.line_chart([(w, n) for w, (_d, n) in enumerate(ABSENCES, 1)],
                                  on_item_click=clicked_point, size="xs", show_dots=True)
                    ui.pie_chart(WORK, on_item_click=clicked_slice, size="xs",
                                 show_legend=False)
                click_log()
            with card("The keyboard", "Press Tab until a chart is ringed, then "
                      "the arrows walk its points (the tooltip follows), Enter "
                      "clicks, Escape leaves. One tab stop per chart.",
                      "nothing to write", new=True):
                ui.bar_chart(TESTS, on_item_click=clicked_bar, size="sm")
            with card("A legend that hides a series", "Click « 5B » in the legend. "
                      "Grouped bars, lines and scatters; a stack keeps its "
                      "legend still (a hole would make it lie).",
                      "show_legend=True (the default)", new=True):
                ui.bar_chart(TERMS, size="sm", y_max=20)
            with card("The data behind the drawing", "« Show the data » unfolds the "
                      "numbers as a table. Without it, the table is still there, "
                      "invisible, for a screen reader.",
                      "show_data=True", new=True):
                ui.bar_chart(TESTS, show_data=True, size="sm", y_max=20)

        section("Bars", "One series, several, stacked, lying down — and the "
                "histogram, which counts raw values itself.")
        with ui.grid(cols={"base": 1, "lg": 2}, gap="md"):
            with card("A histogram", "Give the raw marks: it counts them per "
                      "point (or per step, or between your bins) and marks the "
                      "mean. A click gives the tranche's bounds.",
                      "ui.histogram(marks, x_min=0, x_max=20, show_mean=True)",
                      new=True):
                ui.histogram(MARKS, x_min=0, x_max=20, show_mean=True, size="sm",
                             x_label="Mark", y_label="Pupils")
            with card("…per step, or between your own bounds", "step=5 groups "
                      "by quarter of the scale; bins= sets irregular bands.",
                      "step=5 · bins=[0, 9, 13, 15, 20]", new=True):
                with ui.grid(cols=2, gap="sm"):
                    ui.histogram(MARKS, x_min=0, x_max=20, step=5, size="xs",
                                 show_values=True)
                    ui.histogram(MARKS, bins=[0, 9, 13, 15, 20], size="xs",
                                 show_values=True, color="success")
            with card("Stacked", "The total and what makes it.",
                      'variant="stacked"'):
                ui.bar_chart(SKILLS, variant="stacked", size="sm")
            with card("Share of 100 %", "The mix of each category, whatever its size.",
                      'variant="stacked_100"'):
                ui.bar_chart(SKILLS, variant="stacked_100", size="sm")
            with card("Lying down", "Long labels read better on rows.",
                      'orientation="horizontal"'):
                ui.bar_chart([("Practise scientific methods", 72),
                              ("Design and make", 64),
                              ("Use tools and methods", 58),
                              ("Use languages", 41)],
                             orientation="horizontal", show_values=True,
                             y_unit="%", size="sm", color="info")
            with card("A target line", "A goal, a threshold, a pass mark — "
                      "behind the bars, labelled at the right.",
                      'y_reference_lines=[Reference(10, "Pass mark")]'):
                ui.bar_chart(TESTS, size="sm", y_max=20,
                             y_reference_lines=[Reference(10, "Pass mark", color="error")])

        section("Lines", "Over time: dates on the axis format themselves.")
        with ui.grid(cols={"base": 1, "lg": 2}, gap="md"):
            with card("Several series, a crosshair", "Hover anywhere: the "
                      "crosshair snaps to the nearest week and the tooltip "
                      "gives every series.", "ui.line_chart([Series(...), Series(...)])"):
                ui.line_chart(CLASSES, size="sm", y_label="Class mean")
            with card("Area, dots, straight", "area_fill, show_dots, and "
                      "smooth=False for measures that do not flow.",
                      "area_fill=True · show_dots=True · smooth=False"):
                ui.line_chart(ABSENCES, area_fill=True, show_dots=True, smooth=False,
                              size="sm", color="warning", y_label="Absences")

        section("Pies and points", "")
        with ui.grid(cols={"base": 1, "lg": 3}, gap="md"):
            with card("A donut and its total", "The middle holds the figure "
                      "read first.", 'variant="donut", center_text="24"'):
                ui.pie_chart(WORK, variant="donut", center_text="24", size="sm")
            with card("Shares on the slices", "show_labels writes each share.",
                      "show_labels=True"):
                ui.pie_chart(WORK, show_labels=True, size="sm",
                             colors=["success", "warning", "error"])
            with card("A cloud of points", "Effort against result, one point "
                      "a pupil; Tab and the arrows walk them.",
                      'ui.scatter_chart(points, x_label="Hours", y_label="Mark")'):
                ui.scatter_chart(EFFORT, size="sm", x_label="Hours of work",
                                 y_label="Mark", y_max=20)

        section("Small things", "")
        with ui.grid(cols={"base": 1, "lg": 3}, gap="md"):
            with card("A sparkline", "A trend beside its number, in a card or "
                      "a table row.", "ui.sparkline([...], area_fill=True)"):
                with ui.hstack(gap="md", align="center"):
                    ui.heading("13,8", level=2)
                    ui.sparkline([12.1, 12.4, 12.9, 13.0, 12.6, 13.3, 13.5, 13.8],
                                 area_fill=True, show_last_dot=True, color="success")
            with card("Five sizes", "xs, sm and md here, up to xl: the height, "
                      "the fonts, the bars.", 'size="xs" … size="xl"'):
                with ui.hstack(gap="sm", align="end"):
                    for size in ("xs", "sm", "md"):
                        ui.bar_chart(SHORT[:2], size=size, width=90, show_axis=False)
            with card("An empty chart", "It says why and what to do, instead "
                      "of « No data ».",
                      "empty_text= · empty_icon= · empty_description="):
                ui.bar_chart([], empty_text="No mark yet", empty_icon="clipboard-check",
                             empty_description="Marks arrive with the first copy typed.",
                             size="xs")
