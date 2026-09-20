"""features/realtime — screen 11: what another tab makes arrive here.

What this screen puts under constraint: **SSE**. A zone
``@refreshable(deps=[DealsRev, ViewerPrefs], broadcast=[DealsRev])``: two
dependencies, only one broadcast — the pipeline is global, the portfolio
being looked at is personal. When the pipeline writes in one tab,
`DealsRev` moves, and the base layer pushes a signal to the OTHER tabs,
which redo their request. No line of JavaScript here, no URL — the zone
carries its `data-bz-subscribe-url`, the runtime reads it.

**The test to do with two tabs**: open this page on the left, the
pipeline on the right, drag a card. The figures on the left move without
being touched. A single tab proves nothing — it would have re-rendered
its own zone anyway.

``LiveConnection().connected`` is the connection's state, held by the
runtime and read here: it is a ``ClientState``, so showing it does not
cost a zone — the value comes back down in a patch and the browser writes
into the node.
"""

from __future__ import annotations

from bretzel import Feature, LiveConnection, page, refreshable, ui
from examples.crm.core.domain import (
    OPEN_STAGES,
    STAGE_COLOR,
    STAGE_LABEL,
    euros,
)
from examples.crm.core.ui import kpi
from examples.crm.features.access import ViewerPrefs, visible_owner
from examples.crm.features.deals_data import (
    DealsRev,
    column_heads,
    live_board,
)
from examples.crm.features.shell import shell


@refreshable(deps=[DealsRev, ViewerPrefs], broadcast=[DealsRev])
def board_pulse() -> None:
    """The pipeline's state, all holders together — pushed to the other
    tabs.

    Two dependencies, **only one broadcast**, and that is the whole
    subject:

    - ``DealsRev`` is a property of the DATABASE. Two open tabs must see
      the same figure, and the one that did nothing must move too — so it
      is broadcast;
    - ``ViewerPrefs`` is the portfolio THIS directorate is looking at. It
      re-renders the zone here, and it has no business at the others'.

    ⚠️ This writing did not exist before 2026-08-23. ``broadcast`` was a
    boolean, so ``deps`` served two roles at once: adding ``ViewerPrefs``
    would have made the whole world refetch as soon as a single person
    changed THEIR setting. So the zone did not follow the portfolio
    change — not by oversight, for want of being able to write it.
    """
    rows = live_board(visible_owner())
    total = sum(r["total"] or 0 for r in rows.values())
    with ui.vstack(gap="md"):
        with ui.grid(cols={"base": 2, "md": 4}, gap="md"):
            for stage in OPEN_STAGES:
                row = rows.get(stage, {})
                kpi(f"{STAGE_LABEL[stage]} · {row.get('n', 0)}",
                    euros(row.get("total") or 0), "folder-open",
                    STAGE_COLOR[stage])
        with ui.hstack(justify="between", align="center"):
            ui.text("Total open", color="muted", size="sm")
            ui.heading(euros(total), level=3, size="md")


@refreshable(deps=[DealsRev, ViewerPrefs], broadcast=[DealsRev])
def recent_moves() -> None:
    """The ten deals at the head of their columns, in kanban order.

    It is the list that moves when somebody reorders: the rank is the
    only thing drag and drop writes, hence the only thing that testifies.

    The same split as ``board_pulse``: the rank is global and is
    broadcast, the portfolio being looked at is personal and stays here.
    """
    rows = column_heads(visible_owner(), limit=12)
    with ui.vstack(gap="sm"):
        ui.heading("Leading the column", level=2, size="md")
        if not rows:
            ui.text("No open deal.", color="muted", size="sm")
        for row in ui.each(rows, key="id"):
            with ui.card(padding="sm"), ui.hstack(gap="sm", align="center"):
                ui.badge(STAGE_LABEL[row["stage"]],
                         color=STAGE_COLOR[row["stage"]], variant="soft",
                         size="xs")
                with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                    ui.text(row["account_name"], size="sm",
                            weight="medium", truncate=True)
                    ui.text(f"{row['name']} · {row['owner']}",
                            color="muted", size="xs", truncate=True)
                ui.text(euros(row["amount"]), color="muted", size="xs")


def connection_badge() -> None:
    """The SSE connection's state, bound — so with no zone.

    Were it a ``@refreshable`` zone, it would add HTML to every one of the
    responses it claims to describe.
    """
    live = LiveConnection()
    with ui.hstack(gap="sm", align="center"):
        ui.icon("radio", color="success", size="sm",
                visible=live.connected)
        ui.icon("radio", color="muted", size="sm",
                visible=~live.connected)
        ui.text("Live stream", color="muted", size="sm")


@page("/realtime", layout=shell, title="Realtime")
def realtime_page() -> None:
    with ui.vstack(gap="lg"):
        with ui.hstack(justify="between", align="center", wrap=True):
            ui.heading("Realtime", level=1, size="2xl")
            connection_badge()
        ui.alert(
            "Open the Pipeline in a second tab and drag a card: the "
            "figures on this page move without being reloaded.",
            color="info", icon="info",
        )
        board_pulse()
        recent_moves()


feature = Feature(
    name="realtime",
    kind="page",
    provides=[realtime_page],
    uses=["deals_data", "access"],
)
