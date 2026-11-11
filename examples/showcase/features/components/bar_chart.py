"""``/bar-chart`` — categories side by side, the chart every dashboard opens with."""

from bretzel import refreshable, ui
from bretzel.components import Reference, Series
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Compare categories at a glance: grouped, stacked or sideways, "
           "with targets drawn in and a click that runs Python.")


def dollars(value: float) -> str:
    return f"${value / 1000:.0f}k"


def monthly_revenue() -> list[tuple[str, float]]:
    return [("Jan", 38200), ("Feb", 41900), ("Mar", 47300), ("Apr", 44100),
            ("May", 52800), ("Jun", 58400), ("Jul", 55900), ("Aug", 61200)]


def revenue_card() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        with ui.hstack(justify="between", align="start", wrap=True):
            with ui.vstack(gap="none"):
                ui.text("Revenue", size="sm", color="muted")
                ui.heading("$399.8k", level=3, size="2xl")
            ui.badge("+18.2% vs last year", color="success", variant="soft",
                     size="sm", icon_left="trending-up")
        ui.bar_chart(data=monthly_revenue(), y_format=dollars, size="sm")


def plan_mix() -> list[Series]:
    quarters = ["Q1", "Q2", "Q3", "Q4"]
    return [
        Series("Starter", list(zip(quarters, [410, 468, 502, 547], strict=True))),
        Series("Pro", list(zip(quarters, [236, 281, 334, 390], strict=True))),
        Series("Enterprise", list(zip(quarters, [42, 51, 63, 71], strict=True))),
    ]


def stacked() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        with ui.vstack(gap="none"):
            ui.text("Paying workspaces by plan", size="sm", color="muted")
            ui.heading("1,008", level=3, size="2xl")
        ui.bar_chart(data=plan_mix(), variant="stacked", size="sm")


def orders_vs_last_year() -> list[Series]:
    weeks = ["W27", "W28", "W29", "W30", "W31", "W32"]
    return [
        Series("2026", list(zip(weeks, [1240, 1385, 1310, 1502, 1620, 1330], strict=True))),
        Series("2025", list(zip(weeks, [1080, 1150, 1210, 1190, 1305, 1290], strict=True)),
               color="muted"),
    ]


def grouped() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        with ui.hstack(justify="between", align="start", wrap=True):
            with ui.vstack(gap="none"):
                ui.text("Weekly orders", size="sm", color="muted")
                ui.heading("8,387", level=3, size="2xl")
            ui.badge("Target met 2 weeks of 6", color="info", variant="soft",
                     size="sm")
        ui.bar_chart(data=orders_vs_last_year(), color="secondary",
                     y_reference_lines=[Reference(1400, "Weekly target")])


def top_pages() -> list[tuple[str, float]]:
    return [("/pricing", 18420), ("/docs/quickstart", 14210),
            ("/blog/launch-week", 9870), ("/changelog", 6130),
            ("/integrations", 4580), ("/careers", 2240)]


def horizontal() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        ui.text("Top pages · last 30 days", size="sm", color="muted")
        ui.bar_chart(data=top_pages(), orientation="horizontal",
                     show_values=True, show_gridlines=False,
                     y_format="abbreviated", color="info")


def ticket_sentiment() -> list[Series]:
    channels = ["Email", "Live chat", "Phone", "Community"]
    return [
        Series("Positive", list(zip(channels, [412, 688, 205, 131], strict=True)),
               color="success"),
        Series("Neutral", list(zip(channels, [230, 190, 96, 164], strict=True)),
               color="muted"),
        Series("Negative", list(zip(channels, [98, 61, 58, 27], strict=True)),
               color="error"),
    ]


def composition() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        ui.text("Ticket sentiment by channel", size="sm", color="muted")
        ui.bar_chart(data=ticket_sentiment(), variant="stacked_100", size="sm")


def team_scores() -> list[tuple[str, float]]:
    return [("Support", 8.6), ("Sales", 7.9), ("Product", 7.1),
            ("Finance", 6.4), ("Operations", 5.8)]


def fixed_scale() -> None:
    with ui.card(padding="md"), ui.vstack(gap="sm"):
        ui.text("Team satisfaction survey", size="sm", color="muted")
        ui.bar_chart(data=team_scores(), y_max=10, x_label="Team",
                     y_label="Score out of 10", show_data=True, size="sm")


def region_facts(region: str) -> tuple[str, str, str]:
    return {
        "North America": ("$182.4k", "2,140 accounts",
                          "Strongest quarter since launch."),
        "Europe": ("$121.9k", "1,688 accounts", "Germany alone grew 31%."),
        "Asia-Pacific": ("$64.7k", "902 accounts",
                         "Singapore office opens in May."),
        "Latin America": ("$30.8k", "511 accounts", "Churn down to 1.9%."),
    }[region]


class Drilldown(PageState):
    region: str = field(default="North America")


def pick_region(label: str, value: float) -> None:
    Drilldown().region = label


@refreshable
def region_detail() -> None:
    region = Drilldown().region
    revenue, accounts, remark = region_facts(region)
    with ui.card(padding="md"), ui.vstack(gap="xs"):
        ui.text(region, size="sm", color="muted")
        ui.heading(revenue, level=3, size="2xl")
        ui.badge(accounts, color="primary", variant="soft", size="sm")
        ui.text(remark, size="sm")


def drilldown() -> None:
    with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
        with ui.card(padding="md", classes="md:col-span-2"), ui.vstack(gap="sm"):
            ui.text("Revenue by region · click a bar", size="sm", color="muted")
            ui.bar_chart(data=[("North America", 182400), ("Europe", 121900),
                               ("Asia-Pacific", 64700), ("Latin America", 30800)],
                         y_format=dollars, size="sm", on_item_click=pick_region)
        region_detail()


def page() -> None:
    page_header("bar_chart", "Bar chart", SUMMARY)
    example("A revenue card", revenue_card, uses=[dollars, monthly_revenue],
            full=True,
            note="Pairs of (label, value) are enough. y_format takes a "
                 "function when the shorthands (abbreviated, percent, "
                 "currency) do not fit.")
    example("Grouped, against a target", grouped, uses=[orders_vs_last_year],
            full=True,
            note="One Series per group. Pin a colour on the baseline so the "
                 "current period stands out, and draw the goal as a "
                 "reference line. A click on the legend hides a series.")
    example("On its own scale", fixed_scale, uses=[team_scores], full=True,
            note="y_max keeps a score out of 10 on a 0–10 axis, x_label and "
                 "y_label name the axes, and show_data folds the numbers "
                 "under the chart.")
    example("Stacked", stacked, uses=[plan_mix], full=True,
            note="Stacking shows the total and what it is made of.")
    example("Share of 100%", composition, uses=[ticket_sentiment], full=True,
            note="stacked_100 compares the mix of each category, whatever "
                 "its size.")
    example("A horizontal ranking", horizontal, uses=[top_pages], full=True,
            note="Long labels read better on rows than on a slanted axis.")
    example("A click that runs Python", drilldown,
            uses=[dollars, region_facts, Drilldown, pick_region, region_detail], full=True,
            note="on_item_click receives the bar's label and value. The "
                 "state changes on the server and the detail card follows. "
                 "From the keyboard: Tab to the chart, the arrows, Enter.")
