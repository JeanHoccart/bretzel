"""features/pipeline — screen 1: the pipeline, as a draggable kanban.

What this screen puts under constraint: ``ui.dropzone`` + ``ui.drag_each``
in columns that **scroll**, with cards of constrained width. The 17
existing apps only drag lists of three items in a container that never
overflows.

The drop is OPTIMISTIC: the browser moves the card before any request,
the handler mutates or refuses, and the morph puts back what the server
contradicts. Refusing is mutating nothing — there is no ``reject()``.
"""

from __future__ import annotations

from bretzel import Feature, page, refreshable, ui
from bretzel.components import Move
from bretzel.state import PageState, field, validator
from examples.crm.core.domain import (
    OPEN_STAGES,
    STAGE_COLOR,
    STAGE_LABEL,
    euros,
)
from examples.crm.features.access import ViewerPrefs, visible_owner
from examples.crm.features.deals_data import (
    DealsRev,
    move_deal,
    pipeline_deals,
    pipeline_totals,
)
from examples.crm.features.analyse_nav import analyse_nav

#: The horizons offered, in days. A pipeline reads over a quarter;
#: "everything" is not an option — 9 400 cards are not a view.
HORIZONS: tuple[tuple[str, str], ...] = (
    ("30", "30 days"), ("90", "90 days"), ("180", "6 months"),
)

#: The drag group. A deal card only falls into a deals column — the day
#: the screen gains another zone, the group refuses it.
DEAL_GROUP = "deal"


class PipelineUI(PageState):
    """How far we look. **No more "who"**: the portfolio is a scoping,
    not a screen filter, and it lives in the sidebar (cf.
    ``access.visible_owner``). A selector here would be a second control
    for the same thing — and, for a salesperson, a control entitled to
    only one value."""

    horizon: str = field(default='90')

    @validator("horizon")
    def _horizon(cls, value: str) -> str:
        allowed = {key for key, _label in HORIZONS}
        return value if value in allowed else "90"


def filter_changed(state: PipelineUI) -> None:
    """The changed control's value is hydrated; ``deps=`` re-renders."""


def drop_deal(m: Move) -> None:
    """What a drop applies — or refuses. The view is enough to describe
    it."""
    ui_state = PipelineUI()
    if not move_deal(m, owner=visible_owner(),
                     horizon_days=int(ui_state.horizon)):
        ui.notification(
            "Move refused — the deal no longer exists, or the column "
            "does not accept this card.",
            variant="warning", duration_ms=3000,
        )


def deal_card(deal: dict) -> None:
    with ui.card(padding="sm"):
        with ui.vstack(gap="xs"):
            ui.text(deal["account_name"], weight="medium", size="sm",
                    truncate=True)
            ui.text(deal["name"], color="muted", size="xs", truncate=True)
            with ui.hstack(justify="between", align="center"):
                ui.badge(euros(deal["amount"]), variant="soft",
                         color=STAGE_COLOR[deal["stage"]], size="xs")
                ui.text(deal["close_date"], color="muted", size="xs")


def stage_column(stage: str, deals: list[dict], total: dict | None) -> None:
    shown, overall = len(deals), (total or {}).get("n", 0)
    # The WINDOW's amount, not that of the cards shown: the cap cuts the
    # rendering, not the pipeline.
    amount = (total or {}).get("total") or 0
    with ui.vstack(gap="sm", classes="min-h-0"):
        with ui.hstack(justify="between", align="center"):
            with ui.hstack(gap="xs", align="center"):
                ui.heading(STAGE_LABEL[stage], level=3, size="sm")
                ui.badge(f"{shown} / {overall}", variant="soft",
                         color=STAGE_COLOR[stage], size="xs")
            ui.text(euros(amount), color="muted", size="xs")
        # The column scrolls: it is what the screen puts under
        # constraint. The height is bounded by the viewport, not by the
        # number of cards.
        #
        # ⚠️ **It is the ZONE that scrolls, not a container around it.**
        # The reverse — a ``dropzone`` placed INSIDE the scrolling
        # container — makes its border slide with the cards: measured,
        # after 300 px of scrolling the zone's box goes from [52, 472] to
        # [-248, 172], so its frame cuts the middle of the column instead
        # of framing it, and the "this column accepts" highlight leaves
        # the screen during the drag — at the precise moment it serves.
        # Here the zone IS the window: its box does not move by a pixel.
        with ui.dropzone(
            name=stage, accepts=[DEAL_GROUP], on_move=drop_deal,
            classes="min-h-0 max-h-[calc(100vh-19rem)] overflow-y-auto pr-1",
        ):
            with ui.vstack(gap="sm", classes="pb-2"):
                for deal in ui.drag_each(deals, group=DEAL_GROUP,
                                         key="id"):
                    deal_card(deal)


@refreshable(deps=[PipelineUI, DealsRev, ViewerPrefs])
def board() -> None:
    ui_state = PipelineUI()
    scope = visible_owner()
    deals = pipeline_deals(scope, int(ui_state.horizon))
    totals = pipeline_totals(scope, int(ui_state.horizon))
    with ui.grid(cols={"base": 1, "md": 2, "xl": 4}, gap="md"):
        for stage in OPEN_STAGES:
            stage_column(stage, deals[stage], totals.get(stage))


def filter_bar() -> None:
    # ``ui.grid``, not ``ui.hstack``: cf. the twin comment in
    # ``contacts.py`` — a ``form_field`` is ``w-full``.
    ui_state = PipelineUI()
    with ui.grid(cols={"base": 1, "md": 4}, gap="md"):
        with ui.form_field(label="Closing within"):
            ui.select(value=ui_state.horizon, options=list(HORIZONS),
                      on_change=filter_changed)


@page("/", layout=analyse_nav, title="Pipeline")
def pipeline_page() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("Pipeline", level=1, size="2xl")
        filter_bar()
        board()


feature = Feature(
    name="pipeline",
    kind="page",
    provides=[pipeline_page, PipelineUI],
    uses=["deals_data", "access"],
)
