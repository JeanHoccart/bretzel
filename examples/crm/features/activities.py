"""features/activities — screen 6: the log, and the pickers AS FILTERS.

What this screen puts under constraint: ``ui.date_range_picker``,
``ui.calendar`` and ``ui.date_picker`` **in a real filter bar and in a
real form**, not mounted alone on a bench. The playground renders all
three — but none is bound there to a server state, so the path "I choose
a period, the server re-reads the database" had never been walked.

Three distinct uses, taken at their word:

- the **period** is a ``date_range_picker``: two bounds, one gesture;
- the **day** is a ``ui.calendar``: you scan it with your eyes before
  clicking, which a field does not allow;
- the **date of an activity being logged** is a ``date_picker``: a field
  in a form, between two other fields.
"""

from __future__ import annotations

from datetime import timedelta

from bretzel import Feature, page, refreshable, ui
from bretzel.state import PageState, field, validator
from examples.crm.core.domain import (
    ACTIVITY_KEYS,
    ACTIVITY_KINDS,
    OWNERS,
    TODAY,
    activity_badge,
)
from examples.crm.core.ui import kpi
from examples.crm.features.access import ViewerPrefs, visible_owner
from examples.crm.features.activities_data import (
    ActivitiesRev,
    activities_between,
    activity_counts,
    add_activity,
    busiest_days,
)
from examples.crm.features.shell import shell

#: The default window: the past month. Computed from ``TODAY``, the data
#: set's frozen date — not from the clock, otherwise the page would be
#: empty the day this repository is re-read.
DEFAULT_END = TODAY
DEFAULT_START = TODAY - timedelta(days=30)


def parse_range(raw) -> tuple[str, str]:
    """The period's two bounds, put back in order.

    The JSON decoding is no longer here: the base layer does it at the
    field's edge. What is left is domain — a period whose end precedes
    its start is an entry, not an error, and we swap it rather than
    refuse it.
    """
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return DEFAULT_START.isoformat(), DEFAULT_END.isoformat()
    start, end = raw
    if not start or not end:
        return DEFAULT_START.isoformat(), DEFAULT_END.isoformat()
    return (start, end) if start <= end else (end, start)


class ActivitiesUI(PageState):
    """The window being looked at: period, chosen day, type.

    **No more owner**: the portfolio is a scoping, not a screen filter —
    cf. ``access.visible_owner``.
    """

    #: A LIST, and its default is written out in the open. The component
    #: serialises its two bounds as JSON in a hidden field, and the base
    #: layer decodes it on arrival (``_coerce_composite``) — it was the
    #: work's finding 10, lifted by the fix of the 19th: both were the
    #: same hole, seen from two components.
    period: list = field(
        default_factory=lambda: [DEFAULT_START.isoformat(),
                                 DEFAULT_END.isoformat()]
    )
    day: str = field(default='')
    kind: str = field(default='all')
    #: The month the calendar SHOWS.
    #:
    #: A real field, and **not** `day or period_end` at the call
    #: site. `a or b` returns the operand AS IT IS: the provenance stamp
    #: therefore survived when `day` was filled and disappeared when it
    #: was empty, and the calendar resynchronised one time in two
    #: depending on the data. Visible consequence: with no day chosen,
    #: changing the period did not move the calendar.
    #:
    #: It is the same trap as the one already written in `save_activity`,
    #: where an `or` undid the portfolio lock. Guarded by the
    #: `state-lost-by-a-cast` rule, widened to `BoolOp` on 2026-08-30.
    month: str = field(default=DEFAULT_END.isoformat())

    @validator("kind")
    def _kind(cls, value: str) -> str:
        return value if value in ACTIVITY_KEYS else "all"


class ActivityDraft(PageState):
    """Le formulaire de journalisation."""

    contact_id: int = field(default=0)
    kind: str = field(default='call')
    subject: str = field(default='')
    at: str = field(default=TODAY.isoformat())
    owner: str = field(default=OWNERS[0])

    @validator("kind")
    def _kind(cls, value: str) -> str:
        return value if value in ACTIVITY_KEYS else "call"


