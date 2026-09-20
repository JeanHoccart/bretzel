"""features/reports — screen 7: the five chart families, on SQL.

What this screen puts under constraint: ``bar_chart``, ``line_chart``,
``pie_chart``, ``scatter_chart`` and ``sparkline`` fed by ``GROUP BY``,
not by hand-written lists. Real data brings what a demo list never
brings — orders of magnitude that do not line up, gaps, long labels, and
nine-digit values on a 400 px axis.

``Series`` is imported from ``bretzel.components`` — the public door
exists for it as for ``Move``. It is the contrast with ``Query``, which
has none (finding 2 of the work): three value objects of the same funnel,
two exported, one not.
"""

from __future__ import annotations

from datetime import date

from bretzel import Feature, page, ui
from bretzel.components import Series
from examples.crm.core.domain import (
    MONTHS_SHORT,
    OPEN_STAGES,
    STAGE_LABEL,
    euros,
)
from examples.crm.features.access import visible_owner
from examples.crm.features.reports_data import (
    accounts_by_industry,
    activities_by_month,
    arr_versus_contacts,
    pipeline_by_stage_and_owner,
    weekly_activity,
)
from examples.crm.features.analyse_nav import analyse_nav


def pipeline_series() -> list[Series]:
    """The (stage, owner) matrix folded into aligned series.

    Every series must carry ALL the stages, in the same order: a grouped
    bar aligns its series by position, so an owner with nothing in
    negotiation must be zero there, not skip the category.
    """
    rows = pipeline_by_stage_and_owner(visible_owner())
    owners: list[str] = []
    for row in rows:
        if row["owner"] not in owners:
            owners.append(row["owner"])
    totals = {(r["stage"], r["owner"]): r["total"] for r in rows}
    return [
        Series(
            name=owner,
            data=[
                (STAGE_LABEL[stage], totals.get((stage, owner), 0) or 0)
                for stage in OPEN_STAGES
            ],
        )
        for owner in owners
    ]


def chart_card(title: str, subtitle: str, render, *args) -> None:
    with ui.card(padding="md"):
        with ui.vstack(gap="sm"):
            ui.heading(title, level=2, size="md")
            ui.text(subtitle, color="muted", size="xs")
            render(*args)


def pipeline_chart(series: list[Series]) -> None:
    ui.bar_chart(
        data=series,
        variant="grouped",
        orientation="horizontal",
        y_format="abbreviated",
        y_unit="€",
        size="md",
        empty_text="No open deal.",
    )


def month_axis(moment) -> str:
    """The time axis in French.

    Always necessary, and for a reason that will not move: a chart's axis
    is baked into the SVG **server side**, hence out of reach of the
    browser's ``Intl`` the date components live on. Python cannot name a
    month without a dependency — its ``locale`` module is process-global
    state. ``x_format=`` is therefore the handle, and rightly so.

    What changed on 2026-08-24: the parameter arrives as a ``datetime``,
    no longer as a POSIX timestamp. This function used to start by
    converting it back by hand, which the component — which KNOWS it is a
    date — now does.
    """
    return f"{MONTHS_SHORT[moment.month - 1]} {moment.year}"


def activity_chart() -> None:
    rows = activities_by_month(visible_owner())
    ui.line_chart(
        data=[(date.fromisoformat(r["day"]), r["n"]) for r in rows],
        area_fill=True,
        show_dots=True,
        x_format=month_axis,
        size="md",
        empty_text="No activity over the range.",
    )


def industry_chart() -> None:
    rows = accounts_by_industry(visible_owner())
    ui.pie_chart(
        data=[(r["industry"], r["n"]) for r in rows],
        variant="donut",
        center_text=f"{sum(r['n'] for r in rows)} accounts",
        size="md",
        empty_text="No account.",
    )


def correlation_chart() -> None:
    rows = arr_versus_contacts(visible_owner())
    ui.scatter_chart(
        data=[(r["contacts"], r["arr"]) for r in rows],
        x_unit=" contacts",
        y_format="abbreviated",
        y_unit="€",
        size="md",
        empty_text="No account in the sample.",
    )


def trend_card() -> None:
    weeks = weekly_activity(visible_owner())
    with ui.card(padding="md"):
        with ui.hstack(gap="md", align="center", justify="between"):
            with ui.vstack(gap="none"):
                ui.text("Activity, last 12 weeks", color="muted",
                        size="xs")
                ui.heading(str(sum(weeks)), level=3, size="lg")
            ui.sparkline(data=weeks, area_fill=True, show_last_dot=True,
                         size="md", color="primary")


def pipeline_total_card(series: list[Series]) -> None:
    total = sum(value for s in series for _label, value in s.data)
    with ui.card(padding="md"):
        with ui.hstack(gap="md", align="center"):
            with ui.flex(align="center", justify="center",
                         classes="w-10 h-10 rounded-lg bg-text/5 shrink-0"):
                ui.icon("trending-up", color="success")
            with ui.vstack(gap="none"):
                # ⚠️ The label follows the SCOPING. Scoped, there is
                # only one holder — announcing "top 3" would be a false
                # figure on screen, the form of lie one never re-reads.
                ui.text("Open pipeline, my portfolio"
                        if visible_owner() is not None
                        else "Pipeline ouvert, 3 premiers porteurs",
                        color="muted", size="xs")
                ui.heading(euros(total), level=3, size="lg")


@page("/reports", layout=analyse_nav, title="Reports")
def reports_page() -> None:
    # ONCE only: the header card and the chart each read the same
    # aggregate on their own side, that is two ``GROUP BY`` too many on
    # the page whose subject IS holding up on real aggregates.
    series = pipeline_series()
    with ui.vstack(gap="lg"):
        ui.heading("Reports", level=1, size="2xl")
        with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
            trend_card()
            pipeline_total_card(series)
        with ui.grid(cols={"base": 1, "xl": 2}, gap="lg"):
            chart_card(
                "Pipeline by stage",
                ("Montant ouvert — SUM(amount) GROUP BY stage"
                 if visible_owner() is not None else
                 "Open amount, grouped by owner — SUM(amount) "
                 "GROUP BY stage, owner"),
                pipeline_chart, series,
            )
            chart_card(
                "Activity by month",
                "Twelve rolling months — COUNT(*) GROUP BY substr(at, 1, 7)",
                activity_chart,
            )
            chart_card(
                "Accounts by industry",
                "The first eight — COUNT(*) GROUP BY industry",
                industry_chart,
            )
            chart_card(
                "ARR contre nombre de contacts",
                "A sample of 250 accounts — LEFT JOIN + GROUP BY a.id",
                correlation_chart,
            )


feature = Feature(
    name="reports",
    kind="page",
    provides=[reports_page],
    uses=["reports_data", "access"],
)
