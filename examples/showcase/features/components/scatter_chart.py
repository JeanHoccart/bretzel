"""``/scatter-chart`` — two measures per point, to see how they relate."""

from bretzel import refreshable, ui
from bretzel.components import Reference, Series
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Two measures per point to show how they relate: clusters, "
           "outliers, a goal line, one colour per segment.")


def dollars(value: float) -> str:
    return f"${value / 1000:.0f}k"


def deals() -> list[Series]:
    return [
        Series("SMB", [(9, 4200), (14, 6100), (12, 3800), (21, 7900),
                       (7, 2900), (18, 5400), (25, 8800), (11, 4700)]),
        Series("Mid-market", [(34, 18500), (41, 24800), (29, 15200),
                              (52, 31000), (38, 21400), (46, 19900)]),
        Series("Enterprise", [(74, 62000), (96, 88500), (63, 54000),
                              (118, 112000), (85, 71500)]),
    ]


def segments() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        with ui.hstack(justify="between", align="start", wrap=True):
            with ui.vstack(gap="none"):
                ui.text("Deal size against sales cycle", size="sm",
                        color="muted")
                ui.heading("19 deals closed in Q3", level=3, size="xl")
            ui.badge("Median cycle 34 days", color="info", variant="soft",
                     size="sm")
        ui.scatter_chart(data=deals(), x_unit="days", y_format=dollars)


def campaigns() -> list[tuple[float, float]]:
    return [(1200, 38), (2400, 71), (3100, 84), (1800, 22), (4200, 131),
            (5600, 149), (2900, 44), (6400, 201), (3700, 96), (7800, 188),
            (4900, 73), (8600, 262)]


def goal_line() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        with ui.vstack(gap="none"):
            ui.text("Ad spend against conversions, per campaign", size="sm",
                    color="muted")
            ui.heading("12 campaigns · $52.6k spent", level=3, size="xl")
        ui.scatter_chart(data=campaigns(), color="secondary", size="sm",
                         x_format=dollars, y_unit="conv.",
                         y_reference_lines=[Reference(100, "Monthly goal",
                                                    "success")])


def requests() -> list[tuple[float, float]]:
    return [(12, 84), (48, 102), (96, 131), (140, 158), (220, 203),
            (310, 246), (35, 91), (180, 179), (260, 412), (400, 311),
            (75, 118), (500, 364), (22, 88), (350, 290)]


def outliers() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        with ui.hstack(justify="between", align="start", wrap=True):
            with ui.vstack(gap="none"):
                ui.text("Response time against payload size", size="sm",
                        color="muted")
                ui.heading("1 outlier above 400 ms", level=3, size="xl")
            ui.badge("POST /v2/reports", color="warning", variant="soft",
                     size="sm")
        ui.scatter_chart(data=requests(), color="warning", size="sm",
                         x_unit="KB", y_unit="ms", show_gridlines=False)


class Cohort(PageState):
    plan: str = field(default="all")


def change_plan(state: Cohort) -> None:
    """The typed parameter receives the toggle's value; nothing else to do."""


def usage(plan: str) -> list[Series]:
    teams = {
        "starter": Series("Starter", [(3, 4), (5, 9), (4, 6), (8, 14),
                                      (6, 11), (2, 3)]),
        "pro": Series("Pro", [(12, 26), (18, 41), (15, 30), (24, 52),
                              (20, 38)]),
        "business": Series("Business", [(40, 88), (55, 131), (48, 97),
                                        (70, 160)]),
    }
    return list(teams.values()) if plan == "all" else [teams[plan]]


@refreshable
def usage_chart() -> None:
    ui.scatter_chart(data=usage(Cohort().plan), x_unit="seats", size="sm")


def live_filter() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        with ui.hstack(justify="between", align="center", wrap=True):
            ui.text("Active projects against seats, per workspace",
                    size="sm", color="muted")
            ui.toggle_group(value=Cohort().plan, on_change=change_plan,
                            size="sm",
                            options=[("all", "All"), ("starter", "Starter"),
                                     ("pro", "Pro"), ("business", "Business")])
        usage_chart()


def page() -> None:
    page_header("scatter_chart", "Scatter chart", SUMMARY)
    example("One colour per segment", segments, uses=[dollars, deals],
            full=True,
            note="Each Series is its own cloud, with its own colour and its "
                 "entry in the legend.")
    example("Against a goal", goal_line, uses=[dollars, campaigns], full=True,
            note="Pairs of (x, y) for a single series; x_format and y_unit "
                 "label both axes.")
    example("Spot the outlier", outliers, uses=[requests], full=True,
            note="Hover a point to read its exact values — or Tab to the "
                 "chart and walk its points with the arrows.")
    example("A filter that reloads the chart", live_filter,
            uses=[Cohort, change_plan, usage, usage_chart], full=True,
            note="The toggle writes the plan to a server state; only the "
                 "chart that reads it is rendered again.")