def filter_changed(state: ActivitiesUI) -> None:
    """The period or the type has moved; ``deps=`` re-renders the zone.

    The month shown FOLLOWS the period: without that, you move the window
    and the calendar stays on the old month.
    """
    state.month = parse_range(list(state.period))[1]


def pick_day(state: ActivitiesUI) -> None:
    """A click in the calendar: the chosen day becomes the window."""
    if state.day:
        state.month = str(state.day)


def clear_day() -> None:
    """Back to the whole period — the month starts from its end again."""
    state = ActivitiesUI()
    state.day = ""
    state.month = parse_range(list(state.period))[1]


def save_activity(form: ActivityDraft) -> None:
    subject = str(form.subject).strip()[:120]
    if not subject or not form.contact_id:
        ui.notification("A subject and a contact identifier are required.",
                        variant="warning", duration_ms=2500)
        return
    # The scoping OVERWRITES the field: it arrives from the browser, so
    # a salesperson could forge it to log in a colleague's name. The
    # field is only read where there is no scoping — the directorate.
    #
    # ⚠️ The test is `is None`, not an `or`. A first writing said
    # `effective_owner(...) or str(form.owner)`: for an anonymous visitor
    # the scoping is `NOBODY` (`""`), which is FALSE, so the `or`
    # returned the browser's value — the lock undone by its own writing.
    scope = visible_owner()
    stamped = str(form.owner) if scope is None else scope
    if stamped not in OWNERS:
        ui.notification("Unknown owner.", variant="error",
                        duration_ms=3000)
        return
    created = add_activity(int(form.contact_id), str(form.kind), subject,
                           str(form.at), stamped, scope)
    if not created:
        ui.notification(f"Aucun contact n'a l'identifiant {form.contact_id}.",
                        variant="error", duration_ms=3000)
        return
    form.subject = ""
    ui.notification("Activity logged", variant="success",
                    duration_ms=2000)


def window_of(state: ActivitiesUI) -> tuple[str, str]:
    """The effective window: the chosen day wins over the period."""
    if state.day:
        return str(state.day), str(state.day)
    return parse_range(list(state.period))


# ``ViewerPrefs`` in the ``deps``: without it, changing portfolio in the
# sidebar would leave the zone on the previous one's data.
@refreshable(deps=[ActivitiesUI, ActivitiesRev, ViewerPrefs])
def counters() -> None:
    state = ActivitiesUI()
    start, end = window_of(state)
    counts = activity_counts(start, end, str(state.kind), visible_owner())
    with ui.grid(cols={"base": 2, "md": 5}, gap="md"):
        for key, (label, icon, color) in ACTIVITY_KINDS.items():
            kpi(label, str(counts.get(key, 0)), icon, color)


@refreshable(deps=[ActivitiesUI, ActivitiesRev, ViewerPrefs])
def agenda() -> None:
    """The calendar + the ranking of busy days.

    ⚠️ The two go together by default of the component: ``ui.calendar``
    cannot MARK a day (no events prop, no cell slot), so it cannot show
    where something is happening. The table beside it says what the
    calendar should carry.
    """
    state = ActivitiesUI()
    start, end = window_of(state)
    with ui.vstack(gap="md"):
        with ui.hstack(justify="between", align="center"):
            ui.heading("Calendar", level=2, size="md")
            if state.day:
                ui.button("The whole range", size="xs", variant="ghost",
                          icon_left="x", on_click=clear_day)
        ui.calendar(value=state.day, month=state.month,
                    weekstart=1, size="sm", on_change=pick_day)
        ui.divider(label="Busiest days")
        days = busiest_days(start, end, str(state.kind), visible_owner())
        if not days:
            ui.text("Nothing in this window.", color="muted", size="sm")
        for day in ui.each(days, key="day"):
            with ui.hstack(justify="between", align="center"):
                ui.text(day["day"], size="sm")
                ui.badge(str(day["n"]), variant="soft", color="muted",
                         size="xs")


@refreshable(deps=[ActivitiesUI, ActivitiesRev, ViewerPrefs])
def journal() -> None:
    state = ActivitiesUI()
    start, end = window_of(state)
    rows = activities_between(start, end, str(state.kind),
                              visible_owner())
    with ui.vstack(gap="sm"):
        with ui.hstack(justify="between", align="center"):
            ui.heading("Log", level=2, size="md")
            ui.text(f"{start} → {end}", color="muted", size="xs")
        if not rows:
            ui.empty_state("No activity", icon="calendar-x",
                           description="Widen the range or change the type.")
        for row in ui.each(rows, key="id"):
            _label, icon, color = activity_badge(row["kind"])
            with ui.card(padding="sm"):
                with ui.hstack(gap="sm", align="center"):
                    ui.icon(icon, color=color, size="sm")
                    with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                        ui.text(row["subject"], size="sm", weight="medium",
                                truncate=True)
                        ui.link(
                            f"{row['first_name']} {row['last_name']} · "
                            f"{row['account_name']}",
                            href=f"/contacts/{row['contact_id']}",
                            variant="hover", color="muted",
                        )
                    with ui.vstack(gap="none", align="end"):
                        ui.text(row["at"], color="muted", size="xs")
                        ui.text(row["owner"], color="muted", size="xs")


def filter_bar() -> None:
    state = ActivitiesUI()
    start, end = parse_range(list(state.period))
    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
        with ui.form_field(label="Range",
                           hint="The day picked in the calendar wins "
                                "over this bound."):
            ui.date_range_picker(value=state.period,
                                 placeholder_start=start, placeholder_end=end,
                                 on_change=filter_changed)
        with ui.form_field(label="Type"):
            ui.select(
                value=state.kind,
                options=[("all", "Every type"),
                         *[(k, lbl) for k, (lbl, _i, _c)
                           in ACTIVITY_KINDS.items()]],
                on_change=filter_changed,
            )



@refreshable(deps=[ActivityDraft, ViewerPrefs])
def log_form() -> None:
    draft = ActivityDraft()
    with ui.form(on_submit=save_activity):
        with ui.vstack(gap="md"):
            ui.heading("Log an activity", level=2, size="md")
            with ui.grid(cols={"base": 1, "md": 5}, gap="md"):
                with ui.form_field(label="Contact (id)", required=True):
                    ui.number_input(value=draft.contact_id, min=1,
                                    max=120_000)
                with ui.form_field(label="Type"):
                    ui.select(value=draft.kind,
                              options=[(k, lbl) for k, (lbl, _i, _c)
                                       in ACTIVITY_KINDS.items()])
                with ui.form_field(label="Subject", required=True):
                    ui.input(value=draft.subject, maxlength=120,
                             placeholder="Progress check")
                with ui.form_field(label="Date"):
                    ui.date_picker(value=draft.at, clearable=False)
                if visible_owner() is None:
                    # The directorate MUST say who it is logging for; a
                    # salesperson has no such choice to make.
                    with ui.form_field(label="Owner"):
                        ui.select(value=draft.owner,
                                  options=[(o, o) for o in OWNERS])
            with ui.hstack(justify="end"):
                ui.button("Log it", type="submit", color="primary",
                          icon_left="plus")


@page("/activities", layout=shell, title="Activities")
def activities_page() -> None:
    with ui.vstack(gap="lg"):
        ui.heading("Activities", level=1, size="2xl")
        filter_bar()
        counters()
        with ui.card(padding="md"):
            log_form()
        # Two EQUAL columns, not a third / two thirds: ``ui.grid``
        # exposes only ``cols`` and ``gap``, so none of its children can
        # take two columns. The only way to get "a third / two thirds"
        # would be a ``classes="lg:col-span-2"``, which this work forbids
        # placing.
        with ui.grid(cols={"base": 1, "lg": 2}, gap="lg"):
            with ui.card(padding="md"):
                agenda()
            journal()


feature = Feature(
    name="activities",
    kind="page",
    provides=[activities_page, ActivitiesUI, ActivityDraft],
    uses=["activities_data", "access"],
)
